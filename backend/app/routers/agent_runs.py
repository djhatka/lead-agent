"""
Agent run endpoints - the AI team's diary.

Every time the AI workflow runs, one row is saved in agent_runs with each
agent's step: what it decided, how long it took, mock or real AI.
The dashboard's "AI team" page (Task 30) will replay these.

    GET /agent-runs?business_id=1        latest runs for a business
    GET /agent-runs/{run_id}             one run with all its steps
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import can_access
from app.database import get_db
from app.routers.businesses import business_or_404
from app.models import AgentRun
from app.schemas import AgentRunOut, RunStatus, Workflow

router = APIRouter(prefix="/agent-runs", tags=["AI runs"])


@router.get("", response_model=list[AgentRunOut])
def list_runs(
    business_id: int,
    lead_id: Optional[int] = None,
    workflow: Optional[Workflow] = None,
    status: Optional[RunStatus] = None,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    business_or_404(business_id, db)
    query = select(AgentRun).where(AgentRun.business_id == business_id)
    if lead_id:
        query = query.where(AgentRun.lead_id == lead_id)
    if workflow:
        query = query.where(AgentRun.workflow == workflow)
    if status:
        query = query.where(AgentRun.status == status)
    return list(db.scalars(query.order_by(AgentRun.id.desc()).limit(limit)))


@router.get("/{run_id}", response_model=AgentRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None or not can_access(run.business_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run
