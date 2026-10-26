"""
The public website (no login): served as plain, fast HTML pages.

    /            home              /pricing     prices (straight from app/plans.py)
    /about       about us          /contact     contact details + form
    /terms  /privacy  /refunds  /shipping  /data-deletion     the legal pages
    /pay/<token>                   a customer's payment page (Task 31): pays the owner's UPI ID directly
    /robots.txt  /sitemap.xml      for Google
    /static/...                    the stylesheet

Company details on these pages come from .env (COMPANY_NAME, COMPANY_ADDRESS,
SUPPORT_EMAIL, SUPPORT_PHONE, GRIEVANCE_OFFICER...). Anything not filled in yet
is shown highlighted in yellow, and listed by GET /admin/launch-check.
"""

import json
import re
import time
from collections import defaultdict
from html import escape
from pathlib import Path

import segno

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Business, ContactMessage, Due
from app.plans import PLANS, TRIAL_PLAN
from app.services import dues_service, email_service

HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"
pages = Jinja2Templates(directory=str(HERE / "templates"))
router = APIRouter(include_in_schema=False)
PUBLIC_PAGES = ["/", "/pricing", "/about", "/contact", "/terms", "/privacy", "/refunds", "/shipping", "/data-deletion"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
_contact_times: dict[str, list[float]] = defaultdict(list)       # ip → recent form sends

FAQ = [
    ("Do I need to be good with computers?",
     "No. If you can use WhatsApp, you can use this. Setup takes about ten minutes, and the dashboard works on your phone."),
    ("What happens after the free trial?",
     "Choose a plan and pay through Razorpay (UPI, card or net banking). If you don't, the dashboard pauses, but new enquiries keep being saved, so nothing is lost when you come back."),
    ("Will the AI post or reply without asking me?",
     "No. Posts, replies and review answers are drafts until you approve them. The only automatic message is the optional 'please review us' WhatsApp after you mark a sale as won, and you can skip any of those."),
    ("Which platforms does it work with?",
     "WhatsApp, Instagram, Facebook and Google Business Profile connect directly. Justdial, Sulekha, Practo, IndiaMART and similar sites work through their lead emails. Your website form and old Excel lists can be added too."),
    ("Does it write in Hindi or Hinglish?",
     "Yes. Set your brand voice to Hinglish (or Hindi, or English) and posts and replies are written that way."),
    ("Is my customers' data safe?",
     "Each business sees only its own data, platform keys are stored encrypted, and nothing is sold or used for advertising. You can download or delete everything at any time. Details are in the privacy policy."),
    ("Can my staff use it?",
     "Yes. Add staff from Settings; they can answer enquiries and manage posts, but only the owner can change billing and settings."),
    ("Can I cancel any time?",
     "Yes, from Billing, with no fees. You keep access until the end of the month you've paid for."),
]


def _missing(name: str) -> str:
    return f'<span class="missing">[set {name} in .env]</span>'


def site_info() -> dict:
    site = (settings.site_url or settings.public_api_url).rstrip("/")
    app_url = settings.frontend_origin.rstrip("/")
    email = settings.support_email
    plans = list(PLANS.values())
    trial = PLANS[TRIAL_PLAN]
    schema = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": settings.app_name,
              "applicationCategory": "BusinessApplication", "operatingSystem": "Web", "url": site,
              "offers": [{"@type": "Offer", "name": p.name, "price": p.price, "priceCurrency": "INR"} for p in plans]}
    return {
        "brand": settings.app_name, "company": settings.company_name, "address": settings.company_address,
        "phone": settings.support_phone, "site_url": site, "app_url": app_url,
        "signup_url": f"{app_url}/signup?from=site", "login_url": f"{app_url}/login",
        "address_html": escape(settings.company_address) if settings.company_address else _missing("COMPANY_ADDRESS"),
        "email_html": f'<a href="mailto:{escape(email)}">{escape(email)}</a>' if email else _missing("SUPPORT_EMAIL"),
        "phone_html": escape(settings.support_phone) if settings.support_phone else _missing("SUPPORT_PHONE"),
        "grievance_html": (f'{escape(settings.grievance_officer)} (<a href="mailto:{escape(settings.grievance_email)}">'
                           f'{escape(settings.grievance_email)}</a>)'
                           if settings.grievance_officer and settings.grievance_email
                           else _missing("GRIEVANCE_OFFICER and GRIEVANCE_EMAIL")),
        "legal_city": settings.legal_city, "updated": settings.policies_updated,
        "trial_days": settings.trial_days, "trial_plan": TRIAL_PLAN, "trial_name": trial.name,
        "grace_days": settings.payment_grace_days, "plans": plans, "cheapest": min(p.price for p in plans),
        "faq": FAQ, "schema_json": json.dumps(schema).replace("</", "<\\/"),
        "css_version": int((STATIC_DIR / "site.css").stat().st_mtime),
    }


def _page(request: Request, name: str, **extra):
    return pages.TemplateResponse(request, name, {"s": site_info(), **extra},
                                  headers={"Cache-Control": "public, max-age=300"})


@router.get("/")
def home(request: Request):
    return _page(request, "home.html")


@router.get("/pricing")
def pricing(request: Request):
    return _page(request, "pricing.html")


