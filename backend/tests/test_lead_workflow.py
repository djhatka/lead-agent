"""
Checks for Workflow 1 - the LangGraph lead workflow (Task 10).

The plan's test: send a webhook → within moments the lead has a score,
a tone and a priority saved, and the AI diary shows every step.
"""

import json
from pathlib import Path

import pytest

from app.agents.lead_graph import LEAD_GRAPH
from app.agents.nodes.priority_router import decide_priority
from app.models import AgentRun, Lead
from app.services.lead_pipeline import analyze_lead

SAMPLES = Path(__file__).resolve().parents[1] / "seed" / "sample_payloads"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


# ----- The flowchart itself -------------------------------------------------------------------
def test_graph_has_all_workers():
    nodes = set(LEAD_GRAPH.get_graph().nodes)
    assert {"intake", "tone", "scoring", "priority", "hot_alert", "normal_queue", "save"} <= nodes


@pytest.mark.parametrize("score, sentiment, expected", [
    (75, "casual", "hot"),        # high score
    (45, "frustrated", "hot"),    # annoyed customer
    (66, "urgent", "hot"),        # wants it soon
    (60, "casual", "normal"),
    (60, "urgent", "normal"),     # urgent, but not likely enough to buy
])
def test_priority_rules(score, sentiment, expected):
    assert decide_priority(score, sentiment)[0] == expected


# ----- Running the workflow on one lead ---------------------------------------------------------
def test_workflow_saves_analysis(db_session):
    lead_id = db_session.query(Lead.id).first()[0]
    run = analyze_lead(db_session, lead_id)
    assert run.status == "success" and run.finished_at is not None
    agents = [step["agent"] for step in run.steps]
    assert agents[:4] == ["intake", "tone", "scoring", "priority"]
    assert agents[-1] == "save"
    assert ("hot_alert" in agents) != ("normal_queue" in agents)        # exactly one path taken

    lead = db_session.get(Lead, lead_id)
    assert 1 <= lead.analysis.score <= 100
    assert lead.analysis.sentiment in ("urgent", "casual", "frustrated")
    assert lead.analysis.priority in ("hot", "normal")
    assert lead.analysis.score_breakdown["Starting points"] == 10


def test_running_twice_updates_not_duplicates(db_session):
    lead_id = db_session.query(Lead.id).first()[0]
    analyze_lead(db_session, lead_id)
    analyze_lead(db_session, lead_id)
    lead = db_session.get(Lead, lead_id)
    assert lead.analysis is not None
    assert db_session.query(AgentRun).filter_by(lead_id=lead_id).count() == 2      # two diary entries


def test_broken_agent_is_logged_not_crashing(db_session, monkeypatch):
    import app.agents.lead_graph as graph_module
    monkeypatch.setattr(graph_module, "run_tone", lambda *a, **k: 1 / 0)       # make an agent crash
    lead_id = db_session.query(Lead.id).first()[0]
    run = analyze_lead(db_session, lead_id)
    assert run.status == "failed" and "ZeroDivisionError" in run.error


# ----- The full journey: webhook → background AI → saved results -------------------------------
def test_whatsapp_lead_gets_analysed_automatically(client):
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json")).json()
    assert r["new_leads"] == 1 and r["ai_analysis_queued"] == 1
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["analysis"] is not None                       # the background job already ran
    assert lead["service"] == "Zumba"                         # filled in by the Intake agent
    assert lead["details"]["batch"] == "evening"
    assert lead["analysis"]["sentiment"] == "urgent"          # "this week itself"


def test_hot_lead_from_instagram(client):
    payload = sample("instagram_dm.json")
    payload["entry"][0]["messaging"][0]["message"]["text"] = \
        "Sent 3 messages, no reply! Need ceramic coating on my Creta today, can I book a slot?"
    r = client.post("/webhooks/instagram", params={"business_id": 2}, json=payload).json()
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["analysis"]["priority"] == "hot"
    assert lead["analysis"]["sentiment"] == "frustrated"
    assert lead["details"]["car_model"] == "Hyundai Creta"


def test_duplicates_are_not_reanalysed(client):
    client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json"))
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json")).json()
    assert r["duplicates"] == 1 and r["ai_analysis_queued"] == 0


def test_manual_lead_is_analysed_too(client):
    lead = client.post("/leads", json={"business_id": 3, "source": "walk_in", "name": "Meera",
                                       "first_message": "Severe tooth pain, need root canal today. Can I get an appointment now?"}).json()
    lead = client.get(f"/leads/{lead['id']}").json()
    assert lead["analysis"]["priority"] == "hot"


def test_existing_fields_are_not_overwritten(client):
    lead = client.post("/leads", json={"business_id": 2, "source": "walk_in", "name": "Kabir",
                                       "first_message": "I'm Rohan, need PPF"}).json()
    assert client.get(f"/leads/{lead['id']}").json()["name"] == "Kabir"


# ----- Endpoints ---------------------------------------------------------------------------------
def test_analyze_now_endpoint(client):
    run = client.post("/leads/5/analyze").json()
    assert run["status"] == "success" and run["lead_id"] == 5
    assert [s["agent"] for s in run["steps"]][0] == "intake"


def test_analyze_all_then_filter_hot(client):
    result = client.post("/ai/analyze-all", params={"business_id": 2}).json()
    assert result["analysed"] == 40 and result["remaining_without_analysis"] == 0 and result["failed"] == 0
    hot = client.get("/leads", params={"business_id": 2, "priority": "hot"}).json()
    assert hot["total"] == result["hot"]
    ranked = client.get("/leads", params={"business_id": 2, "sort": "score"}).json()["items"]
    scores = [l["analysis"]["score"] for l in ranked]
    assert scores == sorted(scores, reverse=True)                # best leads first


def test_agent_runs_diary(client):
    client.post("/leads/7/analyze")
    runs = client.get("/agent-runs", params={"business_id": 1, "lead_id": 7}).json()
    assert len(runs) == 1 and runs[0]["workflow"] == "lead"
    one = client.get(f"/agent-runs/{runs[0]['id']}").json()
    assert one["steps"][0]["mode"] == "mock"


def test_workflow_diagram(client):
    text = client.get("/ai/lead-workflow").text
    assert "intake" in text and "hot_alert" in text
