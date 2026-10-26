"""
Accounts: sign up, log in, log out, change password, staff.

Safety details:
  - Wrong password and unknown email get the SAME message, so nobody can
    find out which emails have accounts.
  - Too many wrong passwords for one email → locked for a few minutes
    (stops someone guessing passwords automatically).
  - Changing your password logs out your other devices.
  - Removing a staff member logs them out everywhere immediately.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, new_token, token_fingerprint, verify_password
from app.config import settings
from app.models import AuthSession, Business, PasswordReset, User
from app.schemas import ChangePasswordIn, SignupIn, StaffInvite
from app.services import billing_service, email_service

RESETS_PER_HOUR = 3
INVITE_DAYS = 3


class AuthError(Exception):
    """Something the user should be told, e.g. 'wrong email or password'."""


class TooManyAttempts(AuthError):
    pass


_failures: dict[str, list[datetime]] = defaultdict(list)     # email → times of recent wrong passwords


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start_session(db: Session, user: User) -> tuple[str, AuthSession]:
    token = new_token()
    session = AuthSession(user_id=user.id, token_hash=token_fingerprint(token),
                          expires_at=_now() + timedelta(days=settings.session_days))
    user.last_login_at = _now()
    db.add(session)
    db.commit()
    return token, session


def email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email)) is not None


def signup(db: Session, data: SignupIn) -> tuple[str, AuthSession, User, Business]:
    if email_taken(db, data.email):
        raise AuthError("This email already has an account. Please log in.")
    business = Business(name=data.business_name, industry=data.industry, city=data.city,
                        area=data.area, phone=data.phone)
    db.add(business)
    db.flush()
    trial = billing_service.start_trial(db, business)    # every new business starts with a free trial
    user = User(email=data.email, name=data.name, password_hash=hash_password(data.password),
                role="owner", business_id=business.id)
    db.add(user)
    db.flush()
    token, session = _start_session(db, user)
    email_service.send_welcome(db, user, business, trial.trial_ends_at)
    return token, session, user, business


def login(db: Session, email: str, password: str) -> tuple[str, AuthSession, User]:
    window = _now() - timedelta(minutes=settings.login_lock_minutes)
    _failures[email] = [t for t in _failures[email] if t > window]
    if len(_failures[email]) >= settings.max_login_failures:
        raise TooManyAttempts(f"Too many wrong attempts. Try again in {settings.login_lock_minutes} minutes.")

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _failures[email].append(_now())
        raise AuthError("Wrong email or password")
    _failures.pop(email, None)
    token, session = _start_session(db, user)
    return token, session, user


def logout(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_fingerprint(token)))
    db.commit()


def change_password(db: Session, user: User, data: ChangePasswordIn, keep_token: str) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise AuthError("Your current password is wrong")
    user.password_hash = hash_password(data.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id,
                                         AuthSession.token_hash != token_fingerprint(keep_token)))
    db.commit()
    email_service.send_password_changed(db, user)            # "wasn't you?" safety notice


def add_staff(db: Session, owner: User, business_id: int, data: StaffInvite) -> User:
    if email_taken(db, data.email):
        raise AuthError("This email already has an account")
    # No password given → a random one nobody knows; they choose their own from the email link
    staff = User(email=data.email, name=data.name, password_hash=hash_password(data.password or new_token()),
                 role="staff", business_id=business_id)
    db.add(staff)
    db.commit()
    link_token = _new_reset(db, staff, "invite", timedelta(days=INVITE_DAYS))
    email_service.send_staff_invite(db, staff, owner, link_token, INVITE_DAYS)
    return staff


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------
def _new_reset(db: Session, user: User, purpose: str, lasts: timedelta) -> str:
    token = new_token()                                       # the secret goes in the email link...
    db.add(PasswordReset(user_id=user.id, token_hash=token_fingerprint(token), purpose=purpose,
                         expires_at=_now() + lasts))          # ...only its fingerprint is stored
    db.commit()
    return token


def request_reset(db: Session, email: str) -> bool:
    """Send a reset link if the account exists. The website always shows the SAME
    message either way, so nobody can test which emails have accounts.
    Returns True if an email was queued (for tests/logs only)."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return False
    hour_ago = _now() - timedelta(hours=1)
    recent = db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.purpose == "reset",
                                                    PasswordReset.created_at >= hour_ago)).all()
    if len(recent) >= RESETS_PER_HOUR:                        # stops someone flooding a person's inbox
        return False
    token = _new_reset(db, user, "reset", timedelta(minutes=settings.password_reset_minutes))
    email_service.send_password_reset(db, user, token)
    return True


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def reset_password(db: Session, token: str, new_password: str) -> tuple[str, AuthSession, User]:
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_fingerprint(token)))
    if row is None or row.used_at is not None or _utc(row.expires_at) <= _now():
        raise AuthError("This link has expired or was already used. Ask for a new one on the 'Forgot password' page.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthError("This account is no longer active")
    user.password_hash = hash_password(new_password)
    for other in db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id,
                                                        PasswordReset.used_at.is_(None))):
        other.used_at = _now()                                # this link AND any older ones stop working
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))   # logged out everywhere
    _failures.pop(user.email, None)                           # and the wrong-password lock is lifted
    db.commit()
    if row.purpose == "reset":
        email_service.send_password_changed(db, user)
    token_out, session = _start_session(db, user)
    return token_out, session, user


def remove_staff(db: Session, user: User) -> None:
    if user.role != "staff":
        raise AuthError("Only staff accounts can be removed here")
    user.is_active = False
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()


def create_user(db: Session, email: str, name: str, password: str, role: str,
                business_id: Optional[int] = None) -> User:
    """For scripts (demo data, creating the admin)."""
    user = User(email=email.lower(), name=name, password_hash=hash_password(password),
                role=role, business_id=business_id)
    db.add(user)
    db.commit()
    return user
