"""
Follow-up reminders (Task 30): "Rahul asked about Zumba 2 days ago and got no
follow-up". The dashboard lists the enquiries that have gone quiet, with a
ready message the owner can send in one tap. Most sales are lost simply because
nobody followed up.

    due              the enquiries that need a follow-up now (plain rules, below)
    check_lead       the same answer for one lead (the lead drawer)
    draft            the ready message (the Follow-up agent), and how it can be sent
    send             record the follow-up: sent through the connected account, or
                     "sent from my phone" (the owner tapped "Open WhatsApp")
    snooze / stop    "remind me later" / "stop reminding me about this one"
    daily_reminders  scheduler job: once a day (after 10am India time) a live-feed
                     note "📋 3 enquiries need a follow-up today"
    settings_for / update_settings   the Settings card

When does an enquiry need a follow-up? (plain code, not the AI)
    - it's still open: new, contacted or quoted (not booked, won or lost)
    - nothing has happened for `after_days` days (the owner picks 1, 2, 3, 5 or 7; default 2)
    - at most 2 follow-ups since the customer last wrote: after that we stop, no nagging
    - not snoozed, not stopped; and not quiet for more than 14 days (that one's gone cold)
    - the instant AI reply (Task 29) doesn't count as a reply: a person still has to answer
    - when the customer writes again, everything starts fresh (lead_service.receive_message)

Three situations, each with its own wording:
    no_reply    the customer wrote, nobody has replied yet
    waiting     the customer wrote again after your reply, and is waiting for you
    gone_quiet  you replied (or called), the customer hasn't answered

How it can be sent (the platforms' 24-hour rule: see outbox.py):
    app        WhatsApp/Instagram/Facebook connected and the customer wrote in the last 24 hours:
               sent straight from the dashboard
    whatsapp   we have their phone number: "Open WhatsApp" opens a chat on the owner's phone with
               the message already typed (works any time, costs nothing)
    instagram  only their Instagram username: copy the message, open their chat
    copy       nothing else: copy the message (or call them)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.nodes.followup_agent import mock_follow_up, write_follow_up
from app.models import Business, Lead, Message
from app.platforms import PLATFORMS
from app.schemas import MessageCreate
from app.services import billing_service, connection_service, lead_service, outbox
from app.services.auto_reply_service import RISKY
from app.services.event_bus import bus

logger = logging.getLogger("followups")
IST = ZoneInfo("Asia/Kolkata")
OPEN_STATUSES = ("new", "contacted", "quoted")
AFTER_DAYS = (1, 2, 3, 5, 7)
MAX_FOLLOWUPS = 2                     # follow-ups since the customer last wrote, then we stop
TOO_OLD = timedelta(days=14)          # quiet for longer than this = gone cold, not worth a reminder
REMIND_FROM_HOUR = 10                 # the daily note comes after 10am India time
DEFAULTS = {"enabled": True, "after_days": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    saved = business.followup_settings or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def update_settings(db: Session, business: Business, changes: dict) -> Business:
    if "after_days" in changes and changes["after_days"] not in AFTER_DAYS:
        raise ValueError(f"after_days must be one of {', '.join(map(str, AFTER_DAYS))}")
    # a new dict (not an edit of the old one) so the database notices the change
    business.followup_settings = {**(business.followup_settings or {}),
                                  **{k: v for k, v in changes.items() if k in DEFAULTS}}
    db.commit()
    return business


# ---------------------------------------------------------------------------
# Who needs a follow-up?
# ---------------------------------------------------------------------------
def _ago(days: int) -> str:
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def who(lead: Lead) -> str:
    return lead.name or lead.phone or (f"@{lead.handle}" if lead.handle and not lead.handle.isdigit() else None) \
        or "A customer"


def _situation(lead: Lead) -> Optional[dict]:
    """Where the conversation stands, from the messages: the situation, since when, and how many
    follow-ups have gone out since the customer last wrote. None = nothing to follow up."""
    messages = sorted(lead.messages, key=lambda m: _utc(m.sent_at))
    inbound = [m for m in messages if m.direction == "inbound"]
    people = [m for m in messages if m.direction == "outbound" and not m.auto_reply and m.delivery != "failed"]
    last_in = _utc(inbound[-1].sent_at) if inbound else _utc(lead.created_at)
    last_out = _utc(people[-1].sent_at) if people else None
    sent = sum(1 for m in people if m.followup and _utc(m.sent_at) >= last_in)

    if last_out and last_out >= last_in:                      # we spoke last: the customer went quiet
        return {"kind": "gone_quiet", "since": last_out, "sent": sent}
    if last_out:                                              # they wrote after our reply
        return {"kind": "waiting", "since": last_in, "sent": 0}
    if lead.first_response_at:                                # no reply typed here, but they were called / met
        return {"kind": "gone_quiet", "since": max(_utc(lead.first_response_at), last_in), "sent": 0}
    return {"kind": "no_reply", "since": last_in, "sent": 0}


def _reason(lead: Lead, kind: str, days: int, sent: int) -> str:
    """The line under the customer's name: why this reminder is showing."""
    wanted = f"about {lead.service}" if lead.service else "an enquiry"
    if kind == "no_reply":
        text = f"Asked {wanted} {_ago(days)}. No reply yet."
    elif kind == "waiting":
        text = f"Wrote back {_ago(days)}. Still waiting for your answer."
    else:
        text = f"You replied {_ago(days)}. No answer since."
    if sent:
        text += f" {sent} follow-up already sent." if sent == 1 else f" {sent} follow-ups already sent."
    return text


