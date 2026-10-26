"""
Task 19 checks: login, accounts, and "each business sees only its own data".

These tests use `raw_client`, a fake browser with NO automatic login, so
they behave like a real visitor and have to log in themselves.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password, token_fingerprint, verify_password
from app.main import app
from app.models import AuthSession, Lead, User
from app.services import auth_service

PUBLIC = ("/health", "/auth/signup", "/auth/login", "/auth/forgot-password", "/auth/reset-password", "/platforms",
          "/billing/plans", "/webhooks", "/docs", "/openapi",
          "/redoc")


@pytest.fixture(autouse=True)
def forget_wrong_attempts():
    auth_service._failures.clear()
    yield
    auth_service._failures.clear()


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def lead_of(db, business_id):
    return db.scalar(select(Lead.id).where(Lead.business_id == business_id).limit(1))


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def test_passwords_are_scrambled_not_stored():
    stored = hash_password("demo1234")
    assert "demo1234" not in stored and stored.startswith("scrypt$")
    assert verify_password("demo1234", stored)
    assert not verify_password("demo1235", stored)
    assert hash_password("demo1234") != stored          # a new random salt every time


def test_tokens_are_stored_as_fingerprints(raw_client, db_session):
    r = raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"}).json()
    hashes = list(db_session.scalars(select(AuthSession.token_hash)))
    assert r["token"] not in hashes
    assert token_fingerprint(r["token"]) in hashes


# ---------------------------------------------------------------------------
# The locks
# ---------------------------------------------------------------------------
def test_every_private_address_needs_a_login(raw_client):
    """Walks the official list of addresses (the same one /docs shows) and
    knocks on every private door without a login."""
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        if path.startswith(PUBLIC):
            continue
        url = "/".join("1" if part.startswith("{") else part for part in path.split("/"))  # /leads/{lead_id} → /leads/1
        for method in methods:
            r = raw_client.request(method.upper(), url, params={"business_id": 1})
            assert r.status_code == 401, f"{method.upper()} {path} answered {r.status_code} without a login"
            checked += 1
    assert checked > 60


def test_public_addresses_stay_open(raw_client):
    assert raw_client.get("/health").status_code == 200
    assert raw_client.get("/platforms").status_code == 200
    form = {"name": "Ravi", "phone": "9811012345", "message": "Price for monthly membership?"}
    r = raw_client.post("/webhooks/website", params={"business_id": 1}, json=form)
    assert r.status_code == 200 and r.json()["new_leads"] == 1     # the doorbell still works


def test_bad_or_expired_tokens_are_refused(raw_client, db_session):
    assert raw_client.get("/auth/me", headers={"Authorization": "Bearer made-up"}).status_code == 401
    headers = login(raw_client)
    for session in db_session.scalars(select(AuthSession)):
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    r = raw_client.get("/auth/me", headers=headers)
    assert r.status_code == 401 and r.json()["detail"] == "Please log in"


# ---------------------------------------------------------------------------
# Log in / sign up / log out
# ---------------------------------------------------------------------------
def test_login_and_me(raw_client):
    r = raw_client.post("/auth/login", json={"email": "  GYM@demo.in ", "password": "demo1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "owner" and body["business"]["id"] == 1
    assert "password_hash" not in body["user"]
    me = raw_client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["user"]["email"] == "gym@demo.in" and me["business"]["name"] == body["business"]["name"]


def test_wrong_password_and_unknown_email_look_the_same(raw_client):
    a = raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "nope-nope"})
    b = raw_client.post("/auth/login", json={"email": "nobody@demo.in", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"] == "Wrong email or password"


def test_too_many_wrong_passwords_locks_for_a_while(raw_client):
    for _ in range(5):
        raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "guess-guess"})
    r = raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"})
    assert r.status_code == 429                       # even the right password waits now
    other = raw_client.post("/auth/login", json={"email": "garage@demo.in", "password": "demo1234"})
    assert other.status_code == 200                   # other people aren't affected


def test_signup_creates_business_and_owner(raw_client):
    data = {"name": "Priya", "email": "priya@glowsalon.in", "password": "salon-2026",
            "business_name": "Glow Salon", "industry": "Salon", "city": "Pune"}
    r = raw_client.post("/auth/signup", json=data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["business"]["name"] == "Glow Salon" and body["user"]["role"] == "owner"
    headers = {"Authorization": f"Bearer {body['token']}"}
    mine = raw_client.get("/businesses", headers=headers).json()
    assert [b["name"] for b in mine] == ["Glow Salon"]
    bid = body["business"]["id"]
    assert raw_client.get("/leads", params={"business_id": bid}, headers=headers).json()["total"] == 0
    again = raw_client.post("/auth/signup", json=data)
    assert again.status_code == 400 and "already" in again.json()["detail"]


def test_signup_rules(raw_client):
    bad = {"name": "Priya", "email": "not-an-email", "password": "short",
           "business_name": "Glow Salon", "industry": "salon"}
    r = raw_client.post("/auth/signup", json=bad)
    assert r.status_code == 422
    problems = {e["loc"][-1] for e in r.json()["detail"]}
    assert {"email", "password"} <= problems


def test_logout_ends_that_login_only(raw_client):
    phone = login(raw_client)
    laptop = login(raw_client)
    assert raw_client.post("/auth/logout", headers=phone).status_code == 204
    assert raw_client.get("/auth/me", headers=phone).status_code == 401
    assert raw_client.get("/auth/me", headers=laptop).status_code == 200


def test_change_password_logs_out_other_devices(raw_client):
    phone = login(raw_client)
    laptop = login(raw_client)
    wrong = raw_client.post("/auth/change-password", headers=phone,
                            json={"current_password": "wrong-one", "new_password": "newpass123"})
    assert wrong.status_code == 400
    r = raw_client.post("/auth/change-password", headers=phone,
                        json={"current_password": "demo1234", "new_password": "newpass123"})
    assert r.status_code == 204
    assert raw_client.get("/auth/me", headers=phone).status_code == 200      # this device stays in
    assert raw_client.get("/auth/me", headers=laptop).status_code == 401     # the other one is out
    assert raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"}).status_code == 401
    login(raw_client, password="newpass123")


# ---------------------------------------------------------------------------
# Each business sees only its own data
# ---------------------------------------------------------------------------
def test_owner_sees_only_their_business(raw_client, db_session):
    gym = login(raw_client)                                   # owner of business 1
    assert [b["id"] for b in raw_client.get("/businesses", headers=gym).json()] == [1]
    assert raw_client.get("/businesses/1", headers=gym).status_code == 200

    mine, theirs = lead_of(db_session, 1), lead_of(db_session, 2)
    assert raw_client.get(f"/leads/{mine}", headers=gym).status_code == 200
    peek = raw_client.get(f"/leads/{theirs}", headers=gym)
    assert peek.status_code == 404 and peek.json()["detail"] == f"Lead {theirs} not found"

    for url in ("/businesses/2", "/analytics/summary", "/posts", "/reviews", "/growth/reports",
                "/agent-runs", "/content/calendar", "/live/recent", "/social/accounts"):
        r = raw_client.get(url, params={"business_id": 2}, headers=gym)
        assert r.status_code == 404, f"{url} leaked business 2 ({r.status_code})"


def test_owner_cannot_touch_another_business_by_id(raw_client, db_session):
    gym = login(raw_client)
    theirs = lead_of(db_session, 2)
    assert raw_client.patch(f"/leads/{theirs}", json={"status": "lost"}, headers=gym).status_code == 404
    assert raw_client.post(f"/leads/{theirs}/messages", json={"text": "hi", "direction": "outbound"},
                           headers=gym).status_code == 404
    assert raw_client.patch("/businesses/2", json={"brand_voice": "hacked"}, headers=gym).status_code == 404
    post = raw_client.get("/posts", params={"business_id": 2}, headers=login(raw_client, "garage@demo.in"))
    post_id = post.json()["items"][0]["id"]
    assert raw_client.get(f"/posts/{post_id}", headers=gym).status_code == 404
    assert raw_client.post(f"/content/write/{post_id}", headers=gym).status_code == 404
    new = raw_client.post("/leads", json={"business_id": 2, "source": "whatsapp", "phone": "9811000000",
                                          "first_message": "hi"}, headers=gym)
    assert new.status_code == 404


def test_admin_sees_everything(raw_client):
    admin = login(raw_client, "admin@demo.in", "admin1234")
    assert len(raw_client.get("/businesses", headers=admin).json()) == 3
    assert raw_client.get("/analytics/summary", params={"business_id": 2}, headers=admin).status_code == 200
    assert raw_client.get("/scheduler/status", headers=admin).status_code == 200


def test_only_admin_runs_the_whole_platform(raw_client):
    gym = login(raw_client)
    assert raw_client.post("/scheduler/run", headers=gym).status_code == 403
    assert raw_client.get("/scheduler/status", headers=gym).status_code == 403
    r = raw_client.post("/businesses", json={"name": "Side Shop", "industry": "salon"}, headers=gym)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
def test_staff_can_work_but_not_change_settings(raw_client, db_session):
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.get("/leads", params={"business_id": 1}, headers=staff).status_code == 200
    lead = lead_of(db_session, 1)
    assert raw_client.patch(f"/leads/{lead}", json={"status": "contacted"}, headers=staff).status_code == 200
    r = raw_client.patch("/businesses/1", json={"brand_voice": "loud"}, headers=staff)
    assert r.status_code == 403 and "owner" in r.json()["detail"]
    invite = {"name": "Another", "email": "x@demo.in", "password": "password1"}
    assert raw_client.post("/team", json=invite, headers=staff).status_code == 403


def test_owner_adds_and_removes_staff(raw_client):
    owner = login(raw_client)
    invite = {"name": "Rohit", "email": "Rohit@IronPulse.in", "password": "frontdesk1"}
    r = raw_client.post("/team", json=invite, headers=owner)
    assert r.status_code == 201 and r.json()["role"] == "staff" and r.json()["business_id"] == 1
    rohit_id = r.json()["id"]
    team = raw_client.get("/team", headers=owner).json()
    assert {"gym@demo.in", "staff@demo.in", "rohit@ironpulse.in"} <= {u["email"] for u in team}

    rohit = login(raw_client, "rohit@ironpulse.in", "frontdesk1")
    assert raw_client.get("/leads", params={"business_id": 1}, headers=rohit).status_code == 200

    garage = login(raw_client, "garage@demo.in")
    assert raw_client.delete(f"/team/{rohit_id}", headers=garage).status_code == 404   # not their staff
    assert raw_client.delete(f"/team/{rohit_id}", headers=owner).status_code == 204
    assert raw_client.get("/auth/me", headers=rohit).status_code == 401                # logged out at once
    again = raw_client.post("/auth/login", json={"email": "rohit@ironpulse.in", "password": "frontdesk1"})
    assert again.status_code == 401


def test_owner_cannot_remove_themselves(raw_client, db_session):
    owner = login(raw_client)
    me = db_session.scalar(select(User).where(User.email == "gym@demo.in"))
    assert raw_client.delete(f"/team/{me.id}", headers=owner).status_code == 400


# ---------------------------------------------------------------------------
# Live feed: browsers can't add headers to EventSource, so ?token= works too
# ---------------------------------------------------------------------------
def test_live_feed_accepts_token_in_address(raw_client):
    r = raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    sent = raw_client.post("/live/test", params={"business_id": 1}, headers=headers)
    assert sent.status_code == 200
    with raw_client.stream("GET", "/live/stream",
                           params={"business_id": 1, "token": token, "limit": 1,
                                   "after_id": sent.json()["id"] - 1}) as feed:
        assert feed.status_code == 200
        text = "".join(feed.iter_text())
    assert "event: test" in text
    no = raw_client.get("/live/stream", params={"business_id": 2, "token": token, "limit": 1})
    assert no.status_code == 404
    assert raw_client.get("/live/stream", params={"business_id": 1, "limit": 1}).status_code == 401
