"""
Task 25 checks: the public website, legal pages, contact form, and the
data rights (download / delete my account) + the go-live checklist.
"""

import io
import json
import re
import zipfile

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Business, ContactMessage, DeletedAccount, Email, Lead, Payment, User
from app.site import routes as site

PAGES = ["/", "/pricing", "/about", "/contact", "/terms", "/privacy", "/refunds", "/shipping", "/data-deletion"]


@pytest.fixture(autouse=True)
def fresh_contact_limits():
    site._contact_times.clear()
    yield
    site._contact_times.clear()


@pytest.fixture
def company(monkeypatch):
    for name, value in {"company_name": "Bhutani Digital Services", "company_address": "12, Rajouri Garden, New Delhi 110027",
                        "support_email": "support@leadintel.in", "support_phone": "+91 98100 00000",
                        "grievance_officer": "Anmol Bhutani", "grievance_email": "grievance@leadintel.in"}.items():
        monkeypatch.setattr(settings, name, value)


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def test_every_public_page_opens(raw_client):
    for path in PAGES:
        r = raw_client.get(path)
        assert r.status_code == 200, path
        assert r.headers["content-type"].startswith("text/html")
        assert "<title>" in r.text and 'href="/privacy"' in r.text and 'href="/refunds"' in r.text


def test_prices_come_from_the_price_list(raw_client):
    home = raw_client.get("/").text
    assert "₹999" in home and "₹2,499" in home and "₹4,999" in home
    assert "14-day free trial" in home
    schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S).group(1))
    assert [o["price"] for o in schema["offers"]] == [999, 2499, 4999] and schema["offers"][0]["priceCurrency"] == "INR"
    table = raw_client.get("/pricing").text
    assert "Weekly AI growth review" in table and "20 GB" in table


def test_signup_buttons_go_to_the_dashboard(raw_client):
    home = raw_client.get("/").text
    assert 'href="http://localhost:5173/signup?from=site"' in home
    assert "signup?from=site&amp;plan=growth" in home


def test_razorpay_pages_have_what_they_need(raw_client, company):
    contact = raw_client.get("/contact").text
    assert "Bhutani Digital Services" in contact and "12, Rajouri Garden" in contact and "support@leadintel.in" in contact
    assert "+91 98100 00000" in contact
    refunds = raw_client.get("/refunds").text
    assert "5–7 working days" in refunds and "Cancel any time" in refunds
    assert "Nothing physical is shipped" in raw_client.get("/shipping").text
    privacy = raw_client.get("/privacy").text
    for must in ("Anmol Bhutani", "grievance@leadintel.in", "Data Protection Board", "Anthropic", "Razorpay",
                 "Limited Use", "Download my data", "8 years"):
        assert must in privacy, must
    terms = raw_client.get("/terms").text
    assert "Courts at New Delhi" in terms and "AI drafts" in terms


def test_missing_company_details_are_highlighted(raw_client):
    contact = raw_client.get("/contact").text
    assert '<span class="missing">[set COMPANY_ADDRESS in .env]</span>' in contact
    assert "[set GRIEVANCE_OFFICER and GRIEVANCE_EMAIL in .env]" in raw_client.get("/privacy").text


def test_company_details_are_escaped(raw_client, monkeypatch):
    monkeypatch.setattr(settings, "company_address", "<script>alert(1)</script>")
    page = raw_client.get("/contact").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_search_engine_files(raw_client):
    robots = raw_client.get("/robots.txt").text
    assert "Sitemap: http://127.0.0.1:8000/sitemap.xml" in robots and "Disallow: /webhooks/" in robots
    sitemap = raw_client.get("/sitemap.xml").text
    assert sitemap.count("<url>") == len(PAGES) and "<loc>http://127.0.0.1:8000/privacy</loc>" in sitemap
    css = raw_client.get("/static/site.css")
    assert css.status_code == 200 and "--marigold" in css.text


# ---------------------------------------------------------------------------
# Contact form
# ---------------------------------------------------------------------------
FORM = {"name": "Deepak", "email": "Deepak@Gym.in", "phone": "9811000999", "business": "Deepak Fitness",
        "topic": "question", "message": "Does it work with Cult.fit leads?", "website": ""}


