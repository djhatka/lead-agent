"""
Report Writer agent - turns everything into ONE short message for the owner.

Written to be read on WhatsApp in 30 seconds: the headline, what went well,
what needs fixing, and this week's 3 actions. Simple words; in the business's
voice (Hinglish if the brand voice says so).

Same 4-part pattern: form → brief → mock rules → run.
"""

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class ReportAnswer(BaseModel):
    message: str = Field(max_length=1500, description="The owner's weekly message, WhatsApp-ready")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write a short weekly business update for a busy local business owner in India, to be read on "
    "WhatsApp. Max ~180 words. Structure: greeting + one-line headline; 'What went well' (1-2 points); "
    "'Needs attention' (1-2 points); 'This week's 3 actions' (numbered). Use only the numbers given. "
    "Simple words, a few emojis, *bold* with asterisks (WhatsApp style). Match the brand voice; "
    "if it mentions Hinglish, write in friendly Hinglish."
)


# 3. The mock: a template -----------------------------------------------------------
def mock_report(facts: dict, findings: dict, strategy: dict) -> dict:
    name = facts["business"]["name"]
    hinglish = "hinglish" in (facts["business"].get("brand_voice") or "").lower()
    good = [x for x in findings["findings"] if x["impact"] == "good"][:2]
    bad = [x for x in findings["findings"] if x["impact"] == "bad"][:2]

    lines = [f"{'Namaste' if hinglish else 'Hello'} {name} team! 👋", f"*{findings['headline']}*", ""]
    if good:
        lines.append("✅ *What went well*")
        lines += [f"• {x['title']}: {x['detail']}" for x in good]
        lines.append("")
    if bad:
        lines.append("⚠️ *Needs attention*")
        lines += [f"• {x['title']}: {x['detail']}" for x in bad]
        lines.append("")
    lines.append("🎯 *Is hafte ke 3 kaam*" if hinglish else "🎯 *This week's 3 actions*")
    lines += [f"{i}. {a['action']}" for i, a in enumerate(strategy["top_actions"], 1)]
    lines += ["", "Full report on your dashboard. 📊"]
    return {"message": "\n".join(lines)[:1500]}


# 4. The run -----------------------------------------------------------------------
def run_report(facts: dict, findings: dict, strategy: dict) -> AIResult[ReportAnswer]:
    prompt = (f"Business: {facts['business']['name']} ({facts['business']['industry']}); "
              f"brand voice: {facts['business'].get('brand_voice') or 'friendly'}\n"
              f"Headline: {findings['headline']}\nFindings:\n"
              + "\n".join(f"- [{x['impact']}] {x['title']}: {x['detail']}" for x in findings["findings"])
              + "\nActions:\n" + "\n".join(f"- {a['action']} (why: {a['why']})" for a in strategy["top_actions"]))
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=ReportAnswer,
                         mock=lambda: mock_report(facts, findings, strategy), max_tokens=900)
