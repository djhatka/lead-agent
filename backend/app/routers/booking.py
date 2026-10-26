"""
Booking slots inside WhatsApp (Task 37): a customer picks a free time themselves,
instead of a back-and-forth over chat.

    GET  /bookings/settings?business_id=1     working hours, slot length, closed days
    PUT  /bookings/settings?business_id=1     owner: change them (send only what changes)
    GET  /bookings?business_id=1&status=pending   the list (pending / confirmed / cancelled / all; &lead_id= for one enquiry)
    POST /bookings?business_id=1              a new booking: {"lead_id": 12, "service": "...", ...}
    GET  /bookings/{id}                        one booking + the ready message + how it can be sent
    GET  /bookings/{id}/slots                  the free times the customer can currently pick
    POST /bookings/{id}/send                   {"text": "...", "via": "app" | "phone"}
    POST /bookings/{id}/cancel

The customer's side is the public booking page: /book/<token> (app/site/routes.py).
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import check_access, require_owner
from app.database import get_db
from app.models import Booking, Business
from app.routers.businesses import business_or_404
from app.routers.leads import lead_or_404
from app.schemas import UTCDateTime
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["Booking slots"])


class BookingSettings(BaseModel):
    slot_minutes: int
    days_ahead: int
    start_hour: int
    end_hour: int
    closed_weekdays: list[int]           # 0 (Monday) to 6 (Sunday)


class BookingSettingsIn(BaseModel):
    slot_minutes: Optional[int] = None
    days_ahead: Optional[int] = Field(default=None, ge=0, le=30)
    start_hour: Optional[int] = Field(default=None, ge=0, le=24)
    end_hour: Optional[int] = Field(default=None, ge=0, le=24)
    closed_weekdays: Optional[list[int]] = None


class BookingOut(BaseModel):
    id: int
    lead_id: Optional[int]
    customer_name: str
    phone: Optional[str]
    service: str
    status: str                          # pending / confirmed / cancelled
    slot_at: Optional[UTCDateTime]
    slot_label: Optional[str]            # "Mon 2 Nov, 4:00 PM" (None until chosen)
    duration_minutes: int
    confirmed_at: Optional[UTCDateTime]
    cancelled_at: Optional[UTCDateTime]
    book_url: str                        # the customer's booking page
    created_at: UTCDateTime


class BookingIn(BaseModel):
    lead_id: Optional[int] = None
    customer_name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=20)
    service: str = Field(min_length=2, max_length=150, examples=["Personal training session"])


class Ready(BaseModel):
    request: str                         # the message with the booking link
    how: str                             # app / whatsapp / instagram / copy
    link: Optional[str]
    note: str


class BookingDetail(BaseModel):
    booking: BookingOut
    ready: Ready


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    via: Literal["app", "phone"] = "phone"


class SendOut(BaseModel):
    delivery: str                        # sent / failed / logged
    delivery_error: str
    booking: BookingOut


def _out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=booking.id, lead_id=booking.lead_id, customer_name=booking.customer_name, phone=booking.phone,
        service=booking.service, status=booking.status, slot_at=booking.slot_at,
        slot_label=booking_service.say_when(booking_service._utc(booking.slot_at)) if booking.slot_at else None,
        duration_minutes=booking.duration_minutes, confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at, book_url=booking_service.book_url(booking), created_at=booking.created_at)


def _settings(business: Business) -> BookingSettings:
    return BookingSettings(**booking_service.settings_for(business))


def booking_or_404(booking_id: int, db: Session) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="That booking was not found")
    check_access(booking.business_id, "That booking")
    return booking


@router.get("/settings", response_model=BookingSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _settings(business_or_404(business_id, db))


@router.put("/settings", response_model=BookingSettings)
def put_settings(business_id: int, body: BookingSettingsIn, _owner=Depends(require_owner),
                 db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        booking_service.update_settings(db, business, body.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _settings(business)


@router.get("", response_model=list[BookingOut])
def list_bookings(business_id: int, status: Literal["pending", "confirmed", "cancelled", "all"] = "pending",
                  lead_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return [_out(b) for b in booking_service.listing(db, business_id, status, lead_id)]


def _detail(db: Session, booking: Booking) -> BookingDetail:
    business = db.get(Business, booking.business_id)
    return BookingDetail(booking=_out(booking), ready=Ready(request=booking_service.request_message(business, booking),
                                                            **booking_service.how_to_send(db, booking)))


@router.post("", response_model=BookingDetail, status_code=201)
def create_booking(business_id: int, body: BookingIn, db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    lead = None
    if body.lead_id is not None:
        lead = lead_or_404(body.lead_id, db)
        if lead.business_id != business.id:
            raise HTTPException(status_code=404, detail=f"Lead {body.lead_id} not found")
    try:
        booking = booking_service.create(db, business, service=body.service, lead=lead,
                                         customer_name=body.customer_name, phone=body.phone)
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem))
    return _detail(db, booking)


@router.get("/{booking_id}", response_model=BookingDetail)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    return _detail(db, booking_or_404(booking_id, db))


@router.get("/{booking_id}/slots", response_model=list[UTCDateTime])
def get_slots(booking_id: int, db: Session = Depends(get_db)):
    booking = booking_or_404(booking_id, db)
    business = db.get(Business, booking.business_id)
    return booking_service.available_slots(db, business, booking)


@router.post("/{booking_id}/send", response_model=SendOut)
def send(booking_id: int, body: SendIn, db: Session = Depends(get_db)):
    booking = booking_or_404(booking_id, db)
    if booking.status != "pending":
        raise HTTPException(status_code=400, detail="This booking isn't waiting for a time any more")
    try:
        result = booking_service.send(db, booking, body.text.strip(), body.via)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return SendOut(**result, booking=_out(booking))


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel(booking_id: int, db: Session = Depends(get_db)):
    booking = booking_or_404(booking_id, db)
    try:
        booking_service.cancel(db, booking)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return _out(booking)
