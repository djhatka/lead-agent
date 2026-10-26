"""
Lead service - the "clerk" who does the actual work with the filing cabinet.

The routers (next files) are the counters where requests arrive. They don't
touch the database themselves; they call the functions in this file:

    router: "someone wants leads for business 2, only hot ones"
       └─► lead_service.list_leads(db, business_id=2, priority="hot")
              └─► builds the database search, returns the rows

Keeping database work here means the webhooks (Task 6) and the AI agents
(Task 10) can reuse exactly the same functions later.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session, selectinload

from app.models import Business, Lead, LeadAnalysis, Message, Post
from app.schemas import BusinessCreate, BusinessUpdate, IncomingMessage, LeadCreate, LeadUpdate, MessageCreate


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Businesses
# ---------------------------------------------------------------------------
def list_businesses(db: Session) -> list[Business]:
    return list(db.scalars(select(Business).order_by(Business.id)))


def get_business(db: Session, business_id: int) -> Optional[Business]:
    """Returns the business, or None if that id doesn't exist."""
    return db.get(Business, business_id)


def create_business(db: Session, data: BusinessCreate) -> Business:
    business = Business(**data.model_dump())
    db.add(business)
    db.commit()
    return business


def update_business(db: Session, business: Business, data: BusinessUpdate) -> Business:
    # exclude_unset=True → only the fields the user actually sent are changed
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    db.commit()
    return business


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
POST_CODE = re.compile(r"\(code P(\d+)\)", re.IGNORECASE)   # "(code P12)" in a WhatsApp message


def _link_post_from_campaign(db: Session, lead: Lead) -> None:
    """Work out which post brought this customer, if we can:
      - website: the link's tracking tag matches a post's (utm_campaign=post-12)
      - WhatsApp: the pre-filled message from a post's link contains "(code P12)"
    """
    if lead.post_id is not None:
        return
    if lead.campaign:
        lead.post_id = db.scalar(select(Post.id).where(
            Post.business_id == lead.business_id, Post.campaign == lead.campaign))
    if lead.post_id is None and lead.first_message:
        code = POST_CODE.search(lead.first_message)
        if code:
            lead.post_id = db.scalar(select(Post.id).where(
                Post.business_id == lead.business_id, Post.id == int(code.group(1))))

def list_leads(
    db: Session,
    business_id: int,
    status: Optional[str] = None,
    source: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Lead], int]:
    """Find leads for ONE business, with optional filters.

    Returns (the leads on this page, total number of matching leads).
    `limit` and `offset` work like pages in a book: limit=50, offset=50
    means "page 2, 50 leads per page".
    """
    query = (
        select(Lead)
        .outerjoin(LeadAnalysis)          # attach the AI verdict, if there is one
        .where(Lead.business_id == business_id)
    )
    if status:
        query = query.where(Lead.status == status)
    if source:
        query = query.where(Lead.source == source)
    if priority:
        query = query.where(LeadAnalysis.priority == priority)
    if search:
        like = f"%{search.strip()}%"     # % = "anything before/after"
        query = query.where(or_(
            Lead.name.ilike(like), Lead.phone.ilike(like),
            Lead.handle.ilike(like), Lead.first_message.ilike(like), Lead.service.ilike(like),
        ))

    # Count everything that matches BEFORE cutting it into a page
    total = db.scalar(select(func.count()).select_from(query.subquery()))

    order = {
        "newest": [Lead.created_at.desc()],
        "oldest": [Lead.created_at.asc()],
        # Best leads first; leads the AI hasn't scored yet go to the end
        "score": [LeadAnalysis.score.desc().nulls_last(), Lead.created_at.desc()],
    }[sort]
    query = query.order_by(*order).limit(limit).offset(offset).options(selectinload(Lead.analysis))
    return list(db.scalars(query)), total


def get_lead(db: Session, lead_id: int) -> Optional[Lead]:
    """One lead with its messages and AI analysis loaded."""
    query = (
        select(Lead).where(Lead.id == lead_id)
        .options(selectinload(Lead.messages), selectinload(Lead.analysis))
    )
    return db.scalar(query)


def create_lead(db: Session, data: LeadCreate) -> tuple[Lead, bool]:
    """Save a new lead and its first message.

    Returns (lead, created). If the same platform message already arrived
    before (same business + source + external_id), nothing new is saved
    and the existing lead is returned with created=False. This protects us
    when WhatsApp/Instagram send the same webhook twice.
    """
    if data.external_id:
        existing = db.scalar(select(Lead).where(
            Lead.business_id == data.business_id,
            Lead.source == data.source,
            Lead.external_id == data.external_id,
        ))
        if existing:
            return existing, False

    lead = Lead(**data.model_dump())
    if data.first_message:
        lead.messages.append(Message(direction="inbound", text=data.first_message))
    _link_post_from_campaign(db, lead)
    db.add(lead)
    db.commit()
    return lead, True


