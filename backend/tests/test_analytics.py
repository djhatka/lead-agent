"""
Checks for the analytics engine (Task 11).

We build a tiny business with 10 hand-made leads, so we know EXACTLY what
every number should be, then compare with what the calculator says.

    source     leads  won  revenue
    instagram    5     0        0      ← lots of enquiries, no sales
    google       3     2   30,000      ← fewer enquiries, the money
    referral     2     1    5,000
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Business, Lead, LeadAnalysis
from app.services import analytics_service as calc

NOW = datetime.now(timezone.utc)


@pytest.fixture
def tiny(db_session):
    biz = Business(name="Tiny Salon", industry="salon", services=["Haircut", "Facial"])
    db_session.add(biz)
    db_session.flush()

    def add(source, status, days_ago, reply_min=None, value=None, service="Haircut", hot=False):
        created = NOW - timedelta(days=days_ago)
        lead = Lead(business_id=biz.id, source=source, name="X", status=status, job_value=value,
                    service=service, created_at=created,
                    first_response_at=created + timedelta(minutes=reply_min) if reply_min is not None else None)
        lead.analysis = LeadAnalysis(sentiment="casual", score=80 if hot else 40,
                                     priority="hot" if hot else "normal")
        db_session.add(lead)

    # instagram: 5 leads, none won
    add("instagram", "lost", 20, reply_min=300)
    add("instagram", "lost", 18, reply_min=600)
    add("instagram", "lost", 12, reply_min=500)
    add("instagram", "new", 3)                                   # never replied
    add("instagram", "contacted", 2, reply_min=20, hot=True)     # hot and still open
    # google: 3 leads, 2 won
    add("google", "won", 25, reply_min=10, value=20000, service="Facial")
    add("google", "won", 9, reply_min=30, value=10000)
    add("google", "quoted", 5, reply_min=40)
    # referral: 2 leads, 1 won
    add("referral", "won", 4, reply_min=5, value=5000)
    add("referral", "lost", 1, reply_min=700)
    # an old lead OUTSIDE the 90-day window: must be ignored
    add("google", "won", 200, reply_min=5, value=99999)
    db_session.commit()
    return biz.id


def test_overview_numbers(db_session, tiny):
    ov = calc.overview(calc.load_leads(db_session, tiny, 90), 90)
    assert ov.leads == 10                      # the 200-day-old lead is outside the window
    assert ov.won == 3 and ov.lost == 4 and ov.open == 3
    assert ov.conversion_rate == 30.0
    assert ov.revenue == 35000 and ov.avg_sale == 11667
    assert ov.never_replied == 1
    assert ov.hot_open == 1
    assert ov.median_reply_minutes == 40.0     # middle of the 9 reply times


def test_sources_volume_vs_money(db_session, tiny):
    by = {s.source: s for s in calc.sources(calc.load_leads(db_session, tiny, 90))}
    assert by["instagram"].leads == 5 and by["instagram"].share_of_leads == 50.0
    assert by["instagram"].revenue == 0 and by["instagram"].conversion_rate == 0.0
    assert by["google"].won == 2 and by["google"].revenue == 30000
    assert by["google"].share_of_revenue == 85.7
    assert by["referral"].conversion_rate == 50.0
    assert by["google"].name == "Google (Search & Maps)"


def test_funnel(db_session, tiny):
    f = calc.funnel(calc.load_leads(db_session, tiny, 90))
    reached = {s.stage: s.reached for s in f.steps}
    assert reached == {"new": 10, "contacted": 9, "quoted": 4, "booked": 3, "won": 3}
    assert f.lost == 4


def test_reply_speed(db_session, tiny):
    t = calc.timing(calc.load_leads(db_session, tiny, 90))
    by = {b.reply_speed: b for b in t.conversion_by_reply_speed}
    assert by["under 15 min"].leads == 2 and by["under 15 min"].won == 2       # both won
    assert by["4-24 hours"].leads == 4 and by["4-24 hours"].won == 0           # all lost
    assert sum(t.leads_by_hour.values()) == 10
    assert sum(t.leads_by_day.values()) == 10


def test_services(db_session, tiny):
    svcs = calc.services(calc.load_leads(db_session, tiny, 90))
    assert svcs[0].service == "Facial"         # ₹20,000 beats Haircut's ₹15,000: sorted by money
    haircut = next(s for s in svcs if s.service == "Haircut")
    assert haircut.leads == 9 and haircut.revenue == 15000


def test_trend_adds_up(db_session, tiny):
    weeks = calc.trend(calc.load_leads(db_session, tiny, 90))
    assert sum(w.leads for w in weeks) == 10
    assert sum(w.revenue for w in weeks) == 35000
    assert [w.week_start for w in weeks] == sorted(w.week_start for w in weeks)


def test_highlights_find_the_story(db_session, tiny):
    notes = " ".join(calc.summary(db_session, tiny).highlights)
    assert "Instagram brings the most enquiries" in notes
    assert "Google (Search & Maps) brings the most money" in notes
    assert "1 enquiries never got a reply" in notes
    assert "1 hot leads are still open" in notes
    assert "best channel" not in notes      # Instagram earned ₹0: it must never be called the best


def test_shorter_window(db_session, tiny):
    assert calc.overview(calc.load_leads(db_session, tiny, 7), 7).leads == 5     # 3, 2, 5, 4 and 1 days old


def test_empty_business(db_session):
    biz = Business(name="Brand New Cafe", industry="cafe")
    db_session.add(biz)
    db_session.commit()
    s = calc.summary(db_session, biz.id)
    assert s.overview.leads == 0 and s.overview.conversion_rate == 0.0
    assert s.highlights == ["No enquiries in this period yet."]


# ----- Endpoints ---------------------------------------------------------------------
@pytest.mark.parametrize("part", ["summary", "overview", "sources", "funnel", "timing", "services", "trend"])
def test_every_endpoint_works(client, part):
    r = client.get(f"/analytics/{part}", params={"business_id": 1, "days": 90})
    assert r.status_code == 200


def test_summary_endpoint_matches_demo_data(client):
    s = client.get("/analytics/summary", params={"business_id": 1}).json()
    assert s["overview"]["leads"] == sum(x["leads"] for x in s["sources"])
    assert s["overview"]["revenue"] == sum(x["revenue"] for x in s["sources"])
    assert s["highlights"]


def test_unknown_business(client):
    assert client.get("/analytics/summary", params={"business_id": 999}).status_code == 404


def test_days_limits(client):
    assert client.get("/analytics/overview", params={"business_id": 1, "days": 0}).status_code == 422
    assert client.get("/analytics/overview", params={"business_id": 1, "days": 400}).status_code == 422
