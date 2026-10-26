"""
Follow-up reminders (Task 30).

    GET  /followups?business_id=1          the enquiries that need a follow-up now (+ the settings)
    GET  /followups/settings?business_id=1 on/off, and after how many quiet days
    PUT  /followups/settings?business_id=1 owner: change them (send only what changes)
    GET  /followups/{lead_id}              one lead: does it need a follow-up? + the ready message
    POST /followups/{lead_id}/send         send it: {"text": "...", "via": "app" | "phone"}
    POST /followups/{lead_id}/snooze       remind me later: {"days": 1}
    POST /followups/{lead_id}/stop         stop reminding me about this one
    POST /followups/{lead_id}/resume       undo snooze / stop
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.database import get_db
from app.models import Business
from app.routers.businesses import business_or_404
from app.routers.leads import lead_or_404
from app.schemas import MessageOut, UTCDateTime
from app.services import followup_service

router = APIRouter(prefix="/followups", tags=["Follow-up reminders"])


class FollowUpSettings(BaseModel):
    enabled: bool
    after_days: int                   # remind when an enquiry has been quiet this many days


class FollowUpSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    after_days: Optional[int] = Field(default=None, examples=[2])


class Reminder(BaseModel):
    lead_id: int
    customer: str                     # "Rahul Sharma", or the phone / @handle
    source: str
    source_name: str                  # "WhatsApp"
    service: Optional[str]
    status: str
    score: Optional[int]
    priority: str                     # hot / normal
    kind: str                         # no_reply / waiting / gone_quiet
    reason: str                       # "Asked about Zumba 2 days ago. No reply yet."
    since: UTCDateTime                # when the conversation went quiet
    days: int
    followups_sent: int


class ReminderList(BaseModel):
    settings: FollowUpSettings
    count: int
    items: list[Reminder]


class Draft(BaseModel):
    text: str                         # the ready message (the owner can change it before sending)
    kind: str
    nth: int                          # 1 = first follow-up since the customer last wrote
    how: str                          # app / whatsapp / instagram / copy
    link: Optional[str]               # wa.me or ig.me link (add ?text=... for WhatsApp)
    note: str                         # what the owner should know about sending
    ai_mode: str                      # mock / real / fallback
    check: str                        # ok / replaced (the AI mentioned money or a link) / ai_error


class LeadFollowUp(BaseModel):
    due: bool                         # does it need a follow-up right now?
    reminder: Optional[Reminder]      # why (when due)
    snoozed_until: Optional[UTCDateTime]   # only while the snooze is still on
    stopped: bool
    draft: Draft                      # a ready message is always offered, even when not due


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    via: Literal["app", "phone"] = "app"


class SnoozeIn(BaseModel):
    days: int = Field(default=1, ge=1, le=14)


def _settings(business: Business) -> FollowUpSettings:
    return FollowUpSettings(**followup_service.settings_for(business))


@router.get("", response_model=ReminderList)
def list_due(business_id: int, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    items = followup_service.due(db, business)
    return ReminderList(settings=_settings(business), count=len(items), items=items)


@router.get("/settings", response_model=FollowUpSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _settings(business_or_404(business_id, db))


@router.put("/settings", response_model=FollowUpSettings)
def put_settings(business_id: int, body: FollowUpSettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        followup_service.update_settings(db, business, body.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _settings(business)


def _lead_view(db: Session, lead) -> LeadFollowUp:
    business = db.get(Business, lead.business_id)
    on = followup_service.settings_for(business)["enabled"]
    reminder = followup_service.check_lead(lead, business) if on else None
    snoozed = followup_service._utc(lead.followup_snoozed_until)
    return LeadFollowUp(due=reminder is not None, reminder=reminder,
                        snoozed_until=snoozed if snoozed and snoozed > followup_service._now() else None,
                        stopped=lead.followup_stopped, draft=followup_service.draft(db, lead, reminder))


@router.get("/{lead_id}", response_model=LeadFollowUp)
def for_lead(lead_id: int, db: Session = Depends(get_db)):
    return _lead_view(db, lead_or_404(lead_id, db))


@router.post("/{lead_id}/send", response_model=MessageOut)
def send(lead_id: int, body: SendIn, db: Session = Depends(get_db)):
    """The answer's `delivery` says what happened: sent / failed (+ why) / logged (sent from your phone)."""
    lead = lead_or_404(lead_id, db)
    try:
        return followup_service.send(db, lead, body.text.strip(), body.via)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))


@router.post("/{lead_id}/snooze", response_model=LeadFollowUp)
def snooze(lead_id: int, body: SnoozeIn, db: Session = Depends(get_db)):
    lead = lead_or_404(lead_id, db)
    followup_service.snooze(db, lead, body.days)
    return _lead_view(db, lead)


@router.post("/{lead_id}/stop", response_model=LeadFollowUp)
def stop(lead_id: int, db: Session = Depends(get_db)):
    lead = lead_or_404(lead_id, db)
    followup_service.stop(db, lead)
    return _lead_view(db, lead)


@router.post("/{lead_id}/resume", response_model=LeadFollowUp)
def resume(lead_id: int, db: Session = Depends(get_db)):
    """Undo "remind me later" / "stop reminding me"."""
    lead = lead_or_404(lead_id, db)
    lead.followup_stopped, lead.followup_snoozed_until = False, None
    db.commit()
    return _lead_view(db, lead)
