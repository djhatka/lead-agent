"""
Checks for content stats, the festival calendar and the Content Planner (Task 13).
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.agents.nodes.content_planner as planner
from app.agents.llm import LLM
from app.festivals import upcoming
from app.models import AgentRun, Business, Post
from app.services import planner_service
from app.services.content_stats import content_stats

IST = timezone(timedelta(hours=5, minutes=30))
TOMORROW = datetime.now(IST).date() + timedelta(days=1)


# ----- Festivals ------------------------------------------------------------------------------
def test_festival_dates():
    events = upcoming(date(2026, 11, 1), 7, "car_detailing")
    names = {e["name"] for e in events}
    assert {"Dhanteras", "Diwali"} <= names                      # 6 Nov and 8 Nov 2026
    assert "Karwa Chauth" not in names                           # salon/retail only, and it's 29 Oct


def test_festivals_only_for_the_right_industry():
    assert any(e["name"] == "World Oral Health Day" for e in upcoming(date(2027, 3, 15), 7, "clinic"))
    assert not any(e["name"] == "World Oral Health Day" for e in upcoming(date(2027, 3, 15), 7, "gym"))


# ----- Content stats ------------------------------------------------------------------------------
def test_content_stats_on_demo_data(db_session):
    stats = content_stats(db_session, 1)
    assert stats.published_posts > 30
    assert {g.name for g in stats.by_pillar} <= {"offer", "tips", "transformation", "trend",
                                                  "testimonial", "festival", "behind_the_scenes"}
    trend = next(g for g in stats.by_pillar if g.name == "trend")
    assert trend.avg_reach == max(g.avg_reach for g in stats.by_pillar)     # trends get the most reach...
    assert trend.revenue == 0                                                # ...but no money
    assert stats.by_kind[0].name == "reel"                                   # reels reach the most
    assert stats.findings


def test_content_stats_for_brand_new_business(db_session):
    biz = Business(name="New Cafe", industry="cafe")
    db_session.add(biz)
    db_session.commit()
    stats = content_stats(db_session, biz.id)
    assert stats.published_posts == 0 and "Not enough" in stats.findings[0]


# ----- The plan ---------------------------------------------------------------------------------------
def plan(db_session, business_id=1, start=TOMORROW):
    return planner_service.plan_week(db_session, db_session.get(Business, business_id), start)


def test_plan_week_saves_ideas(db_session):
    run, posts, strategy, skipped = plan(db_session)
    assert run.status == "success" and run.workflow == "content_plan"
    assert 4 <= len(posts) <= 10 and strategy
    for p in posts:
        assert p.status == "idea" and p.created_by == "ai"
        assert p.title and p.media_note and p.ai_reason
        assert p.campaign == f"post-{p.id}"
        day = p.scheduled_for.astimezone(IST).date()
        assert TOMORROW <= day < TOMORROW + timedelta(days=7)


def test_plan_uses_the_business_results(db_session):
    """The demo gym's best earner is 'offer' and trends earned nothing."""
    _, posts, strategy, _ = plan(db_session, 1)
    pillars = [p.pillar for p in posts]
    assert "offer" in pillars
    assert "trend" not in pillars
    assert any("₹" in p.ai_reason or "enquir" in p.ai_reason or "festival" in p.ai_reason.lower() for p in posts)


def test_plan_has_variety(db_session):
    _, posts, _, _ = plan(db_session, 2)
    titles = [p.title for p in posts]
    assert len(set(titles)) == len(titles)                      # no repeated post
    assert len({p.platform for p in posts}) >= 2               # not only Instagram


def test_plan_never_double_books(db_session):
    _, posts, _, _ = plan(db_session)
    owner_slots = {(p.scheduled_for.astimezone(IST).date(), p.platform)
                   for p in db_session.query(Post).filter_by(business_id=1, created_by="owner")
                   if p.scheduled_for and p.status in ("scheduled", "draft")}
    ai_slots = {(p.scheduled_for.astimezone(IST).date(), p.platform) for p in posts}
    assert not owner_slots & ai_slots


def test_replanning_replaces_ai_ideas_only(db_session):
    plan(db_session)
    first = db_session.query(Post).filter_by(business_id=1, status="idea", created_by="ai").count()
    plan(db_session)
    again = db_session.query(Post).filter_by(business_id=1, status="idea", created_by="ai").count()
    assert first == again                                       # replaced, not doubled
    assert db_session.query(Post).filter_by(business_id=1, status="idea", created_by="owner").count() == 1


