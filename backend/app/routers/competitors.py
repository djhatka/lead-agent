"""
Competitor watch (Task 35): 3-5 nearby rivals, their rating and review count, with an
alert here and on the live feed whenever one of them moves.

    GET    /competitors?business_id=1       the watched competitors + their latest numbers
    POST   /competitors?business_id=1       add one: {"name": "...", "area": "..."} (max 5)
    DELETE /competitors/{id}                stop watching it
    POST   /competitors/{id}/check          look it up again right now
    GET    /competitors/alerts?business_id=1   recent "they moved" alerts

No official Google ranking API exists, so real numbers need a paid map-search data
service (DATAFORSEO_LOGIN/PASSWORD in .env). Until then this runs in free mock mode
with realistic, slowly-drifting pretend numbers.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.config import settings
from app.database import get_db
from app.models import Competitor
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import competitor_service

router = APIRouter(prefix="/competitors", tags=["Competitor watch"])


class CompetitorOut(BaseModel):
    id: int
    name: str
    area: str
    rating: Optional[float]
    review_count: Optional[int]
    previous_rating: Optional[float]
    previous_review_count: Optional[int]
    category: str
    address: str
    problem: str
    last_checked_at: Optional[UTCDateTime]
    mode: str                              # "real" or "mock"


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    area: Optional[str] = Field(default=None, max_length=100)


class AlertOut(BaseModel):
    id: int
    competitor_id: int
    kind: str
    message: str
    created_at: UTCDateTime


def _mode() -> str:
    return "real" if settings.mapsearch_enabled else "mock"


def _out(c: Competitor) -> dict:
    return {"id": c.id, "name": c.name, "area": c.area, "rating": c.rating, "review_count": c.review_count,
            "previous_rating": c.previous_rating, "previous_review_count": c.previous_review_count,
            "category": c.category, "address": c.address, "problem": c.problem,
            "last_checked_at": c.last_checked_at, "mode": _mode()}


def _competitor_or_404(competitor_id: int, db: Session) -> Competitor:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"Competitor {competitor_id} not found")
    business_or_404(competitor.business_id, db)      # 404s if it belongs to someone else
    return competitor


@router.get("", response_model=list[CompetitorOut])
def list_competitors(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return [_out(c) for c in competitor_service.list_for(db, business_id)]


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    alerts = competitor_service.recent_alerts(db, business_id)
    return [{"id": a.id, "competitor_id": a.competitor_id, "kind": a.kind, "message": a.message,
             "created_at": a.created_at} for a in alerts]


@router.post("", response_model=CompetitorOut, status_code=status.HTTP_201_CREATED)
def add_competitor(business_id: int, data: CompetitorIn, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    try:
        competitor = competitor_service.add(db, business, data.name, data.area or "")
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return _out(competitor)


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_competitor(competitor_id: int, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    competitor = _competitor_or_404(competitor_id, db)
    competitor_service.remove(db, competitor)


@router.post("/{competitor_id}/check", response_model=CompetitorOut)
def check_competitor(competitor_id: int, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    competitor = _competitor_or_404(competitor_id, db)
    competitor_service.check(db, competitor)
    return _out(competitor)
