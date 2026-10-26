"""
Checks for the demo data maker (seed/seed_data.py).

These tests use a temporary database that lives only in memory, so your
real data/leads.db is never touched.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Business, Lead, Message
from seed.seed_data import seed


def make_test_db():
    """A brand-new, empty database in memory (disappears after the test)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_seed_creates_three_businesses_with_leads():
    db = make_test_db()
    seed(db, leads_per_business=30)
    assert db.query(Business).count() == 3
    assert db.query(Lead).count() == 90
    assert {b.industry for b in db.query(Business)} == {"gym", "car_detailing", "clinic"}


def test_every_lead_has_its_first_message():
    db = make_test_db()
    seed(db, leads_per_business=30)
    for lead in db.query(Lead):
        assert lead.messages, "each lead should have at least one message"
        assert lead.messages[0].direction == "inbound"
        assert lead.messages[0].text == lead.first_message


def test_money_only_on_won_leads():
    db = make_test_db()
    seed(db, leads_per_business=50)
    for lead in db.query(Lead):
        if lead.status == "won":
            assert lead.job_value and lead.job_value > 0
        else:
            assert lead.job_value is None


def test_unanswered_leads_have_no_reply_time():
    db = make_test_db()
    seed(db, leads_per_business=50)
    for lead in db.query(Lead).filter(Lead.status == "new"):
        assert lead.first_response_at is None
        assert all(m.direction == "inbound" for m in lead.messages)


def test_same_seed_gives_same_data():
    a, b = make_test_db(), make_test_db()
    seed(a, leads_per_business=20)
    seed(b, leads_per_business=20)
    texts_a = [m.text for m in a.query(Message).order_by(Message.id)]
    texts_b = [m.text for m in b.query(Message).order_by(Message.id)]
    assert texts_a == texts_b
