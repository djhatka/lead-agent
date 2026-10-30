"""
Phone call tracking (Task 38): a tracking number per business. Customers call it
instead of the owner's real number; it forwards straight through, but now every
call shows up on the dashboard: missed calls flagged for a call-back, completed
calls with a recording link, and (when a transcript is available) a short AI note
on what was asked.

    number_for           the business's tracking number (bought the first time it's needed)
    record_call          a call event arrived (real webhook, or "Simulate a call")
    listing / summary    the Calls page
    mark_called_back     owner rang the customer back

Needs a calling provider such as Exotel or MyOperator (CALLTRACKING_SID/TOKEN/SUBDOMAIN
in .env, paid per number + per minute - see the go-live guide). Until set, this runs
free in mock mode: a demo number, and "Simulate a call" to try the feature out.
"""

import logging
import random
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.nodes.call_note_agent import mock_call_note, write_call_note
from app.config import settings
from app.integrations import calltracking
from app.models import Business, Call, TrackingNumber
from app.services.event_bus import bus

logger = logging.getLogger("calltracking")

MISSED_STATUSES = ("missed", "no-answer", "no_answer", "busy", "canceled", "cancelled")
ANSWERED_STATUSES = ("completed",)
RINGING_STATUSES = ("ringing", "in-progress", "in_progress", "queued", "initiated")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops timezone info on the way back out of the database even for a
    DateTime(timezone=True) column, so a value that round-tripped through it can come
    back naive while _now() stays aware. Treat a naive value as UTC before any
    subtraction or comparison, the same way dues_service.py and others do."""
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def _mock_number(business_id: int) -> str:
    """A believable fake Indian mobile number, stable per business (no real line behind it)."""
    r = random.Random(business_id * 7919 + 1)
    return f"+91 {r.randint(70000, 99999)} {r.randint(10000, 99999)}"


def _status(provider_status: str) -> str:
    s = (provider_status or "").lower().strip()
    if s in MISSED_STATUSES:
        return "missed"
    if s in ANSWERED_STATUSES:
        return "completed"
    if s in RINGING_STATUSES or not s:
        return "ringing"
    return "failed"


# ---------------------------------------------------------------------------
# The tracking number
# ---------------------------------------------------------------------------
def number_for(db: Session, business: Business) -> TrackingNumber:
    """The business's tracking number, buying one the first time it's needed."""
    tn = db.scalar(select(TrackingNumber).where(TrackingNumber.business_id == business.id))
    if tn is not None:
        return tn
    if settings.calltracking_enabled:
        bought = calltracking.buy_number()
        tn = TrackingNumber(business_id=business.id, number=bought["number"], provider_sid=bought["sid"])
    else:
        tn = TrackingNumber(business_id=business.id, number=_mock_number(business.id))
    db.add(tn)
    db.commit()
    return tn


# ---------------------------------------------------------------------------
# A call event
# ---------------------------------------------------------------------------
def record_call(db: Session, business: Business, *, external_id: str, from_number: str = "",
                provider_status: str = "", duration_seconds: int = 0, recording_url: str = "",
                transcript: str = "", now: Optional[datetime] = None) -> Call:
    """A call event arrived (a real webhook, or a simulated one): create the Call the
    first time we hear about it, update it on later events for the same call (e.g.
    "ringing" then "completed")."""
    now = now or _now()
    call = db.scalar(select(Call).where(Call.business_id == business.id, Call.external_id == external_id))
    is_new = call is None
    if call is None:
        # duration_seconds=0 explicitly: the model's default isn't applied until the next
        # flush, so reading it back right now (below) would see None, not 0.
        call = Call(business_id=business.id, external_id=external_id[:100], from_number=from_number[:20],
                    started_at=now, duration_seconds=0)
        db.add(call)
    was_missed_before = call.status == "missed"
    call.status = _status(provider_status)
    call.duration_seconds = max(call.duration_seconds or 0, duration_seconds or 0)
    if from_number and not call.from_number:
        call.from_number = from_number[:20]
    if recording_url:
        call.recording_url = recording_url[:500]
    if transcript:
        call.transcript = transcript[:4000]
    db.commit()

    if call.status == "missed" and (is_new or not was_missed_before):
        bus.publish(business.id, "call.missed", f"📵 Missed call from {call.from_number or 'a customer'}",
                    "Call them back when you can", {"call_id": call.id})
    if call.status == "completed" and call.transcript and not call.note:
        _write_note(db, business, call)
    return call


def _write_note(db: Session, business: Business, call: Call) -> None:
    profile = {"name": business.name, "industry": business.industry, "services": business.services or []}
    try:
        result = write_call_note(profile, call.transcript)
        note = result.data.note.strip()
    except Exception:  # noqa: BLE001 - a failed AI note must never break saving the call
        logger.exception("Call note agent failed for call %s", call.id)
        note = ""
    if not note:
        note = mock_call_note(profile, call.transcript)["note"]
    call.note = note[:300]
    db.commit()


def simulate_call(db: Session, business: Business, *, from_number: str = "", missed: bool = False,
                  now: Optional[datetime] = None) -> Call:
    """Demo helper (mock mode only): pretend a customer just called, so the owner can
    see how the Calls page works before connecting a real provider."""
    now = now or _now()
    from_number = from_number or f"+91 {random.randint(70000, 99999)} {random.randint(10000, 99999)}"
    external_id = f"demo_{secrets.token_hex(6)}"
    if missed:
        return record_call(db, business, external_id=external_id, from_number=from_number,
                           provider_status="no-answer", now=now)
    services = business.services or ["your services"]
    service = random.choice(services)
    transcript = (f"Hi, I saw your page online. I wanted to ask about {service} - what's the price, "
                 f"and do you have anything available this week?")
    return record_call(db, business, external_id=external_id, from_number=from_number, provider_status="completed",
                       duration_seconds=random.randint(40, 240), transcript=transcript, now=now)


# ---------------------------------------------------------------------------
# The Calls page
# ---------------------------------------------------------------------------
def listing(db: Session, business_id: int, status: str = "all") -> list[Call]:
    query = select(Call).where(Call.business_id == business_id)
    if status != "all":
        query = query.where(Call.status == status)
    return list(db.scalars(query.order_by(Call.started_at.desc()).limit(300)))


def mark_called_back(db: Session, call: Call, now: Optional[datetime] = None) -> Call:
    if call.status != "missed":
        raise ValueError("Only a missed call can be marked called back")
    if call.called_back_at is not None:
        raise ValueError("This call has already been marked called back")
    call.called_back_at = now or _now()
    db.commit()
    return call


def summary(db: Session, business_id: int, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    today = now.astimezone(timezone.utc).date()
    calls = list(db.scalars(select(Call).where(Call.business_id == business_id)))
    missed_waiting = [c for c in calls if c.status == "missed" and c.called_back_at is None]
    completed = [c for c in calls if c.status == "completed"]
    today_calls = [c for c in calls if _utc(c.started_at) and _utc(c.started_at).date() == today]
    return {"total": len(calls), "missed_waiting": len(missed_waiting), "completed": len(completed),
            "today": len(today_calls), "mode": "real" if settings.calltracking_enabled else "mock"}
