"""
Growth facts - every number the weekly review needs, calculated by plain code.

The AI agents in the growth workflow only READ these facts and explain them.
They never calculate anything themselves, so they can't invent a number.

It compares THIS week (last 7 days) with the week before, and adds the
bigger 90-day picture (which sources and posts really earn money).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.festivals import upcoming
from app.models import Business, Lead, Post, SocialAccount
from app.platforms import PLATFORMS, platforms_for
from app.services import analytics_service as calc
from app.services.content_stats import content_stats
from app.services.reputation_service import summary as reputation_summary

IST = timezone(timedelta(hours=5, minutes=30))
POSTS_PER_WEEK_TARGET = {"instagram": 3, "facebook": 1, "google": 1}


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _change(now: float, before: float):
    """% change, or None when there's nothing to compare with."""
    return round(100 * (now - before) / before, 1) if before else None


def collect(db: Session, business: Business) -> dict:
    now = datetime.now(timezone.utc)
    week_ago, two_weeks_ago = now - timedelta(days=7), now - timedelta(days=14)

    recent = calc.load_leads(db, business.id, 14)
    this_week = [l for l in recent if _utc(l.created_at) >= week_ago]
    last_week = [l for l in recent if two_weeks_ago <= _utc(l.created_at) < week_ago]
    tw, lw = calc.overview(this_week, 7), calc.overview(last_week, 7)

    ninety = calc.summary(db, business.id, 90)
    content = content_stats(db, business.id, 90)

    # Posting in the last 7 days, per platform
    posts_week = list(db.scalars(select(Post).where(
        Post.business_id == business.id, Post.status == "published", Post.published_at >= week_ago)))
    posted = {p: sum(1 for x in posts_week if x.platform == p) for p in POSTS_PER_WEEK_TARGET}
    accounts = sorted({a.platform for a in db.scalars(select(SocialAccount).where(
        SocialAccount.business_id == business.id))})
    upcoming_posts = db.scalars(select(Post).where(
        Post.business_id == business.id, Post.status.in_(["idea", "draft", "scheduled"]),
        Post.scheduled_for >= now, Post.scheduled_for < now + timedelta(days=7)).order_by(Post.scheduled_for))

    # Industry platforms (Practo for clinics, Zomato for restaurants...) and whether
    # any enquiry came from them in 90 days (= they're probably listed there)
    sources_90 = {s.source for s in ninety.sources}
    industry_platforms = [{"key": p.key, "name": p.name, "brings_leads": p.key in sources_90}
                          for p in platforms_for(business.industry)
                          if p.category in ("marketplace", "directory") and p.industries != ("all",)]

    hot_waiting = [l for l in this_week + last_week
                   if l.analysis and l.analysis.priority == "hot" and l.status in ("new", "contacted")]

    return {
        "business": {"name": business.name, "industry": business.industry, "area": business.area,
                     "city": business.city, "services": business.services, "brand_voice": business.brand_voice},
        "period": {"from": week_ago.astimezone(IST).date().isoformat(), "to": now.astimezone(IST).date().isoformat()},
        "this_week": {
            "leads": tw.leads, "won": tw.won, "revenue": tw.revenue, "conversion_rate": tw.conversion_rate,
            "median_reply_minutes": tw.median_reply_minutes, "never_replied": tw.never_replied,
            "hot_waiting": len(hot_waiting),
            "sources": [{"name": s.name, "leads": s.leads, "won": s.won, "revenue": s.revenue}
                        for s in calc.sources(this_week)],
        },
        "last_week": {"leads": lw.leads, "won": lw.won, "revenue": lw.revenue},
        "change": {"leads": _change(tw.leads, lw.leads), "revenue": _change(tw.revenue, lw.revenue)},
        "ninety_days": {
            "sources": [{"key": s.source, "name": s.name, "leads": s.leads, "share_of_leads": s.share_of_leads,
                         "conversion_rate": s.conversion_rate, "revenue": s.revenue,
                         "share_of_revenue": s.share_of_revenue} for s in ninety.sources],
            "conversion_rate": ninety.overview.conversion_rate,
            "reply_speed": [b.model_dump() for b in ninety.timing.conversion_by_reply_speed],
            "highlights": ninety.highlights,
            "top_services": [{"service": s.service, "revenue": s.revenue} for s in ninety.services[:3]],
        },
        "content": {
            "by_pillar": [{"name": g.name, "posts": g.posts, "avg_reach": g.avg_reach, "enquiries": g.enquiries,
                           "revenue_per_post": g.revenue_per_post} for g in content.by_pillar],
            "findings": content.findings,
            "posted_this_week": posted,
            "targets": POSTS_PER_WEEK_TARGET,
            "accounts": accounts,
            "planned_next_7_days": [{"title": p.title, "platform": p.platform, "status": p.status}
                                    for p in upcoming_posts],
        },
        "industry_platforms": industry_platforms,
        "reputation": {**reputation_summary(db, business.id).model_dump(),
                       "has_review_link": bool(business.google_review_link)},
        "events": upcoming(now.astimezone(IST).date(), 14, business.industry, look_ahead=0),
    }


def platform_name(key: str) -> str:
    return PLATFORMS[key].name if key in PLATFORMS else key
