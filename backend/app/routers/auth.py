"""
Account endpoints.

    POST /auth/signup            new business + owner account → logged in
    POST /auth/login             email + password → a token (send it as "Authorization: Bearer <token>")
    POST /auth/logout            end this login
    GET  /auth/me                who am I? (+ my business)
    POST /auth/change-password   (logs out your other devices)
    POST /auth/forgot-password   email me a "set a new password" link
    POST /auth/reset-password    use that link's token → new password, logged in

    GET    /team                 people with access to my business
    POST   /team                 owner adds a staff member
    DELETE /team/{user_id}       owner removes a staff member

On the /docs page: log in, copy the token, click "Authorize" (top right), paste it.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import bearer, get_current_user, require_owner
from app.database import get_db
from app.models import Business, User
from app.schemas import (AuthOut, ChangePasswordIn, ForgotPasswordIn, LoginIn, ResetPasswordIn, SignupIn, StaffInvite,
                         UserOut)
from app.services import auth_service, billing_service, email_service

router = APIRouter(tags=["Accounts"])


def _auth_out(token, session, user: User, business) -> AuthOut:
    return AuthOut(token=token, expires_at=session.expires_at, user=user, business=business)


@router.post("/auth/signup", response_model=AuthOut, status_code=201)
def signup(data: SignupIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        token, session, user, business = auth_service.signup(db, data)
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    background.add_task(email_service.deliver_in_background)       # the welcome email, after replying
    return _auth_out(token, session, user, business)


FORGOT_REPLY = {"message": "If that email has an account, we've sent a link to set a new password. "
                           "Check your inbox (and spam) in a minute."}


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(data: ForgotPasswordIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always the same answer, whether or not the email has an account (on purpose)."""
    if auth_service.request_reset(db, data.email):
        background.add_task(email_service.deliver_in_background)
    return FORGOT_REPLY


@router.post("/auth/reset-password", response_model=AuthOut)
def reset_password(data: ResetPasswordIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Also used by new staff members (the link in their invite email)."""
    try:
        token, session, user = auth_service.reset_password(db, data.token, data.new_password)
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    background.add_task(email_service.deliver_in_background)
    business = db.get(Business, user.business_id) if user.business_id else None
    return _auth_out(token, session, user, business)


@router.post("/auth/login", response_model=AuthOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    try:
        token, session, user = auth_service.login(db, data.email, data.password)
    except auth_service.TooManyAttempts as problem:
        raise HTTPException(status_code=429, detail=str(problem))
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=401, detail=str(problem))
    business = db.get(Business, user.business_id) if user.business_id else None
    return _auth_out(token, session, user, business)


def _token(credentials: HTTPAuthorizationCredentials | None, request: Request) -> str:
    return credentials.credentials if credentials else request.query_params.get("token", "")


@router.post("/auth/logout", status_code=204)
def logout(request: Request, credentials=Depends(bearer), _user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    auth_service.logout(db, _token(credentials, request))


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    business = db.get(Business, user.business_id) if user.business_id else None
    from app.schemas import BusinessOut
    return {"user": UserOut.model_validate(user),
            "business": BusinessOut.model_validate(business) if business else None}


@router.post("/auth/change-password", status_code=204)
def change_password(data: ChangePasswordIn, request: Request, background: BackgroundTasks, credentials=Depends(bearer),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        auth_service.change_password(db, user, data, keep_token=_token(credentials, request))
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    background.add_task(email_service.deliver_in_background)


def _team_business(user: User, business_id: int | None) -> int:
    """Owners manage their own business; the admin must say which one."""
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_id
    return user.business_id


@router.get("/team", response_model=list[UserOut])
def team(business_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bid = _team_business(user, business_id) if user.role == "admin" else user.business_id
    return list(db.scalars(select(User).where(User.business_id == bid, User.is_active).order_by(User.id)))


@router.post("/team", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_staff(data: StaffInvite, background: BackgroundTasks, business_id: int | None = None,
              owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    """They get an email with a link to choose their own password (valid 3 days)."""
    bid = _team_business(owner, business_id)
    try:
        billing_service.check_room(db, bid, "staff_seats")         # plan limit
    except billing_service.PlanLimit as problem:
        raise HTTPException(status_code=403, detail=str(problem))
    try:
        staff = auth_service.add_staff(db, owner, bid, data)
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    background.add_task(email_service.deliver_in_background)
    return staff


@router.delete("/team/{user_id}", status_code=204)
def remove_staff(user_id: int, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    staff = db.get(User, user_id)
    if staff is None or (owner.role != "admin" and staff.business_id != owner.business_id):
        raise HTTPException(status_code=404, detail="That person was not found")
    try:
        auth_service.remove_staff(db, staff)
    except auth_service.AuthError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