def check_lead(lead: Lead, business: Business, now: Optional[datetime] = None,
               ignore_snooze: bool = False) -> Optional[dict]:
    """None if this lead doesn't need a follow-up right now, else the reminder."""
    now = now or _now()
    if lead.status not in OPEN_STATUSES or lead.followup_stopped:
        return None
    snoozed = _utc(lead.followup_snoozed_until)
    if snoozed and snoozed > now and not ignore_snooze:
        return None
    where = _situation(lead)
    if where is None or where["sent"] >= MAX_FOLLOWUPS:
        return None
    quiet = now - where["since"]
    if quiet < timedelta(days=settings_for(business)["after_days"]) or quiet > TOO_OLD:
        return None
    days = quiet.days
    score = lead.analysis.score if lead.analysis else None
    return {"lead_id": lead.id, "customer": who(lead), "source": lead.source,
            "source_name": PLATFORMS[lead.source].name if lead.source in PLATFORMS else lead.source,
            "service": lead.service, "status": lead.status, "score": score,
            "priority": lead.analysis.priority if lead.analysis else "normal",
            "kind": where["kind"], "since": where["since"], "days": days, "followups_sent": where["sent"],
            "reason": _reason(lead, where["kind"], days, where["sent"])}


def _open_leads(db: Session, business_id: int, now: datetime) -> list[Lead]:
    return list(db.scalars(
        select(Lead).options(selectinload(Lead.messages), selectinload(Lead.analysis))
        .where(Lead.business_id == business_id, Lead.status.in_(OPEN_STATUSES), Lead.followup_stopped.is_(False),
               Lead.created_at >= now - timedelta(days=90))))


