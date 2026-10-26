"""
Writer service - runs the Writer agent on posts and saves the result.

    write_post   one post: idea/draft → draft with caption, hashtags, script, shot list
    write_week   every AI idea in a date range, in one go

The post becomes a "draft": the owner reads it, edits if they like, adds the
photo/video, then schedules it. Nothing is ever posted without the owner.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import get_llm
from app.agents.nodes.writer_agent import run_writer
from app.festivals import FIXED_DAYS, LUNAR_DAYS
from app.models import AgentRun, Business, Post
from app.services.social_service import check_platform_rules

IST = timezone(timedelta(hours=5, minutes=30))
WRITABLE = ("idea", "draft")


def _festival_for(post: Post) -> str | None:
    """If the post's title mentions a festival, return its name (e.g. 'Diwali')."""
    names = {e.name for e in FIXED_DAYS.values()} | {e.name for e in LUNAR_DAYS.values()}
    title = f"{post.title} {post.media_note}".lower()
    return next((n for n in sorted(names, key=len, reverse=True) if n.lower() in title), None)


def _business_dict(b: Business) -> dict:
    return {"name": b.name, "industry": b.industry, "area": b.area, "city": b.city, "services": b.services,
            "brand_voice": b.brand_voice, "target_audience": b.target_audience, "phone": b.phone}


def _write_one(post: Post, business: Business) -> dict:
    """Write one post in place; returns its diary entry."""
    if post.status not in WRITABLE:
        raise ValueError(f"Post {post.id} is '{post.status}'; only ideas and drafts can be (re)written")
    info = {"id": post.id, "platform": post.platform, "kind": post.kind, "pillar": post.pillar,
            "title": post.title or post.pillar, "media_note": post.media_note}
    result = run_writer(info, _business_dict(business), _festival_for(post))
    written = result.data
    check_platform_rules(post.platform, written.caption, written.hashtags)

    idea = post.media_note
    post.caption = written.caption
    post.hashtags = written.hashtags
    post.script = written.script
    post.media_note = f"{written.shot_list}\n\nIdea: {idea}" if idea and idea not in written.shot_list else written.shot_list
    post.status = "draft"

    entry = result.log_entry("writer")
    entry["output"] = {"post_id": post.id, "caption_chars": len(written.caption), "hashtags": len(written.hashtags)}
    return entry


def _run(db: Session, business: Business, posts: list[Post]) -> tuple[AgentRun, list[Post], list[str]]:
    run = AgentRun(business_id=business.id, workflow="content_write", status="running", ai_mode=get_llm().mode)
    db.add(run)
    db.commit()
    steps, done, problems = [], [], []
    for post in posts:
        try:
            steps.append(_write_one(post, business))
            done.append(post)
        except ValueError as problem:
            problems.append(str(problem))
    run.steps = steps
    run.status = "success" if done or not posts else "failed"
    run.error = "; ".join(problems)[:500] or None
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run, done, problems


def write_post(db: Session, post: Post) -> tuple[AgentRun, Post]:
    business = db.get(Business, post.business_id)
    if post.status not in WRITABLE:
        raise ValueError(f"This post is '{post.status}'; only ideas and drafts can be (re)written")
    run, done, problems = _run(db, business, [post])
    if problems:
        raise ValueError(problems[0])
    return run, post


def write_week(db: Session, business: Business, start: date, days: int = 7) -> tuple[AgentRun, list[Post], list[str]]:
    """Write every AI idea scheduled in [start, start+days)."""
    begin = datetime.combine(start, datetime.min.time(), tzinfo=IST).astimezone(timezone.utc)
    end = begin + timedelta(days=days)
    ideas = list(db.scalars(select(Post).where(
        Post.business_id == business.id, Post.status == "idea",
        Post.scheduled_for >= begin, Post.scheduled_for < end).order_by(Post.scheduled_for)))
    return _run(db, business, ideas)
