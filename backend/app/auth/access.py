"""
The guard at the door: who is asking, and may they see this?

1. get_current_user (used by every protected router)
   Reads the login token from the request:
       Authorization: Bearer <token>        (normal requests)
       ?token=<token>                       (the live feed: browsers can't add headers there)
   Finds the matching active login, or replies 401 "please log in".

2. check_access(business_id) (called inside every ..._or_404 helper)
   owner/staff → only their own business.   admin → every business.
   Asking for another business's data gives 404 "not found", so we don't
   even reveal that it exists.

How the two connect: get_current_user remembers the user in a "context
variable", a note that travels with this one request (and only this one),
so check_access can read it from anywhere without passing it around.
Routes with no login at all (the webhooks that WhatsApp/Instagram call)
never set the note, and check_access lets them through.
"""

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import token_fingerprint
from app.database import get_db
from app.models import AuthSession, User

_current_user: ContextVar[Optional[User]] = ContextVar("current_user", default=None)

# Adds the "Authorize" padlock button on the /docs page
bearer = HTTPBearer(auto_error=False, description="Paste the token from POST /auth/login")


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def remember_user(user: Optional[User]) -> None:
    _current_user.set(user)


def current_user() -> Optional[User]:
    return _current_user.get()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    token: Optional[str] = Query(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
) -> User:
    raw = credentials.credentials if credentials else token
    not_logged_in = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in",
                                  headers={"WWW-Authenticate": "Bearer"})
    if not raw:
        raise not_logged_in

    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_fingerprint(raw)))
    now = datetime.now(timezone.utc)
    if session is None or _utc(session.expires_at) <= now:
        raise not_logged_in
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise not_logged_in

    if now - _utc(session.last_used_at) > timedelta(minutes=5):   # don't write on every single request
        session.last_used_at = now
        db.commit()
    remember_user(user)
    return user


def can_access(business_id: Optional[int]) -> bool:
    user = current_user()
    if user is None:          # a route without login (webhooks): nothing to check
        return True
    return user.role == "admin" or user.business_id == business_id


def check_access(business_id: Optional[int], what: str = "That") -> None:
    if not can_access(business_id):
        raise HTTPException(status_code=404, detail=f"{what} was not found")


def require_owner(user: User = Depends(get_current_user)) -> User:
    """Settings and team changes: owners (and the admin) only, not staff."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only the business owner can do this")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the platform admin can do this")
    return user
