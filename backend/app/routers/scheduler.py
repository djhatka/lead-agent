"""
Scheduling, publishing and performance endpoints.

    POST /posts/{id}/schedule        approve a draft and set when it goes out
    POST /posts/{id}/unschedule      take it back to draft
    POST /posts/{id}/publish-now     publish immediately
    POST /posts/{id}/mark-posted     the owner posted it by hand: record it as published
    GET  /scheduler/status           is the alarm clock running? what's due next?
    POST /scheduler/run              run one cycle right now (publish due posts + refresh numbers)
    POST /content/refresh-stats      re-read the numbers of a business's recent posts now
    GET  /content/top-posts          best posts by ₹, enquiries, reach or engagement
"""

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Post
from app.auth.access import require_admin
from app.routers.businesses import business_or_404
from app.routers.social import post_or_404
from app.schemas import PostOut, UTCDateTime
from app.services import scheduler_service, social_service

router = APIRouter(tags=["Scheduling & performance"])


class ScheduleRequest(BaseModel):
    scheduled_for: datetime


def _apply(action, db: Session, *args):
    try:
        return action(db, *args)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))


@router.post("/posts/{post_id}/schedule", response_model=PostOut)
def schedule(post_id: int, body: ScheduleRequest, db: Session = Depends(get_db)):
    """Example body: {"scheduled_for": "2026-10-20T19:00:00+05:30"} (7pm India time)"""
    post = _apply(scheduler_service.schedule_post, db, post_or_404(post_id, db), body.scheduled_for)
    return social_service.posts_out(db, [post])[0]


@router.post("/posts/{post_id}/unschedule", response_model=PostOut)
def unschedule(post_id: int, db: Session = Depends(get_db)):
    post = _apply(scheduler_service.unschedule, db, post_or_404(post_id, db))
    return social_service.posts_out(db, [post])[0]


@router.post("/posts/{post_id}/publish-now", response_model=PostOut)
def publish_now(post_id: int, db: Session = Depends(get_db)):
    post = _apply(scheduler_service.publish_now, db, post_or_404(post_id, db))
    return social_service.posts_out(db, [post])[0]


@router.post("/posts/{post_id}/mark-posted", response_model=PostOut)
def mark_posted(post_id: int, db: Session = Depends(get_db)):
    post = _apply(scheduler_service.mark_posted, db, post_or_404(post_id, db))
    return social_service.posts_out(db, [post])[0]


class SchedulerStatus(BaseModel):
    enabled: bool
    wakes_up_every_seconds: int
    last_run: dict
    scheduled_posts: int
    next_post_at: Optional[UTCDateTime]


@router.get("/scheduler/status", response_model=SchedulerStatus)
def status(_admin=Depends(require_admin), db: Session = Depends(get_db)):
    waiting = select(Post).where(Post.status == "scheduled")
    nxt = db.scalar(waiting.order_by(Post.scheduled_for).limit(1))
    return SchedulerStatus(
        enabled=settings.scheduler_enabled, wakes_up_every_seconds=settings.scheduler_interval_seconds,
        last_run=scheduler_service.LAST_RUN,
        scheduled_posts=db.scalar(select(func.count()).select_from(waiting.subquery())),
        next_post_at=nxt.scheduled_for if nxt else None,
    )


@router.post("/scheduler/run")
def run_now(_admin=Depends(require_admin), db: Session = Depends(get_db)):
    """Don't want to wait for the next minute? Run one cycle now."""
    return scheduler_service.run_cycle(db)


@router.post("/content/refresh-stats")
def refresh_stats(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return {"posts_updated": scheduler_service.refresh_stats(db, business_id, force=True)}


@router.get("/content/top-posts", response_model=list[PostOut])
def top_posts(
    business_id: int,
    by: Literal["revenue", "enquiries", "reach", "engagement"] = "revenue",
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """The best published posts. 'revenue' and 'enquiries' show what brought customers;
    'reach' and 'engagement' show what people liked."""
    business_or_404(business_id, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    posts = list(db.scalars(select(Post).where(
        Post.business_id == business_id, Post.status == "published", Post.published_at >= since)))
    out = social_service.posts_out(db, posts)
    key = {"revenue": lambda p: (p.revenue, p.enquiries), "enquiries": lambda p: (p.enquiries, p.revenue),
           "reach": lambda p: p.reach, "engagement": lambda p: p.engagement_rate}[by]
    return sorted(out, key=key, reverse=True)[:limit]
