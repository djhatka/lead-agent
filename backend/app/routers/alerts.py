"""
Alerts to the owner's own phone (Task 28).

    GET  /alerts/settings?business_id=1   the phone, the choices, who sends them, and the latest alerts
    PUT  /alerts/settings?business_id=1   owner: change the phone / turn hot-lead alerts on or off / quiet hours
    POST /alerts/test?business_id=1       owner: send a test alert now
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth.access import require_owner
from app.database import get_db
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime, clean_phone
from app.services import alerts_service
from app.services.messenger import alert_messenger

router = APIRouter(prefix="/alerts", tags=["Phone alerts"])


class AlertOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    kind: str
    lead_id: Optional[int]
    text: str
    status: str
    sent_by: str
    error: str
    created_at: UTCDateTime
    sent_at: Optional[UTCDateTime]


class AlertSettings(BaseModel):
    phone: Optional[str]
    hot_leads: bool
    quiet_hours: bool
    sender: str                       # lead_intel / business / practice
    recent: list[AlertOut]


class AlertSettingsIn(BaseModel):
    """Send only what changes. phone: the owner's OWN WhatsApp number (empty to remove it)."""

    phone: Optional[str] = Field(default=None, examples=["98100 00000"])
    hot_leads: Optional[bool] = None
    quiet_hours: Optional[bool] = None

    _phone = field_validator("phone")(clean_phone)


def _out(db: Session, business) -> AlertSettings:
    choices = alerts_service.settings_for(business)
    _, sender = alert_messenger(db, business.id)
    return AlertSettings(phone=business.alert_phone, hot_leads=choices["hot_leads"], quiet_hours=choices["quiet_hours"],
                         sender=sender, recent=[AlertOut.model_validate(a) for a in alerts_service.recent(db, business.id)])


@router.get("/settings", response_model=AlertSettings)
def get_settings(business_id: int, db: Session = Depends(get_db)):
    return _out(db, business_or_404(business_id, db))


@router.put("/settings", response_model=AlertSettings)
def put_settings(business_id: int, body: AlertSettingsIn, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    if body.phone and business.phone and body.phone == business.phone:
        raise HTTPException(status_code=422, detail="Use your own WhatsApp number, not the business number: "
                                                    "a business number can't send an alert to itself.")
    alerts_service.update_settings(db, business, body.phone, body.hot_leads, body.quiet_hours,
                                   phone_given="phone" in body.model_fields_set)
    return _out(db, business)


@router.post("/test", response_model=AlertOut)
def send_test(business_id: int, _owner=Depends(require_owner), db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    if not business.alert_phone:
        raise HTTPException(status_code=422, detail="Add your WhatsApp number first")
    return alerts_service.send_test(db, business)
