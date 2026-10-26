"""
The paywall: is this business's plan (or free trial) still running?

Added to every locked router in main.py, right after the login check.
If the trial ended or payment stopped → 402 "Payment Required" with a
friendly message; the website shows the "Choose a plan" page instead.

Still open while locked: logging in, /auth/me and /billing (so they can pay),
and the webhooks (enquiries keep being saved). The admin is never blocked.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.access import get_current_user
from app.database import get_db
from app.models import User
from app.services import billing_service


def require_active_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    if user.role == "admin" or user.business_id is None:
        return
    info = billing_service.access(db, user.business_id)
    if not info.usable:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=info.message)
