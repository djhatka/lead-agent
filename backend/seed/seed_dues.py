"""
Demo payments and dues (Task 31), so the Payments page has something to show.

Each demo business gets a practice UPI ID (on a made-up "okdemo" bank handle,
so nobody can pay a real person by mistake) and a handful of dues: some paid
this month, some waiting, one overdue, and one where the customer pressed
"I've paid" and the owner still has to confirm.
"""

import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, Due, Lead

UPI_IDS = {"gym": "ironpulse.demo@okdemo", "car_detailing": "glossgarage.demo@okdemo", "clinic": "smilecare.demo@okdemo"}
PURPOSES = {
    "gym": [("Monthly membership", 2500), ("3-month membership", 6500), ("Personal training (8 sessions)", 8000),
            ("Zumba batch fee", 1800)],
    "car_detailing": [("Advance for ceramic coating", 5000), ("PPF advance", 10000), ("Interior deep clean", 2500),
                      ("Balance for ceramic coating", 13500)],
    "clinic": [("Root canal (sitting 1)", 4000), ("Teeth whitening", 6000), ("Braces consultation", 800),
               ("Scaling and polishing", 1500)],
}


def make_dues(db: Session, r: random.Random, business: Business, now: datetime) -> None:
    business.payment_settings = {"upi_id": UPI_IDS.get(business.industry, "demo@okdemo"), "payee_name": "",
                                 "auto_reminders": False}
    leads = list(db.scalars(select(Lead).where(Lead.business_id == business.id, Lead.name.is_not(None),
                                               Lead.phone.is_not(None)).order_by(Lead.id)))
    if not leads:
        return
    today = now.astimezone(timezone(timedelta(hours=5, minutes=30))).date()
    month_start = datetime(today.year, today.month, 1, 12, tzinfo=timezone.utc)
    #          (status, days until due (negative = overdue), customer says paid?)
    plan = [("paid", -10, False), ("paid", -4, False), ("paid", -2, False),
            ("open", 3, False), ("open", 0, False), ("open", -6, False), ("open", -1, True), ("open", None, False)]
    for status, due_in, claimed in plan:
        lead: Lead = r.choice(leads)
        purpose, amount = r.choice(PURPOSES.get(business.industry, PURPOSES["gym"]))
        due_date = today + timedelta(days=due_in) if due_in is not None else None
        paid_at = None
        if status == "paid":                          # paid this month, a few days after it was asked for
            paid_at = min(now, max(month_start, now - timedelta(days=r.randint(0, 6), hours=r.randint(1, 8))))
        db.add(Due(business_id=business.id, lead_id=lead.id, customer_name=lead.name, phone=lead.phone,
                   amount=amount, purpose=purpose, due_date=due_date, status=status, token=secrets.token_urlsafe(12),
                   paid_at=paid_at, paid_via="upi" if paid_at else "",
                   customer_says_paid_at=now - timedelta(hours=3) if claimed else None,
                   created_at=now - timedelta(days=r.randint(3, 15))))
