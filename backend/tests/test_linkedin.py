"""
Task 40 checks: LinkedIn Company Page connect + publishing.

Two kinds of test:
  - MOCK mode (no LinkedIn app keys): the whole Connect journey with a
    pretend company page, so the feature can be demoed for free.
  - REAL mode against a FAKE LinkedIn API: FakeLinkedIn answers exactly
    like LinkedIn does, and records every request we send, so we can
    check our server calls the right endpoints with the right data.
    No test ever touches the real internet.
"""

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.auth import vault
from app.config import settings
from app.integrations import base
from app.models import Connection, Post, SocialAccount
from app.services.scheduler_service import publish_due, refresh_stats

ORG_ID = "98765432"
MEMBER_ID = "AaBbCcDd"


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------------------
# Fake LinkedIn API
# ---------------------------------------------------------------------------
class FakeLinkedIn:
    def __init__(self):
        self.calls: list[dict] = []

    def called(self, method: str, piece: str) -> list[dict]:
        return [c for c in self.calls if c["method"] == method and piece in c["url"]]

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        body: dict = {}
        if request.content:
            try:
                body = json.loads(request.content.decode())
            except ValueError:                   # LinkedIn's token endpoint takes a form (a=1&b=2), not JSON
                body = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.calls.append({"method": request.method, "url": str(url),
                           "params": dict(url.params), "body": body,
                           "auth": request.headers.get("authorization", "")})

        # Token exchange
        if url.host == "www.linkedin.com":
            if url.path == "/oauth/v2/authorization":
                return httpx.Response(302, headers={"location": f"{API}/auth#code=li-code&state={url.params['state']}"})
            if url.path == "/oauth/v2/accessToken":
                return httpx.Response(200, json={"access_token": "LI_ACCESS_TOKEN", "expires_in": 5184000})

        if url.host == "api.linkedin.com":
            path = url.path

            # Basic profile (member id)
            if path == "/v2/me":
                return httpx.Response(200, json={"id": MEMBER_ID, "localizedFirstName": "Arjun",
                                                 "localizedLastName": "Singh"})

            # Company pages (admin roles)
            if path == "/v2/organizationAcls":
                return httpx.Response(200, json={"elements": [{
                    "organizationRole": "ADMINISTRATOR",
                    "organization~": {
                        "id": int(ORG_ID),
                        "localizedName": "Iron Pulse Fitness",
                        "followingInfo": {"followerCount": 412},
                    },
                }]})

            # UGC post publish
            if path == "/v2/ugcPosts":
                return httpx.Response(201, json={"id": f"urn:li:ugcPost:{ORG_ID}_001"})

            # Post metrics
            if "/v2/socialMetadata/" in path:
                return httpx.Response(200, json={
                    "totalSocialActivityCounts": {"numLikes": 88, "numImpressions": 650}
                })

        return httpx.Response(404, json={"message": f"fake: no route for {request.method} {url}"})


@pytest.fixture
def fake_li(monkeypatch):
    li = FakeLinkedIn()
    monkeypatch.setattr(base, "HTTP", httpx.Client(transport=httpx.MockTransport(li.handle)))
    return li


@pytest.fixture
def real_li(monkeypatch, fake_li):
    """LinkedIn app keys set → 'real' mode, all calls land on fake internet."""
    monkeypatch.setattr(settings, "linkedin_client_id", "li-client-id")
    monkeypatch.setattr(settings, "linkedin_client_secret", "li-client-secret")
    return fake_li


def connect_linkedin(client, headers, code="li-code"):
    """Click Connect → approve on LinkedIn → come back. Returns the redirect."""
    start = client.post("/connections/linkedin/start", headers=headers).json()
    state = parse_qs(urlparse(start["url"]).query)["state"][0]
    return client.get("/connections/linkedin/callback",
                      params={"code": code, "state": state},
                      follow_redirects=False)


# ---------------------------------------------------------------------------
# Setup info
# ---------------------------------------------------------------------------
def test_setup_info_includes_linkedin(raw_client):
    info = raw_client.get("/connections/setup", headers=login(raw_client)).json()
    assert "linkedin" in info["platforms"]
    assert info["platforms"]["linkedin"]["mode"] == "mock"    # no keys set in test env
    assert info["platforms"]["linkedin"]["label"] == "LinkedIn Company Page"