def test_festival_offer_before_diwali(db_session):
    _, posts, strategy, _ = plan(db_session, 2, start=date(2026, 11, 2))
    diwali = [p for p in posts if "Diwali" in p.title or "Dhanteras" in p.title]
    assert diwali, [p.title for p in posts]
    assert any(p.pillar == "offer" for p in diwali)            # an OFFER, not only a greeting


def test_no_accounts_no_plan(db_session):
    biz = Business(name="Offline Shop", industry="retail")
    db_session.add(biz)
    db_session.commit()
    with pytest.raises(ValueError):
        planner_service.plan_week(db_session, biz, TOMORROW)
    assert db_session.query(AgentRun).filter_by(business_id=biz.id).one().status == "failed"


# ----- Real-AI path (fake Claude): its plan is safety-checked ---------------------------------------
def test_real_ai_plan_is_checked(db_session, monkeypatch):
    answer = {"strategy": "Focus on offers.", "posts": [
        {"day": 1, "time": "19:00", "platform": "instagram", "kind": "reel", "pillar": "offer",
         "title": "Big offer", "idea": "Show it", "why": "Offers earned ₹792 per post"},
        {"day": 2, "time": "19:00", "platform": "youtube", "kind": "video", "pillar": "tips",   # no YouTube account
         "title": "Video", "idea": "x", "why": "y"},
        {"day": 12, "time": "19:00", "platform": "facebook", "kind": "photo", "pillar": "tips",  # outside the week
         "title": "Late", "idea": "x", "why": "y"},
    ]}
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)], usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(planner, "get_llm", lambda: LLM(client=fake, enabled=True))
    run, posts, strategy, skipped = plan(db_session, 1, start=TOMORROW + timedelta(days=10))
    assert [p.title for p in posts] == ["Big offer"]
    assert len(skipped) == 2 and run.steps[0]["mode"] == "real"


# ----- Endpoints ------------------------------------------------------------------------------------
def test_plan_and_calendar_endpoints(client):
    result = client.post("/content/plan-week", params={"business_id": 3}).json()
    assert result["posts"] and result["mode"] == "mock"
    assert all(p["ai_reason"] for p in result["posts"])
    days = client.get("/content/calendar", params={"business_id": 3}).json()
    assert len(days) == 7
    ideas = [p for d in days for p in d["posts"] if p["status"] == "idea"]
    assert len(ideas) == len(result["posts"])


def test_calendar_shows_published_posts_too(client):
    week_ago = (datetime.now(IST).date() - timedelta(days=7)).isoformat()
    days = client.get("/content/calendar", params={"business_id": 1, "start": week_ago}).json()
    assert any(p["status"] == "published" for d in days for p in d["posts"])


def test_stats_and_events_endpoints(client):
    assert client.get("/content/stats", params={"business_id": 1}).json()["published_posts"] > 0
    assert client.get("/content/events", params={"business_id": 1, "days": 60}).status_code == 200


def test_cannot_plan_the_past(client):
    r = client.post("/content/plan-week", params={"business_id": 1, "start": "2020-01-01"})
    assert r.status_code == 400


def test_festive_offer_is_never_replaced_by_the_greeting():
    """Festival tomorrow, today already taken: the offer goes on the festival
    day and the greeting moves to Facebook (it must not overwrite the offer)."""
    from app.agents.nodes.content_planner import mock_plan
    stats = {"best_hour": 19, "by_pillar": []}
    context = {"stats": stats, "days": 7, "platforms": ["instagram", "facebook"], "top_services": ["Zumba"],
               "business": {"services": ["Zumba"]},
               "taken": [{"day": 0, "platform": "instagram", "title": "Owner's own post"}],
               "events": [{"date": "2026-10-20", "name": "Dussehra", "angle": "festive offer", "days_away": 1}]}
    posts = mock_plan(context)["posts"]
    day1 = {(p["platform"], p["pillar"]) for p in posts if p["day"] == 1}
    assert ("instagram", "offer") in day1 and ("facebook", "festival") in day1
    assert any("Dussehra special offer" in p["title"] for p in posts)

