"""
Platform endpoint - shows the platform list from app/platforms.py.

    GET /platforms                     every platform we support
    GET /platforms?industry=clinic     only the ones that matter for clinics

The dashboard will use this for dropdowns ("Where did this lead come from?")
and later the AI uses it to check "is this business listed everywhere it
should be?".
"""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.platforms import CATEGORIES, PLATFORMS, platforms_for
from app.schemas import Industry

router = APIRouter(prefix="/platforms", tags=["Platforms"])


class PlatformOut(BaseModel):
    key: str
    name: str
    category: str
    category_name: str
    connection: str          # api / email / manual
    industries: list[str]


@router.get("", response_model=list[PlatformOut])
def list_platforms(industry: Optional[Industry] = Query(default=None, description="e.g. gym, clinic, restaurant")):
    chosen = platforms_for(industry) if industry else PLATFORMS.values()
    return [
        PlatformOut(
            key=p.key, name=p.name, category=p.category, category_name=CATEGORIES[p.category],
            connection=p.connection, industries=list(p.industries),
        )
        for p in chosen
    ]
