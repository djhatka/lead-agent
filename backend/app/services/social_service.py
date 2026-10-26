"""
Social service - the clerk for social accounts and posts.

Besides saving and loading, it does two important jobs:

1. PLATFORM RULES: e.g. an Instagram caption can't be longer than 2,200
   characters or have more than 30 hashtags. We check before saving, so a
   post never fails at publishing time.

2. POST → LEADS → MONEY: for every post it counts the enquiries that came
   from it, how many bought, and the ₹ earned. Likes are nice; this is
   what actually matters to a business owner.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Lead, Post, SocialAccount
from app.services import media_service
from app.schemas import (
    CAPTION_LIMITS, MAX_HASHTAGS, PostCreate, PostOut, PostStatsUpdate, PostUpdate,
    SocialAccountCreate, SocialAccountUpdate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def list_accounts(db: Session, business_id: int) -> list[SocialAccount]:
    return list(db.scalars(select(SocialAccount).where(SocialAccount.business_id == business_id)
                           .order_by(SocialAccount.id)))


def get_account(db: Session, account_id: int) -> Optional[SocialAccount]:
    return db.get(SocialAccount, account_id)


def create_account(db: Session, data: SocialAccountCreate) -> SocialAccount:
    exists = db.scalar(select(SocialAccount).where(
        SocialAccount.business_id == data.business_id, SocialAccount.platform == data.platform,
        SocialAccount.handle == data.handle))
    if exists:
        raise ValueError(f"@{data.handle} on {data.platform} is already added for this business")
    account = SocialAccount(**data.model_dump())
    db.add(account)
    db.commit()
    return account


def update_account(db: Session, account: SocialAccount, data: SocialAccountUpdate) -> SocialAccount:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value.lstrip("@") if field == "handle" and value else value)
    db.commit()
    return account


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
def check_platform_rules(platform: str, caption: str, hashtags: list[str]) -> None:
    """Raise ValueError if the post breaks the platform's own limits."""
    limit = CAPTION_LIMITS.get(platform)
    if limit and len(caption) > limit:
        raise ValueError(f"Caption is {len(caption)} characters; {platform} allows {limit}")
    max_tags = MAX_HASHTAGS.get(platform)
    if max_tags and len(hashtags) > max_tags:
        raise ValueError(f"{len(hashtags)} hashtags; {platform} allows {max_tags}")


def create_post(db: Session, account: SocialAccount, data: PostCreate) -> Post:
    check_platform_rules(account.platform, data.caption, data.hashtags)
    if data.scheduled_for and _as_utc(data.scheduled_for) <= _now():
        raise ValueError("scheduled_for must be in the future")
    post = Post(business_id=account.business_id, platform=account.platform,
                **data.model_dump(exclude={"account_id", "media_id"}), account_id=account.id)
    if data.media_id:
        media_service.attach(db, post, data.media_id)   # a photo/video from the library
    db.add(post)
    db.flush()                                       # gives the post its id
    if not post.campaign:
        post.campaign = f"post-{post.id}"            # tracking tag for links in this post
    db.commit()
    return post


def update_post(db: Session, post: Post, data: PostUpdate) -> Post:
    changes = data.model_dump(exclude_unset=True)
    if post.status == "published" and set(changes) & {"caption", "hashtags", "kind", "scheduled_for", "media_id", "media_url"}:
        raise ValueError("This post is already published; its content can't be changed here")
    check_platform_rules(post.platform, changes.get("caption", post.caption), changes.get("hashtags", post.hashtags))

    new_status = changes.get("status", post.status)
    when = changes.get("scheduled_for", post.scheduled_for)
    if new_status == "scheduled":
        if when is None:
            raise ValueError("A scheduled post needs scheduled_for (when to publish it)")
        if "scheduled_for" in changes and _as_utc(when) <= _now():
            raise ValueError("scheduled_for must be in the future")

    with_media = "media_id" in changes
    media_id = changes.pop("media_id", None)
    for field, value in changes.items():
        setattr(post, field, value)
    if with_media:
        media_service.attach(db, post, media_id)     # checks it's this business's file and the right kind
    if new_status == "published" and post.published_at is None:
        post.published_at = _now()
    db.commit()
    return post


def update_stats(db: Session, post: Post, data: PostStatsUpdate) -> Post:
    if post.status != "published":
        raise ValueError("Only published posts have numbers")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    post.stats_updated_at = _now()
    db.commit()
    return post


def delete_post(db: Session, post: Post) -> None:
    if post.status == "published":
        raise ValueError("Published posts are kept for the records; they can't be deleted")
    db.delete(post)
    db.commit()


def get_post(db: Session, post_id: int) -> Optional[Post]:
    return db.get(Post, post_id)


def list_posts(db: Session, business_id: int, platform: Optional[str] = None, status: Optional[str] = None,
               pillar: Optional[str] = None, kind: Optional[str] = None,
               limit: int = 50, offset: int = 0) -> tuple[list[Post], int]:
    query = select(Post).where(Post.business_id == business_id)
    if platform:
        query = query.where(Post.platform == platform)
    if status:
        query = query.where(Post.status == status)
    if pillar:
        query = query.where(Post.pillar == pillar)
    if kind:
        query = query.where(Post.kind == kind)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    # Newest first: published date, or scheduled date, or created date
    order = func.coalesce(Post.published_at, Post.scheduled_for, Post.created_at).desc()
    posts = list(db.scalars(query.order_by(order).limit(limit).offset(offset)))
    return posts, total


def post_for_campaign(db: Session, business_id: int, campaign: Optional[str]) -> Optional[Post]:
    """Find the post whose tracking tag matches, e.g. utm_campaign=post-12."""
    if not campaign:
        return None
    return db.scalar(select(Post).where(Post.business_id == business_id, Post.campaign == campaign))


# ---------------------------------------------------------------------------
# Post → leads → money
# ---------------------------------------------------------------------------
def lead_results(db: Session, post_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """For each post: (leads, won, revenue), counted in ONE database query."""
    if not post_ids:
        return {}
    won = case((Lead.status == "won", 1), else_=0)
    money = case((Lead.status == "won", func.coalesce(Lead.job_value, 0)), else_=0)
    rows = db.execute(
        select(Lead.post_id, func.count(Lead.id), func.sum(won), func.sum(money))
        .where(Lead.post_id.in_(post_ids)).group_by(Lead.post_id)
    )
    return {post_id: (count, int(w or 0), int(m or 0)) for post_id, count, w, m in rows}


def to_out(post: Post, results: tuple[int, int, int] = (0, 0, 0)) -> PostOut:
    # Copy the post's own fields; the four worked-out ones are filled in below
    worked_out = {"engagement_rate", "enquiries", "sales", "revenue"}
    out = PostOut.model_validate({f: getattr(post, f) for f in PostOut.model_fields if f not in worked_out})
    interactions = post.likes + post.comments + post.shares + post.saves
    out.engagement_rate = round(100 * interactions / post.reach, 1) if post.reach else 0.0
    out.enquiries, out.sales, out.revenue = results
    return out


def posts_out(db: Session, posts: list[Post]) -> list[PostOut]:
    results = lead_results(db, [p.id for p in posts])
    return [to_out(p, results.get(p.id, (0, 0, 0))) for p in posts]
