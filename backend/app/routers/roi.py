"""
The monthly ROI report addresses (Task 27): "what Lead Intel did for you".

    GET  /roi?business_id=1&month=2026-10     any month, counted right now (default: this month so far)
    GET  /roi/reports?business_id=1           the saved monthly reports, newest first
    GET  /roi/reports/{id}                    one saved report
    GET  /roi/reports/{id}/whatsapp           the report as a WhatsApp-ready message
    POST /roi/reports?business_id=1&month=…   owner: save a finished month's report and email it now

The scheduler also saves and emails last month's report on the 1st of every month.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import can_access, require_owner
from app.database import get_db
from app.models import RoiReport
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import roi_service

router = APIRouter(prefix="/roi", tags=["ROI report"])


class RoiNow(BaseModel):
    month: str
    stats: dict
    message: str


class RoiReportOut(BaseModel):
    id: int
    business_id: int
    month: str
    stats: dict
    message: str
    emailed_at: Optional[UTCDateTime]
    created_at: UTCDateTime


class RoiReportRow(BaseModel):
    id: int
    month: str
    label: str
    headline: str
    customers: int
    revenue: int
    return_multiple: Optional[float]
    emailed_at: Optional[UTCDateTime]


def _month(month: Optional[str]) -> str:
    month = month or roi_service.month_of(datetime.now(timezone.utc))
    if not roi_service.valid_month(month):
        raise HTTPException(status_code=422, detail="month must look like 2026-10")
    start, _ = roi_service.month_bounds(month)
    if start > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="That month hasn't started yet")
    return month


def _report_or_404(report_id: int, db: Session) -> RoiReport:
    report = db.get(RoiReport, report_id)
    if report is None or not can_access(report.business_id):
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


@router.get("", response_model=RoiNow)
def roi_now(business_id: int, month: Optional[str] = Query(default=None, examples=["2026-10"]),
            db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    month = _month(month)
    stats = roi_service.compute(db, business, month)
    return RoiNow(month=month, stats=stats, message=roi_service.message(business, stats))


@router.get("/reports", response_model=list[RoiReportRow])
def reports(business_id: int, limit: int = Query(default=12, ge=1, le=60), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    saved = db.scalars(select(RoiReport).where(RoiReport.business_id == business_id)
                       .order_by(RoiReport.month.desc()).limit(limit))
    return [RoiReportRow(id=r.id, month=r.month, label=r.stats.get("label", r.month), headline=r.stats.get("headline", ""),
                         customers=r.stats.get("sales", {}).get("customers", 0),
                         revenue=r.stats.get("sales", {}).get("revenue", 0),
                         return_multiple=r.stats.get("return_multiple"), emailed_at=r.emailed_at) for r in saved]


@router.get("/reports/{report_id}", response_model=RoiReportOut)
def one_report(report_id: int, db: Session = Depends(get_db)):
    return _report_or_404(report_id, db)


@router.get("/reports/{report_id}/whatsapp", response_class=PlainTextResponse)
def whatsapp_text(report_id: int, db: Session = Depends(get_db)):
    return _report_or_404(report_id, db).message


@router.post("/reports", response_model=RoiReportOut, status_code=201)
def send_now(business_id: int, month: Optional[str] = Query(default=None, examples=["2026-09"]),
             _owner=Depends(require_owner), db: Session = Depends(get_db)):
    """Save a finished month's report and email it to the owners now (default: last month)."""
    business = business_or_404(business_id, db)
    month = _month(month or roi_service.previous_month(datetime.now(timezone.utc)))
    _, end = roi_service.month_bounds(month)
    if end > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="That month isn't over yet: open it with GET /roi to see it so far")
    report = roi_service.save(db, business, month)
    roi_service.email_owners(db, business, report)
    return report
