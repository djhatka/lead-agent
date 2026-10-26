"""
Content endpoints - the social media planning desk.

    GET  /content/stats?business_id=1        what kind of posts work for this business
    GET  /content/events?business_id=1       festivals coming up that matter for it
    POST /content/plan-week?business_id=1    the AI plans the next 7 days (saved as "ideas")
    GET  /content/calendar?business_id=1     the posting calendar, day by day
    POST /content/write/{post_id}            the AI writes one post (caption, hashtags, script)
    POST /content/write-week?business_id=1   the AI writes every planned idea for the week
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.festivals import upcoming
from app.auth.access import can_access
from app.routers.businesses import business_or_404
from app.schemas import PostOut
from app.services import content_stats, planner_service, social_service, writer_service

router = APIRouter(prefix="/content", tags=["Content planning"])
IST = timezone(timedelta(hours=5, minutes=30))


def _tomorrow() -> date:
    return datetime.now(IST).date() + timedelta(days=1)


class PlanResult(BaseModel):
    run_id: int
    mode: str                    # mock / real / fallback
    start: date
    strategy: str
    posts: list[PostOut]
    skipped: list[str]


class CalendarDay(BaseModel):
    date: date
    weekday: str
    posts: list[PostOut]


@router.get("/stats", response_model=content_stats.ContentStats)
def stats(business_id: int, days: int = Query(default=90, ge=7, le=365), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return content_stats.content_stats(db, business_id, days)


@router.get("/events")
def events(business_id: int, days: int = Query(default=30, ge=1, le=120), db: Session = Depends(get_db)):
    business = business_or_404(business_id, db)
    return upcoming(datetime.now(IST).date(), days, business.industry, look_ahead=0)


@router.post("/plan-week", response_model=PlanResult)
def plan_week(
    business_id: int,
    start: Optional[date] = Query(default=None, description="First day of the plan (default: tomorrow)"),
    db: Session = Depends(get_db),
):
    """The Content Planner looks at this business's results and upcoming festivals,
    and plans 7 days of posts. They're saved as 'ideas' you can edit or delete.
    Running it again for the same week replaces the AI's earlier ideas."""
    business = business_or_404(business_id, db)
    start = start or _tomorrow()
    if start < datetime.now(IST).date():
        raise HTTPException(status_code=400, detail="Can't plan for dates in the past")
    try:
        run, posts, strategy, skipped = planner_service.plan_week(db, business, start)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return PlanResult(run_id=run.id, mode=run.steps[0]["mode"], start=start, strategy=strategy,
                      posts=social_service.posts_out(db, posts), skipped=skipped)


@router.get("/calendar", response_model=list[CalendarDay])
def calendar(
    business_id: int,
    start: Optional[date] = Query(default=None, description="First day (default: tomorrow)"),
    days: int = Query(default=7, ge=1, le=31),
    db: Session = Depends(get_db),
):
    business_or_404(business_id, db)
    result = []
    for day in planner_service.calendar(db, business_id, start or _tomorrow(), days):
        result.append(CalendarDay(date=day["date"], weekday=day["weekday"],
                                  posts=social_service.posts_out(db, day["posts"])))
    return result


class WriteResult(BaseModel):
    run_id: int
    mode: str
    posts: list[PostOut]
    problems: list[str] = []


@router.post("/write/{post_id}", response_model=WriteResult)
def write_one(post_id: int, db: Session = Depends(get_db)):
    """The Writer agent writes (or rewrites) one idea/draft in the business's brand voice.
    The post becomes a 'draft' for the owner to check before scheduling."""
    post = social_service.get_post(db, post_id)
    if post is None or not can_access(post.business_id):
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    try:
        run, post = writer_service.write_post(db, post)
    except ValueError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return WriteResult(run_id=run.id, mode=run.steps[0]["mode"], posts=social_service.posts_out(db, [post]))


@router.post("/write-week", response_model=WriteResult)
def write_week(
    business_id: int,
    start: Optional[date] = Query(default=None, description="First day (default: tomorrow)"),
    db: Session = Depends(get_db),
):
    """Write every AI idea planned for the 7 days from `start`."""
    business = business_or_404(business_id, db)
    run, posts, problems = writer_service.write_week(db, business, start or _tomorrow())
    mode = run.steps[0]["mode"] if run.steps else run.ai_mode
    return WriteResult(run_id=run.id, mode=mode, posts=social_service.posts_out(db, posts), problems=problems)

