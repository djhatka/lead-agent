"""
Strategy agent - "so what should I DO this week?"

Reads the analyst's findings and the presence checklist, and picks the
3 actions that will bring the most customers for the least effort.
Each action says why (with a number) and how hard it is.

Same 4-part pattern: form → brief → mock rules → run.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class Action(BaseModel):
    action: str = Field(max_length=120, description="What to do, starting with a verb")
    why: str = Field(max_length=220, description="The reason, with a number from the facts")
    effort: Literal["low", "medium", "high"]


class StrategyAnswer(BaseModel):
    top_actions: list[Action] = Field(min_length=1, max_length=3)


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You are a growth coach for a small local business owner in India who is busy and not technical. "
    "From the findings and checklist, choose the 3 actions that will bring the most paying customers "
    "this week for the least effort. Fix leaks first (unanswered or slow replies, waiting hot leads), "
    "then double down on what earns money, then fix weak platforms. Be concrete: what exactly to do. "
    "Every 'why' must use a number from the facts. Never suggest paid tools or hiring."
)


# 3. The mock: a priority list of rules --------------------------------------------
def mock_strategy(f: dict, findings: dict, checklist: list[dict]) -> dict:
    tw, actions = f["this_week"], []
    warn = {c["item"]: c for c in checklist if c["status"] != "ok"}

    if tw["never_replied"]:
        actions.append({"action": f"Reply today to the {tw['never_replied']} unanswered enquiries",
                        "why": "Every unanswered enquiry is a customer who may already be at a competitor.",
                        "effort": "low"})
    if tw["hot_waiting"]:
        actions.append({"action": f"Call the {tw['hot_waiting']} hot leads first thing tomorrow",
                        "why": "Hot leads scored 70+: they are the most likely to buy.", "effort": "low"})
    rep = f.get("reputation") or {}
    if rep.get("needs_attention"):
        n = rep["needs_attention"]
        actions.append({"action": f"Reply to the {n} unhappy review{'s' if n > 1 else ''} today (drafts are ready)",
                        "why": "New customers read bad reviews first; a calm reply shows you care.",
                        "effort": "low"})
    speed = f["ninety_days"]["reply_speed"]
    fast = speed[0]["conversion_rate"] if speed else 0
    slow = max((b["conversion_rate"] for b in speed[3:5]), default=0)
    if tw["median_reply_minutes"] and tw["median_reply_minutes"] > 60:
        actions.append({"action": "Reply to every new enquiry within 1 hour (set WhatsApp notifications on)",
                        "why": f"Fast replies converted {fast:.0f}% vs {slow:.0f}% for slow ones over 90 days.",
                        "effort": "low"})

    money = [p for p in f["content"]["by_pillar"] if p["posts"] >= 3 and p["revenue_per_post"]]
    if money:
        p = money[0]
        actions.append({"action": f"Post 2 more '{p['name']}' posts this week, fewer trend posts",
                        "why": f"'{p['name']}' posts earned ₹{p['revenue_per_post']:,} per post; trends earned ₹0.",
                        "effort": "medium"})

    for c in warn.values():
        if c["item"].startswith("Listed on"):
            actions.append({"action": f"Check your {c['item'][10:]} listing: photos, prices, timings",
                            "why": c["tip"], "effort": "medium"})
            break
    for c in warn.values():
        if "posts a week" in c["item"]:
            actions.append({"action": f"Catch up on {c['item'].split(':')[0]}", "why": c["tip"], "effort": "low"})
            break

    if not actions:
        actions.append({"action": "Keep the current rhythm and plan next week's posts",
                        "why": "No problems found this week.", "effort": "low"})
    return {"top_actions": actions[:3]}


# 4. The run -----------------------------------------------------------------------
def run_strategy(facts: dict, findings: dict, checklist: list[dict], facts_text: str) -> AIResult[StrategyAnswer]:
    prompt = (f"{facts_text}\n\nAnalyst findings:\n"
              + "\n".join(f"- [{x['impact']}] {x['title']}: {x['detail']}" for x in findings["findings"])
              + "\n\nPresence checklist:\n"
              + "\n".join(f"- [{c['status']}] {c['item']}: {c['tip']}" for c in checklist))
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=StrategyAnswer,
                         mock=lambda: mock_strategy(facts, findings, checklist), smart=True, max_tokens=900)
