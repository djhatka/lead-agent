"""
Workflow 2: "Weekly growth review" - built with LangGraph.

    START
      │
    collect            plain code: every number (growth_facts.py)
      ├──────────────┐
    analyst       presence      ← these two run AT THE SAME TIME
      └──────┬───────┘
         strategist             waits for BOTH, then picks the top 3 actions
             │
           writer               the owner's WhatsApp-ready message
             │
            save ──► END        stored in growth_reports

New idea compared with Workflow 1: PARALLEL work. graph.add_edge(["analyst",
"presence"], "strategist") means "start the strategist only when both are done".
"""

import json
import time
from datetime import date

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.growth_analyst import run_analyst
from app.agents.nodes.presence_auditor import audit, weak_platforms
from app.agents.nodes.report_writer import run_report
from app.agents.nodes.strategy_agent import run_strategy
from app.agents.state import GrowthState
from app.models import Business, GrowthReport
from app.services.growth_facts import collect


def _rule_step(agent: str, start: float, output: dict) -> dict:
    return {"agent": agent, "mode": "rules", "model": None,
            "ms": int((time.perf_counter() - start) * 1000), "tokens": 0, "output": output, "error": None}


def collect_node(state: GrowthState, config: RunnableConfig) -> dict:
    start = time.perf_counter()
    db = config["configurable"]["db"]
    facts = collect(db, db.get(Business, state["business_id"]))
    text = "FACTS (all numbers calculated by code; use them as given):\n" + json.dumps(
        facts, indent=1, ensure_ascii=False, default=str)
    return {"facts": facts, "facts_text": text,
            "steps": [_rule_step("collect_facts", start, {"leads_this_week": facts["this_week"]["leads"]})]}


def analyst_node(state: GrowthState) -> dict:
    result = run_analyst(state["facts"], state["facts_text"])
    return {"findings": result.data.model_dump(), "steps": [result.log_entry("growth_analyst")]}


def presence_node(state: GrowthState) -> dict:
    start = time.perf_counter()
    checklist, weak = audit(state["facts"]), weak_platforms(state["facts"])
    problems = sum(1 for c in checklist if c["status"] != "ok")
    return {"checklist": checklist, "weak_platforms": weak,
            "steps": [_rule_step("presence_auditor", start, {"items": len(checklist), "problems": problems,
                                                             "weak_platforms": weak})]}


def strategist_node(state: GrowthState) -> dict:
    result = run_strategy(state["facts"], state["findings"], state["checklist"], state["facts_text"])
    return {"strategy": result.data.model_dump(), "steps": [result.log_entry("strategist")]}


def writer_node(state: GrowthState) -> dict:
    result = run_report(state["facts"], state["findings"], state["strategy"])
    return {"report": result.data.message, "steps": [result.log_entry("report_writer")]}


def save_node(state: GrowthState, config: RunnableConfig) -> dict:
    start = time.perf_counter()
    db = config["configurable"]["db"]
    facts = state["facts"]
    report = GrowthReport(
        business_id=state["business_id"],
        week_start=date.fromisoformat(facts["period"]["from"]),
        agent_run_id=config["configurable"].get("run_id"),
        summary=state["report"],
        stats={"headline": state["findings"]["headline"], "findings": state["findings"]["findings"],
               "this_week": facts["this_week"], "last_week": facts["last_week"], "change": facts["change"]},
        weak_platforms=state["weak_platforms"],
        presence_audit=state["checklist"],
        top_actions=state["strategy"]["top_actions"],
        content_plan=facts["content"]["planned_next_7_days"],
    )
    db.add(report)
    db.commit()
    return {"report_id": report.id, "steps": [_rule_step("save", start, {"report_id": report.id})]}


def build_growth_graph():
    graph = StateGraph(GrowthState)
    graph.add_node("collect", collect_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("presence", presence_node)
    graph.add_node("strategist", strategist_node)
    graph.add_node("writer", writer_node)
    graph.add_node("save", save_node)

    graph.add_edge(START, "collect")
    graph.add_edge("collect", "analyst")                 # these two edges start
    graph.add_edge("collect", "presence")                # two workers at once
    graph.add_edge(["analyst", "presence"], "strategist")  # wait for BOTH
    graph.add_edge("strategist", "writer")
    graph.add_edge("writer", "save")
    graph.add_edge("save", END)
    return graph.compile()


GROWTH_GRAPH = build_growth_graph()
