"""
Task 21 checks: connecting real WhatsApp / Instagram / Facebook / Google.

Two kinds of test:
  - MOCK mode (no app keys): the whole Connect journey with pretend accounts
  - REAL mode against a FAKE internet: FakePlatforms answers exactly like
    Meta / Instagram / Google do, and records every request we send, so we
    can check our server calls the right addresses with the right data.
    No test ever touches the real internet.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.auth import vault
from app.config import settings
from app.integrations import base, instagram
from app.models import Connection, Lead, Message, Post, Review, ReviewRequest, SocialAccount, Subscription
from app.services import connection_service, outbox
from app.services.reputation_service import send_due_requests
from app.services.scheduler_service import publish_due, refresh_stats

IG_ID = "17841400000000001"
DAYTIME = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)          # 11:30am India time


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def meta_sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# The fake internet
# ---------------------------------------------------------------------------
class FakePlatforms:
    def __init__(self):
        self.calls: list[dict] = []
        self.expired_whatsapp = False
        self.container_checks = 0

    def called(self, method: str, piece: str) -> list[dict]:
        return [c for c in self.calls if c["method"] == method and piece in c["url"]]

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        params = dict(url.params)
        body: dict = {}
        if request.content:
            text = request.content.decode()
            try:
                body = json.loads(text)
            except ValueError:
                body = {k: v[0] for k, v in parse_qs(text).items()}
        self.calls.append({"method": request.method, "url": str(url), "params": params, "body": body,
                           "auth": request.headers.get("authorization", "")})
        key = (request.method, url.host, url.path)
        ok = {"success": True}

        if url.host == "graph.facebook.com":
            path = url.path.removeprefix("/v26.0/")
            if path == "oauth/access_token":
                if "fb_exchange_token" in params:
                    return httpx.Response(200, json={"access_token": "LONG_USER"})
                return httpx.Response(200, json={"access_token": "WA_BUSINESS_TOKEN" if params.get("code") == "wa-code"
                                                 else "SHORT_USER"})
            if path == "me/accounts":
                return httpx.Response(200, json={"data": [{"id": "PAGE1", "name": "Iron Pulse Fitness",
                                                           "username": "ironpulse", "access_token": "PAGE_TOKEN",
                                                           "followers_count": 900}]})
            if path in ("PAGE1/subscribed_apps", "WABA1/subscribed_apps", "PHONE1/register"):
                return httpx.Response(200, json=ok)
            if path == "PHONE1":
                return httpx.Response(200, json={"display_phone_number": "+91 98110 11111", "verified_name": "Iron Pulse"})
            if path == "WABA1/message_templates":
                return httpx.Response(200, json={"id": "tmpl1", "status": "PENDING"})
            if path == "PHONE1/messages":
                if self.expired_whatsapp:
                    return httpx.Response(401, json={"error": {"message": "Error validating access token", "code": 190}})
                return httpx.Response(200, json={"messages": [{"id": "wamid.SENT1"}]})
            if path == "PAGE1/messages":
                return httpx.Response(200, json={"message_id": "m_1"})
            if path == "PAGE1/feed":
                return httpx.Response(200, json={"id": "PAGE1_POST1"})
            if path == "PAGE1/photos":
                return httpx.Response(200, json={"id": "photo1", "post_id": "PAGE1_POST2"})

        if key == ("POST", "api.instagram.com", "/oauth/access_token"):
            return httpx.Response(200, json={"data": [{"access_token": "IG_SHORT", "user_id": "999",
                                                       "permissions": "instagram_business_basic"}]})
        if url.host == "graph.instagram.com":
            path = url.path.removeprefix("/v26.0/")
            if url.path == "/access_token":
                return httpx.Response(200, json={"access_token": "IG_LONG", "expires_in": 5183944})
            if url.path == "/refresh_access_token":
                return httpx.Response(200, json={"access_token": "IG_LONG_2", "expires_in": 5183944})
            if path == "me":
                return httpx.Response(200, json={"user_id": IG_ID, "id": "999", "username": "ironpulsefitness",
                                                 "followers_count": 2400})
            if path == "me/subscribed_apps":
                return httpx.Response(200, json=ok)
            if path == f"{IG_ID}/messages":
                return httpx.Response(200, json={"recipient_id": body.get("recipient", {}).get("id"), "message_id": "aWdf"})
            if path == f"{IG_ID}/media":
                return httpx.Response(200, json={"id": "CONTAINER1"})
            if path == "CONTAINER1":
                self.container_checks += 1
                return httpx.Response(200, json={"status_code": "IN_PROGRESS" if self.container_checks == 1 else "FINISHED"})
            if path == f"{IG_ID}/media_publish":
                return httpx.Response(200, json={"id": "MEDIA1"})
            if path == "MEDIA1/insights":
                return httpx.Response(200, json={"data": [{"name": "reach", "values": [{"value": 1500}]},
                                                          {"name": "likes", "values": [{"value": 120}]},
                                                          {"name": "saved", "values": [{"value": 30}]}]})

        if key == ("POST", "oauth2.googleapis.com", "/token"):
            if body.get("grant_type") == "refresh_token":
                return httpx.Response(200, json={"access_token": "G_ACCESS_2", "expires_in": 3599})
            return httpx.Response(200, json={"access_token": "G_ACCESS", "refresh_token": "G_REFRESH", "expires_in": 3599})
        if key == ("GET", "mybusinessaccountmanagement.googleapis.com", "/v1/accounts"):
            return httpx.Response(200, json={"accounts": [{"name": "accounts/111"}]})
        if key == ("GET", "mybusinessbusinessinformation.googleapis.com", "/v1/accounts/111/locations"):
            return httpx.Response(200, json={"locations": [{"name": "locations/222", "title": "Iron Pulse Fitness"}]})
        if key == ("GET", "mybusiness.googleapis.com", "/v4/accounts/111/locations/222/reviews"):
            loc = "accounts/111/locations/222/reviews"
            return httpx.Response(200, json={"reviews": [
                {"name": f"{loc}/r1", "reviewer": {"displayName": "Neha S"}, "starRating": "FIVE",
                 "comment": "Great trainers, very clean gym!", "createTime": "2026-10-17T10:00:00Z"},
                {"name": f"{loc}/r2", "reviewer": {"displayName": "Rahul"}, "starRating": "TWO",
                 "comment": "Waited 20 minutes for a trainer, AC not working.", "createTime": "2026-10-16T09:00:00Z"},
                {"name": f"{loc}/r3", "reviewer": {"displayName": "Simran"}, "starRating": "FOUR",
                 "comment": "Good place", "createTime": "2026-10-15T09:00:00Z", "reviewReply": {"comment": "Thank you!"}},
            ]})
        if request.method == "PUT" and url.path.endswith("/reply"):
            return httpx.Response(200, json={"comment": body.get("comment")})
        if key == ("POST", "mybusiness.googleapis.com", "/v4/accounts/111/locations/222/localPosts"):
            return httpx.Response(200, json={"name": "accounts/111/locations/222/localPosts/lp1"})
        return httpx.Response(404, json={"error": {"message": f"fake: no route for {request.method} {url}"}})


@pytest.fixture
def fake(monkeypatch):
    platforms = FakePlatforms()
    monkeypatch.setattr(base, "HTTP", httpx.Client(transport=httpx.MockTransport(platforms.handle)))
    monkeypatch.setattr(instagram, "SLEEP", lambda seconds: None)
    return platforms


@pytest.fixture
def real(monkeypatch, fake):
    """App keys set → 'real' mode, but every call lands on the fake internet."""
    for name, value in {"meta_app_id": "111", "meta_app_secret": "meta-secret", "meta_whatsapp_config_id": "cfg-1",
                        "instagram_app_id": "222", "instagram_app_secret": "ig-secret",
                        "google_client_id": "g-id", "google_client_secret": "g-secret"}.items():
        monkeypatch.setattr(settings, name, value)
    return fake


def connect(client, headers, platform, code="the-code"):
    """Click Connect, approve on the platform, come back. Returns the redirect to the website."""
    start = client.post(f"/connections/{platform}/start", headers=headers).json()
    state = parse_qs(urlparse(start["url"]).query)["state"][0]
    return client.get(f"/connections/{platform}/callback", params={"code": code, "state": state},
                      follow_redirects=False)


def connect_whatsapp(client, headers):
    r = client.post("/connections/whatsapp", headers=headers,
                    json={"code": "wa-code", "waba_id": "WABA1", "phone_number_id": "PHONE1"})
    assert r.status_code == 201, r.text
    return r.json()


def whatsapp_delivery(phone_number_id="PHONE1", sender="919811012345", text="Hi, monthly fees kitni hai?",
                      message_id="wamid.IN1"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": phone_number_id},
        "contacts": [{"wa_id": sender, "profile": {"name": "Ravi Kumar"}}],
        "messages": [{"from": sender, "id": message_id, "timestamp": str(int(datetime.now().timestamp())),
                      "type": "text", "text": {"body": text}}]}}]}]}


def ring_meta(client, payload, secret="meta-secret"):
    raw = json.dumps(payload).encode()
    return client.post("/webhooks/meta", content=raw, headers={"Content-Type": "application/json",
                                                               "X-Hub-Signature-256": meta_sign(raw, secret)})


# ---------------------------------------------------------------------------
# Mock mode: the whole journey with pretend accounts
# ---------------------------------------------------------------------------
def test_mock_connect_instagram_end_to_end(raw_client, db_session):
    gym = login(raw_client)
    start = raw_client.post("/connections/instagram/start", headers=gym).json()
    assert start["mode"] == "mock" and "/connections/instagram/callback?code=mock" in start["url"]
    back = connect(raw_client, gym, "instagram", code="mock")
    assert back.status_code == 302
    assert back.headers["location"].startswith("http://localhost:5173/settings/connections?platform=instagram&connected=")

    listed = raw_client.get("/connections", headers=gym).json()
    assert len(listed) == 1 and listed[0]["mode"] == "mock" and listed[0]["status"] == "connected"
    account = db_session.get(SocialAccount, listed[0]["social_account_id"])
    assert account.platform == "instagram" and account.connected       # the gym's existing profile
    assert "mock-key" not in json.dumps(listed) and "locked" not in json.dumps(listed)   # keys never leave the server


def test_mock_whatsapp_then_messages_and_replies(raw_client, db_session):
    gym = login(raw_client)
    wa = raw_client.post("/connections/whatsapp", headers=gym, json={"code": "mock"}).json()
    assert wa["mode"] == "mock" and wa["external_id"] == "mock_whatsapp_1"

    r = raw_client.post("/webhooks/meta", json=whatsapp_delivery("mock_whatsapp_1")).json()   # no app secret: unsigned OK
    assert r["new_leads"] == 1
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.business_id == 1 and lead.phone == "+919811012345"

    before = len(outbox.MOCK_SENT)
    sent = raw_client.post(f"/leads/{lead.id}/messages", headers=gym,
                           json={"direction": "outbound", "text": "Hi Ravi! ₹1,999/month. Free trial tomorrow?"}).json()
    assert sent["delivery"] == "sent" and sent["delivery_error"] == ""
    assert outbox.MOCK_SENT[before:] == [{"platform": "whatsapp", "to": "+919811012345", "business_id": 1,
                                          "text": "Hi Ravi! ₹1,999/month. Free trial tomorrow?"}]
    assert raw_client.get(f"/leads/{lead.id}", headers=gym).json()["status"] == "contacted"


def test_reply_without_a_connection_is_only_noted(raw_client):
    gym = login(raw_client)
    form = {"name": "Kunal", "phone": "9811077777", "message": "Batch timings?"}
    lead_id = raw_client.post("/webhooks/website", params={"business_id": 1}, json=form).json()["lead_ids"][0]
    r = raw_client.post(f"/leads/{lead_id}/messages", headers=gym,
                        json={"direction": "outbound", "text": "Called him back"}).json()
    assert r["delivery"] == "logged"
    note = raw_client.post(f"/leads/{lead_id}/messages", headers=gym,
                           json={"direction": "outbound", "text": "Sent from my phone", "send": False}).json()
    assert note["delivery"] == "logged"


def test_broken_or_expired_connect_links(raw_client):
    gym = login(raw_client)
    bad = raw_client.get("/connections/instagram/callback", params={"code": "mock", "state": "made.up"},
                         follow_redirects=False)
    assert "error=" in bad.headers["location"]
    start = raw_client.post("/connections/google/start", headers=gym).json()
    state = parse_qs(urlparse(start["url"]).query)["state"][0]
    wrong = raw_client.get("/connections/instagram/callback", params={"code": "mock", "state": state},
                           follow_redirects=False)
    assert "different+platform" in wrong.headers["location"]
    cancelled = raw_client.get("/connections/google/callback", params={"error": "access_denied", "state": state},
                               follow_redirects=False)
    assert "cancelled" in cancelled.headers["location"]


def test_disconnect_and_staff_rules(raw_client, db_session):
    gym = login(raw_client)
    connect(raw_client, gym, "facebook", code="mock")
    conn = raw_client.get("/connections", headers=gym).json()[0]
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.post("/connections/google/start", headers=staff).status_code == 403
    assert raw_client.delete(f"/connections/{conn['id']}", headers=staff).status_code == 403
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.delete(f"/connections/{conn['id']}", headers=garage).status_code == 404   # not theirs

    assert raw_client.delete(f"/connections/{conn['id']}", headers=gym).status_code == 204
    assert raw_client.get("/connections", headers=gym).json() == []
    row = db_session.get(Connection, conn["id"])
    assert row.access_token_locked is None and not db_session.get(SocialAccount, conn["social_account_id"]).connected


def test_plan_limit_on_new_social_accounts(raw_client, db_session):
    r = raw_client.post("/auth/signup", json={"name": "Priya", "email": "priya@glow.in", "password": "salon-2026",
                                              "business_name": "Glow Salon", "industry": "salon"}).json()
    headers = {"Authorization": f"Bearer {r['token']}"}
    sub = db_session.scalar(select(Subscription).where(Subscription.business_id == r["business"]["id"]))
    sub.plan = "starter"                                                     # 2 social accounts
    db_session.commit()
    assert "connected=" in connect(raw_client, headers, "instagram", "mock").headers["location"]
    assert "connected=" in connect(raw_client, headers, "facebook", "mock").headers["location"]
    third = connect(raw_client, headers, "google", "mock").headers["location"]
    assert "error=" in third and "Starter" in third


def test_setup_info_has_no_secrets(raw_client, real):
    info = raw_client.get("/connections/setup", headers=login(raw_client)).json()
    assert info["platforms"]["whatsapp"]["mode"] == "real" and info["whatsapp_signup"]["config_id"] == "cfg-1"
    assert "meta-secret" not in json.dumps(info) and "ig-secret" not in json.dumps(info)


# ---------------------------------------------------------------------------
# Real mode (fake internet): connecting
# ---------------------------------------------------------------------------
def test_facebook_page_connect(raw_client, db_session, real):
    gym = login(raw_client)
    url = raw_client.post("/connections/facebook/start", headers=gym).json()["url"]
    assert url.startswith("https://www.facebook.com/v26.0/dialog/oauth?") and "client_id=111" in url
    assert "pages_messaging" in url
    back = connect(raw_client, gym, "facebook")
    assert "connected=Iron+Pulse+Fitness" in back.headers["location"]

    exchange = real.called("GET", "oauth/access_token")[0]["params"]
    assert exchange["code"] == "the-code" and exchange["redirect_uri"] == "http://127.0.0.1:8000/connections/facebook/callback"
    assert real.called("POST", "PAGE1/subscribed_apps")[0]["auth"] == "Bearer PAGE_TOKEN"
    conn = db_session.scalar(select(Connection).where(Connection.platform == "facebook"))
    assert conn.mode == "real" and conn.external_id == "PAGE1"
    listed = json.dumps(raw_client.get("/connections", headers=gym).json())
    assert "PAGE_TOKEN" not in listed and conn.access_token_locked not in listed
    assert conn.access_token_locked != "PAGE_TOKEN" and vault.unlock(conn.access_token_locked) == "PAGE_TOKEN"


def test_instagram_connect(raw_client, db_session, real):
    gym = login(raw_client)
    url = raw_client.post("/connections/instagram/start", headers=gym).json()["url"]
    assert url.startswith("https://www.instagram.com/oauth/authorize?") and "instagram_business_content_publish" in url
    connect(raw_client, gym, "instagram")
    conn = db_session.scalar(select(Connection).where(Connection.platform == "instagram"))
    assert conn.external_id == IG_ID and conn.display_name == "@ironpulsefitness"
    assert vault.unlock(conn.access_token_locked) == "IG_LONG"                       # the 60-day key
    assert 59 <= (connection_service._utc(conn.token_expires_at) - datetime.now(timezone.utc)).days <= 60
    account = db_session.get(SocialAccount, conn.social_account_id)
    assert account.handle == "ironpulsefitness" and account.followers == 2400 and account.connected


def test_instagram_strips_the_extra_hash(real):
    instagram.exchange_code("abc123#_", "http://x/cb")
    assert real.called("POST", "api.instagram.com")[0]["body"]["code"] == "abc123"


def test_one_account_cannot_belong_to_two_businesses(raw_client, real):
    connect(raw_client, login(raw_client), "instagram")
    back = connect(raw_client, login(raw_client, "garage@demo.in"), "instagram")        # same Instagram
    assert "already+connected+to+another+business" in back.headers["location"]


def test_whatsapp_connect(raw_client, real):
    wa = connect_whatsapp(raw_client, login(raw_client))
    assert wa["display_name"] == "+91 98110 11111" and wa["mode"] == "real"
    assert wa["details"]["waba_id"] == "WABA1" and wa["details"]["review_template"] == "submitted"
    assert "pin_locked" not in wa["details"]
    register = real.called("POST", "PHONE1/register")[0]
    assert register["auth"] == "Bearer WA_BUSINESS_TOKEN" and len(register["body"]["pin"]) == 6
    assert real.called("POST", "WABA1/subscribed_apps")
    template = real.called("POST", "WABA1/message_templates")[0]["body"]
    assert template["name"] == "review_request" and "{{3}}" in template["components"][0]["text"]


# ---------------------------------------------------------------------------
# Real mode: messages in, replies out
# ---------------------------------------------------------------------------
def test_meta_doorbell_checks_signature_and_finds_the_business(raw_client, db_session, real):
    connect_whatsapp(raw_client, login(raw_client))
    raw = json.dumps(whatsapp_delivery()).encode()
    assert raw_client.post("/webhooks/meta", content=raw).status_code == 401                    # unsigned
    assert ring_meta(raw_client, whatsapp_delivery(), secret="wrong").status_code == 401
    r = ring_meta(raw_client, whatsapp_delivery()).json()
    assert r["new_leads"] == 1 and db_session.get(Lead, r["lead_ids"][0]).business_id == 1
    stranger = ring_meta(raw_client, whatsapp_delivery("PHONE_UNKNOWN", message_id="wamid.X")).json()
    assert stranger["new_leads"] == 0 and "isn't connected" in stranger["notes"][0]


def test_whatsapp_reply_is_sent_for_real(raw_client, db_session, real):
    gym = login(raw_client)
    connect_whatsapp(raw_client, gym)
    lead_id = ring_meta(raw_client, whatsapp_delivery()).json()["lead_ids"][0]
    r = raw_client.post(f"/leads/{lead_id}/messages", headers=gym,
                        json={"direction": "outbound", "text": "Hi Ravi, ₹1,999/month 💪"}).json()
    assert r["delivery"] == "sent"
    call = real.called("POST", "PHONE1/messages")[-1]
    assert call["body"]["to"] == "919811012345" and call["body"]["text"]["body"] == "Hi Ravi, ₹1,999/month 💪"
    assert call["auth"] == "Bearer WA_BUSINESS_TOKEN"
    assert db_session.scalar(select(Message).where(Message.external_id == "wamid.SENT1")) is not None


def test_24_hour_rule(raw_client, db_session, real):
    gym = login(raw_client)
    connect_whatsapp(raw_client, gym)
    lead_id = ring_meta(raw_client, whatsapp_delivery()).json()["lead_ids"][0]
    lead = db_session.get(Lead, lead_id)
    for m in lead.messages:
        m.sent_at = datetime.now(timezone.utc) - timedelta(hours=30)
    db_session.commit()
    sends_before = len(real.called("POST", "PHONE1/messages"))
    r = raw_client.post(f"/leads/{lead_id}/messages", headers=gym, json={"direction": "outbound", "text": "Hello?"}).json()
    assert r["delivery"] == "failed" and "24 hours" in r["delivery_error"]
    assert len(real.called("POST", "PHONE1/messages")) == sends_before                      # nothing sent
    assert raw_client.get(f"/leads/{lead_id}", headers=gym).json()["status"] == "new"       # still waiting


def test_expired_key_asks_the_owner_to_reconnect(raw_client, db_session, real):
    gym = login(raw_client)
    connect_whatsapp(raw_client, gym)
    lead_id = ring_meta(raw_client, whatsapp_delivery()).json()["lead_ids"][0]
    real.expired_whatsapp = True
    r = raw_client.post(f"/leads/{lead_id}/messages", headers=gym, json={"direction": "outbound", "text": "Hi"}).json()
    assert r["delivery"] == "failed" and "access token" in r["delivery_error"]
    conn = raw_client.get("/connections", headers=gym).json()[0]
    assert conn["status"] == "needs_reconnect" and conn["problem"]
    events = raw_client.get("/live/recent", params={"business_id": 1}, headers=gym).json()
    assert any(e["type"] == "connection.problem" for e in events)


def test_instagram_dm_in_and_reply_out(raw_client, db_session, real):
    gym = login(raw_client)
    connect(raw_client, gym, "instagram")
    dm = {"object": "instagram", "entry": [{"id": IG_ID, "time": 1, "messaging": [{
        "sender": {"id": "IGSID_55"}, "recipient": {"id": IG_ID}, "timestamp": int(datetime.now().timestamp() * 1000),
        "message": {"mid": "aWdM1", "text": "Personal training price?"}}]}]}
    r = ring_meta(raw_client, dm, secret="ig-secret").json()                 # Instagram signs with its own secret
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.source == "instagram" and lead.handle == "IGSID_55" and lead.business_id == 1
    sent = raw_client.post(f"/leads/{lead.id}/messages", headers=gym,
                           json={"direction": "outbound", "text": "₹6,000 for 12 sessions!"}).json()
    assert sent["delivery"] == "sent"
    assert real.called("POST", f"{IG_ID}/messages")[-1]["body"] == {"recipient": {"id": "IGSID_55"},
                                                                   "message": {"text": "₹6,000 for 12 sessions!"}}


def test_facebook_messenger_routed_by_page(raw_client, db_session, real):
    gym = login(raw_client)
    connect(raw_client, gym, "facebook")
    msg = {"object": "page", "entry": [{"id": "PAGE1", "time": 1, "messaging": [{
        "sender": {"id": "PSID_9"}, "recipient": {"id": "PAGE1"}, "timestamp": int(datetime.now().timestamp() * 1000),
        "message": {"mid": "m_in1", "text": "Open on Sunday?"}}]}]}
    lead = db_session.get(Lead, ring_meta(raw_client, msg).json()["lead_ids"][0])
    assert lead.source == "facebook" and lead.handle == "PSID_9"
    raw_client.post(f"/leads/{lead.id}/messages", headers=gym, json={"direction": "outbound", "text": "Yes, 7-1!"})
    assert real.called("POST", "PAGE1/messages")[-1]["body"]["recipient"] == {"id": "PSID_9"}


def test_review_request_uses_the_whatsapp_template(raw_client, db_session, real):
    connect_whatsapp(raw_client, login(raw_client))
    lead = db_session.scalar(select(Lead).where(Lead.business_id == 1, Lead.phone.is_not(None)))
    lead.name = "Neha Sharma"
    business = lead.business
    business.google_review_link = "https://g.page/r/ironpulse/review"
    db_session.add(ReviewRequest(business_id=1, lead_id=lead.id, phone=lead.phone, message="Please review us",
                                 send_after=DAYTIME - timedelta(hours=1)))
    db_session.commit()
    assert send_due_requests(db_session, now=DAYTIME) >= 1
    body = real.called("POST", "PHONE1/messages")[-1]["body"]
    assert body["type"] == "template" and body["template"]["name"] == "review_request"
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == [
        "Neha", business.name, "https://g.page/r/ironpulse/review"]


# ---------------------------------------------------------------------------
# Real mode: publishing and numbers
# ---------------------------------------------------------------------------
def _due_post(db, platform, **fields) -> Post:
    account = db.scalar(select(SocialAccount).where(SocialAccount.business_id == 1, SocialAccount.platform == platform,
                                                    SocialAccount.connected))
    post = Post(business_id=1, account_id=account.id, platform=platform, status="scheduled",
                scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1), **fields)
    db.add(post)
    db.commit()
    return post


def test_instagram_post_is_published_for_real(raw_client, db_session, real):
    connect(raw_client, login(raw_client), "instagram")
    post = _due_post(db_session, "instagram", kind="photo", caption="Diwali offer: 20% off 🪔",
                     hashtags=["gym", "delhi"], media_url="https://cdn.example.com/diwali.jpg")
    no_photo = _due_post(db_session, "instagram", kind="photo", caption="Text only")
    publish_due(db_session)
    assert post.status == "published" and post.external_id == "MEDIA1"
    container = real.called("POST", f"{IG_ID}/media")[0]["body"]
    assert container["image_url"] == "https://cdn.example.com/diwali.jpg" and "#gym #delhi" in container["caption"]
    assert real.container_checks == 2                                    # waited for "FINISHED"
    assert no_photo.status == "failed" and "photo or video" in no_photo.publish_error

    refresh_stats(db_session, business_id=1, force=True)
    assert post.reach == 1500 and post.likes == 120 and post.saves == 30


def test_facebook_and_google_posts(raw_client, db_session, real):
    gym = login(raw_client)
    connect(raw_client, gym, "facebook")
    connect(raw_client, gym, "google")
    fb = _due_post(db_session, "facebook", kind="text", caption="New Zumba batch at 7am!")
    g = _due_post(db_session, "google", kind="photo", caption="Free trial this week", media_url="https://cdn.example.com/a.jpg")
    publish_due(db_session)
    assert fb.status == "published" and fb.external_id == "PAGE1_POST1"
    assert g.status == "published" and g.external_id.endswith("localPosts/lp1")
    local = real.called("POST", "localPosts")[0]["body"]
    assert local["summary"] == "Free trial this week" and local["media"][0]["sourceUrl"] == "https://cdn.example.com/a.jpg"


# ---------------------------------------------------------------------------
# Real mode: Google reviews in, replies out, keys kept fresh
# ---------------------------------------------------------------------------
def test_google_reviews_sync_and_reply(raw_client, db_session, real):
    gym = login(raw_client)
    back = connect(raw_client, gym, "google")
    assert "connected=Iron+Pulse+Fitness" in back.headers["location"]
    conn = raw_client.get("/connections", headers=gym).json()[0]
    assert conn["external_id"] == "accounts/111/locations/222"
    row = db_session.get(Connection, conn["id"])
    assert vault.unlock(row.refresh_token_locked) == "G_REFRESH"

    assert raw_client.post(f"/connections/{conn['id']}/sync", headers=gym).json()["new_reviews"] == 3
    again = raw_client.post(f"/connections/{conn['id']}/sync", headers=gym).json()
    assert again["new_reviews"] == 0                                       # no doubles
    reviews = {r.author_name: r for r in db_session.scalars(select(Review).where(Review.platform == "google",
                                                                               Review.external_id.like("accounts/%")))}
    assert reviews["Neha S"].rating == 5 and reviews["Rahul"].rating == 2
    assert reviews["Rahul"].needs_attention and reviews["Rahul"].reply_status == "drafted"
    assert reviews["Simran"].reply_status == "posted" and reviews["Simran"].reply_text == "Thank you!"

    r = raw_client.post(f"/reviews/{reviews['Rahul'].id}/reply", headers=gym,
                        json={"text": "Sorry Rahul, the AC is fixed. Please ask for Amit next time."})
    assert r.status_code == 200 and r.json()["reply_status"] == "posted"
    put = real.called("PUT", "/reviews/r2/reply")[0]
    assert put["body"] == {"comment": "Sorry Rahul, the AC is fixed. Please ask for Amit next time."}


def test_google_key_is_refreshed_when_old(raw_client, db_session, real):
    connect(raw_client, login(raw_client), "google")
    conn = db_session.scalar(select(Connection).where(Connection.platform == "google"))
    conn.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    connection_service.sync_google_reviews(db_session, conn)
    assert real.called("POST", "oauth2.googleapis.com")[-1]["body"]["grant_type"] == "refresh_token"
    assert real.called("GET", "/reviews")[-1]["auth"] == "Bearer G_ACCESS_2"


def test_instagram_key_renewed_before_it_runs_out(raw_client, db_session, real):
    connect(raw_client, login(raw_client), "instagram")
    conn = db_session.scalar(select(Connection).where(Connection.platform == "instagram"))
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(days=5)
    db_session.commit()
    assert connection_service.refresh_expiring(db_session) == 1
    assert vault.unlock(conn.access_token_locked) == "IG_LONG_2"
