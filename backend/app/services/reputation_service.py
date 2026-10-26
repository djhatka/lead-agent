"""
Reputation service - reviews, replies and review requests.

    add_review          save a review (no duplicates), match it to a customer, draft a reply
    draft_reply         the Review Reply agent writes/re-writes the draft
    post_reply          owner approves → reply is posted (mock for now)
    request_for_lead    a lead was WON → queue a polite "please review us" WhatsApp
    send_due_requests   send queued requests whose time has come (daytime only)
    summary             rating, reply rate, praise & complaints, requests sent...
"""

import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.nodes.review_reply_agent import run_reply
from app.config import settings
from app.models import Business, Lead, Review, ReviewRequest
from app.schemas import ReviewCreate
from app.services import billing_service
from app.services.event_bus import bus
from app.services.messenger import SendError, get_messenger

logger = logging.getLogger("reputation")
IST = timezone(timedelta(hours=5, minutes=30))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _biz(b: Business) -> dict:
    return {"name": b.name, "industry": b.industry, "phone": b.phone}


# ---------------------------------------------------------------------------
# Reviews and replies
# ---------------------------------------------------------------------------
def draft_reply(db: Session, review: Review) -> Review:
    if review.reply_status == "posted":
        raise ValueError("This review already has a posted reply")
    business = db.get(Business, review.business_id)
    result = run_reply(review.rating, review.text, review.author_name, _biz(business))
    review.sentiment = result.data.sentiment
    review.topics = result.data.topics
    review.needs_attention = result.data.needs_attention
    review.reply_text = result.data.reply
    review.reply_status = "drafted"
    db.commit()
    return review


def post_reply(db: Session, review: Review, text: Optional[str] = None) -> Review:
    """The owner approves the reply (optionally edited). For a Google review on a
    connected Google Business Profile it is published on Google for real."""
    from app.integrations import google
    from app.integrations.base import IntegrationError
    from app.services import connection_service as connections
    if review.reply_status == "posted":
        raise ValueError("Already replied")
    final = (text or review.reply_text).strip()
    if not final:
        raise ValueError("There's no reply yet: draft one first")
    conn = connections.active(db, review.business_id, "google") if review.platform == "google" else None
    if conn is not None and conn.mode == "real" and review.external_id.startswith("accounts/"):
        try:
            connections.guarded(db, conn, google.reply, review.external_id, connections.token(db, conn), final)
        except IntegrationError as problem:
            raise ValueError(f"Couldn't post the reply on Google: {problem}")
    review.reply_text = final
    review.reply_status = "posted"
    review.replied_at = _now()
    review.needs_attention = False if review.rating >= 3 else review.needs_attention
    db.commit()
    return review


def _match_customer(db: Session, review: Review) -> None:
    """Did a customer we asked for a review write this one? Match by first name
    among requests sent in the 30 days before the review."""
    first = (review.author_name or "").split(" ")[0].lower()
    if not first:
        return
    since = _utc(review.reviewed_at) - timedelta(days=30)
    for req in db.scalars(select(ReviewRequest).where(
            ReviewRequest.business_id == review.business_id, ReviewRequest.status == "sent",
            ReviewRequest.sent_at >= since)):
        lead = db.get(Lead, req.lead_id)
        if lead and lead.name and lead.name.split(" ")[0].lower() == first:
            review.lead_id = lead.id
            req.status = "reviewed"
            return


def add_review(db: Session, data: ReviewCreate, draft: bool = True) -> tuple[Review, bool]:
    """Save a review. Returns (review, created). Same platform ID twice → not saved again."""
    external_id = data.external_id or f"manual-{uuid.uuid4()}"
    existing = db.scalar(select(Review).where(Review.business_id == data.business_id,
                                              Review.platform == data.platform, Review.external_id == external_id))
    if existing:
        return existing, False
    review = Review(**data.model_dump(exclude={"external_id", "reviewed_at"}), external_id=external_id,
                    reviewed_at=data.reviewed_at or _now())
    db.add(review)
    db.flush()
    _match_customer(db, review)
    db.commit()
    if draft:
        draft_reply(db, review)
    stars = "★" * review.rating
    if review.needs_attention:
        bus.publish(review.business_id, "review.unhappy", f"Unhappy review {stars} from {review.author_name or 'a customer'}",
                    review.text[:140], {"review_id": review.id, "rating": review.rating})
    else:
        bus.publish(review.business_id, "review.new", f"New review {stars} from {review.author_name or 'a customer'}",
                    review.text[:140], {"review_id": review.id, "rating": review.rating})
    return review, True


# ---------------------------------------------------------------------------
# Asking happy customers for reviews
# ---------------------------------------------------------------------------
def request_message(business: Business, lead: Lead) -> str:
    first = (lead.name or "").split(" ")[0] or "there"
    service = f" for {lead.service}" if lead.service else ""
    if "hinglish" in (business.brand_voice or "").lower():
        return (f"Hi {first}! {business.name} choose karne ke liye thank you 🙏 Aapka experience kaisa raha? "
                f"Agar achha laga ho to 1 minute mein Google review de dijiye, bahut help hogi 😊\n"
                f"{business.google_review_link}")
    return (f"Hi {first}, thank you for choosing {business.name}{service}! 🙏 "
            f"If you were happy with us, would you take 1 minute to leave a Google review? It really helps.\n"
            f"{business.google_review_link}")


