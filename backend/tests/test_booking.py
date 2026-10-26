"""
Task 37 checks: booking slots inside WhatsApp. A customer picks a free time
themselves through a shareable link, same shape as the Payments page.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Booking, Business, Lead
from app.services import booking_service

GYM = 1
IST = booking_service.IST
MONDAY_10AM = datetime(2026, 11, 2, 10, 0, tzinfo=IST).astimezone(timezone.utc)   # a Monday


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def new_booking(db, business_id=GYM, lead=None, **extra):
    business = db.get(Business, business_id)
    args = {"service": "Personal training session", "lead": lead,
            "customer_name": "" if lead else "Rahul Sharma", "phone": "" if lead else "+919811066002", **extra}
    return booking_service.create(db, business, **args)


def _clear(db):
    for b in db.scalars(select(Booking).where(Booking.business_id == GYM)):
        db.delete(b)
    db.commit()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,hello", [("Rahul Sharma", "Hi Rahul!"), ("Mr Verma", "Hi Mr Verma!"),
                                        ("dr. anita rao", "Hi Dr. Rao!"), ("+919811066009", "Hi!")])
def test_greeting_by_name(db_session, name, hello):
    booking = new_booking(db_session, customer_name=name)
    assert booking_service.request_message(db_session.get(Business, GYM), booking).startswith(hello + " ")


def test_needs_a_name_and_a_service(db_session):
    gym = db_session.get(Business, GYM)
    with pytest.raises(ValueError):
        booking_service.create(db_session, gym, service="", customer_name="Rahul")
    with pytest.raises(ValueError):
        booking_service.create(db_session, gym, service="Training", customer_name="")


def test_say_when_reads_naturally():
    monday_4pm = datetime(2026, 11, 2, 16, 0, tzinfo=IST).astimezone(timezone.utc)
    assert booking_service.say_when(monday_4pm) == "Mon 2 Nov, 4:00 PM"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_default_and_validation(db_session):
    gym = db_session.get(Business, GYM)
    s = booking_service.settings_for(gym)
    assert s == {"slot_minutes": 30, "days_ahead": 7, "start_hour": 10, "end_hour": 19, "closed_weekdays": []}

    with pytest.raises(ValueError):
        booking_service.update_settings(db_session, gym, {"slot_minutes": 23})
    with pytest.raises(ValueError):
        booking_service.update_settings(db_session, gym, {"start_hour": 20, "end_hour": 18})
    with pytest.raises(ValueError):
        booking_service.update_settings(db_session, gym, {"closed_weekdays": [7]})

    booking_service.update_settings(db_session, gym, {"slot_minutes": 45, "closed_weekdays": [6, 0]})
    assert booking_service.settings_for(gym)["slot_minutes"] == 45
    assert booking_service.settings_for(gym)["closed_weekdays"] == [0, 6]


# ---------------------------------------------------------------------------
# Available slots: working hours, closed days, and no double-booking
# ---------------------------------------------------------------------------
def test_available_slots_stay_inside_working_hours(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    booking_service.update_settings(db_session, gym, {"start_hour": 10, "end_hour": 12, "slot_minutes": 30,
                                                       "days_ahead": 0, "closed_weekdays": []})
    booking = new_booking(db_session)
    now = datetime(2026, 11, 2, 0, 0, tzinfo=IST).astimezone(timezone.utc)   # same Monday, before opening
    slots = booking_service.available_slots(db_session, gym, booking, now)
    assert len(slots) == 4                                      # 10:00, 10:30, 11:00, 11:30
    assert all(s.astimezone(IST).hour in (10, 11) for s in slots)


def test_closed_weekday_has_no_slots(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    booking_service.update_settings(db_session, gym, {"closed_weekdays": [0], "days_ahead": 0})   # Monday off
    booking = new_booking(db_session)
    now = datetime(2026, 11, 2, 0, 0, tzinfo=IST).astimezone(timezone.utc)   # that Monday
    assert booking_service.available_slots(db_session, gym, booking, now) == []


def test_a_confirmed_booking_blocks_that_slot_for_others(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    booking_service.update_settings(db_session, gym, {"start_hour": 10, "end_hour": 11, "slot_minutes": 30,
                                                       "days_ahead": 0})
    now = datetime(2026, 11, 2, 0, 0, tzinfo=IST).astimezone(timezone.utc)
    taken = new_booking(db_session)
    booking_service.choose_slot(db_session, gym, taken, MONDAY_10AM, now)

    other = new_booking(db_session, customer_name="Priya")
    slots = booking_service.available_slots(db_session, gym, other, now)
    assert MONDAY_10AM not in slots
    assert MONDAY_10AM + timedelta(minutes=30) in slots


def test_choosing_a_slot_twice_is_rejected(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    now = datetime(2026, 11, 2, 0, 0, tzinfo=IST).astimezone(timezone.utc)
    booking = new_booking(db_session)
    booking_service.choose_slot(db_session, gym, booking, MONDAY_10AM, now)
    assert booking.status == "confirmed" and booking.slot_at == MONDAY_10AM

    other = new_booking(db_session, customer_name="Priya")
    with pytest.raises(ValueError):
        booking_service.choose_slot(db_session, gym, other, MONDAY_10AM, now)


def test_choosing_an_unavailable_time_is_rejected(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    booking = new_booking(db_session)
    way_in_the_past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        booking_service.choose_slot(db_session, gym, booking, way_in_the_past)


def test_cancel_a_booking(db_session):
    booking = new_booking(db_session)
    booking_service.cancel(db_session, booking)
    assert booking.status == "cancelled" and booking.cancelled_at is not None
    with pytest.raises(ValueError):
        booking_service.cancel(db_session, booking)


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------
def test_add_list_get_and_cancel_via_the_api(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)

    r = raw_client.post("/bookings", params={"business_id": GYM},
                        json={"customer_name": "Rahul Sharma", "phone": "+919811066002", "service": "Zumba trial"},
                        headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["booking"]["service"] == "Zumba trial" and body["booking"]["status"] == "pending"
    assert "/book/" in body["booking"]["book_url"]
    booking_id = body["booking"]["id"]

    r = raw_client.get("/bookings", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200
    assert any(b["id"] == booking_id for b in r.json())

    r = raw_client.get(f"/bookings/{booking_id}/slots", headers=headers)
    assert r.status_code == 200 and len(r.json()) > 0

    r = raw_client.post(f"/bookings/{booking_id}/cancel", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"

    r = raw_client.get("/bookings", params={"business_id": GYM, "status": "cancelled"}, headers=headers)
    assert any(b["id"] == booking_id for b in r.json())


def test_bookings_endpoint_needs_login(raw_client):
    r = raw_client.get("/bookings", params={"business_id": GYM})
    assert r.status_code == 401


def test_bookings_block_other_businesses(raw_client, db_session):
    headers = login(raw_client)                                  # gym owner
    r = raw_client.get("/bookings", params={"business_id": 2}, headers=headers)   # the garage
    assert r.status_code == 404


def test_settings_endpoint_round_trips(raw_client, db_session):
    headers = login(raw_client)
    r = raw_client.put("/bookings/settings", params={"business_id": GYM},
                       json={"slot_minutes": 20, "end_hour": 20}, headers=headers)
    assert r.status_code == 200
    assert r.json()["slot_minutes"] == 20 and r.json()["end_hour"] == 20


# ---------------------------------------------------------------------------
# The public booking page
# ---------------------------------------------------------------------------
def test_public_page_shows_slots_then_confirms_one(raw_client, db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    booking_service.update_settings(db_session, gym, {"start_hour": 10, "end_hour": 12})
    booking = new_booking(db_session)

    r = raw_client.get(f"/book/{booking.token}")
    assert r.status_code == 200 and "Pick a time" in r.text

    slots = booking_service.available_slots(db_session, gym, booking)
    r = raw_client.post(f"/book/{booking.token}/choose", data={"slot": slots[0].isoformat()}, follow_redirects=False)
    assert r.status_code == 303

    db_session.refresh(booking)
    assert booking.status == "confirmed" and booking.slot_at is not None

    r = raw_client.get(f"/book/{booking.token}")
    assert r.status_code == 200 and "booked in" in r.text


def test_public_page_404s_for_an_unknown_token(raw_client):
    r = raw_client.get("/book/does-not-exist-at-all")
    assert r.status_code == 404
