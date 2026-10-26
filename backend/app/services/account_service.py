"""
Your data, your choice: "download all my data" and "delete my account".

Indian privacy law (DPDP Act) gives people the right to get their data and to
have it erased, and Meta/Google require it before approving our app. These two
functions make the privacy policy's promises real.

export_zip()      everything about the business in one .zip: a JSON file plus
                  easy-to-open CSV sheets (leads, messages, posts, reviews, payments)
delete_business() erases the business and everything linked to it. Kept: one
                  small note with the payment records (tax law: 8 years).
"""

import csv
import io
import json
import logging
import zipfile
from html import escape
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.config import settings
from app.emails.templates import _layout, _text
from app.models import (AgentRun, AuthSession, Business, Connection, DeletedAccount, Due, Email, GrowthReport,
                        InboundEmail, Lead, LeadAnalysis, Media, Message, OwnerAlert, PasswordReset, Payment, Post, Review, ReviewRequest,
                        RoiReport, SocialAccount, Subscription, User)
from app.services import email_service, storage
from app.services import payment_gateway as gw

logger = logging.getLogger("account")


class AccountError(Exception):
    pass


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _sheet(rows: list[dict]) -> str:
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else _iso(v)
                             for k, v in row.items()})
    return "﻿" + out.getvalue()                       # "﻿" makes Excel read ₹ and Hindi correctly


