"""
Renewal reminders (Task 32): "Priya's monthly membership ends in 5 days".

Unlike follow-ups (enquiries gone quiet) and dues (money owed), renewals track
when something the customer already bought is about to expire, so the owner can
offer a renewal before the customer disappears.

    due              renewals coming up, due or recently expired
    check_renewal    one renewal: does it need attention?
    draft            the ready message (the Renewal agent) and how to send it
    send             record "I sent the renewal message"
    snooze / stop    "remind me later" / "stop reminding me"
    mark_renewed     the customer renewed
    daily_reminders  scheduler job: once a day after 10am IST, live-feed note
    settings_for / update_settings   the Settings card
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.nodes.renewal_agent import mock_renewal, write_renewal
from app.models import Business, Renewal
from app.services import billing_service, connection_service, outbox
from app.services.auto_reply_service import RISKY
from app.services.event_bus import bus

logger = logging.getLogger("renewals")
IST = ZoneInfo("Asia/Kolkata")
REMIND_DAYS_BEFORE_OPTIONS = (3, 5, 7, 10, 14)
REMIND_FROM_HOUR = 10
DEFAULTS = {"enabled": True, "remind_days_before": 5}
LAPSED_LIMIT = timedelta(days=30)   # don't show renewals expired more than 30 days ago


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Make a datetime timezone-aware (SQLite drops tzinfo on round-trip)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _today(now: Optional[datetime] = None) -> date:
    return ((now or _now()).astimezone(IST)).date()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    saved = business.renewal_settings or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def update_settings(db: Session, business: Business, changes: dict) -> Business:
    if "remind_days_before" in changes and changes["remind_days_before"] not in REMIND_DAYS_BEFORE_OPTIONS:
        raise ValueError(f"remind_days_before must be one of {', '.join(map(str, REMIND_DAYS_BEFORE_OPTIONS))}")
    business.renewal_settings = {**(business.renewal_settings or {}),
                                 **{k: v for k, v in changes.items() if k in DEFAULTS}}
    db.commit()
    return business


# ---------------------------------------------------------------------------
# Who needs a renewal reminder?
# ---------------------------------------------------------------------------
def _kind_and_days(expiry: date, today: date) -> tuple[str, int]:
    """The situation and how many days until (or since) expiry."""
    delta = (expiry - today).days
    if delta > 0:
        return "expiring_soon", delta
    elif delta >= -7:
        return "expired", delta
    else:
        return "lapsed", delta


def _reason(customer: str, service: str, kind: str, days: int) -> str:
    """The line under the customer's name: why this reminder is showing."""
    if kind == "expiring_soon":
        return f"{service} expires in {days} day{'s' if days != 1 else ''}."
    elif kind == "expired" and days == 0:
        return f"{service} expires today."
    elif kind == "expired":
        return f"{service} expired {-days} day{'s' if -days != 1 else ''} ago."
    else:
        return f"{service} expired {-days} days ago."


def check_renewal(renewal: Renewal, settings: dict, today: Optional[date] = None) -> Optional[dict]:
    """None if this renewal doesn't need attention right now, else the reminder dict."""
    today = today or _today()
    if renewal.status in ("renewed", "stopped"):
        return None
    if renewal.snoozed_until and _aware(renewal.snoozed_until) > _now():
        return None
    kind, days = _kind_and_days(renewal.expiry_date, today)
    # Not within the reminder window yet
    if kind == "expiring_soon" and days > settings["remind_days_before"]:
        return None
    # Too old (lapsed more than 30 days ago)
    if days < -LAPSED_LIMIT.days:
        return None
    return {
        "id": renewal.id, "lead_id": renewal.lead_id,
        "customer": renewal.customer_name, "phone": renewal.phone,
        "service": renewal.service, "expiry_date": renewal.expiry_date.isoformat(),
        "renewal_amount": renewal.renewal_amount,
        "kind": kind, "days_until": days,
        "reason": _reason(renewal.customer_name, renewal.service, kind, days),
        "reminders_sent": renewal.reminders_sent,
    }


def _active_renewals(db: Session, business_id: int, today: date) -> list[Renewal]:
    """All renewals that might still need attention: not renewed, not stopped, not ancient."""
    cutoff = today - LAPSED_LIMIT
    return list(db.scalars(
        select(Renewal).where(
            Renewal.business_id == business_id,
            Renewal.status.notin_(("renewed", "stopped")),
            Renewal.expiry_date >= cutoff,
        ).order_by(Renewal.expiry_date)))


def due(db: Session, business: Business, now: Optional[datetime] = None) -> list[dict]:
    """Every renewal that needs attention now: soonest-expiring first."""
    now = now or _now()
    today = _today(now)
    s = settings_for(business)
    if not s["enabled"]:
        return []
    found = [r for ren in _active_renewals(db, business.id, today)
             if (r := check_renewal(ren, s, today))]
    # Sort: expired first (most urgent), then by days_until ascending
    return sorted(found, key=lambda r: r["days_until"])


