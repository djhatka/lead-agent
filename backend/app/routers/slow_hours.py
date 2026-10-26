"""
Fill your empty hours (Task 33).

    GET  /slow-hours?business_id=1           slow time slots + past customers to invite (+ settings)
    GET  /slow-hours/settings?business_id=1  on/off, how many days since a customer bought before we invite them
    PUT  /slow-hours/settings?business_id=1  owner: change them
    GET  /slow-hours/{lead_id}?day=...&hours=...   one customer's ready invite message
    POST /slow-hours/{lead_id}/send          I sent the invite message
    POST /slow-hours/{lead_id}/skip          don't suggest this customer again for a while
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.database import get_db
from app.models import Business, Lead
from app.routers.businesses import business_or_404
from app.services import slow_hours_service

router = APIRouter(prefix="/slow-hours", tags=["Fill your empty hours"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class SlowHoursSettings(BaseModel):
    enabled: bool
    min_days_since_won: int


class SlowHoursSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    min_days_since_won: Optional[int] = Field(default=None, examples=[30])


class SlowWindow(BaseModel):
    weekday: int
    day: str
    hours: str
    enquiries: int
    usual: float


class Candidate(BaseModel):
    lead_id: int
    name: Optional[str]
    phone: Optional[str]
    area: Optional[str]
    service: Optional[str]
    last_bought: str


class Overview(BaseModel):
    settings: SlowHoursSettings
    slow_windows: list[SlowWindow]
    candidates: list[Candidate]


class Draft(BaseModel):
    text: str
    ai_mode: str
    check: str
    how: str                          # whatsapp / copy
    link: Optional[str]
    note: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _settings(business: Business) -> SlowHoursSettings:
    return SlowHoursSettings(**slow_hours_service.settings_for(business))


def _lead_or_404(lead_id: int, db: Session) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Customer not found")
    return lead


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=Overview)
def overview(business_id: int, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    return Overview(
        settings=_settings(business),
        slow_windows=slow_hours_service.slow_windows(db, business),
        candidates=slow_hours_service.candidates(db, business),
    )


@router.get("/settings", response_model=SlowHoursSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _settings(business_or_404(business_id, db))


@router.put("/settings", response_model=SlowHoursSettings)
def put_settings(business_id: int, body: SlowHoursSettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        slow_hours_service.update_settings(db, business, body.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _settings(business)


@router.get("/{lead_id}", response_model=Draft)
def get_draft(lead_id: int, day: str = Query(...), hours: str = Query(...),
              db: Session = Depends(get_db)):
    lead = _lead_or_404(lead_id, db)
    return slow_hours_service.draft(db, lead, {"day": day, "hours": hours})


@router.post("/{lead_id}/send", response_model=Candidate)
def send(lead_id: int, db: Session = Depends(get_db)):
    lead = _lead_or_404(lead_id, db)
    slow_hours_service.send(db, lead)
    return Candidate(lead_id=lead.id, name=lead.name, phone=lead.phone, area=lead.area,
                     service=lead.service, last_bought=lead.won_at.date().isoformat())


@router.post("/{lead_id}/skip", response_model=Candidate)
def skip(lead_id: int, db: Session = Depends(get_db)):
    lead = _lead_or_404(lead_id, db)
    slow_hours_service.skip(db, lead)
    return Candidate(lead_id=lead.id, name=lead.name, phone=lead.phone, area=lead.area,
                     service=lead.service, last_bought=lead.won_at.date().isoformat())
