"""
Analytics endpoints - the numbers the dashboard charts will draw.

All take ?business_id=1 and optionally &days=30 (default: last 90 days).

    GET /analytics/summary     everything at once + plain-English highlights
    GET /analytics/overview    headline numbers
    GET /analytics/sources     per platform: enquiries vs sales vs ₹
    GET /analytics/funnel      new → contacted → quoted → booked → won
    GET /analytics/timing      busiest hours/days + does reply speed matter?
    GET /analytics/services    which services sell
    GET /analytics/trend       week by week
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.businesses import business_or_404
from app.services import analytics_service as calc

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# The same two inputs for every endpoint
Days = Query(default=90, ge=1, le=365, description="Look at the last N days")


def _leads(business_id: int, days: int, db: Session):
    business_or_404(business_id, db)
    return calc.load_leads(db, business_id, days)


@router.get("/summary", response_model=calc.Summary)
def summary(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return calc.summary(db, business_id, days)


@router.get("/overview", response_model=calc.Overview)
def overview(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.overview(_leads(business_id, days, db), days)


@router.get("/sources", response_model=list[calc.SourceStats])
def sources(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.sources(_leads(business_id, days, db))


@router.get("/funnel", response_model=calc.Funnel)
def funnel(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.funnel(_leads(business_id, days, db))


@router.get("/timing", response_model=calc.Timing)
def timing(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.timing(_leads(business_id, days, db))


@router.get("/services", response_model=list[calc.ServiceStats])
def services(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.services(_leads(business_id, days, db))


@router.get("/trend", response_model=list[calc.WeekStats])
def trend(business_id: int, days: int = Days, db: Session = Depends(get_db)):
    return calc.trend(_leads(business_id, days, db))