def due(db: Session, business: Business, now: Optional[datetime] = None) -> list[dict]:
    """Every enquiry that needs a follow-up now: hot ones first, then higher scores, then the freshest
    (a customer who went quiet 2 days ago is warmer than one from 2 weeks ago)."""
    now = now or _now()
    if not settings_for(business)["enabled"]:
        return []
    found = [r for lead in _open_leads(db, business.id, now) if (r := check_lead(lead, business, now))]
    return sorted(found, key=lambda r: (r["priority"] != "hot", -((r["score"] or 0) // 10), -r["since"].timestamp()))


# ---------------------------------------------------------------------------
# The ready message, and how it can go out
# ---------------------------------------------------------------------------
def _wa_number(phone: Optional[str]) -> Optional[str]:
    """A phone number as WhatsApp links want it: digits with the country code (India = 91)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits if 11 <= len(digits) <= 15 else None


def how_to_send(db: Session, lead: Lead, now: Optional[datetime] = None) -> dict:
    """{"how": app / whatsapp / instagram / copy, "link": ..., "note": what the owner should know}"""
    now = now or _now()
    platform = lead.source if lead.source in outbox.CHAT_PLATFORMS else None
    if platform and connection_service.active(db, lead.business_id, platform) is not None:
        last = outbox._last_customer_message(lead)
        to = lead.phone if platform == "whatsapp" else lead.handle
        if to and last and now - last <= timedelta(hours=24):
            label = connection_service.LABELS[platform]
            return {"how": "app", "link": None, "note": f"Goes out from your connected {label}."}
    number = _wa_number(lead.phone)
    if number:
        note = ("Opens WhatsApp on your phone with the message ready: just press send."
                if lead.source != "whatsapp" else
                "It's been over 24 hours since they wrote, so WhatsApp only lets you message them from your own "
                "phone. This opens the chat with the message ready: just press send.")
        return {"how": "whatsapp", "link": f"https://wa.me/{number}", "note": note}
    if lead.handle and lead.source == "instagram" and not lead.handle.isdigit():
        return {"how": "instagram", "link": f"https://ig.me/m/{quote(lead.handle)}",
                "note": "Copy the message, then open their Instagram chat and paste it."}
    return {"how": "copy", "link": None,
            "note": "We don't have a number or chat for this customer: copy the message, or call them."}


def draft(db: Session, lead: Lead, reminder: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    """The ready message for one lead, plus how it can be sent. Never raises."""
    now = now or _now()
    business = db.get(Business, lead.business_id)
    reminder = reminder or check_lead(lead, business, now, ignore_snooze=True)
    where = _situation(lead) or {"kind": "gone_quiet", "since": now, "sent": 0}
    kind = reminder["kind"] if reminder else where["kind"]
    nth = (reminder["followups_sent"] if reminder else where["sent"]) + 1
    days = (now - where["since"]).days
    asked = next((m.text for m in sorted(lead.messages, key=lambda m: _utc(m.sent_at), reverse=True)
                  if m.direction == "inbound"), lead.first_message or "")
    profile = {"name": business.name, "industry": business.industry, "services": business.services or [],
               "brand_voice": business.brand_voice or ""}
    args = (profile, lead.name, asked, lead.service, kind, nth)
    try:
        result = write_follow_up(*args, days)
        text, ai_mode, check = result.data.message.strip(), result.mode, "ok"
    except Exception:  # noqa: BLE001 - the owner still gets the ready-made message
        logger.exception("Follow-up agent failed for lead %s", lead.id)
        text, ai_mode, check = "", "fallback", "ai_error"
    if not text or RISKY.search(text):
        if text:
            check = "replaced"            # the AI mentioned money or a link: use the safe message instead
        text = mock_follow_up(*args)["message"]
    return {"text": text[:1000], "kind": kind, "nth": nth, "ai_mode": ai_mode, "check": check,
            **how_to_send(db, lead, now)}


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def send(db: Session, lead: Lead, text: str, via: str, now: Optional[datetime] = None) -> Message:
    """via = "app" (send through the connected account) or "phone" (the owner sent it from their own
    phone, e.g. after "Open WhatsApp"). Like any reply, a new lead moves to "contacted"."""
    now = now or _now()
    if via == "app":
        delivery, problem, external_id = outbox.send_reply(db, lead, text)
        if delivery == "logged":                       # not connected: nothing went out
            raise ValueError(problem or "This customer can't be messaged from here. Use Open WhatsApp or call them.")
    else:
        delivery, problem, external_id = "logged", "", None
    message = lead_service.add_message(db, lead, MessageCreate(direction="outbound", text=text, send=via == "app"),
                                       delivery, problem, external_id)
    message.followup = True
    message.sent_at = now
    if delivery != "failed":
        lead.followup_snoozed_until = None
    db.commit()
    return message


def snooze(db: Session, lead: Lead, days: int, now: Optional[datetime] = None) -> Lead:
    lead.followup_snoozed_until = (now or _now()) + timedelta(days=days)
    db.commit()
    return lead


def stop(db: Session, lead: Lead) -> Lead:
    lead.followup_stopped = True
    db.commit()
    return lead


# ---------------------------------------------------------------------------
# The daily note (scheduler)
# ---------------------------------------------------------------------------
def daily_reminders(db: Session, now: Optional[datetime] = None) -> int:
    """Once a day per business, after 10am India time: '📋 3 enquiries need a follow-up today'
    on the live feed. Returns how many notes were sent."""
    now = now or _now()
    local = now.astimezone(IST)
    if local.hour < REMIND_FROM_HOUR:
        return 0
    today = local.date().isoformat()
    paused, sent = None, 0
    for business in db.scalars(select(Business)):
        saved = business.followup_settings or {}
        if saved.get("reminded_on") == today or not settings_for(business)["enabled"]:
            continue
        if paused is None:
            paused = billing_service.paused_business_ids(db)
        business.followup_settings = {**saved, "reminded_on": today}     # once a day, even if none are due
        db.commit()
        if business.id in paused:
            continue
        waiting = due(db, business, now)
        if not waiting:
            continue
        names = ", ".join(r["customer"] for r in waiting[:3]) + (f" and {len(waiting) - 3} more"
                                                                 if len(waiting) > 3 else "")
        count = f"{len(waiting)} enquir{'y needs' if len(waiting) == 1 else 'ies need'}"
        bus.publish(business.id, "followup.due", f"📋 {count} a follow-up today", names,
                    {"count": len(waiting), "lead_ids": [r["lead_id"] for r in waiting[:20]]})
        sent += 1
    return sent
