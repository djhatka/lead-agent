"""
Reputation endpoints - reviews, replies and review requests.

    GET  /reviews/summary?business_id=1     rating, reply rate, praise & complaints
    GET  /reviews?business_id=1&...         reviews, newest first (filters: stars, needs_attention...)
    POST /reviews                           add a review (typed in, or imported); the AI drafts a reply
    POST /reviews/draft-all?business_id=1   draft replies for every review that has none
    POST /reviews/{id}/draft-reply          (re)draft the reply for one review
    POST /reviews/{id}/reply                approve and post the reply (edit it first if you like)
    GET  /review-requests?business_id=1     "please review us" messages: pending / sent / reviewed
    POST /review-requests/{id}/skip         don't send this one
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Review, ReviewRequest
from app.auth.access import can_access
from app.routers.businesses import business_or_404
from app.schemas import ReplyApprove, ReviewCreate, ReviewOut, ReviewPlatform, ReviewRequestOut
from app.services import reputation_service as rep

router = APIRouter(tags=["Reputation"])


def review_or_404(review_id: int, db: Session) -> Review:
    review = db.get(Review, review_id)
    if review is None or not can_access(review.business_id):
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")
    return review


def _try(action, *args):
    try:
        return action(*args)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))


@router.get("/reviews/summary", response_model=rep.ReputationSummary)
def summary(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return rep.summary(db, business_id)


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    business_id: int,
    stars: Optional[int] = Query(default=None, ge=1, le=5),
    platform: Optional[ReviewPlatform] = None,
    needs_attention: Optional[bool] = None,
    unreplied: Optional[bool] = Query(default=None, description="true = only reviews without a posted reply"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    business_or_404(business_id, db)
    query = select(Review).where(Review.business_id == business_id)
    if stars:
        query = query.where(Review.rating == stars)
    if platform:
        query = query.where(Review.platform == platform)
    if needs_attention is not None:
        query = query.where(Review.needs_attention == needs_attention)
    if unreplied:
        query = query.where(Review.reply_status != "posted")
    return list(db.scalars(query.order_by(Review.reviewed_at.desc()).limit(limit)))


@router.post("/reviews", response_model=ReviewOut, status_code=201)
def add_review(data: ReviewCreate, db: Session = Depends(get_db)):
    business_or_404(data.business_id, db)
    review, _ = rep.add_review(db, data)
    return review


@router.post("/reviews/draft-all")
def draft_all(business_id: int, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    """Draft replies for reviews that have none yet (newest first)."""
    business_or_404(business_id, db)
    todo = list(db.scalars(select(Review).where(Review.business_id == business_id, Review.reply_status == "none")
                           .order_by(Review.reviewed_at.desc()).limit(limit)))
    for review in todo:
        rep.draft_reply(db, review)
    return {"drafted": len(todo), "need_attention": sum(1 for r in todo if r.needs_attention)}


@router.post("/reviews/{review_id}/draft-reply", response_model=ReviewOut)
def draft_reply(review_id: int, db: Session = Depends(get_db)):
    return _try(rep.draft_reply, db, review_or_404(review_id, db))


@router.post("/reviews/{review_id}/reply", response_model=ReviewOut)
def post_reply(review_id: int, body: ReplyApprove, db: Session = Depends(get_db)):
    """Body: {} to post the AI draft as it is, or {"text": "your edited reply"}."""
    return _try(rep.post_reply, db, review_or_404(review_id, db), body.text)


@router.get("/review-requests", response_model=list[ReviewRequestOut])
def list_requests(business_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    query = select(ReviewRequest).where(ReviewRequest.business_id == business_id)
    if status:
        query = query.where(ReviewRequest.status == status)
    return list(db.scalars(query.order_by(ReviewRequest.id.desc())))


@router.post("/review-requests/{request_id}/skip", response_model=ReviewRequestOut)
def skip_request(request_id: int, db: Session = Depends(get_db)):
    req = db.get(ReviewRequest, request_id)
    if req is None or not can_access(req.business_id):
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Already {req.status}")
    req.status = "skipped"
    db.commit()
    return req
