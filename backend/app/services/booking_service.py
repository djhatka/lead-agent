"""
Booking slots inside WhatsApp (Task 37): "Pick a time for your personal training session"
instead of a back-and-forth over chat.

The owner picks working hours once (Settings → Bookings). For one customer, the owner
creates a booking and sends them a link (mirrors Payments: /pay/<token> → /book/<token>).
The customer opens the link, sees the free slots for the next few days, and taps one -
no login, no app. Nothing is double-booked: a slot already taken by a confirmed booking
for this business doesn't show up for the next customer.

    settings_for / update_settings   the owner's working hours and slot length
    create              a new booking (from an enquiry, or typed in for a walk-in)
    request_message     "Pick a time for your session..." (ready to send)
    available_slots      the free times a customer can pick, for the next few days
    choose_slot          the customer picked one: pending → confirmed
    cancel                owner cancels it (or the customer never picked a slot)
    send                 record it: sent through the connected chat, or "sent from my phone"
    listing              the Bookings page: waiting for a slot, confirmed and upcoming, past
"""

import logging
import secrets
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Booking, Business, Lead, Message
from app.schemas import MessageCreate
from app.services import followup_service, lead_service, outbox
from app.services.event_bus import bus

logger = logging.getLogger("bookings")
IST = ZoneInfo("Asia/Kolkata")
SLOT_MINUTES = (15, 20, 30, 45, 60)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULTS = {"slot_minutes": 30, "days_ahead": 7, "start_hour": 10, "end_hour": 19, "closed_weekdays": []}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops timezone info on the way back out of the database even for a
    DateTime(timezone=True) column, so a value that round-tripped through it can come
    back naive while _now() stays aware. Treat a naive value as UTC before any
    subtraction or comparison, the same way dues_service.py and competitor_service.py do."""
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def say_when(slot: datetime) -> str:
    """A customer-friendly way to say a slot: 'Mon 2 Nov, 4:00 PM'."""
    local = slot.astimezone(IST)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{DAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {hour12}:{local.minute:02d} {ampm}"


# ---------------------------------------------------------------------------
# Settings: the owner's working hours
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    saved = business.booking_settings or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def update_settings(db: Session, business: Business, changes: dict) -> Business:
    changes = {k: v for k, v in changes.items() if k in DEFAULTS}
    if "slot_minutes" in changes and changes["slot_minutes"] not in SLOT_MINUTES:
        raise ValueError(f"Slot length must be one of: {', '.join(str(m) for m in SLOT_MINUTES)} minutes")
    if "days_ahead" in changes and not 0 <= changes["days_ahead"] <= 30:
        raise ValueError("Days ahead must be between 0 (today only) and 30")
    merged = {**settings_for(business), **changes}
    if "start_hour" in changes or "end_hour" in changes:
        if not 0 <= merged["start_hour"] < merged["end_hour"] <= 24:
            raise ValueError("Opening hours must run from an earlier hour to a later one, within one day")
    if "closed_weekdays" in changes:
        days = changes["closed_weekdays"] or []
        if not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
            raise ValueError("closed_weekdays must be numbers 0 (Monday) to 6 (Sunday)")
        changes["closed_weekdays"] = sorted(set(days))
    business.booking_settings = {**(business.booking_settings or {}), **changes}   # a new dict: the database notices
    db.commit()
    return business


# ---------------------------------------------------------------------------
# One booking
# ---------------------------------------------------------------------------
def book_url(booking: Booking) -> str:
    return f"{settings.public_api_url.rstrip('/')}/book/{booking.token}"


def create(db: Session, business: Business, *, service: str, lead: Optional[Lead] = None,
           customer_name: str = "", phone: str = "") -> Booking:
    service = (service or "").strip()
    name = (customer_name or "").strip() or (lead.name if lead else "") or (lead.phone if lead else "") or ""
    if not service or not name:
        raise ValueError("Add the customer's name and what they're booking")
    booking = Booking(business_id=business.id, lead_id=lead.id if lead else None, customer_name=name[:100],
                      phone=((phone or "").strip() or (lead.phone if lead else None) or None), service=service[:150],
                      duration_minutes=settings_for(business)["slot_minutes"], token=secrets.token_urlsafe(12))
    db.add(booking)
    db.commit()
    return booking


def _hinglish(business: Business) -> bool:
    return "hinglish" in (business.brand_voice or "").lower() or "hindi" in (business.brand_voice or "").lower()


TITLES = {"mr", "mrs", "ms", "miss", "dr", "shri", "smt", "sri"}


def _first(booking: Booking) -> str:
    """How to greet them: 'Rahul Sharma' → 'Rahul', 'Mr Verma' → 'Mr Verma', a phone number → ''."""
    words = (booking.customer_name or "").strip().split()
    if not words or words[0].lstrip("+").isdigit():
        return ""
    if words[0].lower().rstrip(".") in TITLES and len(words) > 1:
        return f"{words[0].title()} {words[-1].title()}"
    return words[0].title()


def request_message(business: Business, booking: Booking) -> str:
    first, url = _first(booking), book_url(booking)
    hello = f"Hi {first}!" if first else "Hi!"
    if _hinglish(business):
        return (f"{hello} {business.name} ki taraf se {booking.service} ke liye ek time choose kar lijiye:\n{url}\n"
                f"Jo time aapko suit kare, bas tap kar dein. Thank you 🙏")
    return (f"{hello} Please pick a time for your {booking.service} at {business.name}:\n{url}\n"
            f"Just tap the time that works for you. Thank you 🙏")


def confirmation_message(business: Business, booking: Booking) -> str:
    first = _first(booking)
    hello = f"Hi {first}," if first else "Hi,"
    when = say_when(_utc(booking.slot_at))
    if _hinglish(business):
        return f"{hello} aapka {booking.service} {when} ke liye confirm ho gaya hai. Milte hain! 🙏"
    return f"{hello} you're booked in for {booking.service} on {when}. See you then! 🙏"


def how_to_send(db: Session, booking: Booking, lead: Optional[Lead] = None, now: Optional[datetime] = None) -> dict:
    """Same choices as follow-ups and payments: app (inside WhatsApp's 24 hours) / whatsapp
    (own phone) / instagram / copy."""
    lead = lead or (db.get(Lead, booking.lead_id) if booking.lead_id else None)
    if lead is not None:
        way = followup_service.how_to_send(db, lead, now)
        if way["how"] != "copy" or not booking.phone:
            return way
    number = followup_service._wa_number(booking.phone)
    if number:
        return {"how": "whatsapp", "link": f"https://wa.me/{number}",
                "note": "Opens WhatsApp on your phone with the message ready: just press send."}
    return {"how": "copy", "link": None, "note": "We don't have a number for this customer: copy the message."}


def send(db: Session, booking: Booking, text: str, via: str, now: Optional[datetime] = None) -> dict:
    """via = "app" (through the connected chat, needs an enquiry) or "phone" (sent from the
    owner's phone). Returns {"delivery", "delivery_error"}."""
    now = now or _now()
    lead = db.get(Lead, booking.lead_id) if booking.lead_id else None
    if via == "app":
        if lead is None:
            raise ValueError("This booking isn't linked to a chat. Use Open WhatsApp instead.")
        delivery, problem, external_id = outbox.send_reply(db, lead, text)
        if delivery == "logged":
            raise ValueError(problem or "This customer can't be messaged from here. Use Open WhatsApp instead.")
    else:
        delivery, problem, external_id = "logged", "", None
    if lead is not None:
        lead_service.add_message(db, lead, MessageCreate(direction="outbound", text=text, send=via == "app"),
                                 delivery, problem, external_id)
    return {"delivery": delivery, "delivery_error": problem}


# ---------------------------------------------------------------------------
# Picking a slot
# ---------------------------------------------------------------------------
def available_slots(db: Session, business: Business, booking: Booking, now: Optional[datetime] = None) -> list[datetime]:
    """The free times a customer can pick for this booking, for the next `days_ahead` days,
    within working hours, skipping closed weekdays, the past, and any time already taken by
    a confirmed booking for this business (any duration overlap counts as taken)."""
    now = now or _now()
    s = settings_for(business)
    length = timedelta(minutes=booking.duration_minutes or s["slot_minutes"])
    taken: list[tuple[datetime, datetime]] = []
    for other in db.scalars(select(Booking).where(Booking.business_id == business.id, Booking.status == "confirmed",
                                                   Booking.id != booking.id, Booking.slot_at.is_not(None))):
        start = _utc(other.slot_at)
        taken.append((start, start + timedelta(minutes=other.duration_minutes or s["slot_minutes"])))

    slots: list[datetime] = []
    today = now.astimezone(IST).date()
    for day_offset in range(s["days_ahead"] + 1):
        day = today + timedelta(days=day_offset)
        if day.weekday() in s["closed_weekdays"]:
            continue
        start_of_day = datetime.combine(day, time(s["start_hour"], 0), tzinfo=IST)
        end_of_day = datetime.combine(day, time(s["end_hour"], 0), tzinfo=IST)
        slot = start_of_day
        while slot + length <= end_of_day:
            slot_utc = slot.astimezone(timezone.utc)
            if slot_utc > now and not any(slot_utc < t_end and slot_utc + length > t_start for t_start, t_end in taken):
                slots.append(slot_utc)
            slot += timedelta(minutes=s["slot_minutes"])
    return slots


def choose_slot(db: Session, business: Business, booking: Booking, slot_at: datetime,
                now: Optional[datetime] = None) -> Booking:
    if booking.status != "pending":
        raise ValueError("This booking isn't waiting for a time any more")
    slot_at = _utc(slot_at)
    if slot_at not in available_slots(db, business, booking, now):
        raise ValueError("That time isn't available any more. Please pick another one.")
    booking.slot_at = slot_at
    booking.status = "confirmed"
    booking.confirmed_at = now or _now()
    db.commit()
    bus.publish(booking.business_id, "booking.confirmed",
               f"📅 {booking.customer_name} booked {booking.service} for {say_when(slot_at)}",
               "", {"booking_id": booking.id, "lead_id": booking.lead_id})
    return booking


def cancel(db: Session, booking: Booking) -> Booking:
    if booking.status == "cancelled":
        raise ValueError("This booking is already cancelled")
    booking.status = "cancelled"
    booking.cancelled_at = _now()
    db.commit()
    return booking


# ---------------------------------------------------------------------------
# The Bookings page
# ---------------------------------------------------------------------------
def listing(db: Session, business_id: int, status: str = "pending", lead_id: Optional[int] = None) -> list[Booking]:
    query = select(Booking).where(Booking.business_id == business_id)
    if status != "all":
        query = query.where(Booking.status == status)
    if lead_id is not None:
        query = query.where(Booking.lead_id == lead_id)
    bookings = list(db.scalars(query.order_by(Booking.id.desc()).limit(300)))
    if status == "confirmed":
        far = datetime.max.replace(tzinfo=timezone.utc)
        bookings.sort(key=lambda b: _utc(b.slot_at) or far)        # soonest first
    return bookings
