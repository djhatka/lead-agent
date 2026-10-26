"""
Lead endpoints - the counter the dashboard uses for enquiries.

    GET    /leads?business_id=1&...      list leads (with filters and pages)
    POST   /leads                        add a lead by hand (walk-in, phone call)
    GET    /leads/{id}                   one lead + full conversation + AI verdict
    PATCH  /leads/{id}                   update status, ₹ value, details
    POST   /leads/{id}/messages          add a message to the conversation
    POST   /leads/{id}/analyze           run the AI workflow on this lead right now

How a request travels:
    browser/dashboard ─► this file (checks the request)
                      ─► lead_service (talks to the database)
                      ─► back here ─► converted to JSON with the ...Out schemas
"""

from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.access import can_access
from app.routers.businesses import business_or_404
from app.config import settings
from app.schemas import (
    AgentRunOut, LeadCreate, LeadDetailOut, LeadPage, LeadSource, LeadStatus,
    LeadUpdate, MessageCreate, MessageOut, Priority,
)
from app.services import lead_pipeline, lead_service, outbox
from app.services.event_bus import bus

router = APIRouter(prefix="/leads", tags=["Leads"])


def lead_or_404(lead_id: int, db: Session):
    lead = lead_service.get_lead(db, lead_id)
    if lead is None or not can_access(lead.business_id):
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return lead


@router.get("", response_model=LeadPage)
def list_leads(
    # Query(...) = these come from the address, e.g. /leads?business_id=1&status=won
    business_id: int = Query(description="Which business's leads to show"),
    status: Optional[LeadStatus] = Query(default=None, description="e.g. new, won, lost"),
    source: Optional[LeadSource] = Query(default=None, description="e.g. whatsapp, instagram"),
    priority: Optional[Priority] = Query(default=None, description="hot or normal (set by the AI)"),
    search: Optional[str] = Query(default=None, max_length=100, description="name, phone, handle or words in the message"),
    sort: Literal["newest", "oldest", "score"] = "newest",
    limit: int = Query(default=50, ge=1, le=200, description="leads per page"),
    offset: int = Query(default=0, ge=0, description="how many to skip (for page 2, 3...)"),
    db: Session = Depends(get_db),
):
    """List one business's leads. Every filter is optional and they can be combined."""
    business_or_404(business_id, db)
    items, total = lead_service.list_leads(
        db, business_id, status=status, source=source, priority=priority,
        search=search, sort=sort, limit=limit, offset=offset,
    )
    return LeadPage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=LeadDetailOut, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Add a lead by hand, e.g. someone who walked in or phoned.
    The AI workflow then analyses it in the background."""
    business_or_404(data.business_id, db)
    lead, created = lead_service.create_lead(db, data)
    if created:
        bus.publish(lead.business_id, "lead.new", f"New enquiry from {lead.name or lead.phone or 'someone'}",
                    lead.first_message[:140], {"lead_id": lead.id, "source": lead.source})
    if created and settings.auto_analyze:
        background.add_task(lead_pipeline.analyze_in_background, lead.id)
    return lead_or_404(lead.id, db)


@router.get("/{lead_id}", response_model=LeadDetailOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """Everything about one lead: details, whole conversation, AI verdict."""
    return lead_or_404(lead_id, db)


@router.patch("/{lead_id}", response_model=LeadDetailOut)
def update_lead(lead_id: int, data: LeadUpdate, db: Session = Depends(get_db)):
    """Example: {"status": "won", "job_value": 12000}"""
    lead = lead_or_404(lead_id, db)
    try:
        lead_service.update_lead(db, lead, data)
    except ValueError as problem:
        # A business rule was broken: reply 400 ("bad request") with the reason
        raise HTTPException(status_code=400, detail=str(problem))
    return lead_or_404(lead_id, db)


@router.post("/{lead_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def add_message(lead_id: int, data: MessageCreate, db: Session = Depends(get_db)):
    """Add a message. direction "outbound" = the business replied: it is SENT through
    the connected WhatsApp / Instagram / Facebook (send=false to only note it down).
    The answer's `delivery` says what happened: sent / failed (+ why) / logged."""
    lead = lead_or_404(lead_id, db)
    if data.direction == "outbound" and data.send:
        delivery, problem, external_id = outbox.send_reply(db, lead, data.text)
        return lead_service.add_message(db, lead, data, delivery, problem, external_id)
    return lead_service.add_message(db, lead, data, "logged" if data.direction == "outbound" else "")


@router.post("/{lead_id}/analyze", response_model=AgentRunOut)
def analyze_lead_now(lead_id: int, db: Session = Depends(get_db)):
    """Run the whole AI workflow on this lead now and wait for the result.
    The reply is the run's diary: every agent's step, in order."""
    lead_or_404(lead_id, db)
    return lead_pipeline.analyze_lead(db, lead_id)
