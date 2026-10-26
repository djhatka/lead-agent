"""
Content stats - "what kind of posts actually work for THIS business?"

Plain maths, no AI (same rule as analytics_service.py). Looks at a business's
published posts from the last N days and groups them three ways:

    by pillar    offer vs tips vs trend...  → reach, engagement, enquiries, ₹
    by kind      reel vs photo vs story...  → mostly about reach
    by platform  how often they post, and what each platform earns

Plus the best hour to post. The Content Planner reads all of this, so its
plan is based on the business's own results, not generic internet advice.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Post
from app.services.social_service import lead_results

IST = timezone(timedelta(hours=5, minutes=30))


class GroupStats(BaseModel):
    name: str                         # e.g. "offer", "reel", "instagram"
    posts: int
    avg_reach: int
    avg_engagement: float             # %
    enquiries: int
    sales: int
    revenue: int
    enquiries_per_post: float
    revenue_per_post: int


class ContentStats(BaseModel):
    days: int
    published_posts: int
    by_pillar: list[GroupStats]       # sorted: best ₹ per post first
    by_kind: list[GroupStats]         # sorted: best reach first
    by_platform: list[GroupStats]
    posts_per_week: dict[str, float]  # platform → how often they post
    best_hour: Optional[int]          # hour (India time) with the best average reach
    findings: list[str]               # plain-English summary of the above


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _group(name: str, posts: list[Post], results: dict) -> GroupStats:
    n = len(posts)
    reach = sum(p.reach for p in posts)
    interactions = sum(p.likes + p.comments + p.shares + p.saves for p in posts)
    enquiries = sum(results.get(p.id, (0, 0, 0))[0] for p in posts)
    sales = sum(results.get(p.id, (0, 0, 0))[1] for p in posts)
    revenue = sum(results.get(p.id, (0, 0, 0))[2] for p in posts)
    return GroupStats(
        name=name, posts=n, avg_reach=reach // n if n else 0,
        avg_engagement=round(100 * interactions / reach, 1) if reach else 0.0,
        enquiries=enquiries, sales=sales, revenue=revenue,
        enquiries_per_post=round(enquiries / n, 2) if n else 0.0,
        revenue_per_post=revenue // n if n else 0,
    )


def content_stats(db: Session, business_id: int, days: int = 90) -> ContentStats:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    posts = list(db.scalars(select(Post).where(
        Post.business_id == business_id, Post.status == "published", Post.published_at >= since)))
    results = lead_results(db, [p.id for p in posts])

    def grouped(key) -> list[GroupStats]:
        groups: dict[str, list[Post]] = defaultdict(list)
        for p in posts:
            groups[getattr(p, key)].append(p)
        return [_group(name, group, results) for name, group in groups.items()]

    by_pillar = sorted(grouped("pillar"), key=lambda g: (-g.revenue_per_post, -g.enquiries_per_post))
    by_kind = sorted(grouped("kind"), key=lambda g: -g.avg_reach)
    by_platform = sorted(grouped("platform"), key=lambda g: -g.posts)

    weeks = max(days / 7, 1)
    per_week = {g.name: round(g.posts / weeks, 1) for g in by_platform}

    reach_by_hour: dict[int, list[int]] = defaultdict(list)
    for p in posts:
        reach_by_hour[_utc(p.published_at).astimezone(IST).hour].append(p.reach)
    usable = {h: sum(v) / len(v) for h, v in reach_by_hour.items() if len(v) >= 3}   # need a few posts to judge
    best_hour = max(usable, key=usable.get) if usable else None

    return ContentStats(days=days, published_posts=len(posts), by_pillar=by_pillar, by_kind=by_kind,
                        by_platform=by_platform, posts_per_week=per_week, best_hour=best_hour,
                        findings=_findings(by_pillar, by_kind, best_hour))


def _findings(by_pillar: list[GroupStats], by_kind: list[GroupStats], best_hour: Optional[int]) -> list[str]:
    notes: list[str] = []
    judged = [g for g in by_pillar if g.posts >= 3]          # too few posts → can't judge
    if not judged:
        return ["Not enough published posts yet to see what works. Post regularly for a few weeks."]

    money = [g for g in judged if g.revenue > 0]
    if money:
        best = money[0]
        enq = "1 enquiry" if best.enquiries == 1 else f"{best.enquiries} enquiries"
        sales = "1 sale" if best.sales == 1 else f"{best.sales} sales"
        notes.append(f"'{best.name}' posts earn the most: ₹{best.revenue_per_post:,} per post "
                     f"({enq}, {sales} from {best.posts} posts).")
    most_reach = max(judged, key=lambda g: g.avg_reach)
    if most_reach.revenue == 0 and most_reach.posts >= 3:
        notes.append(f"'{most_reach.name}' posts get the most reach ({most_reach.avg_reach:,} on average) "
                     f"but brought ₹0. Good for followers, not for customers: keep them few.")
    zero = [g.name for g in judged if g.enquiries == 0]
    if zero:
        notes.append(f"No enquiries at all from: {', '.join(zero)}.")
    if by_kind and len(by_kind) > 1 and by_kind[-1].avg_reach:
        top, low = by_kind[0], by_kind[-1]
        notes.append(f"{top.name.title()}s reach {top.avg_reach / low.avg_reach:.1f}x more people than {low.name}s.")
    if best_hour is not None:
        notes.append(f"Posts around {best_hour % 12 or 12}{'am' if best_hour < 12 else 'pm'} reach the most people.")
    return notes
