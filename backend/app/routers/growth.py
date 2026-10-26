"""
Growth review endpoints - the owner's weekly report.

    POST /growth/review?business_id=1       run the weekly review now (also runs by itself Mondays 9am)
    GET  /growth/reports?business_id=1      past reports, newest first
    GET  /growth/reports/{id}               one report (findings, checklist, actions, message)
    GET  /growth/reports/{id}/whatsapp      just the message, ready to send on WhatsApp
    GET  /growth/workflow                   the flowchart (paste into mermaid.live)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.growth_graph import GROWTH_GRAPH
from app.database import get_db
from app.models import GrowthReport
from app.auth.access import can_access
from app.routers.businesses import business_or_404
from app.services import billing_service
from app.schemas import GrowthReportOut
from app.services import growth_service

router = APIRouter(prefix="/growth", tags=["Weekly growth review"])


class ReviewResult(BaseModel):
    run_id: int
    status: str
    steps: list[dict]
    report: GrowthReportOut | None


def report_or_404(report_id: int, db: Session) -> GrowthReport:
    report = db.get(GrowthReport, report_id)
    if report is None or not can_access(report.business_id):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


@router.post("/review", response_model=ReviewResult)
def review(business_id: int, db: Session = Depends(get_db)):
    """Run the whole growth workflow now: facts → analyst + presence auditor
    (at the same time) → strategist → report writer → saved."""
    business = business_or_404(business_id, db)
    try:
        billing_service.require_feature(db, business.id, "weekly_review")    # Growth plan and up
    except billing_service.PlanLimit as problem:
        raise HTTPException(status_code=403, detail=str(problem))
    run, report = growth_service.run_review(db, business)
    if run.status == "failed":
        raise HTTPException(status_code=500, detail=f"The review failed: {run.error}")
    return ReviewResult(run_id=run.id, status=run.status, steps=run.steps, report=report)


@router.get("/reports", response_model=list[GrowthReportOut])
def reports(business_id: int, limit: int = Query(default=10, ge=1, le=52), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return list(db.scalars(select(GrowthReport).where(GrowthReport.business_id == business_id)
                           .order_by(GrowthReport.id.desc()).limit(limit)))


@router.get("/reports/{report_id}", response_model=GrowthReportOut)
def one_report(report_id: int, db: Session = Depends(get_db)):
    return report_or_404(report_id, db)


@router.get("/reports/{report_id}/whatsapp", response_class=PlainTextResponse)
def whatsapp_text(report_id: int, db: Session = Depends(get_db)):
    return report_or_404(report_id, db).summary


@router.get("/workflow", response_class=PlainTextResponse)
def workflow_diagram():
    return GROWTH_GRAPH.get_graph().draw_mermaid()
