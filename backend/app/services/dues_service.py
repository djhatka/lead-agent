"""
Payments and dues (Task 31): "₹2,000 advance for ceramic coating", "October membership fee".

The money goes STRAIGHT to the owner: every due gets a small payment page
(/pay/<token>, app/site/routes.py) with a "Pay with any UPI app" button and a
QR code for the owner's own UPI ID. Lead Intel never holds anyone's money
(collecting for others would need an RBI payment-aggregator licence). Later,
owners with their own Razorpay account can get automatic links through the
Razorpay Partner program (see the go-live guide); until then the owner confirms
each payment with one tap, and the customer can press "I've paid" to tell them.

    create               a new due (from an enquiry, or typed in for a walk-in)
    request_message      "Here's the payment link for ₹2,000 ..." (ready to send)
    reminder_message     "A gentle reminder: ₹2,000 ... is due today" (ready to send)
    send                 record it: sent through the connected chat, or "sent from my phone"
    mark_paid / cancel / reopen
    customer_says_paid   the customer pressed "I've paid" on the payment page
    listing / summary    the Payments page: "₹ recovered this month", what's waiting, what's overdue
    send_due_reminders   scheduler job: polite automatic WhatsApp reminders (if the owner turned them on)

Automatic reminders (plain rules, off until the owner turns them on):
    - only dues with a due date and a phone number, and only 10am-8pm India time
    - on the due date, then 3 days later, then 7 days later: 3 at most, at least 2 days apart
    - never after the customer pressed "I've paid", never on a paused plan
    - sent with an approved WhatsApp template (businesses can only start a chat that way);
      without a real WhatsApp connection they run in practice mode (recorded, not delivered)
"""

import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Business, Due, Lead, Message
from app.schemas import MessageCreate
from app.services import billing_service, followup_service, lead_service, outbox
from app.services.event_bus import bus
from app.services.messenger import MockMessenger, SendError, get_messenger

logger = logging.getLogger("dues")
IST = ZoneInfo("Asia/Kolkata")
UPI_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-_]{1,255}@[a-zA-Z][a-zA-Z0-9]{1,63}$")   # name@bank, e.g. ironpulse@okaxis
MAX_AMOUNT = 1_000_000                       # ₹10 lakh: a bigger number is almost certainly a typo
PAID_VIA = ("upi", "cash", "card", "bank", "other")
REMIND_ON = (0, 3, 7)                        # reminder 1, 2, 3: this many days after the due date
REMIND_GAP = timedelta(days=2)               # at least this long between two reminders
REMIND_HOURS = (10, 20)                      # 10am to 8pm India time
DEFAULTS = {"upi_id": "", "payee_name": "", "auto_reminders": False}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def _today(now: datetime) -> date:
    return now.astimezone(IST).date()


