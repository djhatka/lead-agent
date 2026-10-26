"""
Checks for the scheduler, (mock) publishing and the performance tracker (Task 15).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Business, Post
from app.services import planner_service, scheduler_service, writer_service
from app.services.publishers import MockPublisher, PublishError

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def fresh_clock():
    """Read the clock when EACH test starts (not once when the file loads):
    a long test run must never push a 'one minute from now' time into the past."""
    global NOW
    NOW = datetime.now(timezone.utc)
TOMORROW = datetime.now(IST).date() + timedelta(days=1)


@pytest.fixture
def drafts(db_session):
    """Plan + write the gym's week → a list of ready drafts."""
    biz = db_session.get(Business, 1)
    planner_service.plan_week(db_session, biz, TOMORROW)
    _, posts, _ = writer_service.write_week(db_session, biz, TOMORROW)
    return posts


# ----- Scheduling --------------------------------------------------------------------------------
def test_schedule_a_draft(db_session, drafts):
    post = scheduler_service.schedule_post(db_session, drafts[0], NOW + timedelta(hours=2))
    assert post.status == "scheduled"


def test_cannot_schedule_in_the_past(db_session, drafts):
    with pytest.raises(ValueError, match="future"):
        scheduler_service.schedule_post(db_session, drafts[0], NOW - timedelta(minutes=1))


def test_cannot_schedule_without_caption(db_session):
    idea = Post(business_id=1, account_id=1, platform="instagram", kind="photo", status="idea", caption="")
    db_session.add(idea)
    db_session.commit()
    with pytest.raises(ValueError, match="caption"):
        scheduler_service.schedule_post(db_session, idea, NOW + timedelta(hours=1))


def test_unschedule(db_session, drafts):
    scheduler_service.schedule_post(db_session, drafts[0], NOW + timedelta(hours=2))
    assert scheduler_service.unschedule(db_session, drafts[0]).status == "draft"


# ----- Publishing ----------------------------------------------------------------------------------
def test_due_posts_get_published(db_session, drafts):
    soon, later = drafts[0], drafts[1]
    scheduler_service.schedule_post(db_session, soon, NOW + timedelta(minutes=5))
    scheduler_service.schedule_post(db_session, later, NOW + timedelta(days=3))
    published, failed = scheduler_service.publish_due(db_session, now=NOW + timedelta(minutes=10))
    assert soon.status == "published" and soon.external_id.startswith("mock_")
    assert later.status == "scheduled"                     # not its time yet
    assert failed == 0 and published >= 1


def test_failed_publish_is_explained_and_can_be_retried(db_session, drafts, monkeypatch):
    def broken(self, post, account):
        raise PublishError("Instagram is down")
    monkeypatch.setattr(MockPublisher, "publish", broken)
    post = drafts[0]
    scheduler_service.schedule_post(db_session, post, NOW + timedelta(minutes=1))
    scheduler_service.publish_due(db_session, now=NOW + timedelta(minutes=2))
    assert post.status == "failed" and "down" in post.publish_error
    monkeypatch.undo()
    scheduler_service.schedule_post(db_session, post, NOW + timedelta(hours=1))   # owner reschedules
    assert post.status == "scheduled" and post.publish_error == ""


def test_publish_now(db_session, drafts):
    post = scheduler_service.publish_now(db_session, drafts[0])
    assert post.status == "published" and post.published_at is not None
    with pytest.raises(ValueError):
        scheduler_service.publish_now(db_session, post)    # not twice


# ----- Performance tracker ---------------------------------------------------------------------------
def test_numbers_grow_over_the_first_days(db_session, drafts):
    post = scheduler_service.publish_now(db_session, drafts[0])
    publisher, account = MockPublisher(), post.account
    post.published_at = NOW - timedelta(hours=6)
    early = publisher.fetch_stats(post, account)["reach"]
    post.published_at = NOW - timedelta(days=3)
    later = publisher.fetch_stats(post, account)["reach"]
    assert later > early > 0


def test_refresh_stats_updates_recent_posts_and_never_lowers(db_session):
    recent = db_session.query(Post).filter(Post.business_id == 1, Post.status == "published",
                                           Post.published_at >= NOW - timedelta(days=30)).first()
    recent.reach = 10**6                                  # pretend we already saw a very high number
    db_session.commit()
    updated = scheduler_service.refresh_stats(db_session, business_id=1, force=True)
    assert updated > 0
    assert recent.reach == 10**6                          # numbers only go up
    assert recent.stats_updated_at is not None


def test_refresh_skips_recently_refreshed(db_session):
    scheduler_service.refresh_stats(db_session, business_id=1, force=True)
    assert scheduler_service.refresh_stats(db_session, business_id=1) == 0     # all fresh


# ----- The background cycle ---------------------------------------------------------------------------
def test_run_cycle(db_session, drafts, monkeypatch):
    now = datetime.now(timezone.utc)                                   # the clock right now, not when the file loaded
    scheduler_service.schedule_post(db_session, drafts[0], now + timedelta(seconds=30))
    drafts[0].scheduled_for = now - timedelta(seconds=1)              # time passes...
    db_session.commit()

    class KeepOpen:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass
    monkeypatch.setattr(scheduler_service, "SESSION_FACTORY", KeepOpen)
    scheduler_service.run_cycle_in_background()
    assert drafts[0].status == "published"
    assert scheduler_service.LAST_RUN["published"] >= 1


# ----- Endpoints --------------------------------------------------------------------------------------
def test_schedule_endpoints(client, drafts):
    pid = drafts[0].id
    when = (datetime.now(IST) + timedelta(days=1)).replace(hour=19, minute=0).isoformat()
    r = client.post(f"/posts/{pid}/schedule", json={"scheduled_for": when})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    status = client.get("/scheduler/status").json()
    assert status["scheduled_posts"] >= 1 and status["next_post_at"]
    assert client.post(f"/posts/{pid}/unschedule").json()["status"] == "draft"
    assert client.post(f"/posts/{pid}/publish-now").json()["status"] == "published"


def test_schedule_endpoint_rejects_past(client, drafts):
    r = client.post(f"/posts/{drafts[0].id}/schedule", json={"scheduled_for": "2020-01-01T10:00:00+05:30"})
    assert r.status_code == 400


def test_run_and_refresh_endpoints(client):
    assert "published" in client.post("/scheduler/run").json()
    assert client.post("/content/refresh-stats", params={"business_id": 1}).json()["posts_updated"] >= 0


@pytest.mark.parametrize("by", ["revenue", "enquiries", "reach", "engagement"])
def test_top_posts(client, by):
    posts = client.get("/content/top-posts", params={"business_id": 1, "by": by, "days": 90}).json()
    assert 0 < len(posts) <= 5
    field = {"revenue": "revenue", "enquiries": "enquiries", "reach": "reach", "engagement": "engagement_rate"}[by]
    values = [p[field] for p in posts]
    assert values == sorted(values, reverse=True)