# ---------------------------------------------------------------------------
# The ready message and how to send it
# ---------------------------------------------------------------------------
def _wa_number(phone: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits if 11 <= len(digits) <= 15 else None


def how_to_send(renewal: Renewal) -> dict:
    """{"how": whatsapp / copy, "link": ..., "note": ...}"""
    number = _wa_number(renewal.phone)
    if number:
        return {"how": "whatsapp", "link": f"https://wa.me/{number}",
                "note": "Opens WhatsApp on your phone with the message ready: just press send."}
    return {"how": "copy", "link": None,
            "note": "We don't have a number for this customer: copy the message, or call them."}


def draft(db: Session, renewal: Renewal, reminder: Optional[dict] = None,
          now: Optional[datetime] = None) -> dict:
    """The ready message for one renewal, plus how it can be sent."""
    now = now or _now()
    today = _today(now)
    business = db.get(Business, renewal.business_id)
    s = settings_for(business)
    if reminder is None:
        reminder = check_renewal(renewal, s, today)
    kind, days = _kind_and_days(renewal.expiry_date, today)
    profile = {"name": business.name, "industry": business.industry,
               "services": business.services or [], "brand_voice": business.brand_voice or ""}
    try:
        result = write_renewal(profile, renewal.customer_name, renewal.service, kind, abs(days) if days > 0 else abs(days))
        text, ai_mode, check = result.data.message.strip(), result.mode, "ok"
    except Exception:  # noqa: BLE001
        logger.exception("Renewal agent failed for renewal %s", renewal.id)
        text, ai_mode, check = "", "fallback", "ai_error"
    if not text or RISKY.search(text):
        if text:
            check = "replaced"
        text = mock_renewal(profile, renewal.customer_name, renewal.service, kind,
                            abs(days) if days > 0 else abs(days))["message"]
    return {"text": text[:1000], "kind": kind, "days_until": (renewal.expiry_date - today).days,
            "ai_mode": ai_mode, "check": check, **how_to_send(renewal)}


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def send(db: Session, renewal: Renewal, now: Optional[datetime] = None) -> Renewal:
    """Record that the owner sent the renewal message (from their phone)."""
    now = now or _now()
    renewal.reminders_sent = (renewal.reminders_sent or 0) + 1
    renewal.last_reminder_at = now
    db.commit()
    return renewal


def snooze(db: Session, renewal: Renewal, days: int, now: Optional[datetime] = None) -> Renewal:
    renewal.snoozed_until = (now or _now()) + timedelta(days=days)
    db.commit()
    return renewal


def stop(db: Session, renewal: Renewal) -> Renewal:
    renewal.status = "stopped"
    db.commit()
    return renewal


def mark_renewed(db: Session, renewal: Renewal, now: Optional[datetime] = None) -> Renewal:
    renewal.status = "renewed"
    renewal.renewed_at = now or _now()
    db.commit()
    return renewal


def resume(db: Session, renewal: Renewal) -> Renewal:
    """Undo snooze or stop."""
    today = _today()
    kind, _ = _kind_and_days(renewal.expiry_date, today)
    renewal.status = "upcoming" if kind == "expiring_soon" else "due" if kind == "expired" else "upcoming"
    renewal.snoozed_until = None
    db.commit()
    return renewal


# ---------------------------------------------------------------------------
# The daily note (scheduler)
# ---------------------------------------------------------------------------
def daily_reminders(db: Session, now: Optional[datetime] = None) -> int:
    """Once a day per business, after 10am IST: '🔄 2 renewals coming up'
    on the live feed. Returns how many notes were sent."""
    now = now or _now()
    local = now.astimezone(IST)
    if local.hour < REMIND_FROM_HOUR:
        return 0
    today_str = local.date().isoformat()
    paused, sent = None, 0
    for business in db.scalars(select(Business)):
        saved = business.renewal_settings or {}
        if saved.get("reminded_on") == today_str or not settings_for(business)["enabled"]:
            continue
        if paused is None:
            paused = billing_service.paused_business_ids(db)
        business.renewal_settings = {**saved, "reminded_on": today_str}
        db.commit()
        if business.id in paused:
            continue
        waiting = due(db, business, now)
        if not waiting:
            continue
        names = ", ".join(r["customer"] for r in waiting[:3]) + (f" and {len(waiting) - 3} more"
                                                                 if len(waiting) > 3 else "")
        count = f"{len(waiting)} renewal{'s' if len(waiting) != 1 else ''}"
        bus.publish(business.id, "renewal.due", f"🔄 {count} coming up", names,
                    {"count": len(waiting), "ids": [r["id"] for r in waiting[:20]]})
        sent += 1
    return sent
