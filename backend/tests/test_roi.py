"""
Task 27 checks: the monthly ROI report ("what Lead Intel did for you").
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Business, Email, Lead, Post, RoiReport
from app.services import roi_service
from app.services.roi_service import IST


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def this_month() -> str:
    return roi_service.month_of(datetime.now(timezone.utc))


def first_of_next_month(hour: int) -> datetime:
    """The 1st of next month at `hour` India time (when last month's report goes out)."""
    local = datetime.now(IST)
    return datetime(local.year + (local.month == 12), local.month % 12 + 1, 1, hour, tzinfo=IST)


def sell(client, headers, lead_id: int, value: int):
    r = client.patch(f"/leads/{lead_id}", json={"status": "won", "job_value": value}, headers=headers)
    assert r.status_code == 200, r.text
    return r


def open_lead(db, business_id=1) -> Lead:
    return db.scalar(select(Lead).where(Lead.business_id == business_id, Lead.status.in_(["new", "contacted", "quoted"]))
                     .order_by(Lead.id))


# ---------------------------------------------------------------------------
# Months, in India time
# ---------------------------------------------------------------------------
def test_months_follow_india_time():
    start, end = roi_service.month_bounds("2026-10")
    assert start == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)          # 1 Oct 00:00 IST
    assert end == datetime(2026, 10, 31, 18, 30, tzinfo=timezone.utc)           # 1 Nov 00:00 IST
    assert roi_service.month_bounds("2026-12")[1] == datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc)
    assert roi_service.previous_month(datetime(2027, 1, 5, tzinfo=IST)) == "2026-12"
    late_night = datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)              # already 1 Nov in India
    assert roi_service.month_of(late_night) == "2026-11"
    assert roi_service.month_label("2026-10") == "October 2026"
    assert not roi_service.valid_month("2026-13") and not roi_service.valid_month("oct")


# ---------------------------------------------------------------------------
# What counts
# ---------------------------------------------------------------------------
def test_a_sale_counts_in_the_month_it_happens(raw_client, db_session):
    gym = login(raw_client)
    before = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]["sales"]
    lead = open_lead(db_session)
    sell(raw_client, gym, lead.id, 7_500)
    db_session.refresh(lead)
    assert lead.won_at is not None
    after = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()
    assert after["month"] == this_month() and after["stats"]["so_far"] is True
    assert after["stats"]["sales"]["customers"] == before["customers"] + 1
    assert after["stats"]["sales"]["revenue"] == before["revenue"] + 7_500

    raw_client.patch(f"/leads/{lead.id}", json={"status": "lost"}, headers=gym)     # changed their mind
    db_session.refresh(lead)
    assert lead.won_at is None
    again = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]["sales"]
    assert again == before


def test_imported_old_customers_are_not_counted(raw_client):
    gym = login(raw_client)
    before = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]
    csv = "Name,Phone,Status,Amount\nOld Member,9811099999,Paid,50000\n"
    raw_client.post("/leads/import", params={"dry_run": False}, headers=gym,
                    files={"file": ("register.csv", csv.encode(), "text/csv")})
    after = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]
    assert after["sales"] == before["sales"] and after["enquiries"]["total"] == before["enquiries"]["total"]


def test_sales_from_posts_are_shown_apart(raw_client, db_session):
    gym = login(raw_client)
    post = db_session.scalar(select(Post).where(Post.business_id == 1, Post.status == "published"))
    lead = open_lead(db_session)
    raw_client.patch(f"/leads/{lead.id}", json={"post_id": post.id}, headers=gym)
    sell(raw_client, gym, lead.id, 99_000)                                          # the biggest sale this month
    stats = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]
    assert stats["posts"]["customers"] >= 1 and stats["posts"]["revenue"] >= 99_000
    assert stats["posts"]["best"]["id"] == post.id and stats["posts"]["best"]["revenue"] >= 99_000
    assert stats["sales"]["revenue"] >= stats["posts"]["revenue"]                   # posts are part of all sales


def test_return_on_the_plan(raw_client, db_session):
    gym = login(raw_client)                                       # the gym pays for Growth (₹2,499)
    lead = open_lead(db_session)
    sell(raw_client, gym, lead.id, 50_000)
    stats = raw_client.get("/roi", params={"business_id": 1}, headers=gym).json()["stats"]
    assert stats["plan"]["price"] == 2499 and stats["plan"]["on_trial"] is False
    assert stats["return_multiple"] == round(stats["sales"]["revenue"] / 2499, 1)
    assert "paid for itself" in stats["headline"]

    garage = login(raw_client, "garage@demo.in")                  # on a free trial: "would pay for itself"
    lead = open_lead(db_session, business_id=2)
    sell(raw_client, garage, lead.id, 50_000)
    trial = raw_client.get("/roi", params={"business_id": 2}, headers=garage).json()["stats"]
    assert trial["plan"]["on_trial"] is True and "would pay for itself" in trial["headline"]


