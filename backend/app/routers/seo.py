"""
Local SEO checklist (Task 34).

    GET /seo?business_id=1   a 0-100 score plus the checklist: what's set up, what isn't,
                              why each item affects Google Maps / Search ranking, and how to fix it

No AI involved: this is a plain-code checklist, like the go-live checklist (launch_check.py).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.database import get_db
from app.routers.businesses import business_or_404
from app.services import seo_checklist

router = APIRouter(prefix="/seo", tags=["Local SEO checklist"])


class SeoCheckItem(BaseModel):
    item: str
    ok: bool
    why_it_matters: str
    how_to_fix: str


class SeoChecklist(BaseModel):
    business_id: int
    score: int                         # 0-100: the share of checks that are ok
    checks: list[SeoCheckItem]


@router.get("", response_model=SeoChecklist)
def get_seo_checklist(business_id: int, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    return seo_checklist.build_checklist(db, business)
