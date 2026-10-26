"""
Instant AI first reply (Task 29): a new WhatsApp / Instagram / Facebook enquiry
gets a polite reply within seconds, in the business's voice, even at night.

    reply_in_background   the webhook calls this for every NEW lead, right after
                          answering Meta "got it" (so Meta never waits for the AI)
    reply_to_new_lead     the rules, then the First Reply agent, then the outbox
    settings_for / update_settings / preview / recent   the Settings card

The owner chooses:
    off          never (the default: nothing is sent until the owner turns it on)
    always       every new enquiry, day and night
    after_hours  only when the business is closed (outside opening times / on closed days)

Rules (plain code, not the AI):
    - only a brand-new enquiry, only once, and never if someone already replied
    - only chat platforms we can actually reply on, and only if that account is
      connected (otherwise there's nothing to send through)
    - never on a paused plan; never for a message more than 2 hours old
      ("instant" hours later would look odd)
    - the AI's text is checked: money (₹, Rs, prices, discounts) or links → the
      safe ready-made reply goes out instead. The owner's note is always added.
    - the lead stays "new": a "thanks, we'll get back to you" isn't the owner's
      real reply, so the enquiry still shows as waiting (and reply time isn't faked)
"""

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.nodes.first_reply_agent import mock_first_reply, write_first_reply
from app.models import Business, Lead, Message
from app.services import billing_service, connection_service, lead_service, outbox
from app.services.event_bus import bus

logger = logging.getLogger("auto_reply")
IST = ZoneInfo("Asia/Kolkata")
MODES = ("off", "always", "after_hours")
CHANNELS = ("whatsapp", "instagram", "facebook")       # where we can reply inside the chat
MAX_AGE = timedelta(hours=2)
DEFAULTS = {"mode": "off", "opens": "09:00", "closes": "21:00", "closed_days": [], "note": ""}
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Money or links in an automatic message = risky (a wrong price, a strange link) → use the safe reply
RISKY = re.compile(
    r"₹|\b(rs|inr|rupees?)\.?\s*\d|\d[\d,]*\s*(/-|rs\b|rupees|inr\b)|\d+\s*%\s*off|\bdiscount|\bcashback"
    r"|https?://|www\.", re.IGNORECASE)

# The reply runs in the background with its own database session. Tests point this at the test database.
SESSION_FACTORY = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Opening hours
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    return {**DEFAULTS, **(business.auto_reply_settings or {})}


def _clock(text: str) -> time:
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def is_open(business: Business, now: datetime) -> bool:
    """Is the business open at this moment (India time)? Handles late-night hours like 6pm-2am."""
    s = settings_for(business)
    local = now.astimezone(IST)
    opens, closes, closed = _clock(s["opens"]), _clock(s["closes"]), set(s["closed_days"])
    t, today = local.time(), local.weekday()
    if opens < closes:                                              # e.g. 09:00-21:00
        return today not in closed and opens <= t < closes
    yesterday = (today - 1) % 7                                     # e.g. 18:00-02:00 (past midnight)
    return (t >= opens and today not in closed) or (t < closes and yesterday not in closed)


def _say_time(t: time) -> str:
    """09:00 → '9 am', 17:30 → '5:30 pm'."""
    hour = t.hour % 12 or 12
    return f"{hour}{f':{t.minute:02d}' if t.minute else ''} {'am' if t.hour < 12 else 'pm'}"


def back_at(business: Business, now: datetime) -> str:
    """When the team is next around, in words: 'at 9 am', 'tomorrow at 9 am', 'on Wednesday at 9 am'."""
    s = settings_for(business)
    local = now.astimezone(IST)
    opens, closed = _clock(s["opens"]), set(s["closed_days"])
    for days in range(8):
        day = local.date() + timedelta(days=days)
        moment = datetime.combine(day, opens, tzinfo=IST)
        if moment > local and day.weekday() not in closed:
            when = _say_time(opens)
            return (f"at {when}" if days == 0 else f"tomorrow at {when}" if days == 1
                    else f"on {DAY_NAMES[day.weekday()]} at {when}")
    return "soon"                                                   # closed every day: nothing better to say


# ---------------------------------------------------------------------------
# Writing the reply
# ---------------------------------------------------------------------------
def _profile(business: Business) -> dict:
    return {"name": business.name, "industry": business.industry, "services": business.services or [],
            "brand_voice": business.brand_voice or ""}