def request_for_lead(db: Session, lead: Lead) -> Optional[ReviewRequest]:
    """Called when a lead is marked WON. Queues one request (never two for the same customer).
    Skipped when there's no phone number or the business has no review link."""
    business = db.get(Business, lead.business_id)
    if not (lead.phone and business.google_review_link):
        return None
    if not billing_service.has_feature(db, business.id, "review_requests"):     # Growth plan and up
        return None
    if db.scalar(select(ReviewRequest).where(ReviewRequest.lead_id == lead.id)):
        return None
    req = ReviewRequest(business_id=business.id, lead_id=lead.id, phone=lead.phone,
                        message=request_message(business, lead),
                        send_after=_now() + timedelta(hours=settings.review_request_delay_hours))
    db.add(req)
    db.commit()
    return req


def _daytime(now: datetime) -> bool:
    hour = now.astimezone(IST).hour
    return settings.messages_from_hour <= hour < settings.messages_until_hour


def send_due_requests(db: Session, now: Optional[datetime] = None) -> int:
    """Send pending requests whose time has come, but only in the daytime (India time):
    nobody likes a 'please review us' message at 11pm."""
    now = now or _now()
    if not _daytime(now):
        return 0
    sent = 0
    paused = billing_service.paused_business_ids(db)               # plan ended: don't message their customers
    for req in db.scalars(select(ReviewRequest).where(ReviewRequest.status == "pending",
                                                      ReviewRequest.send_after <= now)):
        if req.business_id in paused:
            continue
        business = db.get(Business, req.business_id)
        lead = db.get(Lead, req.lead_id) if req.lead_id else None
        first_name = ((lead.name if lead else "") or "there").split(" ")[0]
        try:
            # The business's own WhatsApp (an approved template), or the mock if not connected
            get_messenger(db, req.business_id).send_whatsapp(
                req.phone, req.message, template_params=[first_name, business.name, business.google_review_link or ""])
        except SendError as problem:
            logger.warning("Review request %s not sent: %s", req.id, problem)
            continue
        req.status, req.sent_at = "sent", now
        sent += 1
    db.commit()
    return sent


# ---------------------------------------------------------------------------
# Summary numbers (plain maths)
# ---------------------------------------------------------------------------
class ReputationSummary(BaseModel):
    reviews: int
    average_rating: Optional[float]
    average_rating_30_days: Optional[float]
    reviews_30_days: int
    by_stars: dict[int, int]
    unreplied: int
    needs_attention: int
    reply_rate: float                     # % of reviews with a posted reply
    median_reply_hours: Optional[float]
    requests_sent_30_days: int
    requests_turned_into_reviews: int
    praised_for: list[str]                # topics in 4-5 star reviews
    complaints_about: list[str]           # topics in 1-3 star reviews


def summary(db: Session, business_id: int) -> ReputationSummary:
    reviews = list(db.scalars(select(Review).where(Review.business_id == business_id)))
    month_ago = _now() - timedelta(days=30)
    recent = [r for r in reviews if _utc(r.reviewed_at) >= month_ago]
    replied = [r for r in reviews if r.reply_status == "posted"]
    reply_hours = [(_utc(r.replied_at) - _utc(r.reviewed_at)).total_seconds() / 3600
                   for r in replied if r.replied_at]
    requests = list(db.scalars(select(ReviewRequest).where(ReviewRequest.business_id == business_id,
                                                           ReviewRequest.sent_at >= month_ago)))
    praise = Counter(t for r in reviews if r.rating >= 4 for t in r.topics)
    complaints = Counter(t for r in reviews if r.rating <= 3 for t in r.topics)

    def avg(rs: list[Review]) -> Optional[float]:
        return round(sum(r.rating for r in rs) / len(rs), 2) if rs else None

    return ReputationSummary(
        reviews=len(reviews), average_rating=avg(reviews), average_rating_30_days=avg(recent),
        reviews_30_days=len(recent), by_stars={s: sum(1 for r in reviews if r.rating == s) for s in range(5, 0, -1)},
        unreplied=sum(1 for r in reviews if r.reply_status != "posted"),
        needs_attention=sum(1 for r in reviews if r.needs_attention and r.reply_status != "posted"),
        reply_rate=round(100 * len(replied) / len(reviews), 1) if reviews else 0.0,
        median_reply_hours=round(median(reply_hours), 1) if reply_hours else None,
        requests_sent_30_days=len(requests),
        requests_turned_into_reviews=sum(1 for r in requests if r.status == "reviewed"),
        praised_for=[t for t, _ in praise.most_common(3)],
        complaints_about=[t for t, _ in complaints.most_common(3)],
    )
