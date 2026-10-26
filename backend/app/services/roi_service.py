"""
The monthly ROI report: "what Lead Intel did for you this month" (Task 27).

On the 1st of every month (from 9am India time), each business gets last
month's report by email, and it is saved so the dashboard can show it. The
owner can also open the current month at any time ("so far").

Every number is counted by plain code from the business's own records,
never by the AI, and we are careful about what we claim:

    sales tracked here    customers marked "won" this month, from enquiries
                          that came in through Lead Intel
    straight from posts   the part of those sales whose enquiry came from a
                          post we planned / published (the strongest proof)
    return on your plan   sales tracked here ÷ the plan's monthly price

Customers imported from an old Excel/CSV register are left out: we didn't
bring them, so they must not inflate the result.
"""

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.emails.templates import rupees
from app.models import Business, Lead, LeadAnalysis, Post, Review, ReviewRequest, RoiReport
from app.platforms import PLATFORMS
from app.services import billing_service

IST = ZoneInfo("Asia/Kolkata")
SEND_FROM_HOUR = 9            # the report goes out from 9am India time on the 1st
CATCH_UP_DAYS = 7             # if the server was down on the 1st, still send it in the first week


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Months (always India time: "October" means 1 Oct 00:00 to 31 Oct 23:59 IST)
# ---------------------------------------------------------------------------
def month_of(when: datetime) -> str:
    return when.astimezone(IST).strftime("%Y-%m")


def previous_month(when: datetime) -> str:
    first = when.astimezone(IST).replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """'2026-10' → (1 Oct 00:00 IST, 1 Nov 00:00 IST), both in UTC."""
    year, number = (int(x) for x in month.split("-"))
    start = datetime(year, number, 1, tzinfo=IST)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=IST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def month_label(month: str) -> str:
    start, _ = month_bounds(month)
    return start.astimezone(IST).strftime("%B %Y")             # "October 2026"