def test_a_quiet_month_says_so_without_inventing_money(db_session):
    business = Business(name="Brand New Salon", industry="salon", city="Delhi")
    db_session.add(business)
    db_session.commit()
    stats = roi_service.compute(db_session, business, this_month())
    assert stats["sales"]["revenue"] == 0 and stats["return_multiple"] is None
    assert stats["headline"].startswith("No enquiries")
    text = roi_service.message(business, stats)
    assert "₹0 in sales" in text and "came straight from your posts" not in text


# ---------------------------------------------------------------------------
# The addresses
# ---------------------------------------------------------------------------
def test_month_must_be_real_and_started(raw_client):
    gym = login(raw_client)
    assert raw_client.get("/roi", params={"business_id": 1, "month": "2026-13"}, headers=gym).status_code == 422
    next_month = roi_service.month_of(first_of_next_month(10))
    assert raw_client.get("/roi", params={"business_id": 1, "month": next_month}, headers=gym).status_code == 422


def test_send_last_month_now(raw_client, db_session):
    gym = login(raw_client)
    assert raw_client.post("/roi/reports", params={"business_id": 1}, headers=login(raw_client, "staff@demo.in")
                           ).status_code == 403                                     # owners only
    unfinished = raw_client.post("/roi/reports", params={"business_id": 1, "month": this_month()}, headers=gym)
    assert unfinished.status_code == 422

    r = raw_client.post("/roi/reports", params={"business_id": 1}, headers=gym)
    assert r.status_code == 201
    report = r.json()
    assert report["month"] == roi_service.previous_month(datetime.now(timezone.utc)) and report["emailed_at"]
    assert report["stats"]["so_far"] is False and report["message"].startswith("*Iron Pulse Fitness:")
    emails = db_session.scalar(select(func.count(Email.id)).where(Email.kind == "roi_report"))
    assert emails == 1

    raw_client.post("/roi/reports", params={"business_id": 1}, headers=gym)            # again: remade, not re-emailed
    assert db_session.scalar(select(func.count(Email.id)).where(Email.kind == "roi_report")) == 1
    assert db_session.scalar(select(func.count(RoiReport.id)).where(RoiReport.business_id == 1)) == 1

    listed = raw_client.get("/roi/reports", params={"business_id": 1}, headers=gym).json()
    assert listed[0]["id"] == report["id"] and listed[0]["label"] == report["stats"]["label"]
    text = raw_client.get(f"/roi/reports/{report['id']}/whatsapp", headers=gym)
    assert text.headers["content-type"].startswith("text/plain") and text.text == report["message"]


def test_reports_are_private(raw_client):
    report = raw_client.post("/roi/reports", params={"business_id": 1}, headers=login(raw_client)).json()
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get(f"/roi/reports/{report['id']}", headers=garage).status_code == 404
    assert raw_client.get("/roi", params={"business_id": 1}, headers=garage).status_code == 404


# ---------------------------------------------------------------------------
# The 1st of the month
# ---------------------------------------------------------------------------
def test_sent_on_the_first_from_9am_once(db_session):
    assert roi_service.monthly_reports_due(db_session, now=first_of_next_month(8)) == 0       # too early
    made = roi_service.monthly_reports_due(db_session, now=first_of_next_month(10))
    assert made == 3                                                                           # all 3 demo plans run
    assert roi_service.monthly_reports_due(db_session, now=first_of_next_month(11)) == 0      # not twice
    owners_emailed = db_session.scalar(select(func.count(Email.id)).where(Email.kind == "roi_report"))
    assert owners_emailed == 3                                                                 # one owner each
    later = first_of_next_month(10) + timedelta(days=9)
    assert roi_service.monthly_reports_due(db_session, now=later) == 0                        # too late to catch up


def test_catches_up_if_the_server_was_down_on_the_first(db_session):
    assert roi_service.monthly_reports_due(db_session, now=first_of_next_month(10) + timedelta(days=3)) == 3


def test_deleting_an_account_deletes_its_reports(raw_client, db_session):
    gym = login(raw_client)
    raw_client.post("/roi/reports", params={"business_id": 1}, headers=gym)
    r = raw_client.post("/account/delete", json={"password": "demo1234", "confirm": "DELETE"}, headers=gym)
    assert r.status_code in (200, 204), r.text
    assert db_session.scalar(select(func.count(RoiReport.id)).where(RoiReport.business_id == 1)) == 0
