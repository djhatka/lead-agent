"""
Scheduler service - the alarm clock for posts, plus the performance tracker.

    schedule_post   draft → scheduled for a time (owner approved it)
    unschedule      scheduled → back to draft
    publish_now     publish one post immediately
    publish_due     publish every scheduled post whose time has come
    refresh_stats   re-read reach/likes/... for recent published posts
    run_cycle       publish_due + refresh_stats + review requests + Monday growth reviews
                    + the daily follow-up note (Task 30) + ...:
                    what the background loop runs every minute

The background loop itself is started in main.py when the server starts.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Post, SocialAccount
from app.services.billing_service import paused_business_ids
from app.services.event_bus import bus
from app.services.publishers import PublishError, get_publisher

logger = logging.getLogger("scheduler")

# Tests swap this, like in lead_pipeline.py
SESSION_FACTORY = SessionLocal

# A small note of what happened last time, for the /scheduler/status page
LAST_RUN: dict = {"at": None, "published": 0, "failed": 0, "stats_updated": 0,
                  "review_requests_sent": 0, "growth_reviews": 0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def schedule_post(db: Session, post: Post, when: datetime) -> Post:
    """Approve a post and set when it goes out."""
    if post.status not in ("idea", "draft", "failed", "scheduled"):
        raise ValueError(f"A '{post.status}' post can't be scheduled")
    if _utc(when) <= _now():
        raise ValueError("Pick a time in the future")
    if post.kind != "story" and not post.caption.strip():
        raise ValueError("Write the caption first (the Writer agent can do it: POST /content/write/{id})")
    post.scheduled_for = when
    post.status = "scheduled"
    post.publish_error = ""
    db.commit()
    return post


def unschedule(db: Session, post: Post) -> Post:
    if post.status != "scheduled":
        raise ValueError("Only scheduled posts can be unscheduled")
    post.status = "draft"
    db.commit()
    return post


def _publish(db: Session, post: Post) -> bool:
    """Publish one post. Returns True on success; on failure the post is
    marked 'failed' with the reason, so the owner can fix it and reschedule."""
    account = db.get(SocialAccount, post.account_id)
    try:
        post.external_id = get_publisher(account).publish(post, account)
    except PublishError as problem:
        post.status = "failed"
        post.publish_error = str(problem)
        db.commit()
        logger.warning("Post %s failed to publish: %s", post.id, problem)
        bus.publish(post.business_id, "post.failed", f"Post couldn't be published on {post.platform}",
                    str(problem), {"post_id": post.id})
        return False
    post.status = "published"
    post.published_at = _now()
    post.publish_error = ""
    db.commit()
    bus.publish(post.business_id, "post.published", f"Posted on {post.platform} ✅", post.title or post.caption[:80],
                {"post_id": post.id})
    return True


def publish_now(db: Session, post: Post) -> Post:
    if post.status == "published":
        raise ValueError("Already published")
    if post.status == "idea":
        raise ValueError("This is still an idea: write it first")
    _publish(db, post)
    return post


# ---------------------------------------------------------------------------
# The automatic jobs
# ---------------------------------------------------------------------------
def publish_due(db: Session, now: Optional[datetime] = None) -> tuple[int, int]:
    """Publish every scheduled post whose time has come. Returns (published, failed)."""
    now = now or _now()
    due = list(db.scalars(select(Post).where(Post.status == "scheduled", Post.scheduled_for <= now)
                          .order_by(Post.scheduled_for)))
    paused = paused_business_ids(db) if due else set()
    ok = failed = 0
    for post in due:
        if post.business_id in paused:
            # Plan ended: don't post (a "Diwali offer" going out weeks late would be worse)
            post.status = "failed"
            post.publish_error = "Not posted because your plan has ended. Choose a plan, then reschedule it."
            db.commit()
            failed += 1
        elif _publish(db, post):
            ok += 1
        else:
            failed += 1
    return ok, failed


def refresh_stats(db: Session, business_id: Optional[int] = None, force: bool = False) -> int:
    """Re-read the numbers of posts published in the last 30 days.
    Each post is refreshed at most every `stats_refresh_hours`, unless force=True."""
    since = _now() - timedelta(days=30)
    query = select(Post).where(Post.status == "published", Post.published_at >= since)
    if business_id:
        query = query.where(Post.business_id == business_id)
    stale_before = _now() - timedelta(hours=settings.stats_refresh_hours)
    updated = 0
    for post in db.scalars(query):
        if not force and post.stats_updated_at and _utc(post.stats_updated_at) > stale_before:
            continue
        account = db.get(SocialAccount, post.account_id)
        try:
            numbers = get_publisher(account).fetch_stats(post, account)
        except PublishError:
            continue
        for field, value in numbers.items():
            setattr(post, field, max(getattr(post, field) or 0, value))   # numbers only go up
        post.stats_updated_at = _now()
        updated += 1
    db.commit()
    return updated


def run_cycle(db: Session) -> dict:
    from app.services.growth_service import weekly_reviews_due   # imported here to keep startup light
    from app.services.reputation_service import send_due_requests

    from app.services import (alerts_service, competitor_service, connection_service, dues_service, email_service,
                              followup_service, renewal_service, roi_service)

    published, failed = publish_due(db)
    updated = refresh_stats(db)
    asked = send_due_requests(db)
    reviews = weekly_reviews_due(db) if settings.weekly_review_enabled else 0
    google_reviews = connection_service.sync_due(db)            # new Google reviews (every 30 min per business)
    renewed = connection_service.refresh_expiring(db)           # Instagram keys before they run out
    reminders = email_service.trial_reminders(db)               # "your trial ends in 3 days" (once each)
    alerts = alerts_service.send_due(db)                        # owner alerts held in quiet hours, or retries
    roi_reports = roi_service.monthly_reports_due(db)           # on the 1st: last month's "what we did for you"
    followups = followup_service.daily_reminders(db)            # after 10am: "3 enquiries need a follow-up"
    dues = dues_service.send_due_reminders(db)                  # polite "₹2,000 is due" WhatsApps (10am-8pm)
    renewal_reminders = renewal_service.daily_reminders(db)    # "Priya's membership ends in 5 days" (after 10am)
    competitor_checks = competitor_service.weekly_checks_due(db)   # re-check any watched competitor 6+ days stale
    emails = email_service.deliver_pending(db)                  # send queued emails, retry failed ones
    backup = _nightly_backup(db)                                # after 3am India time, once a day
    LAST_RUN.update({"at": _now(), "published": published, "failed": failed, "stats_updated": updated,
                     "review_requests_sent": asked, "growth_reviews": reviews,
                     "google_reviews_fetched": google_reviews, "keys_renewed": renewed,
                     "trial_reminders": reminders, "roi_reports": roi_reports, "followup_reminders": followups, "payment_reminders": dues, "owner_alerts": alerts, "emails_sent": emails,
                     "renewal_reminders": renewal_reminders, "competitor_checks": competitor_checks, "backup": backup})
    return dict(LAST_RUN)


def _nightly_backup(db: Session) -> Optional[str]:
    from app.services.backup_service import nightly_backup_due
    try:
        made = nightly_backup_due(db.get_bind())
    except Exception:  # noqa: BLE001 - a failed backup must never stop the scheduler; it retries next minute
        logger.exception("Nightly backup failed")
        return "failed"
    return made.name if made else None


def run_cycle_in_background() -> None:
    """Called by the background loop in main.py, with its own database session."""
    db = SESSION_FACTORY()
    try:
        result = run_cycle(db)
        if result["published"] or result["failed"]:
            logger.info("Scheduler: %s published, %s failed", result["published"], result["failed"])
    finally:
        db.close()