def test_setup_info_linkedin_real_when_keys_set(raw_client, real_li):
    info = raw_client.get("/connections/setup", headers=login(raw_client)).json()
    assert info["platforms"]["linkedin"]["mode"] == "real"
    assert "li-client-secret" not in json.dumps(info)         # secrets never leave the server


# ---------------------------------------------------------------------------
# Mock mode: full journey with a pretend company page
# ---------------------------------------------------------------------------
def test_mock_connect_linkedin_end_to_end(raw_client, db_session):
    gym = login(raw_client)
    start = raw_client.post("/connections/linkedin/start", headers=gym).json()
    assert start["mode"] == "mock"
    assert "/connections/linkedin/callback?code=mock" in start["url"]

    back = connect_linkedin(raw_client, gym, code="mock")
    assert back.status_code == 302
    location = back.headers["location"]
    assert "platform=linkedin" in location and "connected=" in location

    listed = raw_client.get("/connections", headers=gym).json()
    assert len(listed) == 1
    assert listed[0]["platform"] == "linkedin"
    assert listed[0]["mode"] == "mock"
    assert listed[0]["status"] == "connected"

    # Key never visible to the website
    assert "mock-key" not in json.dumps(listed)
    assert "locked" not in json.dumps(listed)


def test_mock_linkedin_post_published(raw_client, db_session):
    gym = login(raw_client)
    connect_linkedin(raw_client, gym, code="mock")

    account = db_session.scalar(select(SocialAccount).where(
        SocialAccount.business_id == 1, SocialAccount.platform == "linkedin"))
    assert account is not None

    post = Post(
        business_id=1, account_id=account.id, platform="linkedin",
        status="scheduled", kind="text",
        caption="Excited to announce our new corporate wellness programme! 💼",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(post)
    db_session.commit()

    publish_due(db_session)

    assert post.status == "published"
    assert post.external_id.startswith("mock_li_")


def test_mock_linkedin_no_media_still_publishes(raw_client, db_session):
    """LinkedIn text-only posts are fine (unlike Instagram which requires a photo)."""
    gym = login(raw_client)
    connect_linkedin(raw_client, gym, code="mock")
    account = db_session.scalar(select(SocialAccount).where(
        SocialAccount.business_id == 1, SocialAccount.platform == "linkedin"))
    post = Post(
        business_id=1, account_id=account.id, platform="linkedin",
        status="scheduled", kind="text", caption="New batch starting Monday",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(post)
    db_session.commit()
    publish_due(db_session)
    assert post.status == "published"


# ---------------------------------------------------------------------------
# Real mode (fake LinkedIn API)
# ---------------------------------------------------------------------------
def test_real_connect_redirects_to_linkedin(raw_client, real_li):
    gym = login(raw_client)
    url = raw_client.post("/connections/linkedin/start", headers=gym).json()["url"]
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert "r_organization_social" in url
    assert "w_organization_social" in url
    assert "client_id=li-client-id" in url


def test_real_connect_linkedin_saves_page(raw_client, db_session, real_li):
    gym = login(raw_client)
    back = connect_linkedin(raw_client, gym)
    assert back.status_code == 302
    location = back.headers["location"]
    assert "connected=Iron+Pulse+Fitness" in location

    # Token exchange happened
    exchange = real_li.called("POST", "accessToken")[0]
    assert exchange["body"]["code"] == "li-code"
    assert "li-client-secret" in exchange["body"]["client_secret"]

    # Connection saved
    conn = db_session.scalar(select(Connection).where(Connection.platform == "linkedin"))
    assert conn is not None
    assert conn.mode == "real"
    assert conn.external_id == ORG_ID
    assert conn.display_name == "Iron Pulse Fitness"
    assert vault.unlock(conn.access_token_locked) == "LI_ACCESS_TOKEN"

    # SocialAccount created
    account = db_session.get(SocialAccount, conn.social_account_id)
    assert account.platform == "linkedin"
    assert account.followers == 412
    assert account.connected is True

    # Keys never leave the API response
    listed = json.dumps(raw_client.get("/connections", headers=gym).json())
    assert "LI_ACCESS_TOKEN" not in listed


def test_real_linkedin_post_published(raw_client, db_session, real_li):
    gym = login(raw_client)
    connect_linkedin(raw_client, gym)

    account = db_session.scalar(select(SocialAccount).where(
        SocialAccount.business_id == 1, SocialAccount.platform == "linkedin"))
    post = Post(
        business_id=1, account_id=account.id, platform="linkedin",
        status="scheduled", kind="text",
        caption="Exciting news: Iron Pulse is now hiring personal trainers!",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(post)
    db_session.commit()

    publish_due(db_session)

    assert post.status == "published"
    assert post.external_id == f"urn:li:ugcPost:{ORG_ID}_001"

    # Check what was actually sent to LinkedIn
    ugc_call = real_li.called("POST", "ugcPosts")[0]
    assert ugc_call["auth"] == "Bearer LI_ACCESS_TOKEN"
    body = ugc_call["body"]
    assert body["author"] == f"urn:li:organization:{ORG_ID}"
    assert body["lifecycleState"] == "PUBLISHED"
    content = body["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert "Iron Pulse is now hiring" in content["shareCommentary"]["text"]
    assert body["visibility"] == {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}


def test_real_linkedin_post_with_image(raw_client, db_session, real_li):
    gym = login(raw_client)
    connect_linkedin(raw_client, gym)

    account = db_session.scalar(select(SocialAccount).where(
        SocialAccount.business_id == 1, SocialAccount.platform == "linkedin"))
    post = Post(
        business_id=1, account_id=account.id, platform="linkedin",
        status="scheduled", kind="photo",
        caption="Our new gym floor is ready! Come check it out.",
        media_url="https://cdn.example.com/gym_floor.jpg",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(post)
    db_session.commit()

    publish_due(db_session)

    assert post.status == "published"
    content = real_li.called("POST", "ugcPosts")[0]["body"]["specificContent"][
        "com.linkedin.ugc.ShareContent"]
    assert content["shareMediaCategory"] == "IMAGE"
    assert content["media"][0]["originalUrl"] == "https://cdn.example.com/gym_floor.jpg"


def test_real_linkedin_stats_refreshed(raw_client, db_session, real_li):
    gym = login(raw_client)
    connect_linkedin(raw_client, gym)

    account = db_session.scalar(select(SocialAccount).where(
        SocialAccount.business_id == 1, SocialAccount.platform == "linkedin"))
    # Simulate an already-published post
    post = Post(
        business_id=1, account_id=account.id, platform="linkedin",
        status="published", kind="text",
        caption="Growth partner tip of the week",
        external_id=f"urn:li:ugcPost:{ORG_ID}_001",
        published_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(post)
    db_session.commit()

    refresh_stats(db_session, business_id=1, force=True)

    assert post.likes == 88
    assert post.reach == 650


def test_no_company_page_gives_friendly_error(raw_client, real_li, monkeypatch):
    """If the member has no company pages, they get a clear error."""
    import app.integrations.linkedin as li_mod
    monkeypatch.setattr(li_mod, "company_pages", lambda token, member_urn: [])
    gym = login(raw_client)
    back = connect_linkedin(raw_client, gym)
    assert back.status_code == 302
    assert "No+LinkedIn+Company+Page" in back.headers["location"] or \
           "error=" in back.headers["location"]


def test_one_linkedin_account_cannot_belong_to_two_businesses(raw_client, real_li):
    connect_linkedin(raw_client, login(raw_client))
    back = connect_linkedin(raw_client, login(raw_client, "garage@demo.in"))
    assert "already+connected+to+another+business" in back.headers["location"]


def test_disconnect_linkedin(raw_client, db_session):
    gym = login(raw_client)
    connect_linkedin(raw_client, gym, code="mock")
    conn = raw_client.get("/connections", headers=gym).json()[0]
    assert raw_client.delete(f"/connections/{conn['id']}", headers=gym).status_code == 204
    assert raw_client.get("/connections", headers=gym).json() == []
    row = db_session.get(Connection, conn["id"])
    assert row.access_token_locked is None
    assert not db_session.get(SocialAccount, conn["social_account_id"]).connected
