"""
The starting point of the backend.

Running `uvicorn app.main:app` loads this file, creates the `app` object,
plugs in every router (the "counters"), starts the scheduler's alarm clock,
and starts listening for requests.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.auth.access import get_current_user
from app.auth.paywall import require_active_plan
from app.config import settings
from app.database import SessionLocal, init_db
from app.production import SecurityHeaders, bootstrap_admin, startup_problems, startup_warnings
from app.routers import (account, agent_runs, ai, alerts, analytics, auth, auto_reply, billing, businesses, connections,
                         content, dues, email_leads, emails, followups, growth, imports, leads, live, media, platforms,
                         renewals, reviews, roi, scheduler, social, webhooks)
from app.site import routes as site
from app.services import scheduler_service
from app.services.event_bus import bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

if settings.sentry_dsn:                      # optional error alerts by email (sentry.io)
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.0,
                        send_default_pii=False)
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk isn't installed (pip install sentry-sdk)")


async def scheduler_loop():
    """The alarm clock: every minute, publish due posts and refresh post numbers.
    asyncio.to_thread runs the database work on a helper thread, so the
    server keeps answering requests while it works."""
    while True:
        await asyncio.sleep(settings.scheduler_interval_seconds)
        try:
            await asyncio.to_thread(scheduler_service.run_cycle_in_background)
        except Exception:  # noqa: BLE001 - never let one bad cycle stop the clock
            logger.exception("Scheduler cycle failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Code before `yield` runs once when the server starts;
    code after it runs when the server shuts down."""
    init_db()  # create / update the tables (migrations), never deletes data
    with SessionLocal() as db:
        note = bootstrap_admin(db)
    if note:
        logger.warning(note)
    if settings.is_production:
        with SessionLocal() as db:
            problems = startup_problems(db)
        if problems:
            for problem in problems:
                logger.error("NOT STARTING: %s", problem)
            raise RuntimeError("Unsafe production settings: " + " | ".join(problems))
        for warning in startup_warnings():
            logger.warning(warning)
    bus.loop = asyncio.get_running_loop()   # lets background threads hand live events to the server
    clock = asyncio.create_task(scheduler_loop()) if settings.scheduler_enabled else None
    yield
    if clock:
        clock.cancel()


DOCS = not settings.is_production or settings.show_docs     # /docs is for building, hidden on the live site
app = FastAPI(
    docs_url="/docs" if DOCS else None,
    redoc_url="/redoc" if DOCS else None,
    openapi_url="/openapi.json" if DOCS else None,
    title=settings.app_name,
    description=(
        "AI growth partner for local businesses.\n\n"
        "**To try the locked endpoints:** `POST /auth/login` with `gym@demo.in` / `demo1234`, copy the "
        "`token`, click **Authorize** (top right) and paste it."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeaders)

# CORS: browsers block a web page from calling a different address unless
# the server allows it. This lets the React dashboard call our API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Plug in the "counters". Each router file brings its own set of addresses.
#
# OPEN (no login): /health, /auth/signup + /auth/login, /platforms and
# /billing/plans (for the public pricing page), and /webhooks: WhatsApp,
# Instagram, websites and Razorpay ring these doorbells themselves.
app.include_router(site.router)               # the public website: /, /pricing, /terms, /privacy...
app.mount("/static", StaticFiles(directory=site.STATIC_DIR), name="static")
app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(platforms.router)
app.include_router(billing.public)
app.include_router(connections.public)        # Meta/Google send the owner back here after "Connect"
app.include_router(media.public)              # /files/...: photos/videos the platforms fetch when we publish

# LOGIN, NO PAYWALL: the billing pages (so an owner whose plan ended can pay again).
app.include_router(billing.router, dependencies=[Depends(get_current_user)])
app.include_router(emails.router, dependencies=[Depends(get_current_user)])   # admin: the email log
app.include_router(account.router, dependencies=[Depends(get_current_user)])  # export / delete my data

# LOCKED: everything else needs "Authorization: Bearer <token>" (or ?token= for the live feed)
# AND a running plan or free trial (else 402 "choose a plan").
# Inside, each ..._or_404 helper makes sure the data belongs to YOUR business.
login_and_plan = [Depends(get_current_user), Depends(require_active_plan)]
for locked in (businesses, imports, leads, ai, agent_runs, analytics, social, content, scheduler, growth, reviews,
               live, connections, media, email_leads, roi, alerts, auto_reply, followups, dues, renewals):
    app.include_router(locked.router, dependencies=login_and_plan)


@app.get("/health", tags=["System"])
def health():
    """'Are you alive?' Railway calls this after each deploy and keeps the old
    version running until the new one answers 200. Also checks the database."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - any database problem = not healthy
        logger.exception("Health check: database unreachable")
        database = "unreachable"
    body = {"status": "ok" if database == "ok" else "error", "app": settings.app_name, "database": database,
            "environment": settings.environment, "ai_mode": "real" if settings.ai_enabled else "mock"}
    return JSONResponse(body, status_code=200 if database == "ok" else 503)