def valid_month(month: str) -> bool:
    try:
        year, number = (int(x) for x in month.split("-"))
    except ValueError:
        return False
    return len(month) == 7 and 2000 <= year <= 2100 and 1 <= number <= 12


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------
def _in(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    dt = _utc(dt)
    return dt is not None and start <= dt < end


def _ours(lead: Lead) -> bool:
    """Leads Lead Intel handled (not old customers imported from a file)."""
    return not (lead.details or {}).get("imported_from")


def _sales(leads: list[Lead], start: datetime, end: datetime) -> list[Lead]:
    return [lead for lead in leads if lead.status == "won" and _in(lead.won_at, start, end)]


def compute(db: Session, business: Business, month: str, now: Optional[datetime] = None) -> dict:
    """Every number in one month's report, as a plain dict (saved as-is with the report)."""
    now = now or _now()
    start, end = month_bounds(month)
    prev_start, prev_end = month_bounds(previous_month(start))

    leads = [lead for lead in db.scalars(select(Lead).where(Lead.business_id == business.id)) if _ours(lead)]

    # Enquiries that arrived this month
    arrived = [lead for lead in leads if _in(lead.created_at, start, end)]
    by_source: dict[str, int] = {}
    for lead in arrived:
        by_source[lead.source] = by_source.get(lead.source, 0) + 1
    reply_minutes = [(_utc(lead.first_response_at) - _utc(lead.created_at)).total_seconds() / 60
                     for lead in arrived if lead.first_response_at]

    # Sales made this month (and last month, to compare)
    sold = _sales(leads, start, end)
    revenue = sum(lead.job_value or 0 for lead in sold)
    sold_before = _sales(leads, prev_start, prev_end)

    # Posts: published this month, and enquiries / sales that came from a post
    posts = list(db.scalars(select(Post).where(Post.business_id == business.id)))
    published = [p for p in posts if p.status == "published" and _in(p.published_at, start, end)]
    from_posts = [lead for lead in sold if lead.post_id]
    post_money: dict[int, list[Lead]] = {}
    for lead in from_posts:
        post_money.setdefault(lead.post_id, []).append(lead)
    best_post = None
    if post_money:
        post_id, won = max(post_money.items(), key=lambda item: sum(x.job_value or 0 for x in item[1]))
        post = db.get(Post, post_id)
        best_post = {"id": post_id, "title": post.title if post else "", "platform": post.platform if post else "",
                     "customers": len(won), "revenue": sum(x.job_value or 0 for x in won)}

    # Hot leads the AI flagged this month, and how many of them bought
    analyses = {a.lead_id: a for a in db.scalars(select(LeadAnalysis).where(
        LeadAnalysis.lead_id.in_([lead.id for lead in arrived] or [0])))}
    hot = [lead for lead in arrived if analyses.get(lead.id) and analyses[lead.id].priority == "hot"]

    # Reputation
    reviews = [r for r in db.scalars(select(Review).where(Review.business_id == business.id))
               if _in(r.reviewed_at, start, end)]
    replies = db.scalars(select(Review).where(Review.business_id == business.id, Review.reply_status == "posted"))
    requests = db.scalars(select(ReviewRequest).where(ReviewRequest.business_id == business.id))

    access = billing_service.access(db, business.id)
    price = access.price
    multiple = round(revenue / price, 1) if price and revenue else None

    stats = {
        "month": month,
        "label": month_label(month),
        "so_far": now < end,                                   # the month isn't over yet
        "enquiries": {
            "total": len(arrived),
            "by_source": [{"source": s, "name": PLATFORMS[s].name if s in PLATFORMS else s, "count": c}
                          for s, c in sorted(by_source.items(), key=lambda item: -item[1])],
            "answered": len(reply_minutes),
            "answered_within_5_min": sum(1 for m in reply_minutes if m <= 5),
            "median_reply_minutes": round(median(reply_minutes)) if reply_minutes else None,
        },
        "sales": {
            "customers": len(sold),
            "revenue": revenue,
            "average_sale": round(revenue / len(sold)) if sold else None,
        },
        "posts": {
            "published": len(published),
            "published_by_ai": sum(1 for p in published if p.created_by == "ai"),
            "enquiries": sum(1 for lead in arrived if lead.post_id),
            "customers": len(from_posts),
            "revenue": sum(lead.job_value or 0 for lead in from_posts),
            "best": best_post,
        },
        "hot_leads": {"flagged": len(hot), "won": sum(1 for lead in hot if lead.status == "won")},
        "reviews": {
            "new": len(reviews),
            "average_rating": round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None,
            "replies_posted": sum(1 for r in replies if _in(r.replied_at, start, end)),
            "requests_sent": sum(1 for q in requests if _in(q.sent_at, start, end)),
        },
        "plan": {"code": access.plan, "name": access.plan_name, "price": price, "on_trial": access.state == "trial"},
        "return_multiple": multiple,
        "previous": {"month": previous_month(start), "customers": len(sold_before),
                     "revenue": sum(lead.job_value or 0 for lead in sold_before)},
    }
    stats["headline"] = headline(stats)
    return stats


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------
def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def headline(s: dict) -> str:
    sales, plan = s["sales"], s["plan"]
    when = "so far this month" if s["so_far"] else f"in {s['label'].split(' ')[0]}"
    if sales["customers"]:
        line = f"{_n(sales['customers'], 'new customer', 'new customers')} worth {rupees(sales['revenue'])} {when}"
        if s["return_multiple"] and s["return_multiple"] >= 1:
            pays = "would pay" if plan["on_trial"] else "paid"
            line += f": your {plan['name']} plan {pays} for itself {s['return_multiple']:g}×"
        return line + "."
    if s["enquiries"]["total"]:
        return (f"{_n(s['enquiries']['total'], 'enquiry', 'enquiries')} {when}. Mark the ones who buy as 'won' "
                "so we can count the money they bring.")
    return f"No enquiries {when} yet. Connect your WhatsApp and Instagram so every enquiry is counted."


def message(business: Business, s: dict) -> str:
    """The report as a short WhatsApp message (also the email's text)."""
    e, sales, posts, hot, rev = s["enquiries"], s["sales"], s["posts"], s["hot_leads"], s["reviews"]
    lines = [f"*{business.name}: {s['label']}{' (so far)' if s['so_far'] else ''}*", "", s["headline"], ""]
    lines.append(f"📥 {_n(e['total'], 'enquiry', 'enquiries')}"
                 + (f" (most from {e['by_source'][0]['name']})" if e["by_source"] else ""))
    if e["answered"]:
        lines.append(f"⚡ {e['answered_within_5_min']} answered within 5 minutes")
    lines.append(f"💰 {_n(sales['customers'], 'customer', 'customers')}, {rupees(sales['revenue'])} in sales")
    if posts["published"]:
        lines.append(f"📸 {_n(posts['published'], 'post', 'posts')} published"
                     + (f", {posts['published_by_ai']} planned by the AI" if posts["published_by_ai"] else ""))
    if posts["customers"]:
        lines.append(f"🎯 {_n(posts['customers'], 'customer', 'customers')} came straight from your posts "
                     f"({rupees(posts['revenue'])})")
    if hot["flagged"]:
        lines.append(f"🔥 {_n(hot['flagged'], 'hot lead', 'hot leads')} flagged, {hot['won']} bought")
    if rev["new"]:
        lines.append(f"⭐ {_n(rev['new'], 'new review', 'new reviews')} (average {rev['average_rating']:g})")
    if rev["replies_posted"] or rev["requests_sent"]:
        lines.append(f"💬 {_n(rev['replies_posted'], 'review reply', 'review replies')} posted, "
                     f"{_n(rev['requests_sent'], 'review request', 'review requests')} sent")
    before = s["previous"]
    if before["revenue"] and not s["so_far"]:
        change = round((sales["revenue"] - before["revenue"]) / before["revenue"] * 100)
        lines += ["", f"Compared with last month: {'+' if change >= 0 else ''}{change}% in sales."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Saving and sending
# ---------------------------------------------------------------------------
def save(db: Session, business: Business, month: str, now: Optional[datetime] = None) -> RoiReport:
    """Make (or remake) the saved report for one month."""
    stats = compute(db, business, month, now)
    report = db.scalar(select(RoiReport).where(RoiReport.business_id == business.id, RoiReport.month == month))
    if report is None:
        report = RoiReport(business_id=business.id, month=month)
        db.add(report)
    report.stats, report.message = stats, message(business, stats)
    db.commit()
    return report


def email_owners(db: Session, business: Business, report: RoiReport) -> int:
    from app.emails import templates
    from app.services import email_service
    sent = 0
    for owner in email_service.owners_of(db, business.id):
        made = email_service.queue(
            db, owner.email, "roi_report",
            templates.roi_report(owner.name, business.name, report.stats, report.message,
                                 email_service.link(f"/results?month={report.month}")),
            business.id, owner.id, dedupe_key=f"roi:{business.id}:{report.month}:{owner.id}")
        sent += made is not None
    report.emailed_at = _now()
    db.commit()
    return sent


def monthly_reports_due(db: Session, now: Optional[datetime] = None) -> int:
    """Scheduler job: in the first week of a month (from 9am on the 1st, India
    time), save and email last month's report to every business that doesn't
    have it yet. Returns how many reports were made."""
    now = now or _now()
    local = now.astimezone(IST)
    if local.day > CATCH_UP_DAYS or (local.day == 1 and local.hour < SEND_FROM_HOUR):
        return 0
    month = previous_month(now)
    _, month_end = month_bounds(month)
    done_already = set(db.scalars(select(RoiReport.business_id).where(RoiReport.month == month)))
    paused = billing_service.paused_business_ids(db)
    made = 0
    for business in db.scalars(select(Business)):
        if business.id in done_already or business.id in paused or _utc(business.created_at) >= month_end:
            continue                                   # has it / plan ended / joined after that month
        report = save(db, business, month, now)
        email_owners(db, business, report)
        made += 1
    return made
