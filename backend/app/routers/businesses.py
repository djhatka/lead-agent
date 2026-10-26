"""
Business endpoints - the counter for business profiles.

    GET    /businesses          the businesses you can see (owner: yours; admin: all)
    POST   /businesses          add a business by hand (admin only; owners use /auth/signup)
    GET    /businesses/{id}     one business
    PATCH  /businesses/{id}     change some details (owner or admin, not staff)

The words GET / POST / PATCH are called "HTTP methods". They tell the
server what you want to do:
    GET   = read something        POST  = create something new
    PATCH = change part of it     DELETE = remove it (not used here yet)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import can_access, current_user, require_admin, require_owner
from app.database import get_db
from app.models import Business
from app.schemas import BusinessCreate, BusinessOut, BusinessUpdate
from app.services import lead_service

# All addresses in this file start with /businesses.
# "tags" groups them under one heading on the /docs page.
router = APIRouter(prefix="/businesses", tags=["Businesses"])


def business_or_404(business_id: int, db: Session):
    """Fetch a business or reply 'not found' (404) if it doesn't exist
    OR it belongs to someone else (we don't reveal that it exists)."""
    business = lead_service.get_business(db, business_id)
    if business is None or not can_access(business.id):
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")
    return business


@router.get("", response_model=list[BusinessOut])
def list_businesses(db: Session = Depends(get_db)):
    """Owner/staff: just your business. Admin: every business."""
    user = current_user()
    if user is None or user.role == "admin":
        return lead_service.list_businesses(db)
    return list(db.scalars(select(Business).where(Business.id == user.business_id)))


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(data: BusinessCreate, _admin=Depends(require_admin), db: Session = Depends(get_db)):
    """Add a new business. `data` has already passed the BusinessCreate rules
    (Task 3) before this line runs. If it didn't, FastAPI replied 422 for us."""
    return lead_service.create_business(db, data)


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(business_id: int, db: Session = Depends(get_db)):
    return business_or_404(business_id, db)


@router.patch("/{business_id}", response_model=BusinessOut)
def update_business(business_id: int, data: BusinessUpdate, _owner=Depends(require_owner),
                    db: Session = Depends(get_db)):
    """Change only the fields you send, e.g. {"brand_voice": "calm and premium"}."""
    business = business_or_404(business_id, db)
    return lead_service.update_business(db, business, data)
