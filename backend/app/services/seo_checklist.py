"""
Local SEO checklist (Task 34): is this business set up to rank well on Google Maps / Search?

No AI here - like the go-live checklist (launch_check.py), this is a plain-code checklist.
Each item says not just what's missing but WHY it affects ranking, so the owner learns the
"how do I get good local SEO" rules while fixing things, instead of just ticking boxes.

Used by GET /seo?business_id=1.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Business, Connection, Post, Review, utc_now

RECENT_DAYS = 30            # Google rewards a profile that's kept active
MIN_GOOGLE_REVIEWS = 5      # more reviews = more trust signals
GOOD_RATING = 4.0
GOOD_REPLY_RATE = 0.8       # Google notices (and customers notice) when you reply to reviews


def _google_connection(db: Session, business_id: int) -> Connection | None:
    return db.scalar(
        select(Connection).where(Connection.business_id == business_id, Connection.platform == "google")
    )


def _google_reviews(db: Session, business_id: int) -> list[Review]:
    return list(db.scalars(
        select(Review).where(Review.business_id == business_id, Review.platform == "google")
    ))


def _recent_google_posts(db: Session, business_id: int) -> int:
    since = utc_now() - timedelta(days=RECENT_DAYS)
    return db.scalar(
        select(func.count(Post.id)).where(
            Post.business_id == business_id, Post.platform == "google",
            Post.status == "published", Post.published_at >= since,
        )
    ) or 0


def build_checklist(db: Session, business: Business) -> dict:
    """The full checklist for one business: NAP (name/address/phone) consistency,
    a complete Google profile, and ongoing activity (posts, reviews, replies)."""
    conn = _google_connection(db, business.id)
    google_reviews = _google_reviews(db, business.id)
    recent_posts = _recent_google_posts(db, business.id)

    replied = sum(1 for r in google_reviews if r.reply_status == "posted")
    reply_rate = (replied / len(google_reviews)) if google_reviews else 0.0
    avg_rating = (sum(r.rating for r in google_reviews) / len(google_reviews)) if google_reviews else 0.0

    items = [
        dict(
            item="Business name is filled in",
            ok=bool(business.name and business.name.strip()),
            why_it_matters="Google matches search terms against your exact business name. A missing or "
                            "generic name makes it harder for searches like 'gym near me' to find you.",
            how_to_fix="Settings -> Business profile -> set your real business name, exactly as it "
                       "appears on your signboard and on Google Maps.",
        ),
        dict(
            item="City and area are set",
            ok=bool(business.city and business.area),
            why_it_matters="'Near me' and area searches (e.g. 'gym in Dwarka') are how most local "
                            "customers search. Google needs your area to show you for those.",
            how_to_fix="Settings -> Business profile -> fill in City and Area (the exact locality, e.g. "
                       "'Dwarka', not just the city name).",
        ),
        dict(
            item="Phone number is set",
            ok=bool(business.phone),
            why_it_matters="Your phone number must be IDENTICAL everywhere it's listed (your website, "
                            "Google, Justdial...). This is called NAP consistency (Name, Address, Phone), "
                            "and mismatched numbers confuse Google about which listing is really you, "
                            "which hurts ranking.",
            how_to_fix="Settings -> Business profile -> add your phone number, in the same format shown "
                       "on your Google Business Profile.",
        ),
        dict(
            item="Website is set",
            ok=bool(business.website),
            why_it_matters="A working website link is one of the strongest trust signals Google uses, "
                            "and it's one more place your name, address and phone must match exactly.",
            how_to_fix="Settings -> Business profile -> add your website address.",
        ),
        dict(
            item="Business description names your services and area",
            ok=bool(business.description and len(business.description.strip()) >= 80),
            why_it_matters="Google reads your description for the service and area keywords that decide "
                            "which searches you appear in. A thin or empty description gives it nothing "
                            "to match against.",
            how_to_fix="Settings -> Business profile -> write 2-3 sentences naming your main services and "
                       "your area, the way a customer would search (e.g. 'Zumba and personal training in "
                       "Dwarka, West Delhi').",
        ),
        dict(
            item="Services are listed",
            ok=bool(business.services and len(business.services) > 0),
            why_it_matters="Each service you list is a term Google can match to a search - the same way "
                            "'Services' work on your Google Business Profile.",
            how_to_fix="Settings -> Business profile -> add your services, in the plain words customers "
                       "actually search with.",
        ),
        dict(
            item="Google review link is saved",
            ok=bool(business.google_review_link),
            why_it_matters="Review count and recency both affect ranking. A saved link makes it one tap "
                            "for a happy customer to leave a review, instead of them giving up partway "
                            "through finding your listing.",
            how_to_fix="Open your listing on Google Maps -> Share -> Ask for reviews -> copy the link "
                       "into Settings -> Business profile -> Google review link.",
        ),
        dict(
            item="Google Business Profile is connected (not mock)",
            ok=bool(conn and conn.status == "connected" and conn.mode == "real"),
            why_it_matters="Without a real connection, review replies and Google posts made in Lead "
                            "Intel never actually reach Google, so they can't help your ranking.",
            how_to_fix="Settings -> Connections -> Connect Google Business Profile, and finish Google's "
                       "sign-in.",
        ),
        dict(
            item=f"A Google post went up in the last {RECENT_DAYS} days",
            ok=recent_posts > 0,
            why_it_matters="Google treats a profile that's actively updated as more trustworthy than one "
                            "left untouched for months, and a recent post can appear directly in search "
                            "results.",
            how_to_fix="Content -> plan a week, then write and schedule at least one post to Google.",
        ),
        dict(
            item=f"At least {MIN_GOOGLE_REVIEWS} Google reviews",
            ok=len(google_reviews) >= MIN_GOOGLE_REVIEWS,
            why_it_matters="Review count is one of Google's clearest trust signals, and more reviews "
                            "usually means more clicks from the map results too.",
            how_to_fix="Reputation -> turn on automatic review requests, so recently won customers are "
                       "asked for a review.",
        ),
        dict(
            item="Average rating is 4.0 or higher",
            ok=(avg_rating >= GOOD_RATING) if google_reviews else False,
            why_it_matters="Below 4 stars, Google tends to show competitors above you in the map results, "
                            "even when you rank well on everything else.",
            how_to_fix="Reputation -> reply to and resolve negative reviews, and ask happy customers for "
                       "reviews more often to balance the average.",
        ),
        dict(
            item=f"Replying to at least {int(GOOD_REPLY_RATE * 100)}% of Google reviews",
            ok=(reply_rate >= GOOD_REPLY_RATE) if google_reviews else False,
            why_it_matters="Google counts owner replies as a sign the business is active and cares, and "
                            "customers reading your reviews notice it too.",
            how_to_fix="Reputation -> Draft all, then approve and post the AI's draft reply to any review "
                       "still showing 'none'.",
        ),
    ]

    score = round(100 * sum(1 for c in items if c["ok"]) / len(items))
    return {"business_id": business.id, "score": score, "checks": items}