@router.get("/about")
def about(request: Request):
    return _page(request, "about.html")


@router.get("/terms")
def terms(request: Request):
    return _page(request, "terms.html")


@router.get("/privacy")
def privacy(request: Request):
    return _page(request, "privacy.html")


@router.get("/refunds")
def refunds(request: Request):
    return _page(request, "refunds.html")


@router.get("/shipping")
def shipping(request: Request):
    return _page(request, "shipping.html")


@router.get("/data-deletion")
def data_deletion(request: Request):
    return _page(request, "data_deletion.html")


EMPTY_FORM = {"name": "", "email": "", "phone": "", "business": "", "message": "", "topic": "question"}


@router.get("/contact")
def contact(request: Request, sent: str = ""):
    return _page(request, "contact.html", form=EMPTY_FORM, sent="you" if sent else "", error="")


@router.post("/contact")
def contact_send(request: Request, background: BackgroundTasks, name: str = Form(""), email: str = Form(""), phone: str = Form(""),
                 business: str = Form(""), topic: str = Form("question"), message: str = Form(""),
                 website: str = Form(""), db: Session = Depends(get_db)):
    form = {"name": name.strip()[:100], "email": email.strip().lower()[:200], "phone": phone.strip()[:30],
            "business": business.strip()[:150], "message": message.strip()[:4000],
            "topic": topic if topic in ("question", "support", "billing", "privacy") else "question"}
    if website:                                     # the hidden field only robots fill in
        return RedirectResponse("/contact?sent=1", status_code=303)
    ip = request.client.host if request.client else "?"
    now = time.time()
    _contact_times[ip] = [t for t in _contact_times[ip] if t > now - 3600]
    error = ""
    if len(_contact_times[ip]) >= 5:
        error = "You've sent several messages already. Please wait an hour, or email us directly."
    elif not form["name"] or not form["message"]:
        error = "Please fill in your name and message."
    elif not EMAIL_RE.match(form["email"]):
        error = "Please check your email address: we need it to reply."
    if error:
        return pages.TemplateResponse(request, "contact.html", {"s": site_info(), "form": form, "sent": "", "error": error},
                                      status_code=400)
    _contact_times[ip].append(now)
    db.add(ContactMessage(**form))
    db.commit()
    if settings.support_email:
        body = "\n".join(f"{k.title()}: {v}" for k, v in form.items() if v and k != "message") + f"\n\n{form['message']}"
        email_service.queue(db, settings.support_email, "contact_form", (
            f"Website message ({form['topic']}) from {form['name']}", body,
            f"<pre style='font:15px/1.5 sans-serif;white-space:pre-wrap'>{escape(body)}</pre>"))
        background.add_task(email_service.deliver_in_background)
    return RedirectResponse("/contact?sent=1", status_code=303)


# ---------------------------------------------------------------------------
# A customer's payment page (Task 31). The token in the address is the only key:
# long and random, so nobody can guess another customer's page.
# ---------------------------------------------------------------------------
def _due_page(request: Request, db: Session, token: str):
    due = db.scalar(select(Due).where(Due.token == token)) if len(token) <= 32 else None
    if due is None:
        return pages.TemplateResponse(request, "pay_missing.html", {"brand": settings.app_name}, status_code=404,
                                      headers={"Cache-Control": "no-store"})
    business = db.get(Business, due.business_id)
    upi = dues_service.upi_link(business, due)
    qr = segno.make(upi, error="m").svg_inline(scale=6, border=2, dark="#1B1F5E", light="#ffffff")
    state = dues_service.state(due)
    when = state["label"] if due.due_date else ""
    return pages.TemplateResponse(request, "pay.html", {
        "brand": settings.app_name, "payee": dues_service.payee(business), "amount": dues_service.inr(due.amount),
        "purpose": due.purpose, "status": due.status, "claimed": due.customer_says_paid_at is not None,
        "when": when, "late": state["overdue_days"] > 0, "upi_link": upi, "qr": qr,
        "upi_id": dues_service.settings_for(business)["upi_id"], "token": due.token,
    }, headers={"Cache-Control": "no-store"})


@router.get("/pay/{token}")
def pay_page(token: str, request: Request, db: Session = Depends(get_db)):
    return _due_page(request, db, token)


@router.post("/pay/{token}/paid")
def pay_claimed(token: str, db: Session = Depends(get_db)):
    """The customer pressed "I've paid": tell the owner, then show the thank-you page."""
    due = db.scalar(select(Due).where(Due.token == token)) if len(token) <= 32 else None
    if due is not None:
        dues_service.customer_says_paid(db, due)
    return RedirectResponse(f"/pay/{token}", status_code=303)


@router.get("/robots.txt")
def robots():
    site = (settings.site_url or settings.public_api_url).rstrip("/")
    return PlainTextResponse(f"User-agent: *\nAllow: /\nDisallow: /webhooks/\nDisallow: /files/\nDisallow: /pay/\n"
                             f"Sitemap: {site}/sitemap.xml\n")


@router.get("/sitemap.xml")
def sitemap():
    site = (settings.site_url or settings.public_api_url).rstrip("/")
    urls = "".join(f"<url><loc>{escape(site + path)}</loc></url>" for path in PUBLIC_PAGES)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{urls}</urlset>", media_type="application/xml")
