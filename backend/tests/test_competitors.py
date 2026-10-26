"""
Task 35 checks: competitor watch (3-5 nearby rivals, rating/review tracking, alerts).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Competitor, CompetitorAlert
from app.services import competitor_service

GYM = 1
NOW = datetime.now(timezone.utc)


def _utc(dt):
    """SQLite drops tzinfo on the way out of the database even for a DateTime(timezone=True)
    column, so a value read back via db_session.refresh() can come back naive."""
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _clear(db):
    for a in db.scalars(select(CompetitorAlert).where(CompetitorAlert.business_id == GYM)):
        db.delete(a)
    for c in db.scalars(select(Competitor).where(Competitor.business_id == GYM)):
        db.delete(c)
    db.commit()


# ---------------------------------------------------------------------------
# Adding and the 5-competitor limit
# ---------------------------------------------------------------------------
def test_add_runs_the_first_check_immediately(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Fitness First", "Dwarka")
    assert competitor.area == "Dwarka"
    assert competitor.rating is not None            # mock mode: a number came back right away
    assert competitor.review_count is not None
    assert competitor.last_checked_at is not None
    assert competitor.previous_rating is None        # nothing to compare against on the first check


def test_at_most_five_competitors(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    for i in range(competitor_service.MAX_COMPETITORS):
        competitor_service.add(db_session, gym, f"Rival {i}", "Dwarka")
    with pytest.raises(ValueError):
        competitor_service.add(db_session, gym, "One too many", "Dwarka")


def test_mock_numbers_are_stable_across_checks_without_a_new_week(db_session):
    """Re-checking right away (same week) shouldn't make the numbers jump around."""
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Steady Gym", "Dwarka")
    first_rating, first_reviews = competitor.rating, competitor.review_count
    competitor_service.check(db_session, competitor)
    assert competitor.rating == first_rating
    assert competitor.review_count == first_reviews


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def test_new_reviews_raise_an_alert(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Growing Gym", "Dwarka")

    competitor.previous_review_count = competitor.review_count
    competitor.review_count += 7
    competitor_service._raise_alerts(db_session, competitor)

    alerts = competitor_service.recent_alerts(db_session, GYM)
    assert any(a.kind == "new_reviews" and "7 new review" in a.message for a in alerts)


def test_rating_move_raises_an_alert_small_move_does_not(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Wobbly Gym", "Dwarka")

    # A tiny move: no alert.
    competitor.previous_rating = 4.0
    competitor.rating = 4.05
    competitor_service._raise_alerts(db_session, competitor)
    assert competitor_service.recent_alerts(db_session, GYM) == []

    # A real move: an alert, in the right direction.
    competitor.previous_rating = 4.0
    competitor.rating = 3.5
    competitor_service._raise_alerts(db_session, competitor)
    alerts = competitor_service.recent_alerts(db_session, GYM)
    assert any(a.kind == "rating_down" and "moved down to 3.5" in a.message for a in alerts)


def test_first_check_ever_raises_no_alert(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Brand New Watch", "Dwarka")
    assert competitor_service.recent_alerts(db_session, GYM) == []


# ---------------------------------------------------------------------------
# The weekly scheduler job
# ---------------------------------------------------------------------------
def test_weekly_checks_due_rechecks_stale_competitors_only(db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    stale = competitor_service.add(db_session, gym, "Stale Rival", "Dwarka")
    stale.last_checked_at = NOW - timedelta(days=10)
    fresh = competitor_service.add(db_session, gym, "Fresh Rival", "Dwarka")
    fresh.last_checked_at = NOW - timedelta(hours=1)
    db_session.commit()

    checked = competitor_service.weekly_checks_due(db_session, now=NOW)
    assert checked == 1

    db_session.refresh(stale)
    db_session.refresh(fresh)
    assert _utc(stale.last_checked_at) > NOW - timedelta(days=1)
    assert _utc(fresh.last_checked_at) == NOW - timedelta(hours=1)   # untouched


def test_weekly_checks_skip_businesses_with_no_usable_plan(db_session, monkeypatch):
    from app.models import Business
    from app.services import billing_service
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Paused Plan Rival", "Dwarka")
    competitor.last_checked_at = NOW - timedelta(days=10)
    db_session.commit()

    monkeypatch.setattr(billing_service, "paused_business_ids", lambda db: {GYM})
    checked = competitor_service.weekly_checks_due(db_session, now=NOW)
    assert checked == 0


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------
def test_add_list_check_and_remove_via_the_api(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)

    r = raw_client.post("/competitors", params={"business_id": GYM}, json={"name": "API Rival", "area": "Dwarka"},
                        headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "API Rival"
    assert body["mode"] == "mock"              # no DATAFORSEO_LOGIN set in tests
    competitor_id = body["id"]

    r = raw_client.get("/competitors", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200
    assert any(c["id"] == competitor_id for c in r.json())

    r = raw_client.post(f"/competitors/{competitor_id}/check", headers=headers)
    assert r.status_code == 200
    assert r.json()["last_checked_at"] is not None

    r = raw_client.delete(f"/competitors/{competitor_id}", headers=headers)
    assert r.status_code == 204
    r = raw_client.get("/competitors", params={"business_id": GYM}, headers=headers)
    assert all(c["id"] != competitor_id for c in r.json())


def test_sixth_competitor_is_rejected_by_the_api(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)
    for i in range(competitor_service.MAX_COMPETITORS):
        r = raw_client.post("/competitors", params={"business_id": GYM}, json={"name": f"Rival {i}"}, headers=headers)
        assert r.status_code == 201, r.text
    r = raw_client.post("/competitors", params={"business_id": GYM}, json={"name": "One too many"}, headers=headers)
    assert r.status_code == 400


def test_competitors_endpoint_needs_login(raw_client):
    r = raw_client.get("/competitors", params={"business_id": GYM})
    assert r.status_code == 401


def test_competitors_block_other_businesses(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)                                 # gym owner
    r = raw_client.get("/competitors", params={"business_id": 2}, headers=headers)   # the garage
    assert r.status_code == 404


def test_alerts_endpoint_returns_recent_alerts(raw_client, db_session):
    from app.models import Business
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    competitor = competitor_service.add(db_session, gym, "Alert Rival", "Dwarka")
    competitor.previous_review_count = competitor.review_count
    competitor.review_count += 3
    competitor_service._raise_alerts(db_session, competitor)

    headers = login(raw_client)
    r = raw_client.get("/competitors/alerts", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200
    assert any("3 new review" in a["message"] for a in r.json())
