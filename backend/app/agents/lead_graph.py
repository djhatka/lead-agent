"""
Workflow 1: "A new lead just arrived" - built with LangGraph.

LangGraph lets us draw a FLOWCHART of workers ("nodes") joined by arrows
("edges"). We build it once; then for every lead we hand it a clipboard
(state.py) and it runs the workers in order:

    START
      │
    intake ──► tone ──► scoring ──► priority
                                       │   (a "conditional edge": the path depends on the answer)
                         ┌─────────────┴─────────────┐
                    hot_alert                   normal_queue
                         └─────────────┬─────────────┘
                                     save  ──► END   (writes the results to the database)

Each node below is a small function: it reads the clipboard, calls one agent,
and returns what it found plus one diary entry for the "steps" log.
"""

import time

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.intake_agent import run_intake
from app.agents.nodes.priority_router import decide_priority
from app.agents.nodes.scoring_agent import LeadFacts, score_lead
from app.agents.nodes.sentiment_agent import run_tone
from app.agents.state import LeadState
from app.models import Lead, LeadAnalysis


def _rule_step(agent: str, start: float, output: dict) -> dict:
    """Diary entry for steps that use plain rules instead of AI."""
    return {"agent": agent, "mode": "rules", "model": None,
            "ms": int((time.perf_counter() - start) * 1000), "tokens": 0, "output": output, "error": None}


# ---------------------------------------------------------------------------
# The nodes (workers)
# ---------------------------------------------------------------------------
def intake_node(state: LeadState) -> dict:
    biz = state["business"]
    result = run_intake(state["message"], biz["name"], biz["industry"], biz["services"])
    return {"intake": result.data.model_dump(), "steps": [result.log_entry("intake")]}


def tone_node(state: LeadState) -> dict:
    result = run_tone(state["message"], state.get("earlier_messages"))
    return {"tone": result.data.model_dump(), "steps": [result.log_entry("tone")]}


def scoring_node(state: LeadState) -> dict:
    intake = state["intake"]
    result = score_lead(LeadFacts(
        source=state["source"],
        message=state["message"],
        has_phone=state.get("has_phone", False),
        has_name=state.get("has_name", False) or bool(intake.get("customer_name")),
        service=intake.get("service"),
        details=intake.get("details", {}),
        inbound_messages=len(state.get("earlier_messages", [])) + 1,
        sentiment=state["tone"]["sentiment"],
        industry=state["business"]["industry"],
    ))
    score = {"score": result.score, "breakdown": result.breakdown, "reason": result.reason}
    entry = result.ai.log_entry("scoring")
    entry["output"] = score | {"intent": result.ai.data.intent}
    return {"score": score, "steps": [entry]}


def priority_node(state: LeadState) -> dict:
    start = time.perf_counter()
    priority, reason = decide_priority(state["score"]["score"], state["tone"]["sentiment"])
    return {"priority": priority, "priority_reason": reason,
            "steps": [_rule_step("priority", start, {"priority": priority, "reason": reason})]}


def choose_path(state: LeadState) -> str:
    """Used by the conditional edge: which arrow to follow after 'priority'."""
    return state["priority"]                        # "hot" or "normal"


def hot_alert_node(state: LeadState) -> dict:
    """Prepare an alert for the owner. (Task 14 shows it live on the dashboard.)"""
    start = time.perf_counter()
    who = state.get("lead_name") or state["intake"].get("customer_name") or "this customer"
    what = state["intake"].get("service") or "an enquiry"
    alert = f"🔥 Reply to {who} now: {what} (score {state['score']['score']}). {state['priority_reason']}"
    return {"alert": alert, "steps": [_rule_step("hot_alert", start, {"alert": alert})]}


def normal_queue_node(state: LeadState) -> dict:
    start = time.perf_counter()
    return {"alert": None, "steps": [_rule_step("normal_queue", start, {"queued": True})]}


def save_node(state: LeadState, config: RunnableConfig) -> dict:
    """Write the results into the database (the filing cabinet).

    The database session isn't on the clipboard; it's passed separately in
    `config`, because a database connection isn't "information" to share.
    """
    start = time.perf_counter()
    db = config["configurable"]["db"]
    lead = db.get(Lead, state["lead_id"])
    intake, tone, score = state["intake"], state["tone"], state["score"]

    # 1. The AI verdict: create it, or update it if the lead was analysed before
    analysis = lead.analysis or LeadAnalysis(lead_id=lead.id)
    analysis.sentiment = tone["sentiment"]
    analysis.sentiment_reason = tone["reason"]
    analysis.score = score["score"]
    analysis.score_reason = score["reason"]
    analysis.score_breakdown = score["breakdown"]
    analysis.priority = state["priority"]
    lead.analysis = analysis

    # 2. Fill in blanks on the lead card. Never overwrite what's already there.
    filled = []
    for field, value in (("name", intake.get("customer_name")), ("area", intake.get("area")),
                         ("service", intake.get("service"))):
        if value and not getattr(lead, field):
            setattr(lead, field, value)
            filled.append(field)
    new_details = {k: v for k, v in (intake.get("details") or {}).items() if k not in (lead.details or {})}
    if new_details:
        lead.details = {**(lead.details or {}), **new_details}    # new dict so the change is noticed
        filled.append("details")

    db.commit()
    return {"steps": [_rule_step("save", start, {"saved": True, "filled_in": filled})]}


# ---------------------------------------------------------------------------
# Drawing the flowchart
# ---------------------------------------------------------------------------
def build_lead_graph():
    graph = StateGraph(LeadState)

    graph.add_node("intake", intake_node)
    graph.add_node("tone", tone_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("priority", priority_node)
    graph.add_node("hot_alert", hot_alert_node)
    graph.add_node("normal_queue", normal_queue_node)
    graph.add_node("save", save_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "tone")
    graph.add_edge("tone", "scoring")
    graph.add_edge("scoring", "priority")
    graph.add_conditional_edges("priority", choose_path, {"hot": "hot_alert", "normal": "normal_queue"})
    graph.add_edge("hot_alert", "save")
    graph.add_edge("normal_queue", "save")
    graph.add_edge("save", END)

    return graph.compile()      # "compile" = check the drawing and make it runnable


# Built once when the app starts, then reused for every lead
LEAD_GRAPH = build_lead_graph()
