"""
The shared clipboard ("state") that travels through the AI workflow.

LangGraph passes ONE clipboard from agent to agent. Each agent:
    1. reads what it needs from the clipboard
    2. does its job
    3. returns ONLY the parts it wants to add or change
LangGraph then updates the clipboard and hands it to the next agent.

    START ─► intake ─► tone ─► scoring ─► priority ─┬─► hot_alert ────┬─► save ─► END
                                                    └─► normal_queue ─┘

So by the end, the clipboard holds everything every agent worked out.
"""

import operator
from typing import Annotated, Optional, TypedDict


class LeadState(TypedDict, total=False):
    # --- Filled in before the workflow starts --------------------------------
    lead_id: int
    business: dict                 # {"name": ..., "industry": ..., "services": [...]}
    source: str                    # "whatsapp", "google"...
    message: str                   # the customer's latest message
    earlier_messages: list[str]    # what they said before (for context)
    has_phone: bool
    has_name: bool
    lead_name: Optional[str]       # the name already on the lead card, if any

    # --- Added by the agents, one by one ---------------------------------------
    intake: dict                   # Intake agent: service, details, name, area, summary...
    tone: dict                     # Tone agent: sentiment, reason, signals
    score: dict                    # Scoring agent: score, breakdown, reason
    priority: str                  # Priority router: "hot" or "normal"
    priority_reason: str
    alert: Optional[str]           # Hot alert: the message shown to the owner

    # --- The diary ----------------------------------------------------------------
    # Every agent ADDS one entry here. "Annotated[list, operator.add]" tells
    # LangGraph: "don't replace this list, keep adding to it".
    steps: Annotated[list[dict], operator.add]


class GrowthState(TypedDict, total=False):
    """The clipboard for Workflow 2: the weekly growth review.

        START ─► collect ─┬─► analyst ──┬─► strategist ─► writer ─► save ─► END
                          └─► presence ─┘
    analyst and presence work AT THE SAME TIME (they don't need each other);
    the strategist waits for both.
    """

    business_id: int
    facts: dict                    # every number, calculated by code (growth_facts.py)
    facts_text: str                # the same facts as text, for the AI to read
    findings: dict                 # Growth Analyst: headline + findings
    checklist: list[dict]          # Presence Auditor: ok / warn / missing items
    weak_platforms: list[str]
    strategy: dict                 # Strategist: top 3 actions
    report: str                    # Report Writer: the owner's message
    report_id: int                 # the saved growth_reports row
    steps: Annotated[list[dict], operator.add]
