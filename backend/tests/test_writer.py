"""
Checks for the Writer agent (Task 14).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

import app.agents.nodes.writer_agent as writer
from app.agents.llm import LLM
from app.agents.nodes.writer_agent import mock_write, whatsapp_link
from app.models import Business, Post
from app.services import planner_service, writer_service

IST = timezone(timedelta(hours=5, minutes=30))
TOMORROW = datetime.now(IST).date() + timedelta(days=1)
SAMPLES = Path(__file__).resolve().parents[1] / "seed" / "sample_payloads"


def planned_ideas(db_session, business_id):
    planner_service.plan_week(db_session, db_session.get(Business, business_id), TOMORROW)
    return db_session.query(Post).filter_by(business_id=business_id, status="idea", created_by="ai").all()


def info(post):
    return {"id": post.id, "platform": post.platform, "kind": post.kind, "pillar": post.pillar,
            "title": post.title, "media_note": post.media_note}


BIZ = {"name": "Iron Pulse Fitness", "industry": "gym", "area": "Rajouri Garden", "city": "Delhi",
       "services": ["Zumba", "Personal training"], "brand_voice": "energetic, motivating, Hinglish, uses emojis",
       "target_audience": "18-40", "phone": "+919810000001"}


# ----- The WhatsApp link ------------------------------------------------------------------------
def test_whatsapp_link_carries_the_post_code():
    link = whatsapp_link("+91 98100 00001", 12, "Diwali special offer on Ceramic coating for all cars")
    assert link.startswith("https://wa.me/919810000001?text=")
    text = unquote(link.split("text=")[1])
    assert "(code P12)" in text
    assert "Ceramic coating for" not in text or text.count("  ") == 0    # cut at a word, not mid-word
    assert whatsapp_link(None, 12, "x") is None


# ----- Writing (mock) ------------------------------------------------------------------------------
def test_hinglish_voice_for_the_gym():
    post = {"id": 1, "platform": "instagram", "kind": "reel", "pillar": "offer",
            "title": "Special offer on Zumba", "media_note": "Show Zumba"}
    out = mock_write(post, BIZ, "https://wa.me/1", None)
    assert "Zumba" in out["caption"] and "offer" in out["caption"]
    assert "karo" in out["caption"]                                   # Hinglish call to action
    assert "0-3s" in out["script"]                                    # reel → timed script
    assert 5 <= len(out["hashtags"]) <= 12


def test_english_premium_voice():
    biz = BIZ | {"name": "Gloss Garage", "industry": "car_detailing", "services": ["Ceramic coating"],
                 "brand_voice": "premium, confident"}
    post = {"id": 2, "platform": "instagram", "kind": "carousel", "pillar": "tips",
            "title": "3 tips about Ceramic coating", "media_note": "x"}
    out = mock_write(post, biz, None, None)
    assert "karo" not in out["caption"] and "DM us" in out["caption"]
    assert "Slide 1" in out["script"]                                  # carousel → slides


def test_google_posts_have_no_hashtags():
    post = {"id": 3, "platform": "google", "kind": "photo", "pillar": "offer", "title": "Offer on Zumba", "media_note": ""}
    out = mock_write(post, BIZ, "https://wa.me/1", None)
    assert out["hashtags"] == [] and out["script"] == ""


def test_festival_greeting_is_not_a_sales_pitch():
    post = {"id": 4, "platform": "facebook", "kind": "photo", "pillar": "festival", "title": "Happy Diwali!", "media_note": ""}
    out = mock_write(post, BIZ, "https://wa.me/1", "Diwali")
    assert "Diwali" in out["caption"] and "wa.me" not in out["caption"]
    assert "festive" in out["shot_list"].lower()


# ----- Writing saved posts --------------------------------------------------------------------------
def test_write_week_turns_ideas_into_drafts(db_session):
    ideas = planned_ideas(db_session, 1)
    run, posts, problems = writer_service.write_week(db_session, db_session.get(Business, 1), TOMORROW)
    assert run.status == "success" and run.workflow == "content_write"
    assert len(posts) == len(ideas) and not problems
    for p in posts:
        assert p.status == "draft" and p.caption and p.media_note
        if p.platform == "instagram" and p.pillar != "festival":
            assert f"P{p.id}" in unquote(p.caption)                   # its own tracking code
        if p.kind in ("reel", "carousel"):
            assert p.script


def test_published_posts_cannot_be_rewritten(db_session):
    published = db_session.query(Post).filter_by(business_id=1, status="published").first()
    with pytest.raises(ValueError):
        writer_service.write_post(db_session, published)


# ----- The full journey: written post → WhatsApp tap → lead linked to the post ----------------------
def test_whatsapp_from_a_post_links_the_lead(client, db_session):
    # A selling post (a festival greeting has no booking link, on purpose)
    post = next(p for p in planned_ideas(db_session, 1) if p.pillar != "festival")
    written = client.post(f"/content/write/{post.id}").json()["posts"][0]
    prefilled = unquote(written["caption"].split("text=")[1].split()[0])     # what the customer's WhatsApp sends

    payload = json.loads((SAMPLES / "whatsapp_message.json").read_text(encoding="utf-8"))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg["id"], msg["text"]["body"] = "wamid.FROMPOST", prefilled
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=payload).json()

    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["post_id"] == post.id
    assert client.get(f"/posts/{post.id}").json()["enquiries"] == 1


def test_code_for_another_business_is_ignored(client, db_session):
    other = db_session.query(Post).filter_by(business_id=2).first()
    payload = json.loads((SAMPLES / "whatsapp_message.json").read_text(encoding="utf-8"))
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg["id"], msg["text"]["body"] = "wamid.OTHER", f"Hi (code P{other.id})"
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=payload).json()
    assert client.get(f"/leads/{r['lead_ids'][0]}").json()["post_id"] is None


# ----- Real-AI path (fake Claude): answer is tidied ----------------------------------------------------
def test_real_ai_answer_is_tidied(db_session, monkeypatch):
    post = planned_ideas(db_session, 1)[0]
    answer = {"caption": "Great offer!", "shot_list": "Film it",
              "hashtags": ["#Gym", "gym", "fit ness"] + [f"t{i}" for i in range(12)]}   # 15: allowed, but messy
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)], usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(writer, "get_llm", lambda: LLM(client=fake, enabled=True))
    run, written = writer_service.write_post(db_session, post)
    assert run.steps[0]["mode"] == "real"
    assert len(written.hashtags) <= writer.HASHTAG_RANGE[written.platform][1]   # cut to the platform's limit
    if written.hashtags:
        assert written.hashtags[:2] == ["Gym", "fitness"]                       # '#' removed, duplicate dropped, space removed
    if written.pillar != "festival":
        assert "wa.me" in written.caption                             # link added if the AI forgot it


# ----- Endpoints ------------------------------------------------------------------------------------------
def test_write_endpoints(client):
    client.post("/content/plan-week", params={"business_id": 2})
    r = client.post("/content/write-week", params={"business_id": 2}).json()
    assert r["posts"] and r["mode"] == "mock"
    assert all(p["status"] == "draft" for p in r["posts"])
    again = client.post(f"/content/write/{r['posts'][0]['id']}")             # rewriting a draft is allowed
    assert again.status_code == 200


def test_write_missing_post(client):
    assert client.post("/content/write/99999").status_code == 404
