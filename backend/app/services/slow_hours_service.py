"""
Fill your empty hours (Task 33) - finds a business's quietest regular time
slots, and past customers worth inviting back to fill them.

Plain code finds the slow times and picks the customers (never guessed by
AI, same rule as everywhere in Lead Intel); agents/nodes/offer_agent.py (the
AI) only writes the invite message, and never mentions a price - the owner
adds that themselves when they edit and send it.

    slow_windows        this business's regular slow time slots ("Tuesday 2pm-5pm")
    candidates          past customers worth inviting back to fill them
    draft                the ready invite message for one customer + how to send it
    send / skip          record that we invited this customer (or chose to skip them),
                         so we don't keep suggesting the same person too often
    settings_for / update_settings   the Settings card
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.nodes.offer_agent import mock_offer, write_offer
from app.models import Business, Lead
from app.services.auto_reply_service import RISKY
from app.services.renewal_service import _aware, how_to_send

IST = ZoneInfo("Asia/Kolkata")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BLOCK_HOURS = 3           # each time slot is a 3-hour block: 12am-3am, 3am-6am, 6am-9am...
MIN_LEADS_NEEDED = 10     # below this, there isn't enough history yet to say anything useful
SLOW_THRESHOLD = 0.5      # a block counts as "slow" if it gets under half the business's own average
DEFAULTS = {"enabled": True, "min_days_since_won": 30}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _block_label(block: int) -> str:
    """Block 4 (3-hour blocks counted from midnight) -> '12pm-3pm'."""
    start, end = block * BLOCK_HOURS, (block + 1) * BLOCK_HOURS

    def clock(h: int) -> str:
        h = h % 24
        suffix = "am" if h < 12 else "pm"
        hour12 = h % 12
        hour12 = 12 if hour12 == 0 else hour12
        return f"{hour12}{suffix}"

    return f"{clock(start)}-{clock(end)}"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    saved = business.slow_hours_settings or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def update_settings(db: Session, business: Business, changes: dict) -> Business:
    if "min_days_since_won" in changes and not (7 <= changes["min_days_since_won"] <= 180):
        raise ValueError("min_days_since_won must be between 7 and 180")
    business.slow_hours_settings = {**(business.slow_hours_settings or {}),
                                    **{k: v for k, v in changes.items() if k in DEFAULTS}}
    db.commit()
    return business


# ---------------------------------------------------------------------------
# Finding the slow times
# ---------------------------------------------------------------------------
def slow_windows(db: Session, business: Business, weeks: int = 8,
                  now: Optional[datetime] = None) -> list[dict]:
    """This business's regular slow time slots: a 3-hour block, on a weekday,
    that gets noticeably fewer enquiries than the business usually gets.
    Only looks at hours the business is normally active in (so a block the
    business has never had an enquiry in is never flagged - it's probably
    just closed then, not "slow"). Returns up to 3 quietest, spread across
    different days where possible, or [] if there isn't enough history yet."""
    now = now or _now()
    since = now - timedelta(weeks=weeks)
    leads = list(db.scalars(
        select(Lead).where(Lead.business_id == business.id, Lead.created_at >= since)))
    if len(leads) < MIN_LEADS_NEEDED:
        return []

    counts = Counter()
    for lead in leads:
        local = _aware(lead.created_at).astimezone(IST)
        counts[(local.weekday(), local.hour // BLOCK_HOURS)] += 1

    active_blocks = {block for _, block in counts}   # blocks this business has EVER had an enquiry in
    slots = len(active_blocks) * 7
    if not slots:
        return []
    average = len(leads) / slots

    slow = []
    for day in range(7):
        for block in active_blocks:
            n = counts.get((day, block), 0)
            if n < average * SLOW_THRESHOLD:
                slow.append({
                    "weekday": day, "day": DAY_NAMES[day], "hours": _block_label(block),
                    "enquiries": n, "usual": round(average, 1),
                })
    slow.sort(key=lambda w: w["enquiries"])   # quietest first

    # Prefer spreading the picks across different days, rather than showing
    # "Monday 9am, Monday 3pm, Monday 9pm" just because Monday happens to be
    # quietest everywhere. Only repeats a day if there aren't 3 different ones.
    chosen, seen_days = [], set()
    for w in slow:
        if w["weekday"] in seen_days:
            continue
        chosen.append(w)
        seen_days.add(w["weekday"])
        if len(chosen) == 3:
            return chosen
    for w in slow:
        if w not in chosen:
            chosen.append(w)
            if len(chosen) == 3:
                break
    return chosen


# ---------------------------------------------------------------------------
# Finding past customers to invite
# ---------------------------------------------------------------------------
def candidates(db: Session, business: Business, limit: int = 10,
               now: Optional[datetime] = None) -> list[dict]:
    """Past customers worth inviting back: they've bought from us before, it's
    been long enough that a new visit is a real win (not a pointless repeat
    message to someone who was just here), and we haven't already invited
    them back recently."""
    now = now or _now()
    settings = settings_for(business)
    if not settings["enabled"]:
        return []
    cooldown = timedelta(days=settings["min_days_since_won"])
    leads = list(db.scalars(
        select(Lead).where(Lead.business_id == business.id, Lead.status == "won",
                            Lead.won_at.isnot(None))
        .order_by(Lead.won_at.desc())))

    out = []
    for lead in leads:
        if _aware(lead.won_at) > now - cooldown:
            continue   # bought too recently - inviting them back now would feel pushy
        if lead.last_slow_offer_at and _aware(lead.last_slow_offer_at) > now - cooldown:
            continue   # we already invited them back recently
        out.append({
            "lead_id": lead.id, "name": lead.name, "phone": lead.phone,
            "area": lead.area, "service": lead.service,
            "last_bought": lead.won_at.date().isoformat(),
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# The ready message and how to send it
# ---------------------------------------------------------------------------
def draft(db: Session, lead: Lead, window: dict) -> dict:
    """The ready invite message for one customer, for one slow time slot,
    plus how it can be sent."""
    business = db.get(Business, lead.business_id)
    profile = {"name": business.name, "industry": business.industry,
               "services": business.services or [], "brand_voice": business.brand_voice or ""}
    try:
        result = write_offer(profile, lead.name, lead.service, window["day"], window["hours"])
        text, ai_mode, check = result.data.message.strip(), result.mode, "ok"
    except Exception:  # noqa: BLE001
        text, ai_mode, check = "", "fallback", "ai_error"
    if not text or RISKY.search(text):
        if text:
            check = "replaced"
        text = mock_offer(profile, lead.name, lead.service, window["day"], window["hours"])["message"]
    return {"text": text[:1000], "ai_mode": ai_mode, "check": check, **how_to_send(lead)}


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def send(db: Session, lead: Lead, now: Optional[datetime] = None) -> Lead:
    """Record that the owner sent this customer the invite (from their phone)."""
    lead.last_slow_offer_at = now or _now()
    db.commit()
    return lead


def skip(db: Session, lead: Lead, now: Optional[datetime] = None) -> Lead:
    """Record that the owner chose NOT to invite this customer right now, so
    they stop being suggested for a while (same cooldown as a real invite)."""
    lead.last_slow_offer_at = now or _now()
    db.commit()
    return lead