def export_zip(db: Session, business_id: int) -> bytes:
    business = db.get(Business, business_id)
    leads = list(db.scalars(select(Lead).where(Lead.business_id == business_id).order_by(Lead.id)))
    lead_ids = [lead.id for lead in leads]
    data = {
        "business": {c: _iso(getattr(business, c)) for c in ("id", "name", "industry", "city", "area", "description",
                                                              "services", "brand_voice", "target_audience", "phone",
                                                              "website", "google_review_link", "created_at")},
        "team": [{"name": u.name, "email": u.email, "role": u.role, "active": u.is_active, "joined": _iso(u.created_at)}
                 for u in db.scalars(select(User).where(User.business_id == business_id))],
        "leads": [{"id": l.id, "created_at": _iso(l.created_at), "source": l.source, "name": l.name, "phone": l.phone,
                   "handle": l.handle, "area": l.area, "service": l.service, "status": l.status, "value_rs": l.job_value,
                   "won_at": _iso(l.won_at),
                   "first_message": l.first_message, "details": l.details,
                   "ai_score": l.analysis.score if l.analysis else None,
                   "ai_tone": l.analysis.sentiment if l.analysis else None} for l in leads],
        "messages": [{"lead_id": m.lead_id, "sent_at": _iso(m.sent_at), "direction": m.direction, "text": m.text,
                      "delivery": m.delivery, "auto_reply": m.auto_reply} for m in db.scalars(select(Message).where(Message.lead_id.in_(lead_ids))
                                                                  .order_by(Message.id))] if lead_ids else [],
        "posts": [{"id": p.id, "platform": p.platform, "kind": p.kind, "status": p.status, "title": p.title,
                   "caption": p.caption, "hashtags": p.hashtags, "scheduled_for": _iso(p.scheduled_for),
                   "published_at": _iso(p.published_at), "reach": p.reach, "likes": p.likes, "comments": p.comments,
                   "media_url": p.media_url} for p in db.scalars(select(Post).where(Post.business_id == business_id))],
        "reviews": [{"platform": r.platform, "author": r.author_name, "rating": r.rating, "text": r.text,
                     "reviewed_at": _iso(r.reviewed_at), "reply": r.reply_text, "reply_status": r.reply_status}
                    for r in db.scalars(select(Review).where(Review.business_id == business_id))],
        "payments": [{"paid_at": _iso(p.paid_at), "plan": p.plan, "amount_rs": p.amount, "payment_id": p.gateway_payment_id,
                      "status": p.status} for p in db.scalars(select(Payment).where(Payment.business_id == business_id))],
        "customer_dues": [{"customer": d.customer_name, "phone": d.phone, "amount_rs": d.amount, "for": d.purpose,
                           "due_date": d.due_date.isoformat() if d.due_date else None, "status": d.status, "paid_at": _iso(d.paid_at),
                           "paid_via": d.paid_via, "lead_id": d.lead_id, "created_at": _iso(d.created_at)}
                          for d in db.scalars(select(Due).where(Due.business_id == business_id).order_by(Due.id))],
        "media": [{"kind": m.kind, "file": storage.public_url(m.key), "name": m.original_name, "uploaded": _iso(m.created_at)}
                  for m in db.scalars(select(Media).where(Media.business_id == business_id))],
        "connections": [{"platform": c.platform, "account": c.display_name, "status": c.status,
                         "connected_at": _iso(c.connected_at)}                       # keys are never exported
                        for c in db.scalars(select(Connection).where(Connection.business_id == business_id))],
        "monthly_reports": [{"month": r.month, "numbers": r.stats, "message": r.message}
                            for r in db.scalars(select(RoiReport).where(RoiReport.business_id == business_id)
                                                .order_by(RoiReport.month))],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("all-data.json", json.dumps(data, ensure_ascii=False, indent=2))
        for sheet in ("leads", "messages", "posts", "reviews", "payments", "customer_dues"):
            z.writestr(f"{sheet}.csv", _sheet(data[sheet]))
        z.writestr("README.txt", f"Your data from {settings.app_name}, exported {data['exported_at']}.\n"
                                 "all-data.json has everything; the .csv files open in Excel or Google Sheets.\n"
                                 "Photos and videos: the links in all-data.json → media.\n")
    return out.getvalue()


def delete_business(db: Session, owner: User, business_id: int, password: str, confirm: str) -> None:
    if confirm.strip().upper() != "DELETE":
        raise AccountError("Type DELETE to confirm")
    if owner.role != "admin" and not verify_password(password, owner.password_hash):
        raise AccountError("Your password is wrong")
    business = db.get(Business, business_id)
    if business is None:
        raise AccountError("Business not found")

    sub = db.scalar(select(Subscription).where(Subscription.business_id == business_id))
    if sub and sub.gateway_subscription_id:                       # stop future charges first
        try:
            gw.get_gateway().cancel(sub.gateway_subscription_id, at_cycle_end=False)
        except gw.GatewayError as problem:
            logger.warning("Couldn't cancel subscription while deleting business %s: %s", business_id, problem)
    for media in db.scalars(select(Media).where(Media.business_id == business_id)):
        for key in (media.key, media.thumb_key, media.instagram_key):
            if key:
                storage.get_storage().delete(key)

    owner_emails = [o.email for o in db.scalars(select(User).where(User.business_id == business_id, User.role == "owner"))]
    name = business.name
    payments = [{"date": _iso(p.paid_at), "amount_rs": p.amount, "plan": p.plan, "payment_id": p.gateway_payment_id}
                for p in db.scalars(select(Payment).where(Payment.business_id == business_id))]
    db.add(DeletedAccount(business_name=name, owner_email=", ".join(owner_emails) or "(admin deleted)",
                          payments=payments))

    # Erase everything, children first (works whether or not the database cascades by itself)
    user_ids = [u.id for u in db.scalars(select(User).where(User.business_id == business_id))]
    lead_ids = [i for (i,) in db.execute(select(Lead.id).where(Lead.business_id == business_id))]
    steps = [
        delete(AuthSession).where(AuthSession.user_id.in_(user_ids)),
        delete(PasswordReset).where(PasswordReset.user_id.in_(user_ids)),
        delete(Email).where(Email.business_id == business_id),
        delete(InboundEmail).where(InboundEmail.business_id == business_id),
        delete(ReviewRequest).where(ReviewRequest.business_id == business_id),
        delete(Review).where(Review.business_id == business_id),
        delete(GrowthReport).where(GrowthReport.business_id == business_id),
        delete(RoiReport).where(RoiReport.business_id == business_id),
        delete(OwnerAlert).where(OwnerAlert.business_id == business_id),
        delete(Due).where(Due.business_id == business_id),
        delete(AgentRun).where(AgentRun.business_id == business_id),
        delete(Message).where(Message.lead_id.in_(lead_ids)),
        delete(LeadAnalysis).where(LeadAnalysis.lead_id.in_(lead_ids)),
        delete(Lead).where(Lead.business_id == business_id),
        delete(Post).where(Post.business_id == business_id),
        delete(Media).where(Media.business_id == business_id),
        delete(Connection).where(Connection.business_id == business_id),
        delete(SocialAccount).where(SocialAccount.business_id == business_id),
        delete(Payment).where(Payment.business_id == business_id),
        delete(Subscription).where(Subscription.business_id == business_id),
        delete(User).where(User.business_id == business_id),
        delete(Business).where(Business.id == business_id),
    ]
    for step in steps:
        db.execute(step, execution_options={"synchronize_session": False})
    db.commit()
    db.expire_all()

    title = "Your account has been deleted"
    lines = [f"{name} and all its data have been deleted from {settings.app_name}.",
             "We keep only your payment records, because Indian tax law requires it. Thank you for trying us."]
    for address in owner_emails:                                  # no business_id: the business is gone
        email_service.queue(db, address, "account_deleted",
                            (title, _text(title, lines), _layout(title, [escape(x) for x in lines])))
