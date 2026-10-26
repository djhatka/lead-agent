"""
Renewal reminders (Task 32).

    GET  /renewals?business_id=1          renewals coming up / due / recently expired (+ settings)
    GET  /renewals/settings?business_id=1 on/off, how many days before expiry to remind
    PUT  /renewals/settings?business_id=1 owner: change them
    GET  /renewals/{id}                   one renewal + the ready message
    POST /renewals                        add a renewal (customer, service, expiry date)
    POST /renewals/{id}/send              I sent the renewal message
    POST /renewals/{id}/snooze            remind me later
    POST /renewals/{id}/stop              stop reminding me about this one
    POST /renewals/{id}/resume            undo snooze / stop
    POST /renewals/{id}/renewed           the customer renewed
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.database import get_db
from app.models import Business, Renewal
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import renewal_service

router = APIRouter(prefix="/renewals", tags=["Renewal reminders"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RenewalSettings(BaseModel):
    enabled: bool
    remind_days_before: int


class RenewalSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    remind_days_before: Optional[int] = Field(default=None, examples=[5])


class RenewalItem(BaseModel):
    id: int
    lead_id: Optional[int]
    customer: str
    phone: Optional[str]
    service: str
    expiry_date: str                  # ISO date
    renewal_amount: Optional[int]
    kind: str                         # expiring_soon / expired / lapsed
    days_until: int                   # positive = days left, negative = days past
    reason: str
    reminders_sent: int


class RenewalList(BaseModel):
    settings: RenewalSettings
    count: int
    items: list[RenewalItem]


class Draft(BaseModel):
    text: str
    kind: str
    days_until: int
    how: str                          # whatsapp / copy
    link: Optional[str]
    note: str
    ai_mode: str
    check: str


class RenewalDetail(BaseModel):
    id: int
    lead_id: Optional[int]
    customer_name: str
    phone: Optional[str]
    service: str
    expiry_date: str
    renewal_amount: Optional[int]
    status: str
    snoozed_until: Optional[UTCDateTime]
    reminders_sent: int
    draft: Draft


class CreateIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    service: str = Field(min_length=1, max_length=100)
    expiry_date: date
    renewal_amount: Optional[int] = Field(default=None, ge=0)
    lead_id: Optional[int] = None


class SnoozeIn(BaseModel):
    days: int = Field(default=1, ge=1, le=14)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _settings(business: Business) -> RenewalSettings:
    return RenewalSettings(**renewal_service.settings_for(business))


def _renewal_or_404(renewal_id: int, db: Session) -> Renewal:
    renewal = db.get(Renewal, renewal_id)
    if not renewal:
        raise HTTPException(status_code=404, detail="Renewal not found")
    return renewal


def _detail(db: Session, renewal: Renewal) -> RenewalDetail:
    s = renewal_service.settings_for(db.get(Business, renewal.business_id))
    reminder = renewal_service.check_renewal(renewal, s)
    snoozed = renewal.snoozed_until
    if snoozed and renewal_service._aware(snoozed) <= renewal_service._now():
        snoozed = None
    try:
        draft = renewal_service.draft(db, renewal, reminder)
    except Exception:  # noqa: BLE001
        # Fallback draft so the endpoint never 500s because of the AI agent
        send_info = renewal_service.how_to_send(renewal)
        draft = {"text": "Message could not be generated right now.", "kind": "expired",
                 "days_until": 0, "ai_mode": "fallback", "check": "ai_error", **send_info}
    return RenewalDetail(
        id=renewal.id, lead_id=renewal.lead_id,
        customer_name=renewal.customer_name, phone=renewal.phone,
        service=renewal.service, expiry_date=renewal.expiry_date.isoformat(),
        renewal_amount=renewal.renewal_amount, status=renewal.status,
        snoozed_until=snoozed, reminders_sent=renewal.reminders_sent,
        draft=draft,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=RenewalList)
def list_due(business_id: int, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    items = renewal_service.due(db, business)
    return RenewalList(settings=_settings(business), count=len(items), items=items)


@router.get("/settings", response_model=RenewalSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _settings(business_or_404(business_id, db))


@router.put("/settings", response_model=RenewalSettings)
def put_settings(business_id: int, body: RenewalSettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        renewal_service.update_settings(db, business, body.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _settings(business)


@router.post("", response_model=RenewalDetail)
def create(business_id: int, body: CreateIn, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    renewal = Renewal(
        business_id=business.id, lead_id=body.lead_id,
        customer_name=body.customer_name, phone=body.phone,
        service=body.service, expiry_date=body.expiry_date,
        renewal_amount=body.renewal_amount,
    )
    db.add(renewal)
    db.commit()
    db.refresh(renewal)
    return _detail(db, renewal)


@router.get("/{renewal_id}", response_model=RenewalDetail)
def get_one(renewal_id: int, db: Session = Depends(get_db)):
    return _detail(db, _renewal_or_404(renewal_id, db))


@router.post("/{renewal_id}/send", response_model=RenewalDetail)
def send(renewal_id: int, db: Session = Depends(get_db)):
    renewal = _renewal_or_404(renewal_id, db)
    renewal_service.send(db, renewal)
    return _detail(db, renewal)


@router.post("/{renewal_id}/snooze", response_model=RenewalDetail)
def snooze(renewal_id: int, body: SnoozeIn, db: Session = Depends(get_db)):
    renewal = _renewal_or_404(renewal_id, db)
    renewal_service.snooze(db, renewal, body.days)
    return _detail(db, renewal)


@router.post("/{renewal_id}/stop", response_model=RenewalDetail)
def stop_renewal(renewal_id: int, db: Session = Depends(get_db)):
    renewal = _renewal_or_404(renewal_id, db)
    renewal_service.stop(db, renewal)
    return _detail(db, renewal)


@router.post("/{renewal_id}/resume", response_model=RenewalDetail)
def resume(renewal_id: int, db: Session = Depends(get_db)):
    renewal = _renewal_or_404(renewal_id, db)
    renewal_service.resume(db, renewal)
    return _detail(db, renewal)


@router.post("/{renewal_id}/renewed", response_model=RenewalDetail)
def mark_renewed(renewal_id: int, db: Session = Depends(get_db)):
    renewal = _renewal_or_404(renewal_id, db)
    renewal_service.mark_renewed(db, renewal)
    return _detail(db, renewal)
