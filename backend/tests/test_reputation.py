"""
Checks for reputation: review replies, review requests and the summary (Task 17).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.agents.nodes.review_reply_agent as reply_module
from app.agents.llm import LLM
from app.agents.nodes.review_reply_agent import mock_reply, run_reply
from app.models import Business, Lead, Review, ReviewRequest
from app.schemas import LeadUpdate, ReviewCreate
from app.services import lead_service, reputation_service as rep
from app.services.messenger import MockMessenger

IST = timezone(timedelta(hours=5, minutes=30))
CLINIC = {"name": "SmileCare Dental Clinic", "industry": "clinic", "phone": "+919810000003"}


# ----- Reply agent -----------------------------------------------------------------------------------
@pytest.mark.parametrize("stars, sentiment, attention", [(5, "positive", False), (4, "positive", False),
                                                         (3, "neutral", False), (2, "negative", True),
                                                         (1, "negative", True)])
def test_reply_matches_the_stars(stars, sentiment, attention):
    out = mock_reply(stars, "The staff were rude and I waited an hour", "Priya Sharma", CLINIC)
    assert out["sentiment"] == sentiment and out["needs_attention"] == attention
    assert "Priya" in out["reply"] and "SmileCare" in out["reply"]


def test_unhappy_reply_apologises_and_gives_phone_no_discount():
    out = mock_reply(1, "Overcharged and rude staff", "Karan Mehta", CLINIC)
    assert "sorry" in out["reply"].lower() and "+919810000003" in out["reply"]
    assert not any(w in out["reply"].lower() for w in ("discount", "refund", "free", "% off"))


def test_reply_never_repeats_private_treatment_details():
    out = mock_reply(5, "My root canal was painless, thanks Dr. Mehta", "Neha Gupta", CLINIC)
    assert "root canal" not in out["reply"].lower()


def test_topics():
    out = mock_reply(3, "Good result but had to wait and nobody replied on WhatsApp", "Arjun", CLINIC)
    assert {"result", "wait time", "communication"} <= set(out["topics"])


def test_safety_net_for_one_star_even_if_ai_says_positive(monkeypatch):
    answer = {"sentiment": "positive", "topics": [], "needs_attention": False, "reply": "Thanks for the review!"}
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)], usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(reply_module, "get_llm", lambda: LLM(client=fake, enabled=True))
    result = run_reply(1, "Terrible", "X", CLINIC)
    assert result.data.sentiment == "negative" and result.data.needs_attention


# ----- Reviews ---------------------------------------------------------------------------------------
def test_add_review_drafts_a_reply_and_ignores_duplicates(db_session):
    data = ReviewCreate(business_id=2, platform="Google", external_id="g-123", author_name="Rohit Verma",
                        rating=5, text="Amazing ceramic coating, great team")
    review, created = rep.add_review(db_session, data)
    assert created and review.reply_status == "drafted" and review.reply_text
    again, created_again = rep.add_review(db_session, data)
    assert not created_again and again.id == review.id


def test_owner_approves_or_edits_reply(db_session):
    review, _ = rep.add_review(db_session, ReviewCreate(business_id=1, rating=2, author_name="Sahil", text="Rude staff"))
    assert review.needs_attention
    rep.post_reply(db_session, review, "Sorry Sahil, please call us so we can help. - Team Iron Pulse")
    assert review.reply_status == "posted" and review.replied_at and review.reply_text.startswith("Sorry Sahil")
    with pytest.raises(ValueError):
        rep.post_reply(db_session, review)                          # not twice


# ----- Review requests -----------------------------------------------------------------------------------
def won_lead(db_session, business_id=2, name="Meera Kapoor", phone="+919811000777"):
    lead = Lead(business_id=business_id, source="whatsapp", name=name, phone=phone, status="quoted",
                service="PPF", first_message="hi")
    db_session.add(lead)
    db_session.commit()
    lead_service.update_lead(db_session, lead, LeadUpdate(status="won", job_value=50000))
    return lead


def test_winning_a_lead_queues_one_request(db_session):
    lead = won_lead(db_session)
    req = db_session.query(ReviewRequest).filter_by(lead_id=lead.id).one()
    assert req.status == "pending" and "Meera" in req.message and "g.page" in req.message
    send_after = req.send_after.replace(tzinfo=req.send_after.tzinfo or timezone.utc)   # SQLite drops the timezone
    assert send_after > datetime.now(timezone.utc)                  # waits a few hours
    rep.request_for_lead(db_session, lead)                           # asked again → still only one
    assert db_session.query(ReviewRequest).filter_by(lead_id=lead.id).count() == 1


def test_gym_request_is_in_hinglish(db_session):
    lead = won_lead(db_session, business_id=1, phone="+919811000778")
    assert "dijiye" in db_session.query(ReviewRequest).filter_by(lead_id=lead.id).one().message


def test_no_request_without_phone_or_link(db_session):
    db_session.get(Business, 3).google_review_link = None
    db_session.commit()
    won_lead(db_session, business_id=3, phone="+919811000779")
    assert db_session.query(ReviewRequest).filter_by(business_id=3).count() == 0


def test_requests_are_sent_only_in_daytime(db_session):
    won_lead(db_session)
    later = datetime.now(timezone.utc) + timedelta(days=1)
    night = later.astimezone(IST).replace(hour=23, minute=0)
    day = later.astimezone(IST).replace(hour=11, minute=0)
    before = len(MockMessenger.sent)
    assert rep.send_due_requests(db_session, now=night) == 0
    assert rep.send_due_requests(db_session, now=day) == 1
    assert len(MockMessenger.sent) == before + 1


def test_review_from_asked_customer_is_matched(db_session):
    lead = won_lead(db_session)
    sent_time = datetime.now(timezone.utc).astimezone(IST).replace(hour=12) + timedelta(days=1)
    rep.send_due_requests(db_session, now=sent_time)
    review, _ = rep.add_review(db_session, ReviewCreate(business_id=2, author_name="Meera K", rating=5,
                                                        text="Great!", reviewed_at=sent_time + timedelta(hours=5)))
    assert review.lead_id == lead.id
    assert db_session.query(ReviewRequest).filter_by(lead_id=lead.id).one().status == "reviewed"


# ----- Summary -----------------------------------------------------------------------------------------------
def test_summary_numbers(db_session):
    s = rep.summary(db_session, 1)
    reviews = db_session.query(Review).filter_by(business_id=1).all()
    assert s.reviews == len(reviews) == sum(s.by_stars.values())
    assert s.average_rating == round(sum(r.rating for r in reviews) / len(reviews), 2)
    assert s.unreplied == sum(1 for r in reviews if r.reply_status != "posted")


def test_growth_review_includes_reputation(db_session):
    from app.services.growth_service import run_review
    _, report = run_review(db_session, db_session.get(Business, 2))
    items = {c["item"] for c in report.presence_audit}
    assert {"Rating 4.5+ stars", "Every review answered", "Asking customers for reviews"} <= items


# ----- Endpoints ------------------------------------------------------------------------------------------------
def test_review_endpoints(client):
    r = client.post("/reviews", json={"business_id": 3, "rating": 1, "author_name": "Deepak",
                                      "text": "Waited 2 hours, rude staff"})
    assert r.status_code == 201 and r.json()["needs_attention"]
    rid = r.json()["id"]
    urgent = client.get("/reviews", params={"business_id": 3, "needs_attention": True}).json()
    assert any(x["id"] == rid for x in urgent)
    posted = client.post(f"/reviews/{rid}/reply", json={}).json()
    assert posted["reply_status"] == "posted"
    assert client.post(f"/reviews/{rid}/reply", json={}).status_code == 400


def test_draft_all_and_summary_endpoints(client):
    result = client.post("/reviews/draft-all", params={"business_id": 1}).json()
    assert result["drafted"] > 0
    summary = client.get("/reviews/summary", params={"business_id": 1}).json()
    assert summary["reviews"] > 0 and 1 <= summary["average_rating"] <= 5


def test_request_endpoints(client, db_session):
    lead = won_lead(db_session)
    reqs = client.get("/review-requests", params={"business_id": 2, "status": "pending"}).json()
    rid = next(r["id"] for r in reqs if r["lead_id"] == lead.id)
    assert client.post(f"/review-requests/{rid}/skip").json()["status"] == "skipped"
    assert client.post(f"/review-requests/{rid}/skip").status_code == 400


def test_marking_won_via_api_queues_request(client):
    lead = client.post("/leads", json={"business_id": 2, "source": "walk_in", "name": "Varun Arora",
                                       "phone": "9811000888"}).json()
    client.patch(f"/leads/{lead['id']}", json={"status": "won", "job_value": 15000})
    reqs = client.get("/review-requests", params={"business_id": 2}).json()
    assert any(r["lead_id"] == lead["id"] for r in reqs)
