"""
Checks for social accounts, posts and the post → lead → money link (Task 12).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Lead, Post, SocialAccount


def future(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


@pytest.fixture
def insta(client):
    """The gym's Instagram account from the demo data."""
    accounts = client.get("/social/accounts", params={"business_id": 1}).json()
    return next(a for a in accounts if a["platform"] == "instagram")


# ----- Demo data ------------------------------------------------------------------------------
def test_demo_businesses_have_accounts_and_posts(db_session):
    for business_id in (1, 2, 3):
        platforms = {a.platform for a in db_session.query(SocialAccount).filter_by(business_id=business_id)}
        assert platforms == {"instagram", "facebook", "google"}
        assert db_session.query(Post).filter_by(business_id=business_id, status="published").count() > 30


def test_linked_leads_came_after_their_post(db_session):
    linked = db_session.query(Lead).filter(Lead.post_id.isnot(None)).all()
    assert linked
    for lead in linked:
        assert lead.post.platform == lead.source
        assert lead.post.published_at <= lead.created_at


# ----- Accounts -------------------------------------------------------------------------------
def test_add_account(client):
    r = client.post("/social/accounts", json={"business_id": 1, "platform": "YouTube",
                                              "handle": "@ironpulse", "followers": 300})
    assert r.status_code == 201
    assert r.json()["platform"] == "youtube" and r.json()["handle"] == "ironpulse"


def test_cannot_add_account_on_non_posting_platform(client):
    r = client.post("/social/accounts", json={"business_id": 1, "platform": "justdial", "handle": "x"})
    assert r.status_code == 422


def test_same_account_twice_is_refused(client, insta):
    r = client.post("/social/accounts", json={"business_id": 1, "platform": "instagram", "handle": insta["handle"]})
    assert r.status_code == 400


# ----- Creating and editing posts --------------------------------------------------------------
def test_create_draft(client, insta):
    r = client.post("/posts", json={
        "account_id": insta["id"], "kind": "reel", "pillar": "offer",
        "caption": "Diwali offer! 20% off Zumba", "hashtags": ["#Zumba", "zumba", " #DelhiFitness "],
    })
    assert r.status_code == 201
    post = r.json()
    assert post["status"] == "draft" and post["platform"] == "instagram" and post["business_id"] == 1
    assert post["hashtags"] == ["Zumba", "DelhiFitness"]          # cleaned, no duplicates
    assert post["campaign"] == f"post-{post['id']}"               # tracking tag created


def test_schedule_needs_a_future_time(client, insta):
    base = {"account_id": insta["id"], "caption": "hi", "status": "scheduled"}
    assert client.post("/posts", json=base).status_code == 422                                  # no time
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert client.post("/posts", json=base | {"scheduled_for": past}).status_code == 400        # in the past
    assert client.post("/posts", json=base | {"scheduled_for": future()}).status_code == 201


def test_instagram_rules(client, insta):
    too_long = client.post("/posts", json={"account_id": insta["id"], "caption": "x" * 2201})
    assert too_long.status_code == 400 and "2200" in too_long.json()["detail"]
    tags = [f"tag{i}" for i in range(31)]
    assert client.post("/posts", json={"account_id": insta["id"], "hashtags": tags}).status_code == 400


def test_edit_and_publish(client, insta):
    post = client.post("/posts", json={"account_id": insta["id"], "caption": "draft"}).json()
    r = client.patch(f"/posts/{post['id']}", json={"caption": "final caption", "status": "published"})
    assert r.status_code == 200
    assert r.json()["caption"] == "final caption" and r.json()["published_at"] is not None
    # once published, the content is locked
    assert client.patch(f"/posts/{post['id']}", json={"caption": "changed"}).status_code == 400


def test_stats_only_for_published_posts(client, insta):
    post = client.post("/posts", json={"account_id": insta["id"]}).json()
    assert client.post(f"/posts/{post['id']}/stats", json={"reach": 100}).status_code == 400
    client.patch(f"/posts/{post['id']}", json={"status": "published"})
    r = client.post(f"/posts/{post['id']}/stats", json={"reach": 1000, "likes": 50, "comments": 10,
                                                        "shares": 5, "saves": 15})
    assert r.json()["reach"] == 1000 and r.json()["engagement_rate"] == 8.0      # 80 / 1000


def test_delete_only_unpublished(client, db_session, insta):
    draft = client.post("/posts", json={"account_id": insta["id"]}).json()
    assert client.delete(f"/posts/{draft['id']}").status_code == 204
    published = db_session.query(Post).filter_by(business_id=1, status="published").first()
    assert client.delete(f"/posts/{published.id}").status_code == 400


# ----- Listing ------------------------------------------------------------------------------------
def test_list_and_filter_posts(client):
    page = client.get("/posts", params={"business_id": 1, "platform": "instagram", "status": "published"}).json()
    assert page["total"] > 20
    assert all(p["platform"] == "instagram" and p["status"] == "published" for p in page["items"])
    dates = [p["published_at"] for p in page["items"]]
    assert dates == sorted(dates, reverse=True)
    trends = client.get("/posts", params={"business_id": 1, "pillar": "trend"}).json()["items"]
    assert all(p["pillar"] == "trend" for p in trends)


# ----- Post → leads → money -----------------------------------------------------------------------
def test_post_shows_its_leads_and_money(client, db_session):
    post = db_session.query(Post).filter_by(business_id=1, status="published").first()
    won = db_session.query(Lead).filter_by(business_id=1, status="won").first()
    won.post_id = post.id                                    # "this customer came from that post"
    db_session.commit()
    result = client.get(f"/posts/{post.id}").json()
    assert result["enquiries"] >= 1 and result["sales"] >= 1 and result["revenue"] >= won.job_value


def test_website_lead_with_post_tag_is_linked(client, insta):
    post = client.post("/posts", json={"account_id": insta["id"], "caption": "Offer! Link in bio"}).json()
    form = {"name": "Kavya", "phone": "9811012345", "message": "Saw your offer", "utm_campaign": post["campaign"]}
    r = client.post("/webhooks/website", params={"business_id": 1}, json=form).json()
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["post_id"] == post["id"]
    assert client.get(f"/posts/{post['id']}").json()["enquiries"] == 1


def test_link_lead_to_post_by_hand(client, insta):
    post = client.post("/posts", json={"account_id": insta["id"]}).json()
    lead = client.post("/leads", json={"business_id": 1, "source": "walk_in", "name": "Saw it on Insta"}).json()
    r = client.patch(f"/leads/{lead['id']}", json={"post_id": post["id"]})
    assert r.status_code == 200 and r.json()["post_id"] == post["id"]


def test_cannot_link_to_another_business_post(client, db_session):
    other = db_session.query(Post).filter_by(business_id=2).first()
    lead = client.post("/leads", json={"business_id": 1, "source": "walk_in", "name": "X"}).json()
    assert client.patch(f"/leads/{lead['id']}", json={"post_id": other.id}).status_code == 400
