"""
Growth service - runs Workflow 2 (growth_graph.py) for one business and
keeps the AI diary, just like lead_pipeline.py does for leads.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.growth_graph import GROWTH_GRAPH
from app.agents.llm import get_llm
from app.models import AgentRun, Business, GrowthReport
from app.services import billing_service
from app.services.event_bus import bus

logger = logging.getLogger("growth")
IST = timezone(timedelta(hours=5, minutes=30))


def run_review(db: Session, business: Business) -> tuple[AgentRun, GrowthReport | None]:
    run = AgentRun(business_id=business.id, workflow="growth", status="running", ai_mode=get_llm().mode)
    db.add(run)
    db.commit()
    report = None
    try:
        final = GROWTH_GRAPH.invoke({"business_id": business.id, "steps": []},
                                    config={"configurable": {"db": db, "run_id": run.id}})
        run.steps = final["steps"]
        run.status = "success"
        report = db.get(GrowthReport, final["report_id"])
        bus.publish(business.id, "report.ready", "📊 Your weekly growth review is ready",
                    final["findings"]["headline"], {"report_id": report.id})
    except Exception as error:  # noqa: BLE001
        db.rollback()
        logger.exception("Growth review failed for business %s", business.id)
        run = db.get(AgentRun, run.id)
        run.status = "failed"
        run.error = f"{type(error).__name__}: {error}"[:500]
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run, report


def weekly_reviews_due(db: Session, now: datetime | None = None) -> int:
    """Monday from 9am (India time): give every business its weekly review,
    unless it already got one in the last 6 days, its plan has ended, or its
    plan doesn't include the review (Starter). Returns how many were run."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(IST)
    if local.weekday() != 0 or local.hour < 9:
        return 0
    done = 0
    paused = billing_service.paused_business_ids(db)
    for business in db.scalars(select(Business)):
        if business.id in paused or not billing_service.has_feature(db, business.id, "weekly_review"):
            continue
        recent = db.scalar(select(GrowthReport.id).where(
            GrowthReport.business_id == business.id,
            GrowthReport.created_at >= now - timedelta(days=6)))
        if recent is None:
            run_review(db, business)
            done += 1
    return done
