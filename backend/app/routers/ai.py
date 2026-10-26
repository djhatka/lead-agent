"""
AI endpoints - check the AI connector is working.

    GET  /ai/status                is the AI in mock (free) or real mode? which models?
    POST /ai/try                   any message → the Quick Read practice agent
    POST /ai/read-message          any message → Intake + Tone + Scoring agents (for one business)
    POST /ai/read-lead/{lead_id}   an existing lead → Intake + Tone + Scoring agents
    POST /ai/analyze-all           run the full workflow (and SAVE) on many leads at once
    GET  /ai/lead-workflow         the LangGraph flowchart, as a diagram you can paste into mermaid.live

The read-* endpoints only SHOW what the agents think; nothing is saved.
(Saving happens automatically in Task 10, when the agents join the workflow.)
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.lead_graph import LEAD_GRAPH
from app.agents.llm import get_llm
from app.agents.nodes.intake_agent import IntakeAnswer, run_intake
from app.agents.nodes.scoring_agent import LeadFacts, score_lead
from app.agents.nodes.sentiment_agent import ToneAnswer, run_tone
from app.agents.quick_read import QuickRead, quick_read
from app.config import settings
from app.database import get_db
from app.routers.businesses import business_or_404
from app.routers.leads import lead_or_404
from app.models import Lead, LeadAnalysis
from app.schemas import LeadSource
from app.services import lead_pipeline

router = APIRouter(prefix="/ai", tags=["AI"])


class AIStatus(BaseModel):
    mode: str                 # mock / real
    has_api_key: bool
    fast_model: str
    smart_model: str
    how_to_switch: str


class TryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, examples=["Bhai Creta ke liye ceramic coating kitne ka hai? Aaj ho jayega?"])


class TryResponse(BaseModel):
    answer: QuickRead
    mode: str                 # mock / real / fallback
    model: Optional[str]
    ms: int
    tokens: int
    error: Optional[str]


@router.get("/status", response_model=AIStatus)
def ai_status():
    llm = get_llm()
    return AIStatus(
        mode=llm.mode,
        has_api_key=bool(settings.anthropic_api_key),
        fast_model=settings.ai_model_fast,
        smart_model=settings.ai_model,
        how_to_switch=(
            "Real AI is ON." if llm.enabled else
            "Mock mode (free). To use the real AI: in backend/.env set MOCK_AI=false and "
            "ANTHROPIC_API_KEY=your-key, then restart the server."
        ),
    )


@router.post("/try", response_model=TryResponse)
def try_ai(body: TryRequest):
    result = quick_read(body.message)
    return TryResponse(
        answer=result.data, mode=result.mode, model=result.model, ms=result.ms,
        tokens=result.input_tokens + result.output_tokens, error=result.error,
    )


# ---------------------------------------------------------------------------
# Intake + Tone agents
# ---------------------------------------------------------------------------
class ReadMessageRequest(BaseModel):
    business_id: int = Field(examples=[2])
    message: str = Field(min_length=1, max_length=4000, examples=[
        "Hi I'm Rahul from Dwarka. Sent 3 messages, no reply! Need ceramic coating on my Creta this Saturday"
    ])
    source: LeadSource = Field(default="whatsapp", description="Pretend the message came from here")
    has_phone: bool = Field(default=True, description="Did the customer share a phone number?")


class AgentStep(BaseModel):
    mode: str
    ms: int
    error: Optional[str]


class ScoreOut(BaseModel):
    score: int
    breakdown: dict[str, int]
    reason: str
    intent: str


class ReadResult(BaseModel):
    intake: IntakeAnswer
    tone: ToneAnswer
    score: ScoreOut
    intake_run: AgentStep
    tone_run: AgentStep
    score_run: AgentStep


def _read(message: str, business, source: str, has_phone: bool, has_name: bool = False,
          earlier: Optional[list[str]] = None) -> ReadResult:
    intake = run_intake(message, business.name, business.industry, business.services)
    tone = run_tone(message, earlier)
    scored = score_lead(LeadFacts(
        source=source, message=message, has_phone=has_phone,
        has_name=has_name or bool(intake.data.customer_name),
        service=intake.data.service, details=intake.data.details,
        inbound_messages=len(earlier or []) + 1, sentiment=tone.data.sentiment, industry=business.industry,
    ))

    def step(r):
        return AgentStep(mode=r.mode, ms=r.ms, error=r.error)

    return ReadResult(
        intake=intake.data, tone=tone.data,
        score=ScoreOut(score=scored.score, breakdown=scored.breakdown, reason=scored.reason, intent=scored.ai.data.intent),
        intake_run=step(intake), tone_run=step(tone), score_run=step(scored.ai),
    )


@router.post("/read-message", response_model=ReadResult)
def read_message(body: ReadMessageRequest, db: Session = Depends(get_db)):
    """Run the Intake, Tone and Scoring agents on any message, as if it was sent to this business."""
    business = business_or_404(body.business_id, db)
    return _read(body.message, business, source=body.source, has_phone=body.has_phone)


@router.post("/read-lead/{lead_id}", response_model=ReadResult)
def read_lead(lead_id: int, db: Session = Depends(get_db)):
    """Run the Intake, Tone and Scoring agents on an existing lead (nothing is saved)."""
    lead = lead_or_404(lead_id, db)
    said = [m.text for m in lead.messages if m.direction == "inbound"] or [lead.first_message or ""]
    return _read(said[-1], lead.business, source=lead.source, has_phone=bool(lead.phone),
                 has_name=bool(lead.name), earlier=said[:-1])


# ---------------------------------------------------------------------------
# The full workflow
# ---------------------------------------------------------------------------
class AnalyzeAllResult(BaseModel):
    analysed: int
    hot: int
    failed: int
    remaining_without_analysis: int


@router.post("/analyze-all", response_model=AnalyzeAllResult)
def analyze_all(
    business_id: int,
    only_missing: bool = Query(default=True, description="Skip leads the AI has already analysed"),
    limit: int = Query(default=100, ge=1, le=500, description="Max leads this time (real AI costs money!)"),
    db: Session = Depends(get_db),
):
    """Run the full AI workflow on a business's leads and save the results.
    Handy for leads that arrived before the AI existed (like the demo data)."""
    business_or_404(business_id, db)
    query = select(Lead.id).where(Lead.business_id == business_id)
    if only_missing:
        query = query.outerjoin(LeadAnalysis).where(LeadAnalysis.id.is_(None))
    ids = list(db.scalars(query.order_by(Lead.id).limit(limit)))

    hot = failed = 0
    for lead_id in ids:
        run = lead_pipeline.analyze_lead(db, lead_id)
        if run.status == "failed":
            failed += 1
        elif any(step["agent"] == "hot_alert" for step in run.steps):
            hot += 1

    remaining = db.scalar(
        select(func.count(Lead.id)).outerjoin(LeadAnalysis)
        .where(Lead.business_id == business_id, LeadAnalysis.id.is_(None))
    )
    return AnalyzeAllResult(analysed=len(ids), hot=hot, failed=failed, remaining_without_analysis=remaining)


@router.get("/lead-workflow", response_class=PlainTextResponse)
def lead_workflow_diagram():
    """The flowchart LangGraph built. Copy the text into https://mermaid.live to see it drawn."""
    return LEAD_GRAPH.get_graph().draw_mermaid()