OPEN_LEAD_DAYS = 30   # a follow-up within 30 days continues the same enquiry


def _find_open_lead(db: Session, msg: IncomingMessage) -> Optional[Lead]:
    """Is this person already talking to the business about something?
    Same business + same channel + same phone/handle + not finished yet
    + started in the last 30 days."""
    if msg.phone:
        same_person = Lead.phone == msg.phone
    elif msg.handle:
        same_person = Lead.handle == msg.handle
    else:
        return None
    return db.scalar(
        select(Lead)
        .where(
            Lead.business_id == msg.business_id,
            Lead.source == msg.source,
            same_person,
            Lead.status.not_in(["won", "lost"]),
            Lead.created_at >= _now() - timedelta(days=OPEN_LEAD_DAYS),
        )
        .order_by(Lead.created_at.desc())
    )


def receive_message(db: Session, msg: IncomingMessage) -> tuple[Lead, str]:
    """Handle one customer message from a webhook. Three possible outcomes:

    "duplicate"          we already have this exact message → do nothing
    "added_to_existing"  same person, ongoing enquiry → add to that conversation
    "new_lead"           someone new (or a new enquiry) → create a lead
    """
    copy = db.scalar(
        select(Message).join(Lead)
        .where(Lead.business_id == msg.business_id, Message.external_id == msg.external_id)
    )
    if copy:
        return copy.lead, "duplicate"

    sent_at = msg.sent_at or _now()
    lead = _find_open_lead(db, msg)
    if lead:
        lead.messages.append(Message(direction="inbound", text=msg.first_message,
                                     sent_at=sent_at, external_id=msg.external_id))
        lead.updated_at = _now()
        # The customer wrote again: follow-up reminders start fresh (Task 30)
        lead.followup_stopped = False
        lead.followup_snoozed_until = None
        db.commit()
        return lead, "added_to_existing"

    lead = Lead(**msg.model_dump(exclude={"sent_at"}), created_at=sent_at, updated_at=sent_at)
    lead.messages.append(Message(direction="inbound", text=msg.first_message,
                                 sent_at=sent_at, external_id=msg.external_id))
    _link_post_from_campaign(db, lead)
    db.add(lead)
    db.commit()
    return lead, "new_lead"


def update_lead(db: Session, lead: Lead, data: LeadUpdate) -> Lead:
    """Change a lead, e.g. move it from 'quoted' to 'won'.

    Business rules:
      - Marking a lead 'won' needs the ₹ amount (now or saved earlier).
      - Moving a lead away from 'won' clears the ₹ amount.
      - The first time a lead leaves 'new', we note when the business
        first responded (used for "average reply time").
      - When a lead becomes 'won', a review request is queued.
    """
    changes = data.model_dump(exclude_unset=True)
    new_status = changes.get("status", lead.status)

    if new_status == "won" and changes.get("job_value", lead.job_value) is None:
        raise ValueError("Please add job_value (₹ earned) when marking a lead as won")
    if new_status != "won" and "job_value" in changes and changes["job_value"] is not None:
        raise ValueError("job_value can only be set on a lead that is 'won'")
    if changes.get("post_id"):
        post = db.get(Post, changes["post_id"])
        if post is None or post.business_id != lead.business_id:
            raise ValueError("That post doesn't exist for this business")

    just_won = new_status == "won" and lead.status != "won"
    for field, value in changes.items():
        setattr(lead, field, value)
    if new_status != "won":
        lead.job_value = None
        lead.won_at = None
    elif just_won:
        lead.won_at = _now()                     # the sale counts in this month's report
    if new_status != "new" and lead.first_response_at is None:
        lead.first_response_at = _now()

    db.commit()
    if just_won:
        # A happy new customer: queue a polite "please review us" message (Task 17)
        from app.services.reputation_service import request_for_lead
        request_for_lead(db, lead)
    return lead


def add_message(db: Session, lead: Lead, data: MessageCreate, delivery: str = "", delivery_error: str = "",
                external_id: Optional[str] = None) -> Message:
    """Add one chat message to a lead's conversation.

    When the business sends its first reply, the lead automatically moves
    from 'new' to 'contacted' and the reply time is recorded (unless the
    reply couldn't be delivered: then the customer is still waiting).
    """
    message = Message(direction=data.direction, text=data.text, delivery=delivery,
                      delivery_error=delivery_error, external_id=external_id)
    lead.messages.append(message)
    if data.direction == "outbound" and delivery != "failed":
        if lead.first_response_at is None:
            lead.first_response_at = _now()
        if lead.status == "new":
            lead.status = "contacted"
    db.commit()
    return message
