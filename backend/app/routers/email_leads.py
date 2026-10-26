"""
Settings → "Leads from email": the business's lead address and what arrived.

    GET  /email-leads          my lead address, step-by-step forwarding guide,
                               Gmail's confirmation code (if it arrived), recent emails
    POST /email-leads/rotate   a new address (if the old one gets spam); owner only
    POST /email-leads/test     send yourself a sample Justdial lead email (to see it working)
"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import get_current_user, require_owner
from app.database import get_db
from app.models import Business, InboundEmail, User
from app.routers.businesses import business_or_404
from app.routers.webhooks import _save_all
from app.schemas import UTCDateTime, WebhookResult
from app.services import email_leads

router = APIRouter(tags=["Leads from email"])

GMAIL_STEPS = [
    "Gmail → ⚙ Settings → See all settings → 'Forwarding and POP/IMAP' → 'Add a forwarding address' → paste your lead address.",
    "Gmail sends a confirmation code to that address. It appears on this page within a minute: copy it into Gmail and click Verify.",
    "Gmail → search bar → filter icon → From: justdial.com OR sulekha.com OR practo.com (your platforms) → 'Create filter' → tick 'Forward it to' your lead address → Create filter.",
    "Done! Every new lead email from those platforms becomes a lead here, scored by the AI.",
]


class InboundOut(BaseModel):
    id: int
    from_addr: str
    subject: str
    platform: str
    status: str
    lead_id: Optional[int]
    note: str
    received_at: UTCDateTime

    model_config = {"from_attributes": True}


class EmailLeadsSetup(BaseModel):
    address: str
    gmail_steps: list[str]
    platforms: list[str]
    gmail_confirmation_code: Optional[str]
    gmail_confirmation_link: Optional[str]
    recent: list[InboundOut]


def _business(user: User, business_id: Optional[int], db: Session) -> Business:
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_or_404(business_id, db)
    return db.get(Business, user.business_id)


@router.get("/email-leads", response_model=EmailLeadsSetup)
def setup(business_id: Optional[int] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    business = _business(user, business_id, db)
    recent = list(db.scalars(select(InboundEmail).where(InboundEmail.business_id == business.id)
                             .order_by(InboundEmail.id.desc()).limit(20)))
    confirm = next((r for r in recent if r.status == "confirmation"), None)
    code = link = None
    if confirm:
        parts = dict(p.split("=", 1) for p in confirm.note.split(" ") if "=" in p)
        code, link = parts.get("code") or None, parts.get("link") or None
    return EmailLeadsSetup(address=email_leads.address_for(db, business), gmail_steps=GMAIL_STEPS,
                           platforms=sorted(email_leads.NAMES.values()), gmail_confirmation_code=code,
                           gmail_confirmation_link=link, recent=recent)


@router.post("/email-leads/rotate")
def rotate(business_id: Optional[int] = None, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    business = _business(owner, business_id, db)
    business.inbound_token = None
    db.commit()
    return {"address": email_leads.address_for(db, business),
            "note": "Update the forwarding address in Gmail: the old one no longer works."}


SAMPLE = """Dear {business},

You have received a new enquiry on Justdial.

Caller Name : Rohan Malhotra
Mobile : +91 98101 23456
Requirement : {service}
Area : Janakpuri, Delhi
Enquiry Date : today

For help call our customer care 8888888888.
Team Justdial"""


@router.post("/email-leads/test", response_model=WebhookResult)
def send_test(background: BackgroundTasks, business_id: Optional[int] = None,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pretend Justdial emailed you a lead, to see the whole thing work."""
    import uuid
    business = _business(user, business_id, db)
    service = (business.services or ["your services"])[0]
    parsed = email_leads.ParsedEmail(
        to=[email_leads.address_for(db, business)], from_addr="leads@justdial.com", from_name="Justdial",
        subject=f"New enquiry for {business.name} from Justdial", message_id=f"<test-{uuid.uuid4().hex}@justdial.com>",
        text=SAMPLE.format(business=business.name, service=service))
    log, incoming = email_leads.handle(db, parsed)
    result = _save_all(db, [incoming], [], background)
    log.lead_id, log.status = result.lead_ids[0], "lead" if result.new_leads else "added"
    db.commit()
    return result
