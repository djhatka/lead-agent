"""
Lead pipeline - runs Workflow 1 (lead_graph.py) for one lead.

    1. Load the lead and its business from the database
    2. Open a diary entry in agent_runs (status "running")
    3. Fill the clipboard and run the LangGraph flowchart
    4. Close the diary entry: "success" with every agent's steps, or "failed" + the error

Webhooks call `analyze_in_background(lead_id)`: FastAPI first replies
"got it" to WhatsApp, and THEN runs this. So the customer's platform never
waits for the AI, which is what Meta requires.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.agents.lead_graph import LEAD_GRAPH
from app.agents.llm import get_llm
from app.database import SessionLocal
from app.models import AgentRun, Lead
from app.services import lead_service
from app.services.event_bus import bus

logger = logging.getLogger("pipeline")

# How background jobs get their own database session. Tests swap this out
# so background jobs use the temporary test database.
SESSION_FACTORY = SessionLocal


def analyze_lead(db: Session, lead_id: int) -> Optional[AgentRun]:
    """Run the AI workflow on one lead and return the diary entry (AgentRun)."""
    lead = lead_service.get_lead(db, lead_id)
    if lead is None:
        return None

    said = [m.text for m in lead.messages if m.direction == "inbound"] or [lead.first_message or ""]
    run = AgentRun(business_id=lead.business_id, workflow="lead", lead_id=lead.id,
                   status="running", ai_mode=get_llm().mode)
    db.add(run)
    db.commit()

    clipboard = {
        "lead_id": lead.id,
        "business": {"name": lead.business.name, "industry": lead.business.industry,
                     "services": lead.business.services},
        "source": lead.source,
        "message": said[-1],
        "earlier_messages": said[:-1],
        "has_phone": bool(lead.phone),
        "has_name": bool(lead.name),
        "lead_name": lead.name,
        "steps": [],
    }
    hot_score = None
    try:
        final = LEAD_GRAPH.invoke(clipboard, config={"configurable": {"db": db}})
        run.steps = final["steps"]
        run.status = "success"
        score = final["score"]["score"]
        bus.publish(lead.business_id, "lead.analyzed", f"Lead scored {score}",
                    final["score"]["reason"][:140],
                    {"lead_id": lead.id, "score": score, "priority": final["priority"],
                     "sentiment": final["tone"]["sentiment"]})
        if final.get("alert"):
            bus.publish(lead.business_id, "lead.hot", "🔥 Hot lead", final["alert"],
                        {"lead_id": lead.id, "score": score})
            hot_score = score
    except Exception as error:  # noqa: BLE001 - never crash the server because of one lead
        db.rollback()
        logger.exception("Lead workflow failed for lead %s", lead_id)
        run = db.get(AgentRun, run.id)
        run.status = "failed"
        run.error = f"{type(error).__name__}: {error}"[:500]
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    if hot_score is not None:                    # after saving: an alert problem can never undo the AI's work
        from app.services.alerts_service import queue_hot_lead
        queue_hot_lead(db, db.get(Lead, lead_id), hot_score)          # WhatsApp to the owner's phone (Task 28)
    return run


def analyze_in_background(lead_id: int) -> None:
    """Same as analyze_lead, but opens and closes its own database session,
    because it runs after the webhook request has already finished."""
    db = SESSION_FACTORY()
    try:
        analyze_lead(db, lead_id)
    finally:
        db.close()
