"""
Launch (light) mode: the live site shows and runs only what needs no platform approval.
Features switch themselves on when their real keys are added.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import features
from app.config import settings
from app.models import Payment, Post
from app.services import scheduler_service
from app.services.publishers import ManualPublisher, PublishError, get_publisher
from tests.test_billing import login


@pytest.fixture
def light(monkeypatch):
    monkeypatch.setattr(settings, "launch_mode", "light")
    for key in ("meta_app_id", "meta_app_secret", "google_client_id", "google_client_secret",
                "linkedin_client_id", "linkedin_client_secret", "razorpay_key_id", "razorpay_key_secret"):
        if hasattr(settings, key):
            monkeypatch.setattr(settings, key, "")


def test_full_mode_has_everything_on(raw_client, monkeypatch):
    monkeypatch.setattr(settings, "launch_mode", "full")
    data = raw_client.get("/features").json()
    assert data["mode"] == "full" and data["connect_apps"] and data["whatsapp_messaging"] and data["auto_posting"]


def test_light_mode_turns_unapproved_features_off(raw_client, light):
    data = raw_client.get("/features").json()
    assert data["mode"] == "light"
    assert not data["connect_apps"] and not data["auto_posting"] and not data["whatsapp_messaging"]


def test_gated_pages_are_closed_in_light_mode(raw_client, light):
    owner = login(raw_client)
    for path in ("/connections", "/alerts/settings", "/competitors"):
        assert raw_client.get(path, headers=owner).status_code == 404, path
    assert raw_client.get("/leads?business_id=1", headers=owner).status_code == 200      # the core product still works


def test_mock_payment_is_blocked_in_light_mode(raw_client, light):
    owner = login(raw_client, "garage@demo.in")
    assert raw_client.get("/billing/plans").status_code == 200
    assert raw_client.post("/billing/subscribe", json={"plan": "starter"}, headers=owner).status_code >= 400
    assert raw_client.post("/billing/mock-pay", headers=owner).status_code >= 400


def test_admin_can_activate_a_plan_by_hand_and_extend_it(client, db_session, light):
    first = client.post("/admin/billing/activate", json={"business_id": 2, "plan": "starter"})
    assert first.status_code == 200 and first.json()["state"] == "active"
    again = client.post("/admin/billing/activate", json={"business_id": 2, "plan": "starter"})
    assert again.status_code == 200 and again.json()["days_left"] > first.json()["days_left"]
    rows = db_session.scalars(select(Payment).where(Payment.business_id == 2)).all()
    assert len(rows) == 2 and all(r.gateway_payment_id.startswith("manual_") for r in rows)
    assert client.post("/admin/billing/activate", json={"business_id": 2, "plan": "nope"}).status_code >= 400


def test_posts_are_left_for_the_owner_to_post_by_hand(db_session, light):
    now = datetime.now(timezone.utc)
    post = Post(business_id=1, account_id=1, platform="instagram", kind="photo", status="draft", caption="Hello")
    db_session.add(post)
    db_session.commit()
    scheduler_service.schedule_post(db_session, post, now + timedelta(minutes=5))
    assert isinstance(get_publisher(db_session.get(type(post.account), post.account_id), db_session), ManualPublisher)
    scheduler_service.publish_due(db_session, now=now + timedelta(minutes=10))
    assert post.status == "scheduled"                                       # nothing pretended
    with pytest.raises(ValueError, match="Mark as posted"):
        scheduler_service.publish_now(db_session, post)


def test_manual_publisher_refuses():
    with pytest.raises(PublishError, match="Mark as posted"):
        ManualPublisher().publish(None, None)


def test_a_feature_switches_on_when_its_keys_exist(light, monkeypatch):
    assert not features.on("whatsapp_messaging")
    monkeypatch.setattr(settings, "meta_app_id", "123")
    monkeypatch.setattr(settings, "meta_app_secret", "abc")
    assert features.on("whatsapp_messaging") and features.on("connect_apps")


def test_owner_can_mark_a_by_hand_post_as_posted(db_session, light):
    now = datetime.now(timezone.utc)
    post = Post(business_id=1, account_id=1, platform="instagram", kind="photo", status="draft", caption="Hello")
    db_session.add(post)
    db_session.commit()
    scheduler_service.schedule_post(db_session, post, now + timedelta(minutes=5))
    done = scheduler_service.mark_posted(db_session, post)
    assert done.status == "published" and done.published_at is not None
    with pytest.raises(ValueError, match="Already"):
        scheduler_service.mark_posted(db_session, post)


def test_mark_posted_is_refused_when_the_platform_is_connected(db_session, monkeypatch):
    monkeypatch.setattr(settings, "launch_mode", "full")      # practice mode posts by itself
    post = Post(business_id=1, account_id=1, platform="instagram", kind="photo", status="draft", caption="Hello")
    db_session.add(post)
    db_session.commit()
    with pytest.raises(ValueError, match="Post now"):
        scheduler_service.mark_posted(db_session, post)


def test_mark_posted_endpoint(client, db_session, light):
    now = datetime.now(timezone.utc)
    post = Post(business_id=1, account_id=1, platform="instagram", kind="photo", status="draft", caption="Hello")
    db_session.add(post)
    db_session.commit()
    scheduler_service.schedule_post(db_session, post, now + timedelta(minutes=5))
    r = client.post(f"/posts/{post.id}/mark-posted")
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert client.post(f"/posts/{post.id}/mark-posted").status_code == 400
