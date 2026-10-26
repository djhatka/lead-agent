"""
Instant AI first reply (Task 29).

    GET  /auto-reply/settings?business_id=1   the choice, opening hours, note, open now?, connected chats, latest replies
    PUT  /auto-reply/settings?business_id=1   owner: change any of them (send only what changes)
    POST /auto-reply/preview?business_id=1    see the reply the AI WOULD send to a sample message (nothing is sent)
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.llm import get_llm
from app.auth.access import require_owner
from app.database import get_db
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import auto_reply_service

router = APIRouter(prefix="/auto-reply", tags=["Instant first reply"])

CLOCK = r"^([01]\d|2[0-3]):[0-5]\d$"         # "09:00", "21:30" (24-hour clock, India time)


class AutoReplyOut(BaseModel):
    lead_id: int
    customer: str
    text: str
    delivery: str                     # sent / failed
    delivery_error: str
    sent_at: UTCDateTime


class AutoReplySettings(BaseModel):
    mode: Literal["off", "always", "after_hours"]
    opens: str
    closes: str
    closed_days: list[int]            # 0 = Monday ... 6 = Sunday
    note: str
    open_now: bool
    back_at: str                      # "tomorrow at 9 am": what a reply sent now would say
    channels: dict[str, bool]         # {"whatsapp": true, "instagram": false, "facebook": false}
    ai_mode: str                      # mock / real
    recent: list[AutoReplyOut]


class AutoReplySettingsIn(BaseModel):
    mode: Optional[Literal["off", "always", "after_hours"]] = None
    opens: Optional[str] = Field(default=None, pattern=CLOCK, examples=["09:00"])
    closes: Optional[str] = Field(default=None, pattern=CLOCK, examples=["21:00"])
    closed_days: Optional[list[int]] = Field(default=None, max_length=7)
    note: Optional[str] = Field(default=None, max_length=200,
                                examples=["For emergencies call 98100 00000"])


class PreviewIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000,
                         examples=["Hi, what are the timings for Zumba? Kitne ki fees hai?"])


class PreviewOut(BaseModel):
    reply: str
    open_now: bool
    back_at: str
    ai_mode: str                      # mock / real / fallback
    check: str                        # ok / replaced (the AI mentioned money or a link) / ai_error


def _out(db: Session, business) -> AutoReplySettings:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    s = auto_reply_service.settings_for(business)
    recent = [AutoReplyOut(lead_id=lead.id, customer=lead.name or lead.phone or (f"@{lead.handle}" if lead.handle else "Customer"),
                           text=m.text, delivery=m.delivery, delivery_error=m.delivery_error, sent_at=m.sent_at)
              for m, lead in auto_reply_service.recent(db, business.id)]
    return AutoReplySettings(**s, open_now=auto_reply_service.is_open(business, now),
                             back_at=auto_reply_service.back_at(business, now),
                             channels=auto_reply_service.channels(db, business.id), ai_mode=get_llm().mode,
                             recent=recent)


@router.get("/settings", response_model=AutoReplySettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _out(db, business_or_404(business_id, db))


@router.put("/settings", response_model=AutoReplySettings)
def put_settings(business_id: int, body: AutoReplySettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if any(d not in range(7) for d in changes.get("closed_days", [])):
        raise HTTPException(status_code=422, detail="closed_days are 0 (Monday) to 6 (Sunday)")
    if "note" in changes:
        changes["note"] = changes["note"].strip()
    try:
        auto_reply_service.update_settings(db, business, changes)
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _out(db, business)


@router.post("/preview", response_model=PreviewOut)
def preview(business_id: int, body: PreviewIn, db: Session = Depends(get_db)):
    made = auto_reply_service.preview(business_or_404(business_id, db), body.message)
    return PreviewOut(reply=made["text"], open_now=made["open_now"], back_at=made["back_at"],
                      ai_mode=made["ai_mode"], check=made["check"])
