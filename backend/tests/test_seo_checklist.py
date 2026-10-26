"""
Task 34 checks: the local SEO checklist (NAP consistency, Google profile completeness,
ongoing activity) and its /seo endpoint.
"""

import itertools
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Business, Connection, Post, Review, SocialAccount
from app.services import seo_checklist

GYM = 1
NOW = datetime.now(timezone.utc)
_review_ids = itertools.count()


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _blank_business(db) -> Business:
    """Strip the gym down to nothing, so every profile check starts failing."""
    gym = db.get(Business, GYM)
    gym.name, gym.city, gym.area, gym.phone, gym.website = "", "", "", "", ""
    gym.description, gym.services, gym.google_review_link = "", [], ""
    for conn in db.scalars(select(Connection).where(Connection.business_id == GYM, Connection.platform == "google")):
        db.delete(conn)
    for review in db.scalars(select(Review).where(Review.business_id == GYM, Review.platform == "google")):
        db.delete(review)
    for post in db.scalars(select(Post).where(Post.business_id == GYM, Post.platform == "google")):
        db.delete(post)
    db.commit()
    return gym


def _complete_business(db) -> Business:
    gym = db.get(Business, GYM)
    gym.name, gym.city, gym.area = "Iron Pulse Fitness", "Delhi", "Dwarka"
    gym.phone, gym.website = "+919811000000", "https://ironpulsefitness.in"
    gym.description = "Zumba, personal training and group classes in Dwarka, West Delhi, for all fitness levels."
    gym.services = ["Zumba", "Personal training", "Group classes"]
    gym.google_review_link = "https://g.page/r/ironpulse/review"
    db.commit()
    return gym


def _review(db, business_id, *, rating, reply_status="none", when=None):
    review = Review(business_id=business_id, platform="google", external_id=f"g-{next(_review_ids)}",
                    rating=rating, reply_status=reply_status, reviewed_at=when or NOW)
    db.add(review)
    db.commit()
    return review


def _google_post(db, business_id, *, published_at):
    account = db.scalar(select(SocialAccount).where(SocialAccount.business_id == business_id,
                                                     SocialAccount.platform == "google"))
    post = Post(business_id=business_id, account_id=account.id, platform="google", status="published",
               published_at=published_at)
    db.add(post)
    db.commit()
    return post


# ---------------------------------------------------------------------------
# The checklist itself
# ---------------------------------------------------------------------------
def test_blank_business_fails_every_profile_check(db_session):
    gym = _blank_business(db_session)
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}

    assert by_item["Business name is filled in"]["ok"] is False
    assert by_item["City and area are set"]["ok"] is False
    assert by_item["Phone number is set"]["ok"] is False
    assert by_item["Website is set"]["ok"] is False
    assert by_item["Services are listed"]["ok"] is False
    assert by_item["Google review link is saved"]["ok"] is False
    assert by_item["Google Business Profile is connected (not mock)"]["ok"] is False
    assert result["score"] < 50
    # Every item explains why it matters and how to fix it - never left blank.
    assert all(c["why_it_matters"] and c["how_to_fix"] for c in result["checks"])


def test_complete_profile_passes_the_profile_checks(db_session):
    gym = _complete_business(db_session)
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}

    assert by_item["Business name is filled in"]["ok"] is True
    assert by_item["City and area are set"]["ok"] is True
    assert by_item["Phone number is set"]["ok"] is True
    assert by_item["Website is set"]["ok"] is True
    assert by_item["Business description names your services and area"]["ok"] is True
    assert by_item["Services are listed"]["ok"] is True
    assert by_item["Google review link is saved"]["ok"] is True


def test_short_description_does_not_pass(db_session):
    gym = db_session.get(Business, GYM)
    gym.description = "A gym."
    db_session.commit()
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item["Business description names your services and area"]["ok"] is False


def test_real_google_connection_passes_but_mock_does_not(db_session):
    gym = _blank_business(db_session)

    db_session.add(Connection(business_id=GYM, platform="google", external_id="mock-loc", mode="mock",
                              status="connected"))
    db_session.commit()
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item["Google Business Profile is connected (not mock)"]["ok"] is False

    conn = db_session.scalar(select(Connection).where(Connection.business_id == GYM, Connection.platform == "google"))
    conn.mode = "real"
    db_session.commit()
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item["Google Business Profile is connected (not mock)"]["ok"] is True


def test_recent_google_post_passes_old_one_does_not(db_session):
    gym = _blank_business(db_session)
    _google_post(db_session, GYM, published_at=NOW - timedelta(days=90))
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item[f"A Google post went up in the last {seo_checklist.RECENT_DAYS} days"]["ok"] is False

    _google_post(db_session, GYM, published_at=NOW - timedelta(days=2))
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item[f"A Google post went up in the last {seo_checklist.RECENT_DAYS} days"]["ok"] is True


def test_review_count_rating_and_reply_rate(db_session):
    gym = _blank_business(db_session)
    # Mid-range ratings, none replied to yet: leaves room for the rating/reply checks
    # to clearly fail later, whatever the exact thresholds are.
    for _ in range(seo_checklist.MIN_GOOGLE_REVIEWS - 1):
        _review(db_session, GYM, rating=3, reply_status="none")
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item[f"At least {seo_checklist.MIN_GOOGLE_REVIEWS} Google reviews"]["ok"] is False

    # One more review tips the count over the line; still a low average, still unreplied.
    _review(db_session, GYM, rating=1, reply_status="none")
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item[f"At least {seo_checklist.MIN_GOOGLE_REVIEWS} Google reviews"]["ok"] is True
    assert by_item["Average rating is 4.0 or higher"]["ok"] is False
    assert by_item[f"Replying to at least {int(seo_checklist.GOOD_REPLY_RATE * 100)}% of Google reviews"]["ok"] is False


def test_no_reviews_yet_fails_rating_and_reply_checks_without_crashing(db_session):
    gym = _blank_business(db_session)
    result = seo_checklist.build_checklist(db_session, gym)
    by_item = {c["item"]: c for c in result["checks"]}
    assert by_item["Average rating is 4.0 or higher"]["ok"] is False
    assert by_item[f"Replying to at least {int(seo_checklist.GOOD_REPLY_RATE * 100)}% of Google reviews"]["ok"] is False


def test_score_is_the_share_of_passing_checks(db_session):
    gym = _complete_business(db_session)
    result = seo_checklist.build_checklist(db_session, gym)
    passing = sum(1 for c in result["checks"] if c["ok"])
    assert result["score"] == round(100 * passing / len(result["checks"]))


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def test_get_seo_checklist_endpoint(raw_client, db_session):
    _complete_business(db_session)
    headers = login(raw_client)
    r = raw_client.get("/seo", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["business_id"] == GYM
    assert 0 <= body["score"] <= 100
    assert len(body["checks"]) >= 10
    assert all({"item", "ok", "why_it_matters", "how_to_fix"} <= c.keys() for c in body["checks"])


def test_seo_checklist_needs_login(raw_client):
    r = raw_client.get("/seo", params={"business_id": GYM})
    assert r.status_code == 401


def test_seo_checklist_blocks_other_businesses(raw_client, db_session):
    headers = login(raw_client)                               # gym owner
    r = raw_client.get("/seo", params={"business_id": 2}, headers=headers)   # the garage
    assert r.status_code == 404