def inr(amount: int) -> str:
    """2000 → '₹2,000', 150000 → '₹1,50,000' (Indian grouping)."""
    digits = str(int(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        digits = f"{head},{tail}"
    return f"₹{digits}"


def say_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


# ---------------------------------------------------------------------------
# Settings: the owner's UPI ID
# ---------------------------------------------------------------------------
def settings_for(business: Business) -> dict:
    saved = business.payment_settings or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def payee(business: Business) -> str:
    """The name customers see on the payment page and in their UPI app."""
    return settings_for(business)["payee_name"] or business.name


def update_settings(db: Session, business: Business, changes: dict) -> Business:
    changes = {k: v for k, v in changes.items() if k in DEFAULTS}
    if "upi_id" in changes:
        changes["upi_id"] = (changes["upi_id"] or "").strip()
        if changes["upi_id"] and not UPI_ID.match(changes["upi_id"]):
            raise ValueError("That doesn't look like a UPI ID. It looks like name@bank, e.g. ironpulse@okaxis")
    if "payee_name" in changes:
        changes["payee_name"] = (changes["payee_name"] or "").strip()[:60]
    business.payment_settings = {**(business.payment_settings or {}), **changes}   # a new dict: the database notices
    db.commit()
    return business


# ---------------------------------------------------------------------------
# One due
# ---------------------------------------------------------------------------
def pay_url(due: Due) -> str:
    return f"{settings.public_api_url.rstrip('/')}/pay/{due.token}"


def upi_link(business: Business, due: Due) -> str:
    """Opens any UPI app (GPay, PhonePe, Paytm, BHIM...) with the owner's UPI ID and the amount filled in."""
    params = {"pa": settings_for(business)["upi_id"], "pn": payee(business)[:50], "am": f"{due.amount}.00",
              "cu": "INR", "tn": due.purpose[:50]}
    return "upi://pay?" + urlencode(params, quote_via=quote, safe="@")


def state(due: Due, now: Optional[datetime] = None) -> dict:
    """Where a due stands, in words: {"label": "Overdue by 3 days", "overdue_days": 3}."""
    now = now or _now()
    if due.status == "paid":
        return {"label": f"Paid on {say_date(_utc(due.paid_at).astimezone(IST).date())}", "overdue_days": 0}
    if due.status == "cancelled":
        return {"label": "Cancelled", "overdue_days": 0}
    if due.due_date is None:
        return {"label": "Waiting for payment", "overdue_days": 0}
    days = (_today(now) - due.due_date).days
    if days > 0:
        return {"label": f"Overdue by {days} day{'s' if days != 1 else ''}", "overdue_days": days}
    if days == 0:
        return {"label": "Due today", "overdue_days": 0}
    return {"label": "Due tomorrow" if days == -1 else f"Due {say_date(due.due_date)}", "overdue_days": 0}


def create(db: Session, business: Business, *, amount: int, purpose: str, lead: Optional[Lead] = None,
           customer_name: str = "", phone: str = "", due_date: Optional[date] = None,
           auto_remind: bool = True) -> Due:
    if not settings_for(business)["upi_id"]:
        raise ValueError("Add your UPI ID first (Settings → Payments), so customers know where to pay")
    if not 1 <= amount <= MAX_AMOUNT:
        raise ValueError(f"The amount must be between ₹1 and {inr(MAX_AMOUNT)}")
    purpose = purpose.strip()
    name = (customer_name or "").strip() or (lead.name if lead else "") or (lead.phone if lead else "") or ""
    if not purpose or not name:
        raise ValueError("Add the customer's name and what the payment is for")
    due = Due(business_id=business.id, lead_id=lead.id if lead else None, customer_name=name[:100],
              phone=((phone or "").strip() or (lead.phone if lead else None) or None), amount=amount,
              purpose=purpose[:200], due_date=due_date, auto_remind=auto_remind, token=secrets.token_urlsafe(12))
    db.add(due)
    db.commit()
    return due


# ---------------------------------------------------------------------------
# The ready messages (plain text: money is a fact, the AI doesn't write it)
# ---------------------------------------------------------------------------
def _hinglish(business: Business) -> bool:
    return "hinglish" in (business.brand_voice or "").lower() or "hindi" in (business.brand_voice or "").lower()


TITLES = {"mr", "mrs", "ms", "miss", "dr", "shri", "smt", "sri"}


def _first(due: Due) -> str:
    """How to greet them: 'Rahul Sharma' → 'Rahul', 'Mr Verma' → 'Mr Verma', a phone number → ''."""
    words = (due.customer_name or "").strip().split()
    if not words or words[0].lstrip("+").isdigit():
        return ""
    if words[0].lower().rstrip(".") in TITLES and len(words) > 1:
        return f"{words[0].title()} {words[-1].title()}"
    return words[0].title()


def request_message(business: Business, due: Due) -> str:
    first, amount, url = _first(due), inr(due.amount), pay_url(due)
    hello = f"Hi {first}!" if first else "Hi!"
    if _hinglish(business):
        return (f"{hello} {payee(business)} ki taraf se {due.purpose} ke liye {amount} ka payment link:\n{url}\n"
                f"GPay, PhonePe, Paytm ya kisi bhi UPI app se pay kar sakte hain. Thank you 🙏")
    return (f"{hello} Here's the payment link for {amount} ({due.purpose}) at {payee(business)}:\n{url}\n"
            f"You can pay with GPay, PhonePe, Paytm or any UPI app. Thank you 🙏")


def _when(due: Due, now: datetime, hinglish: bool) -> str:
    if due.due_date is None:
        return "pending hain" if hinglish else "is pending"
    days = (_today(now) - due.due_date).days
    if days == 0:
        return "aaj due hain" if hinglish else "is due today"
    if days > 0:
        return f"{say_date(due.due_date)} ko due the" if hinglish else f"was due on {say_date(due.due_date)}"
    return f"{say_date(due.due_date)} ko due hain" if hinglish else f"is due on {say_date(due.due_date)}"


def reminder_message(business: Business, due: Due, now: Optional[datetime] = None) -> str:
    now = now or _now()
    first, amount, url = _first(due), inr(due.amount), pay_url(due)
    hello = f"Hi {first}," if first else "Hi,"
    if _hinglish(business):
        return (f"{hello} {payee(business)} se ek chhota sa reminder: {due.purpose} ke {amount} "
                f"{_when(due, now, True)}. Yahan pay kar sakte hain:\n{url}\n"
                f"Agar pay kar diya hai toh please ignore karein 🙏")
    return (f"{hello} a gentle reminder from {payee(business)}: {amount} for {due.purpose} {_when(due, now, False)}. "
            f"You can pay here:\n{url}\nPlease ignore this if you've already paid 🙏")


def how_to_send(db: Session, due: Due, lead: Optional[Lead] = None, now: Optional[datetime] = None) -> dict:
    """Same choices as follow-ups: app (inside WhatsApp's 24 hours) / whatsapp (own phone) / instagram / copy."""
    lead = lead or (db.get(Lead, due.lead_id) if due.lead_id else None)
    if lead is not None:
        way = followup_service.how_to_send(db, lead, now)
        if way["how"] != "copy" or not due.phone:
            return way
    number = followup_service._wa_number(due.phone)
    if number:
        return {"how": "whatsapp", "link": f"https://wa.me/{number}",
                "note": "Opens WhatsApp on your phone with the message ready: just press send."}
    return {"how": "copy", "link": None, "note": "We don't have a number for this customer: copy the message."}


def send(db: Session, due: Due, text: str, via: str, kind: str, now: Optional[datetime] = None) -> dict:
    """via = "app" (through the connected chat, needs an enquiry) or "phone" (sent from the owner's phone).
    kind = "request" (the first payment link) or "reminder". Returns {"delivery", "delivery_error"}."""
    now = now or _now()
    lead = db.get(Lead, due.lead_id) if due.lead_id else None
    if via == "app":
        if lead is None:
            raise ValueError("This payment isn't linked to a chat. Use Open WhatsApp instead.")
        delivery, problem, external_id = outbox.send_reply(db, lead, text)
        if delivery == "logged":
            raise ValueError(problem or "This customer can't be messaged from here. Use Open WhatsApp instead.")
    else:
        delivery, problem, external_id = "logged", "", None
    if lead is not None:
        lead_service.add_message(db, lead, MessageCreate(direction="outbound", text=text, send=via == "app"),
                                 delivery, problem, external_id)
    if kind == "reminder" and delivery != "failed":
        due.reminders_sent += 1
        due.last_reminder_at = now
    db.commit()
    return {"delivery": delivery, "delivery_error": problem}


# ---------------------------------------------------------------------------
# Paid / cancelled
# ---------------------------------------------------------------------------
def mark_paid(db: Session, due: Due, via: str = "upi", now: Optional[datetime] = None) -> Due:
    if due.status != "open":
        raise ValueError("Only a payment that's still waiting can be marked paid")
    if via not in PAID_VIA:
        raise ValueError(f"Paid by must be one of: {', '.join(PAID_VIA)}")
    due.status, due.paid_at, due.paid_via = "paid", now or _now(), via
    db.commit()
    bus.publish(due.business_id, "payment.received", f"💰 {inr(due.amount)} received from {due.customer_name}",
                due.purpose, {"due_id": due.id, "lead_id": due.lead_id, "amount": due.amount})
    return due


def cancel(db: Session, due: Due) -> Due:
    if due.status != "open":
        raise ValueError("Only a payment that's still waiting can be cancelled")
    due.status = "cancelled"
    db.commit()
    return due


def reopen(db: Session, due: Due) -> Due:
    """Undo "paid" or "cancelled" (e.g. pressed by mistake)."""
    due.status, due.paid_at, due.paid_via, due.customer_says_paid_at = "open", None, "", None
    db.commit()
    return due


def customer_says_paid(db: Session, due: Due, now: Optional[datetime] = None) -> Due:
    """The customer pressed "I've paid" on the payment page. We can't see their bank, so the owner
    checks their UPI app and confirms. Pressing it again changes nothing."""
    if due.status == "open" and due.customer_says_paid_at is None:
        due.customer_says_paid_at = now or _now()
        db.commit()
        bus.publish(due.business_id, "payment.claimed", f"💰 {due.customer_name} says they've paid {inr(due.amount)}",
                    "Check your UPI app, then mark it paid.", {"due_id": due.id, "lead_id": due.lead_id})
    return due


# ---------------------------------------------------------------------------
# The Payments page
# ---------------------------------------------------------------------------
def listing(db: Session, business_id: int, status: str = "open", lead_id: Optional[int] = None,
            now: Optional[datetime] = None) -> list[Due]:
    now = now or _now()
    query = select(Due).where(Due.business_id == business_id)
    if status != "all":
        query = query.where(Due.status == status)
    if lead_id is not None:
        query = query.where(Due.lead_id == lead_id)
    dues = list(db.scalars(query.order_by(Due.id.desc()).limit(300)))
    if status == "open":
        far = date.max
        # "says they've paid" first (just confirm), then the most overdue, then the soonest due
        dues.sort(key=lambda d: (d.customer_says_paid_at is None, d.due_date or far))
    elif status == "paid":
        dues.sort(key=lambda d: _utc(d.paid_at), reverse=True)
    return dues


def _month_start(day: date) -> datetime:
    return datetime(day.year, day.month, 1, tzinfo=IST)


def summary(db: Session, business_id: int, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    today = _today(now)
    this_month = _month_start(today)
    last_month = _month_start(this_month.date() - timedelta(days=1))
    dues = list(db.scalars(select(Due).where(Due.business_id == business_id, Due.status.in_(("open", "paid")))))
    paid_now = [d for d in dues if d.status == "paid" and _utc(d.paid_at) >= this_month]
    paid_before = [d for d in dues if d.status == "paid" and last_month <= _utc(d.paid_at) < this_month]
    open_ = [d for d in dues if d.status == "open"]
    overdue = [d for d in open_ if d.due_date and d.due_date < today]
    return {"recovered_this_month": sum(d.amount for d in paid_now), "paid_this_month": len(paid_now),
            "recovered_last_month": sum(d.amount for d in paid_before),
            "waiting": sum(d.amount for d in open_), "open": len(open_),
            "overdue": sum(d.amount for d in overdue), "overdue_count": len(overdue),
            "says_paid": sum(1 for d in open_ if d.customer_says_paid_at)}


# ---------------------------------------------------------------------------
# Automatic reminders (scheduler)
# ---------------------------------------------------------------------------
def _reminder_due(due: Due, now: datetime) -> bool:
    if due.reminders_sent >= len(REMIND_ON) or due.due_date is None:
        return False
    if _today(now) < due.due_date + timedelta(days=REMIND_ON[due.reminders_sent]):
        return False
    last = _utc(due.last_reminder_at)
    return last is None or now - last >= REMIND_GAP


def send_due_reminders(db: Session, now: Optional[datetime] = None) -> int:
    """Polite automatic WhatsApp reminders for businesses that turned them on. Returns how many went out."""
    now = now or _now()
    if not REMIND_HOURS[0] <= now.astimezone(IST).hour < REMIND_HOURS[1]:
        return 0
    candidates = list(db.scalars(select(Due).where(Due.status == "open", Due.auto_remind.is_(True),
                                                   Due.due_date.is_not(None), Due.phone.is_not(None),
                                                   Due.customer_says_paid_at.is_(None))))
    candidates = [d for d in candidates if _reminder_due(d, now)]
    if not candidates:
        return 0
    paused = billing_service.paused_business_ids(db)
    sent = 0
    for due in candidates:
        business = db.get(Business, due.business_id)
        s = settings_for(business)
        number = followup_service._wa_number(due.phone)
        if due.business_id in paused or not s["auto_reminders"] or not s["upi_id"] or not number:
            continue
        text = reminder_message(business, due, now)
        params = [_first(due) or "there", payee(business),
                  f"{inr(due.amount)} for {due.purpose} {_when(due, now, False)}", pay_url(due)]
        messenger = get_messenger(db, due.business_id)
        try:
            messenger.send_whatsapp(number, text, template_params=params, template=settings.whatsapp_payment_template)
        except SendError as problem:
            logger.warning("Payment reminder for due %s not sent: %s", due.id, problem)
            continue
        practice = isinstance(messenger, MockMessenger)
        due.reminders_sent += 1
        due.last_reminder_at = now
        if due.lead_id:                       # show it in the chat (an automatic message: the lead's status stays)
            lead = db.get(Lead, due.lead_id)
            if lead is not None:
                lead.messages.append(Message(direction="outbound", text=text, sent_at=now,
                                             delivery="logged" if practice else "sent",
                                             delivery_error="Practice mode: not delivered" if practice else ""))
        db.commit()
        sent += 1
    return sent
