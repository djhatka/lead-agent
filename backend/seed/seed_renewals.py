"""
Demo renewals (Task 32), so the Renewals page has something to show.

Each demo business gets a handful of renewals with varied expiry dates:
expiring soon, just expired, and one already renewed.
"""

import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, Lead, Renewal

SERVICES = {
    "gym": [("Monthly membership", 2500), ("3-month membership", 6500), ("Personal training pack", 8000),
            ("Zumba batch", 1800)],
    "car_detailing": [("Annual coating warranty", 5000), ("Monthly wash subscription", 3000),
                      ("PPF maintenance plan", 7000)],
    "clinic": [("6-month checkup plan", 3000), ("Ortho retainer review", 1500),
               ("Annual dental plan", 5000)],
}


def make_renewals(db: Session, r: random.Random, business: Business, now: datetime) -> None:
    business.renewal_settings = {"enabled": True, "remind_days_before": 5}
    leads = list(db.scalars(select(Lead).where(Lead.business_id == business.id, Lead.name.is_not(None),
                                               Lead.phone.is_not(None)).order_by(Lead.id)))
    if not leads:
        return
    today = now.astimezone(timezone(timedelta(hours=5, minutes=30))).date()
    #       (status,  days until expiry)
    plan = [
        ("upcoming", 3),     # expiring in 3 days
        ("upcoming", 5),     # expiring in 5 days
        ("due", 0),          # expires today
        ("due", -2),         # expired 2 days ago
        ("upcoming", -8),    # lapsed (expired 8 days ago)
        ("renewed", -10),    # already renewed
    ]
    for status, days_offset in plan:
        lead: Lead = r.choice(leads)
        service, amount = r.choice(SERVICES.get(business.industry, SERVICES["gym"]))
        expiry = today + timedelta(days=days_offset)
        renewal = Renewal(
            business_id=business.id, lead_id=lead.id,
            customer_name=lead.name, phone=lead.phone,
            service=service, expiry_date=expiry, renewal_amount=amount,
            status=status,
            renewed_at=now - timedelta(days=2) if status == "renewed" else None,
            reminders_sent=1 if status in ("due", "renewed") else 0,
            last_reminder_at=now - timedelta(days=3) if status in ("due", "renewed") else None,
            created_at=now - timedelta(days=r.randint(10, 30)),
        )
        db.add(renewal)
