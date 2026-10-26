"""
Competitor watch (Task 35): 3-5 nearby rivals, their rating and review count, with an
alert whenever one of them moves. No official Google ranking API exists, so real
numbers need a paid map-search data service (DATAFORSEO_LOGIN/PASSWORD in .env). Until
then this runs in free MOCK mode with realistic, slowly-drifting pretend numbers -
stable per competitor, so repeated checks look like a real (slow-moving) business
instead of random noise.

    list_for            the competitors a business watches
    add / remove         owner actions (max 5 per business)
    check                look up one competitor now (real call, or mock)
    weekly_checks_due    the scheduler: re-check anything not looked at in 6+ days
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations import mapsearch
from app.integrations.base import IntegrationError
from app.models import Business, Competitor, CompetitorAlert, utc_now
from app.services.event_bus import bus

logger = logging.getLogger("competitors")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops timezone info on the way back out of the database even for a
    DateTime(timezone=True) column, so a value that round-tripped through it can come
    back naive while utc_now() stays aware. Treat a naive value as UTC before any
    subtraction or comparison, the same way scheduler_service.py and auth/access.py do."""
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))

MAX_COMPETITORS = 5
RATING_MOVE_THRESHOLD = 0.1     # smaller moves are just noise, not worth an alert
RECHECK_AFTER_DAYS = 6          # roughly weekly, same cadence as the growth review


def list_for(db: Session, business_id: int) -> list[Competitor]:
    return list(db.scalars(select(Competitor).where(Competitor.business_id == business_id).order_by(Competitor.name)))


def add(db: Session, business: Business, name: str, area: str = "") -> Competitor:
    name = name.strip()
    if not name:
        raise ValueError("Give the competitor's name")
    if len(list_for(db, business.id)) >= MAX_COMPETITORS:
        raise ValueError(f"You can watch at most {MAX_COMPETITORS} competitors - remove one first")
    competitor = Competitor(business_id=business.id, name=name,
                            area=(area or business.area or business.city or "").strip())
    db.add(competitor)
    db.commit()
    check(db, competitor)   # look it up right away, so the owner sees numbers immediately
    return competitor


def remove(db: Session, competitor: Competitor) -> None:
    db.delete(competitor)
    db.commit()


def _mock_listing(competitor: Competitor) -> dict:
    """Realistic pretend numbers: fixed per competitor (so they don't jump around between
    checks) but drifting slowly forward each week, so it reads like a real business."""
    seed = sum(ord(ch) for ch in competitor.name) + competitor.business_id
    base = random.Random(seed)
    base_rating = round(base.uniform(3.6, 4.7), 1)
    base_reviews = base.randint(40, 400)

    created = _utc(competitor.created_at) or utc_now()
    weeks = max(0, (utc_now() - created).days // 7)
    this_week = random.Random(seed + weeks)                  # a new, but deterministic, "this week's" draw
    reviews = base_reviews + sum(this_week.randint(0, 4) for _ in range(weeks)) if weeks else base_reviews
    rating = max(3.0, min(5.0, base_rating + this_week.uniform(-0.1, 0.1)))

    return {"place_id": "", "rating": round(rating, 1), "review_count": reviews,
            "category": competitor.category or "Local business", "address": competitor.address or competitor.area}


def check(db: Session, competitor: Competitor) -> Competitor:
    """Look up this competitor's current listing (real DataForSEO call once configured,
    otherwise a realistic mock), compare it with last time, and raise an alert if
    something moved enough to matter."""
    try:
        if settings.mapsearch_enabled:
            data = mapsearch.search_listing(competitor.name, competitor.area)
            if data is None:
                competitor.problem = "Not found on Google Maps with this name and area - check the spelling"
                db.commit()
                return competitor
        else:
            data = _mock_listing(competitor)
    except IntegrationError as problem:
        competitor.problem = str(problem)
        db.commit()
        logger.warning("Competitor check failed for %s: %s", competitor.name, problem)
        return competitor

    competitor.previous_rating = competitor.rating
    competitor.previous_review_count = competitor.review_count
    competitor.rating = data.get("rating")
    competitor.review_count = data.get("review_count")
    competitor.category = data.get("category") or competitor.category
    competitor.address = data.get("address") or competitor.address
    competitor.place_id = data.get("place_id") or competitor.place_id
    competitor.problem = ""
    competitor.last_checked_at = utc_now()
    db.commit()

    _raise_alerts(db, competitor)
    return competitor


def _raise_alerts(db: Session, competitor: Competitor) -> None:
    if competitor.previous_rating is None and competitor.previous_review_count is None:
        return   # first check ever: nothing to compare against yet

    moved: list[tuple[str, str]] = []
    if competitor.review_count is not None and competitor.previous_review_count is not None:
        gained = competitor.review_count - competitor.previous_review_count
        if gained > 0:
            moved.append(("new_reviews", f"{competitor.name} got {gained} new review"
                                         f"{'s' if gained != 1 else ''} (now {competitor.review_count})"))
    if competitor.rating is not None and competitor.previous_rating is not None:
        delta = competitor.rating - competitor.previous_rating
        if abs(delta) >= RATING_MOVE_THRESHOLD:
            direction = "up" if delta > 0 else "down"
            moved.append((f"rating_{direction}", f"{competitor.name}'s rating moved {direction} to "
                                                  f"{competitor.rating} (was {competitor.previous_rating})"))
    for kind, message in moved:
        db.add(CompetitorAlert(business_id=competitor.business_id, competitor_id=competitor.id,
                               kind=kind, message=message))
        bus.publish(competitor.business_id, "competitor.moved", message, "", {"competitor_id": competitor.id})
    if moved:
        db.commit()


def recent_alerts(db: Session, business_id: int, limit: int = 20) -> list[CompetitorAlert]:
    return list(db.scalars(select(CompetitorAlert).where(CompetitorAlert.business_id == business_id)
                           .order_by(CompetitorAlert.created_at.desc()).limit(limit)))


def weekly_checks_due(db: Session, now: Optional[datetime] = None) -> int:
    """Called by the scheduler: every watched competitor not checked in the last
    RECHECK_AFTER_DAYS days gets a fresh look. Skips businesses whose plan has ended,
    so a lapsed trial never spends real DataForSEO credit."""
    from app.services.billing_service import paused_business_ids

    now = _utc(now) or utc_now()
    stale_before = now - timedelta(days=RECHECK_AFTER_DAYS)
    paused = paused_business_ids(db)
    checked = 0
    for competitor in db.scalars(select(Competitor).where(
            (Competitor.last_checked_at.is_(None)) | (Competitor.last_checked_at <= stale_before))):
        if competitor.business_id in paused:
            continue
        check(db, competitor)
        checked += 1
    return checked
