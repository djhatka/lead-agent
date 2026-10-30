"""
Phone call tracking (Task 38): one tracking number per business; every call shows up
here, missed calls flagged for a call-back, completed calls with a recording link and
(when a transcript is available) a short AI note on what the caller asked about.

    GET  /calls/number?business_id=1     the business's tracking number (bought on first use)
    GET  /calls/summary?business_id=1    today's calls, missed waiting for a call-back...
    GET  /calls?business_id=1&status=    the list (ringing / completed / missed / failed / all)
    POST /calls/{id}/called-back          owner rang the customer back
    POST /calls/simulate?business_id=1    demo helper (mock mode only): pretend a call just happened

The provider rings the doorbell at /webhooks/calltracking (app/routers/webhooks.py).
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.access import check_access
from app.config import settings
from app.database import get_db
from app.models import Call
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import calltracking_service

router = APIRouter(prefix="/calls", tags=["Phone call tracking"])


class NumberOut(BaseModel):
    number: str
    mode: str                            # real / mock


class CallOut(BaseModel):
    id: int
    from_number: str
    status: str                          # ringing / completed / missed / failed
    duration_seconds: int
    recording_url: str
    note: str
    called_back_at: Optional[UTCDateTime]
    started_at: UTCDateTime


class Summary(BaseModel):
    total: int
    missed_waiting: int
    completed: int
    today: int
    mode: str


def _out(c: Call) -> CallOut:
    return CallOut(id=c.id, from_number=c.from_number, status=c.status, duration_seconds=c.duration_seconds,
                   recording_url=c.recording_url, note=c.note, called_back_at=c.called_back_at,
                   started_at=c.started_at)


def call_or_404(call_id: int, db: Session) -> Call:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="That call was not found")
    check_access(call.business_id, "That call")
    return call


@router.get("/number", response_model=NumberOut)
def get_number(business_id: int, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    tn = calltracking_service.number_for(db, business)
    return NumberOut(number=tn.number, mode="real" if settings.calltracking_enabled else "mock")


@router.get("/summary", response_model=Summary)
def get_summary(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return calltracking_service.summary(db, business_id)


@router.get("", response_model=list[CallOut])
def list_calls(business_id: int, status: Literal["ringing", "completed", "missed", "failed", "all"] = "all",
              db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return [_out(c) for c in calltracking_service.listing(db, business_id, status)]


@router.post("/{call_id}/called-back", response_model=CallOut)
def called_back(call_id: int, db: Session = Depends(get_db)):
    call = call_or_404(call_id, db)
    try:
        calltracking_service.mark_called_back(db, call)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return _out(call)


@router.post("/simulate", response_model=CallOut, status_code=201)
def simulate(business_id: int, missed: bool = False, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    if settings.calltracking_enabled:
        raise HTTPException(status_code=400,
                            detail="A real call-tracking number is connected: simulate is for the free demo only")
    return _out(calltracking_service.simulate_call(db, business, missed=missed))
