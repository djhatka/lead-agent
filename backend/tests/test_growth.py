"""
Checks for Workflow 2 - the weekly growth review (Task 16).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.agents.nodes.growth_analyst as analyst_module
from app.agents.growth_graph import GROWTH_GRAPH
from app.agents.llm import LLM
from app.agents.nodes.presence_auditor import audit, weak_platforms
from app.models import AgentRun, Business, GrowthReport, Lead
from app.services import growth_service
from app.services.growth_facts import collect

IST = timezone(timedelta(hours=5, minutes=30))


# ----- Facts (plain code) ---------------------------------------------------------------------------
def test_facts_add_up(db_session):
    f = collect(db_session, db_session.get(Business, 1))
    tw = f["this_week"]
    assert tw["leads"] == sum(s["leads"] for s in tw["sources"])
    assert tw["revenue"] == sum(s["revenue"] for s in tw["sources"])
    assert set(f["content"]["targets"]) == {"instagram", "facebook", "google"}
    assert {p["key"] for p in f["industry_platforms"]} == {"cultfit", "fitpass"}     # gym-specific apps


# ----- Presence auditor (rules) ---------------------------------------------------------------------
def test_audit_flags_problems():
    facts = {
        "this_week": {"never_replied": 3, "median_reply_minutes": 200, "hot_waiting": 2},
        "content": {"targets": {"instagram": 3, "google": 1}, "accounts": ["instagram"],
                    "posted_this_week": {"instagram": 1}, "planned_next_7_days": []},
        "industry_platforms": [{"key": "practo", "name": "Practo", "brings_leads": False}],
        "ninety_days": {"sources": [], "conversion_rate": 20},
    }
    items = {c["item"]: c["status"] for c in audit(facts)}
    assert items["Instagram: 3+ posts a week"] == "warn"
    assert items["Google (Search & Maps) account"] == "missing"
    assert items["Every enquiry answered"] == "warn"
    assert items["Reply within 1 hour"] == "warn"
    assert items["Hot leads followed up"] == "warn"
    assert items["Listed on Practo"] == "missing"
    assert set(weak_platforms(facts)) == {"instagram", "google"}


# ----- The whole workflow -----------------------------------------------------------------------------
def test_graph_runs_analyst_and_presence_in_parallel():
    edges = {(e.source, e.target) for e in GROWTH_GRAPH.get_graph().edges}
    assert {("collect", "analyst"), ("collect", "presence"),
            ("analyst", "strategist"), ("presence", "strategist")} <= edges


def test_review_creates_a_report(db_session):
    run, report = growth_service.run_review(db_session, db_session.get(Business, 1))
    assert run.status == "success" and run.workflow == "growth"
    agents = [s["agent"] for s in run.steps]
    assert agents[0] == "collect_facts" and agents[-1] == "save"
    assert {"growth_analyst", "presence_auditor", "strategist", "report_writer"} <= set(agents)

    assert report.agent_run_id == run.id
    assert 1 <= len(report.top_actions) <= 3
    assert all(a["action"] and a["why"] for a in report.top_actions)
    assert report.presence_audit and report.stats["findings"]
    assert "Iron Pulse Fitness" in report.summary
    assert "kaam" in report.summary                       # the gym's Hinglish voice


def test_report_numbers_match_the_facts(db_session):
    _, report = growth_service.run_review(db_session, db_session.get(Business, 2))
    tw = report.stats["this_week"]
    assert f"₹{tw['revenue']:,}" in report.stats["headline"]


def test_unanswered_enquiries_become_action_one(db_session):
    biz = db_session.get(Business, 3)
    lead = Lead(business_id=3, source="whatsapp", name="Test", phone="+919811000123",
                first_message="hi", created_at=datetime.now(timezone.utc) - timedelta(hours=3))
    db_session.add(lead)
    db_session.commit()
    _, report = growth_service.run_review(db_session, biz)
    assert "unanswered" in report.top_actions[0]["action"]


def test_broken_agent_is_logged(db_session, monkeypatch):
    monkeypatch.setattr("app.agents.growth_graph.run_analyst", lambda *a: 1 / 0)
    run, report = growth_service.run_review(db_session, db_session.get(Business, 1))
    assert run.status == "failed" and report is None and "ZeroDivisionError" in run.error


def test_real_ai_analyst_is_used(db_session, monkeypatch):
    answer = {"headline": "Strong week: ₹12,700", "findings": [
        {"title": "Google brings the money", "detail": "36% of revenue", "impact": "good"}]}
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)], usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(analyst_module, "get_llm", lambda: LLM(client=fake, enabled=True))
    run, report = growth_service.run_review(db_session, db_session.get(Business, 1))
    assert report.stats["headline"] == "Strong week: ₹12,700"
    assert next(s for s in run.steps if s["agent"] == "growth_analyst")["mode"] == "real"


# ----- Monday 9am automatic reviews -----------------------------------------------------------------------
def test_weekly_reviews_only_on_monday_morning(db_session):
    monday_8am = datetime(2026, 10, 19, 8, 0, tzinfo=IST)
    monday_10am = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
    tuesday = datetime(2026, 10, 20, 10, 0, tzinfo=IST)
    assert growth_service.weekly_reviews_due(db_session, now=monday_8am) == 0
    assert growth_service.weekly_reviews_due(db_session, now=tuesday) == 0
    assert growth_service.weekly_reviews_due(db_session, now=monday_10am) == 3        # one per business
    assert growth_service.weekly_reviews_due(db_session, now=monday_10am) == 0        # not twice


# ----- Endpoints ---------------------------------------------------------------------------------------------
def test_review_endpoints(client):
    result = client.post("/growth/review", params={"business_id": 2}).json()
    assert result["status"] == "success"
    report_id = result["report"]["id"]
    assert client.get("/growth/reports", params={"business_id": 2}).json()[0]["id"] == report_id
    assert client.get(f"/growth/reports/{report_id}").json()["top_actions"]
    text = client.get(f"/growth/reports/{report_id}/whatsapp").text
    assert "Gloss Garage Detailing" in text and "*" in text            # WhatsApp bold


def test_workflow_diagram(client):
    assert "presence" in client.get("/growth/workflow").text


def test_missing_report(client):
    assert client.get("/growth/reports/999").status_code == 404


def test_no_sales_week_is_not_called_revenue_up():
    from app.agents.nodes.growth_analyst import mock_analyst
    facts = {"this_week": {"leads": 8, "won": 0, "revenue": 0, "never_replied": 0, "median_reply_minutes": 30},
             "last_week": {"leads": 5, "won": 0, "revenue": 0}, "change": {"leads": 60.0, "revenue": None},
             "ninety_days": {"sources": [], "conversion_rate": 20}, "content": {"by_pillar": []}}
    titles = [f["title"] for f in mock_analyst(facts)["findings"]]
    assert "Revenue up" not in titles and "No sales closed this week" in titles