def compose(business: Business, message: str, customer_name: Optional[str], now: datetime) -> dict:
    """The reply text, plus how it was made. Never raises."""
    s = settings_for(business)
    open_now, when = is_open(business, now), back_at(business, now)
    note = (s["note"] or "").strip()
    args = (message, _profile(business), customer_name, open_now, when, note)
    try:
        result = write_first_reply(*args)
        text, ai_mode, checked = result.data.reply.strip(), result.mode, "ok"
    except Exception:  # noqa: BLE001 - the customer still gets the safe reply
        logger.exception("First Reply agent failed for business %s", business.id)
        text, ai_mode, checked = "", "fallback", "ai_error"
    if not text or RISKY.search(text.replace(note, "") if note else text):   # the owner's own note is fine
        if text:
            checked = "replaced"            # the AI mentioned money or a link: not sent automatically
        text = mock_first_reply(*args)["reply"]
    if note and note not in text:
        text = f"{text}\n{note}"
    return {"text": text[:1000], "open_now": open_now, "back_at": when, "ai_mode": ai_mode, "check": checked}


# ---------------------------------------------------------------------------
# The rules, then sending
# ---------------------------------------------------------------------------
def why_not(db: Session, business: Business, lead: Lead, now: datetime) -> Optional[str]:
    """None = go ahead. Otherwise the reason we're not replying (for the log)."""
    s = settings_for(business)
    if s["mode"] == "off":
        return "auto-reply is off"
    if lead.source not in CHANNELS:
        return f"can't reply inside {lead.source}"
    if any(m.direction == "outbound" for m in lead.messages):
        return "someone already replied"
    if s["mode"] == "after_hours" and is_open(business, now):
        return "business is open (after-hours mode)"
    inbound = [_utc(m.sent_at) for m in lead.messages if m.direction == "inbound"]
    if not inbound or now - min(inbound) > MAX_AGE:
        return "message is too old for an instant reply"
    if business.id in billing_service.paused_business_ids(db):
        return "plan ended"
    if connection_service.active(db, business.id, lead.source) is None:
        return f"{connection_service.LABELS[lead.source]} isn't connected"
    return None


def reply_to_new_lead(db: Session, lead_id: int, now: Optional[datetime] = None) -> Optional[Message]:
    """Send the instant first reply to one new lead, if the rules allow. Never raises:
    a problem here must never break saving the lead or the AI scoring that follows."""
    now = now or _now()
    try:
        lead = lead_service.get_lead(db, lead_id)
        if lead is None:
            return None
        business = db.get(Business, lead.business_id)
        reason = why_not(db, business, lead, now)
        if reason:
            logger.info("No auto-reply for lead %s: %s", lead_id, reason)
            return None
        said = [m.text for m in lead.messages if m.direction == "inbound"]
        made = compose(business, "\n".join(said) or lead.first_message or "", lead.name, now)
        delivery, problem, external_id = outbox.send_reply(db, lead, made["text"])
        if delivery == "logged":                       # not connected after all: nothing went out
            return None
        message = Message(direction="outbound", text=made["text"], delivery=delivery, delivery_error=problem,
                          external_id=external_id, auto_reply=True, sent_at=now)
        lead.messages.append(message)                  # status stays "new": the owner hasn't replied yet
        db.commit()
        who = lead.name or (f"@{lead.handle}" if lead.handle and not lead.handle.isdigit() else None) \
            or lead.phone or "a new customer"
        if delivery == "sent":
            bus.publish(lead.business_id, "lead.auto_reply", f"🤖 Replied instantly to {who}", made["text"][:140],
                        {"lead_id": lead.id})
        else:
            logger.warning("Auto-reply for lead %s not delivered: %s", lead_id, problem)
        return message
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Auto-reply failed for lead %s", lead_id)
        return None


def reply_in_background(lead_id: int) -> None:
    """Runs after the webhook has answered, with its own database session."""
    from app.services import lead_pipeline
    db = (SESSION_FACTORY or lead_pipeline.SESSION_FACTORY)()
    try:
        reply_to_new_lead(db, lead_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# The Settings card
# ---------------------------------------------------------------------------
def update_settings(db: Session, business: Business, changes: dict) -> Business:
    choices = settings_for(business)
    choices.update({k: v for k, v in changes.items() if k in DEFAULTS})
    if choices["opens"] == choices["closes"]:
        raise ValueError("Opening and closing time can't be the same")
    choices["closed_days"] = sorted(set(choices["closed_days"]))
    if len(choices["closed_days"]) == 7:
        raise ValueError("The business can't be closed on all 7 days")
    business.auto_reply_settings = choices
    db.commit()
    return business


def channels(db: Session, business_id: int) -> dict:
    """Which chat accounts are connected, so the card can say where replies go out."""
    return {p: connection_service.active(db, business_id, p) is not None for p in CHANNELS}


def preview(business: Business, message: str, now: Optional[datetime] = None) -> dict:
    return compose(business, message, None, now or _now())


def recent(db: Session, business_id: int, limit: int = 10) -> list[tuple[Message, Lead]]:
    rows = db.execute(select(Message, Lead).join(Lead)
                      .where(Lead.business_id == business_id, Message.auto_reply.is_(True))
                      .order_by(Message.id.desc()).limit(limit))
    return [(message, lead) for message, lead in rows]
