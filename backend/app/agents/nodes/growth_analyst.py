"""
Growth Analyst agent - "what happened this week, and what does it mean?"

Reads the facts (growth_facts.py) and picks out the 3-6 findings that matter
most to the owner: good news, bad news, and the hidden patterns
("Instagram brings enquiries but not customers").

Same 4-part pattern: form → brief → mock rules → run.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class Finding(BaseModel):
    title: str = Field(max_length=90, description="Short headline, e.g. 'Google brings the money'")
    detail: str = Field(max_length=300, description="1-2 sentences with the actual numbers")
    impact: Literal["good", "bad", "neutral"]


class AnalystAnswer(BaseModel):
    headline: str = Field(max_length=140, description="One line summing up the week, with a number")
    findings: list[Finding] = Field(min_length=1, max_length=6)


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You are a business analyst for a small local business in India. You get this week's numbers, last "
    "week's, and the 90-day picture. Pick the 3-6 findings that matter most for growing sales. "
    "Use ONLY numbers you are given; never calculate new ones or guess. Prefer money and customers over "
    "likes. Mention reply speed and unanswered enquiries if they are a problem. Plain words, no jargon."
)


def _rupees(n: int) -> str:
    return f"₹{n:,}"


def _n(count: int, one: str, many: str) -> str:
    """1 sale / 2 sales."""
    return f"{count} {one if count == 1 else many}"


# 3. The mock: rules over the facts ------------------------------------------------
def mock_analyst(f: dict) -> dict:
    tw, lw, ch, ninety = f["this_week"], f["last_week"], f["change"], f["ninety_days"]
    findings = []

    rev_change = ch["revenue"]
    trend = f" ({'+' if rev_change >= 0 else ''}{rev_change:.0f}% vs last week)" if rev_change is not None else ""
    headline = (f"{_n(tw['leads'], 'enquiry', 'enquiries')}, {_n(tw['won'], 'sale', 'sales')} "
                f"and {_rupees(tw['revenue'])} this week{trend}.")

    if tw["leads"] and not tw["won"]:
        findings.append({"title": "No sales closed this week",
                         "detail": f"{_n(tw['leads'], 'enquiry', 'enquiries')} came in but none became a sale yet. "
                                   f"Follow up on open quotes.", "impact": "bad"})
    elif tw["revenue"] != lw["revenue"]:
        good = tw["revenue"] > lw["revenue"]
        findings.append({"title": "Revenue up" if good else "Revenue down",
                         "detail": f"{_rupees(tw['revenue'])} from {_n(tw['won'], 'sale', 'sales')} vs "
                                   f"{_rupees(lw['revenue'])} from {_n(lw['won'], 'sale', 'sales')} last week.",
                         "impact": "good" if good else "bad"})

    big = [s for s in ninety["sources"] if s["leads"] >= 5]
    if big:
        most = max(big, key=lambda s: s["leads"])
        richest = max(ninety["sources"], key=lambda s: s["revenue"])
        if most["key"] != richest["key"] and richest["revenue"]:
            findings.append({"title": f"{richest['name']} brings the money",
                             "detail": f"Over 90 days {most['name']} brought the most enquiries "
                                       f"({most['share_of_leads']:.0f}%), but {richest['name']} brought "
                                       f"{richest['share_of_revenue']:.0f}% of revenue.", "impact": "neutral"})
        weak = [s for s in big if s["share_of_leads"] >= 15 and s["conversion_rate"] < ninety["conversion_rate"] / 2]
        for s in weak[:1]:
            findings.append({"title": f"{s['name']} enquiries rarely buy",
                             "detail": f"{s['leads']} enquiries in 90 days, only {s['conversion_rate']:.0f}% "
                                       f"became sales ({_rupees(s['revenue'])}).", "impact": "bad"})

    if tw["never_replied"]:
        findings.append({"title": "Enquiries left unanswered",
                         "detail": f"{tw['never_replied']} enquiries this week got no reply at all.", "impact": "bad"})
    elif tw["median_reply_minutes"] and tw["median_reply_minutes"] > 60:
        findings.append({"title": "Replies are slow",
                         "detail": f"Typical reply time this week: {tw['median_reply_minutes']:.0f} minutes. "
                                   f"Fast replies win more customers.", "impact": "bad"})

    rep = f.get("reputation") or {}
    if rep.get("average_rating_30_days") and rep.get("average_rating") \
            and rep["average_rating_30_days"] < rep["average_rating"] - 0.3:
        findings.append({"title": "Recent reviews are lower",
                         "detail": f"Last 30 days: {rep['average_rating_30_days']:.1f}★ vs {rep['average_rating']:.1f}★ "
                                   f"overall. Complaints mention: {', '.join(rep['complaints_about']) or 'various'}.",
                         "impact": "bad"})

    money_pillars = [p for p in f["content"]["by_pillar"] if p["posts"] >= 3 and p["revenue_per_post"]]
    if money_pillars:
        p = money_pillars[0]
        findings.append({"title": f"'{p['name']}' posts bring customers",
                         "detail": f"They earned {_rupees(p['revenue_per_post'])} per post over 90 days.",
                         "impact": "good"})
    trend_p = next((p for p in f["content"]["by_pillar"] if p["name"] == "trend" and p["posts"] >= 3), None)
    if trend_p and not trend_p["revenue_per_post"] and len(findings) < 6:
        findings.append({"title": "Trend posts: likes, no sales",
                         "detail": f"Avg reach {trend_p['avg_reach']:,} but ₹0 earned.", "impact": "neutral"})

    if not findings:
        findings.append({"title": "Quiet week", "detail": "Not much activity to analyse yet.", "impact": "neutral"})
    return {"headline": headline[:140], "findings": findings[:6]}


# 4. The run -----------------------------------------------------------------------
def run_analyst(facts: dict, facts_text: str) -> AIResult[AnalystAnswer]:
    return get_llm().ask(system=SYSTEM, prompt=facts_text, schema=AnalystAnswer,
                         mock=lambda: mock_analyst(facts), smart=True, max_tokens=1200)
