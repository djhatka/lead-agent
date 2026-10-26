"""
Payments and dues (Task 31): money customers owe the business, paid straight to the owner's UPI ID.

    GET  /dues/settings?business_id=1     UPI ID, name shown to customers, automatic reminders on/off
    PUT  /dues/settings?business_id=1     owner: change them (send only what changes)
    GET  /dues/summary?business_id=1      ₹ recovered this month, ₹ waiting, ₹ overdue
    GET  /dues?business_id=1&status=open  the list (open / paid / cancelled / all; &lead_id= for one enquiry)
    POST /dues?business_id=1              a new due: {"lead_id": 12, "amount": 2000, "purpose": "...", "due_date": "..."}
    GET  /dues/{id}                       one due + the ready messages + how they can be sent
    POST /dues/{id}/send                  {"text": "...", "via": "app" | "phone", "kind": "request" | "reminder"}
    POST /dues/{id}/paid                  {"via": "upi" | "cash" | "card" | "bank" | "other"}
    POST /dues/{id}/cancel   /reopen

The customer's side is the public payment page: /pay/<token> (app/site/routes.py).
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import check_access, require_owner
from app.database import get_db
from app.models import Business, Due
from app.routers.businesses import business_or_404
from app.routers.leads import lead_or_404
from app.schemas import UTCDateTime
from app.services import dues_service

router = APIRouter(prefix="/dues", tags=["Payments and dues"])


class PaymentSettings(BaseModel):
    upi_id: str                       # "ironpulse@okaxis" ("" = not set up yet)
    payee_name: str                   # name customers see ("" = the business name)
    auto_reminders: bool
    ready: bool                       # a UPI ID is saved, so payment links can be made
    reminders_mode: str               # real (connected WhatsApp) / practice (recorded, not delivered)


class PaymentSettingsIn(BaseModel):
    upi_id: Optional[str] = Field(default=None, max_length=120, examples=["ironpulse@okaxis"])
    payee_name: Optional[str] = Field(default=None, max_length=60)
    auto_reminders: Optional[bool] = None


class DueOut(BaseModel):
    id: int
    lead_id: Optional[int]
    customer_name: str
    phone: Optional[str]
    amount: int
    purpose: str
    due_date: Optional[date]
    status: str                       # open / paid / cancelled
    label: str                        # "Overdue by 3 days", "Due today", "Paid on 24 Oct"
    overdue_days: int
    customer_says_paid_at: Optional[UTCDateTime]
    paid_at: Optional[UTCDateTime]
    paid_via: str
    auto_remind: bool
    reminders_sent: int
    last_reminder_at: Optional[UTCDateTime]
    pay_url: str                      # the customer's payment page
    created_at: UTCDateTime


class Summary(BaseModel):
    recovered_this_month: int         # ₹ paid this month (India time)
    paid_this_month: int
    recovered_last_month: int
    waiting: int                      # ₹ still open
    open: int
    overdue: int                      # ₹ past the due date
    overdue_count: int
    says_paid: int                    # customers who pressed "I've paid": confirm them


class DueIn(BaseModel):
    lead_id: Optional[int] = None
    customer_name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=20)
    amount: int = Field(ge=1, le=dues_service.MAX_AMOUNT, examples=[2000])
    purpose: str = Field(min_length=2, max_length=200, examples=["Advance for ceramic coating"])
    due_date: Optional[date] = None
    auto_remind: bool = True


class Ready(BaseModel):
    request: str                      # the first message with the payment link
    reminder: str                     # a polite reminder
    how: str                          # app / whatsapp / instagram / copy
    link: Optional[str]
    note: str


class DueDetail(BaseModel):
    due: DueOut
    ready: Ready


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    via: Literal["app", "phone"] = "phone"
    kind: Literal["request", "reminder"] = "request"


class SendOut(BaseModel):
    delivery: str                     # sent / failed / logged
    delivery_error: str
    due: DueOut


class PaidIn(BaseModel):
    via: Literal["upi", "cash", "card", "bank", "other"] = "upi"


def _out(due: Due) -> DueOut:
    return DueOut(**{c: getattr(due, c) for c in DueOut.model_fields if hasattr(due, c)},
                  **dues_service.state(due), pay_url=dues_service.pay_url(due))


def _settings(db: Session, business: Business) -> PaymentSettings:
    from app.services.messenger import MockMessenger, get_messenger
    s = dues_service.settings_for(business)
    real = not isinstance(get_messenger(db, business.id), MockMessenger)
    return PaymentSettings(**s, ready=bool(s["upi_id"]), reminders_mode="real" if real else "practice")


def due_or_404(due_id: int, db: Session) -> Due:
    due = db.get(Due, due_id)
    if due is None:
        raise HTTPException(status_code=404, detail="That payment was not found")
    check_access(due.business_id, "That payment")
    return due


@router.get("/settings", response_model=PaymentSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _settings(db, business_or_404(business_id, db))


@router.put("/settings", response_model=PaymentSettings)
def put_settings(business_id: int, body: PaymentSettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        dues_service.update_settings(db, business, body.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _settings(db, business)


@router.get("/summary", response_model=Summary)
def summary(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return dues_service.summary(db, business_id)


@router.get("", response_model=list[DueOut])
def list_dues(business_id: int, status: Literal["open", "paid", "cancelled", "all"] = "open",
              lead_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return [_out(d) for d in dues_service.listing(db, business_id, status, lead_id)]


@router.post("", response_model=DueDetail, status_code=201)
def create_due(business_id: int, body: DueIn, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    lead = None
    if body.lead_id is not None:
        lead = lead_or_404(body.lead_id, db)
        if lead.business_id != business.id:
            raise HTTPException(status_code=404, detail=f"Lead {body.lead_id} not found")
    try:
        due = dues_service.create(db, business, amount=body.amount, purpose=body.purpose, lead=lead,
                                  customer_name=body.customer_name, phone=body.phone, due_date=body.due_date,
                                  auto_remind=body.auto_remind)
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _detail(db, due)


def _detail(db: Session, due: Due) -> DueDetail:
    business = db.get(Business, due.business_id)
    return DueDetail(due=_out(due), ready=Ready(request=dues_service.request_message(business, due),
                                                reminder=dues_service.reminder_message(business, due),
                                                **dues_service.how_to_send(db, due)))


@router.get("/{due_id}", response_model=DueDetail)
def get_due(due_id: int, db: Session = Depends(get_db)):
    return _detail(db, due_or_404(due_id, db))


@router.post("/{due_id}/send", response_model=SendOut)
def send(due_id: int, body: SendIn, db: Session = Depends(get_db)):
    due = due_or_404(due_id, db)
    if due.status != "open":
        raise HTTPException(status_code=400, detail="This payment isn't waiting any more")
    try:
        result = dues_service.send(db, due, body.text.strip(), body.via, body.kind)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return SendOut(**result, due=_out(due))


def _change(due_id: int, db: Session, action, *args) -> DueOut:
    due = due_or_404(due_id, db)
    try:
        action(db, due, *args)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return _out(due)


@router.post("/{due_id}/paid", response_model=DueOut)
def mark_paid(due_id: int, body: PaidIn, db: Session = Depends(get_db)):
    return _change(due_id, db, dues_service.mark_paid, body.via)


@router.post("/{due_id}/cancel", response_model=DueOut)
def cancel(due_id: int, db: Session = Depends(get_db)):
    return _change(due_id, db, dues_service.cancel)


@router.post("/{due_id}/reopen", response_model=DueOut)
def reopen(due_id: int, db: Session = Depends(get_db)):
    return _change(due_id, db, dues_service.reopen)
