"""
Planner service - runs the Content Planner for one business and saves the plan.

    1. Gather the facts: profile, accounts, content stats, top services,
       festivals, posts already planned
    2. Open a diary entry (agent_runs, workflow "content_plan")
    3. Ask the Content Planner agent for a plan
    4. Safety-check the plan (tidy) and save each post as an "idea" with its reason
    5. Close the diary entry

Planning the same week again REPLACES the AI's earlier ideas for that week,
but never touches posts the owner made or already scheduled/published.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import get_llm
from app.agents.nodes.content_planner import run_planner, tidy
from app.festivals import upcoming
from app.models import AgentRun, Business, Post, SocialAccount
from app.services import analytics_service, content_stats

IST = timezone(timedelta(hours=5, minutes=30))
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _window(start: date, days: int) -> tuple[datetime, datetime]:
    begin = datetime.combine(start, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    return begin, begin + timedelta(days=days)


def _as_ist(dt: datetime) -> datetime:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(IST)


def build_context(db: Session, business: Business, start: date, days: int) -> dict:
    accounts = list(db.scalars(select(SocialAccount).where(SocialAccount.business_id == business.id)))
    stats = content_stats.content_stats(db, business.id)
    services = analytics_service.services(analytics_service.load_leads(db, business.id, 90))
    begin, end = _window(start, days)

    # Posts already in this week that we must work around (anything not an AI idea)
    existing = db.scalars(select(Post).where(
        Post.business_id == business.id, Post.scheduled_for >= begin, Post.scheduled_for < end,
        ~((Post.status == "idea") & (Post.created_by == "ai"))))
    taken = [{"day": (_as_ist(p.scheduled_for).date() - start).days, "platform": p.platform,
              "title": p.title or p.pillar} for p in existing]

    return {
        "business": {"name": business.name, "industry": business.industry, "area": business.area,
                     "city": business.city, "description": business.description,
                     "services": business.services, "brand_voice": business.brand_voice,
                     "target_audience": business.target_audience},
        "platforms": sorted({a.platform for a in accounts}),
        "stats": stats.model_dump(),
        "top_services": [s.service for s in services if s.revenue > 0][:3],
        "events": upcoming(start, days, business.industry),
        "taken": taken,
        "start": start.isoformat(),
        "start_weekday": DAY_NAMES[start.weekday()],
        "days": days,
    }


def plan_week(db: Session, business: Business, start: Optional[date] = None, days: int = 7) -> tuple[AgentRun, list[Post], str, list[str]]:
    """Returns (diary entry, the new idea posts, the strategy text, notes about skipped posts)."""
    start = start or (datetime.now(IST).date() + timedelta(days=1))
    run = AgentRun(business_id=business.id, workflow="content_plan", status="running", ai_mode=get_llm().mode)
    db.add(run)
    db.commit()

    try:
        context = build_context(db, business, start, days)
        if not context["platforms"]:
            raise ValueError("This business has no social accounts yet. Add one first.")

        result = run_planner(context)
        kept, dropped = tidy(result.data, context)

        # Replace the AI's previous ideas for these dates
        begin, end = _window(start, days)
        for old in db.scalars(select(Post).where(
                Post.business_id == business.id, Post.status == "idea", Post.created_by == "ai",
                Post.scheduled_for >= begin, Post.scheduled_for < end)):
            db.delete(old)

        accounts = {a.platform: a for a in db.scalars(select(SocialAccount).where(
            SocialAccount.business_id == business.id))}
        new_posts: list[Post] = []
        for planned in kept:
            hour, minute = map(int, planned.time.split(":"))
            when = datetime.combine(start + timedelta(days=planned.day), time(hour, minute), tzinfo=IST)
            post = Post(business_id=business.id, account_id=accounts[planned.platform].id,
                        platform=planned.platform, kind=planned.kind, pillar=planned.pillar,
                        title=planned.title, media_note=planned.idea, ai_reason=planned.why,
                        status="idea", created_by="ai", scheduled_for=when.astimezone(timezone.utc))
            db.add(post)
            new_posts.append(post)
        db.flush()
        for post in new_posts:
            post.campaign = f"post-{post.id}"

        entry = result.log_entry("content_planner")
        entry["output"] = {"strategy": result.data.strategy, "planned": len(kept), "skipped": dropped}
        run.steps = [entry]
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run, new_posts, result.data.strategy, dropped

    except Exception as error:  # noqa: BLE001
        db.rollback()
        run = db.get(AgentRun, run.id)
        run.status = "failed"
        run.error = f"{type(error).__name__}: {error}"[:500]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise


def calendar(db: Session, business_id: int, start: date, days: int) -> list[dict]:
    """Every post in the date range (ideas, drafts, scheduled, published), grouped by day."""
    begin, end = _window(start, days)
    when = Post.published_at.is_not(None)
    posts = list(db.scalars(select(Post).where(Post.business_id == business_id).where(
        ((when) & (Post.published_at >= begin) & (Post.published_at < end)) |
        ((~when) & (Post.scheduled_for >= begin) & (Post.scheduled_for < end))
    )))
    by_day: dict[date, list[Post]] = {start + timedelta(days=i): [] for i in range(days)}
    for p in posts:
        day = _as_ist(p.published_at or p.scheduled_for).date()
        if day in by_day:
            by_day[day].append(p)
    for items in by_day.values():
        items.sort(key=lambda p: _as_ist(p.published_at or p.scheduled_for))
    return [{"date": d, "weekday": DAY_NAMES[d.weekday()], "posts": items} for d, items in by_day.items()]
