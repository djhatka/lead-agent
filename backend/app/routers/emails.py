"""
The email log (admin only): every email the website sent or tried to send.

    GET /admin/emails                  newest first; filter by kind / status / to
    GET /admin/emails/{id}/preview     see the email exactly as the customer sees it

Handy in mock mode too: the emails also land as .html files in data/outbox/.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import require_admin
from app.config import settings
from app.database import get_db
from app.models import Email
from app.schemas import UTCDateTime

router = APIRouter(tags=["Emails (admin)"], dependencies=[Depends(require_admin)])


class EmailOut(BaseModel):
    id: int
    business_id: Optional[int]
    to: str
    kind: str
    subject: str
    status: str
    attempts: int
    error: str
    created_at: UTCDateTime
    sent_at: Optional[UTCDateTime]

    model_config = {"from_attributes": True}


class EmailLog(BaseModel):
    mode: str                     # "mock" (saved to data/outbox) or "real" (SMTP)
    items: list[EmailOut]


@router.get("/admin/emails", response_model=EmailLog)
def log(kind: Optional[str] = None, status: Optional[str] = None, to: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    query = select(Email)
    if kind:
        query = query.where(Email.kind == kind)
    if status:
        query = query.where(Email.status == status)
    if to:
        query = query.where(Email.to == to.strip().lower())
    items = list(db.scalars(query.order_by(Email.id.desc()).limit(limit)))
    return EmailLog(mode="real" if settings.email_enabled else "mock", items=items)


@router.get("/admin/emails/{email_id}/preview", response_class=HTMLResponse)
def preview(email_id: int, db: Session = Depends(get_db)):
    email = db.get(Email, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return HTMLResponse(email.html, headers={"Content-Security-Policy": "script-src 'none'"})
