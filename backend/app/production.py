"""
Safety rules for the LIVE server (ENVIRONMENT=production).

startup_problems()  things that make starting dangerous, so the server REFUSES
                    to start until they're fixed (better a clear error in the
                    logs than a live site with the demo password):
                      - SECRET_KEY still the demo value (or short)
                      - PUBLIC_API_URL not https
                      - demo accounts (…@demo.in) in the database
startup_warnings()  everything else from the go-live checklist, written to the logs
SecurityHeaders     extra instructions to browsers on every reply (see below)
"""

import logging

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services import launch_check

logger = logging.getLogger("production")


def startup_problems(db) -> list[str]:
    from app.models import User
    problems = []
    if settings.secret_key == launch_check.DEFAULTS["secret_key"] or len(settings.secret_key) < 32:
        problems.append('SECRET_KEY is the demo value or too short. Make one: '
                        'python -c "import secrets; print(secrets.token_urlsafe(48))"')
    if not settings.public_api_url.startswith("https://"):
        problems.append("PUBLIC_API_URL must be the server's https address")
    if db.scalar(select(User.id).where(User.email.like("%@demo.in")).limit(1)):
        problems.append("Demo accounts (…@demo.in) are in the database. The live site must start from an empty "
                        "database: never run seed_data on it. Create your admin with seed.create_admin.")
    return problems


def startup_warnings() -> list[str]:
    return [f"{c['item']}: not done yet ({c['how']})" for c in launch_check.checks() if not c["ok"]]


def bootstrap_admin(db) -> str:
    """Create the platform admin from BOOTSTRAP_ADMIN_EMAIL / _PASSWORD, once. Returns what happened."""
    from app.models import User
    from app.services.auth_service import create_user
    email = settings.bootstrap_admin_email.strip().lower()
    if not email:
        return ""
    if len(settings.bootstrap_admin_password) < 12:
        return "BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters: admin NOT created"
    if db.scalar(select(User.id).where(User.email == email)):
        return f"Admin {email} already exists: delete the BOOTSTRAP_ADMIN_* variables now"
    create_user(db, email, "Platform admin", settings.bootstrap_admin_password, role="admin")
    return f"Admin {email} created. Delete the BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD variables now."


class SecurityHeaders(BaseHTTPMiddleware):
    """Extra safety instructions sent with every reply:
       nosniff        browsers must not guess file types (stops disguised scripts)
       frame DENY     nobody can show our pages inside their site (stops click-jacking)
       referrer       links to other sites don't leak our page addresses
       HSTS           (live server) browsers always use https for us, never plain http"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.is_production:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