def test_contact_form(raw_client, db_session, company, email_outbox):
    r = raw_client.post("/contact", data=FORM, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/contact?sent=1"
    saved = db_session.scalar(select(ContactMessage))
    assert saved.email == "deepak@gym.in" and saved.message == "Does it work with Cult.fit leads?"
    [mail] = [e for e in email_outbox if e["kind"] == "contact_form"]
    assert mail["to"] == "support@leadintel.in" and "Deepak Fitness" in mail["text"]
    assert "Thanks, your message was sent" in raw_client.get("/contact?sent=1").text


def test_contact_form_checks(raw_client, db_session):
    bad = raw_client.post("/contact", data={**FORM, "email": "not-an-email"})
    assert bad.status_code == 400 and "check your email address" in bad.text and "Does it work with Cult.fit" in bad.text
    robot = raw_client.post("/contact", data={**FORM, "website": "http://spam.example"}, follow_redirects=False)
    assert robot.status_code == 303 and db_session.scalar(select(func.count(ContactMessage.id))) == 0
    for _ in range(5):
        raw_client.post("/contact", data=FORM, follow_redirects=False)
    sixth = raw_client.post("/contact", data=FORM)
    assert sixth.status_code == 400 and "wait an hour" in sixth.text


# ---------------------------------------------------------------------------
# Download my data
# ---------------------------------------------------------------------------
def test_download_my_data(raw_client, db_session):
    r = raw_client.get("/account/export", headers=login(raw_client))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert re.search(r'filename="iron-pulse-fitness-data-\d{4}-\d{2}-\d{2}\.zip"', r.headers["content-disposition"])
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"all-data.json", "leads.csv", "messages.csv", "posts.csv", "reviews.csv", "payments.csv", "README.txt"} <= set(z.namelist())
    data = json.loads(z.read("all-data.json"))
    assert data["business"]["name"] == "Iron Pulse Fitness"
    assert len(data["leads"]) == db_session.scalar(select(func.count(Lead.id)).where(Lead.business_id == 1))
    assert {lead["id"] for lead in data["leads"]} == {i for (i,) in db_session.execute(select(Lead.id).where(Lead.business_id == 1))}
    everything = z.read("all-data.json").decode() + z.read("leads.csv").decode("utf-8-sig")
    assert "scrypt$" not in everything and "password" not in everything.lower()           # no secrets
    assert z.read("leads.csv").startswith("﻿".encode())                                # opens right in Excel


def test_only_owners_download(raw_client):
    assert raw_client.get("/account/export", headers=login(raw_client, "staff@demo.in")).status_code == 403
    garage = raw_client.get("/account/export", params={"business_id": 1}, headers=login(raw_client, "garage@demo.in"))
    assert json.loads(zipfile.ZipFile(io.BytesIO(garage.content)).read("all-data.json"))["business"]["id"] == 2


# ---------------------------------------------------------------------------
# Delete my account
# ---------------------------------------------------------------------------
def test_delete_needs_password_and_confirmation(raw_client):
    gym = login(raw_client)
    assert raw_client.post("/account/delete", headers=gym, json={"password": "demo1234", "confirm": "yes"}).status_code == 400
    wrong = raw_client.post("/account/delete", headers=gym, json={"password": "wrong-pass", "confirm": "DELETE"})
    assert wrong.status_code == 400 and "password is wrong" in wrong.json()["detail"]
    assert raw_client.post("/account/delete", headers=login(raw_client, "staff@demo.in"),
                           json={"password": "demo1234", "confirm": "DELETE"}).status_code == 403


def test_delete_my_account(raw_client, db_session, email_outbox):
    gym = login(raw_client)
    paid = db_session.scalar(select(func.count(Payment.id)).where(Payment.business_id == 1))
    garage_leads = db_session.scalar(select(func.count(Lead.id)).where(Lead.business_id == 2))
    r = raw_client.post("/account/delete", headers=gym, json={"password": "demo1234", "confirm": "delete"})
    assert r.status_code == 200 and r.json()["deleted"]

    assert db_session.get(Business, 1) is None
    assert db_session.scalar(select(func.count(Lead.id)).where(Lead.business_id == 1)) == 0
    assert db_session.scalar(select(User).where(User.email.in_(["gym@demo.in", "staff@demo.in"]))) is None
    assert raw_client.get("/auth/me", headers=gym).status_code == 401                   # logged out everywhere
    assert raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"}).status_code == 401
    assert db_session.scalar(select(func.count(Lead.id)).where(Lead.business_id == 2)) == garage_leads   # others untouched

    note = db_session.scalar(select(DeletedAccount))
    assert note.business_name == "Iron Pulse Fitness" and note.owner_email == "gym@demo.in" and len(note.payments) == paid
    [bye] = [e for e in email_outbox if e["kind"] == "account_deleted"]
    assert bye["to"] == "gym@demo.in" and "payment records" in bye["text"]


# ---------------------------------------------------------------------------
# Go-live checklist
# ---------------------------------------------------------------------------
def test_launch_check(raw_client, monkeypatch, company):
    admin = login(raw_client, "admin@demo.in", "admin1234")
    first = raw_client.get("/admin/launch-check", headers=admin).json()
    assert not first["ready"] and "SECRET_KEY changed from the demo value" in first["blocking"]
    assert "Company details on the legal pages" not in first["blocking"]                   # filled by the fixture
    for name, value in {"secret_key": "x" * 48, "webhook_verify_token": "verify-123", "inbound_email_secret": "in-456",
                        "public_api_url": "https://api.leadintel.in", "frontend_origin": "https://app.leadintel.in"}.items():
        monkeypatch.setattr(settings, name, value)
    assert raw_client.get("/admin/launch-check", headers=admin).json()["ready"]
    assert raw_client.get("/admin/launch-check", headers=login(raw_client)).status_code == 403
