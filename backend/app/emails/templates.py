"""
Every email's words, in one place, as (subject, plain text, html).

Rules:
  - short, friendly, one clear button
  - anything a USER typed (names, business names) is "escaped" before it goes
    into the HTML, so a business called "<script>..." can't sneak code into an email
  - inline styles only (email apps ignore style sheets)
"""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.config import settings

IST = ZoneInfo("Asia/Kolkata")
ACCENT = "#4f46e5"


def day(dt: datetime) -> str:
    local = dt.astimezone(IST)
    return f"{local.day} {local:%B %Y}"                      # 1 November 2026


def rupees(amount: int) -> str:
    """₹1,45,500 (Indian grouping)."""
    s = str(int(amount))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return "₹" + ",".join([head] + groups if head else groups) + "," + tail


def _layout(title: str, paragraphs: list[str], button: tuple[str, str] | None = None, footer: str = "") -> str:
    """paragraphs may contain simple HTML that WE wrote; user text must be escaped by the caller."""
    body = "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#1f2937">{p}</p>' for p in paragraphs)
    cta = ""
    if button:
        label, link = button
        cta = (f'<p style="margin:22px 0"><a href="{escape(link, quote=True)}" style="background:{ACCENT};color:#ffffff;'
               f'text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:600;font-size:15px;'
               f'display:inline-block">{escape(label)}</a></p>'
               f'<p style="margin:0 0 14px;font-size:12px;color:#6b7280">Button not working? Copy this link: '
               f'<br><span style="word-break:break-all">{escape(link)}</span></p>')
    return (f'<!doctype html><html><body style="margin:0;background:#f3f4f6;padding:24px 12px;'
            f'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
            f'<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;padding:28px 26px">'
            f'<div style="font-weight:700;font-size:16px;color:{ACCENT};margin-bottom:18px">{escape(settings.app_name)}</div>'
            f'<h1 style="font-size:21px;line-height:1.3;margin:0 0 16px;color:#111827">{escape(title)}</h1>'
            f'{body}{cta}'
            f'<p style="margin:26px 0 0;font-size:12px;color:#9ca3af">{footer or "You are getting this email because you have an account with us."}</p>'
            f'</div></body></html>')


def _text(title: str, lines: list[str], link: str = "") -> str:
    return "\n\n".join([title] + lines + ([link] if link else [])) + f"\n\n— {settings.app_name}"


def welcome(name: str, business: str, trial_ends: datetime, link: str) -> tuple[str, str, str]:
    subject = f"Welcome to {settings.app_name}, {name.split(' ')[0]}! 🎉"
    title = f"{business} is all set up"
    lines = [f"Your free trial runs until {day(trial_ends)}: every feature is unlocked.",
             "Three things to do first (10 minutes):",
             "1. Connect your WhatsApp and Instagram (Settings → Connections) so every enquiry lands in one inbox.",
             "2. Tap 'Plan my week': the AI plans and writes a week of posts for you.",
             "3. Add your Google review link, so happy customers can review you."]
    html = _layout(title, [escape(lines[0]), escape(lines[1]),
                           "<br>".join(escape(x) for x in lines[2:])], ("Open my dashboard", link))
    return subject, _text(title, lines, link), html


def password_reset(name: str, link: str, minutes: int) -> tuple[str, str, str]:
    subject = "Reset your password"
    title = "Set a new password"
    lines = [f"Hi {name.split(' ')[0]}, someone (hopefully you) asked to reset your password.",
             f"This link works once, for the next {minutes} minutes.",
             "Didn't ask? Ignore this email: your password stays the same."]
    html = _layout(title, [escape(x) for x in lines], ("Choose a new password", link),
                   "For your safety we never ask for your password by email or phone.")
    return subject, _text(title, lines, link), html


def password_changed(name: str, link: str) -> tuple[str, str, str]:
    subject = "Your password was changed"
    title = "Your password was changed"
    lines = [f"Hi {name.split(' ')[0]}, your password was just changed and you were logged out on other devices.",
             "If this wasn't you, reset your password straight away and reply to this email."]
    html = _layout(title, [escape(x) for x in lines], ("Reset my password", link))
    return subject, _text(title, lines, link), html


def staff_invite(name: str, business: str, owner: str, link: str, days: int) -> tuple[str, str, str]:
    subject = f"You've been added to {business}"
    title = f"Join {business} on {settings.app_name}"
    lines = [f"Hi {name.split(' ')[0]}, {owner} added you to the team, so you can reply to customer enquiries, "
             "manage posts and answer reviews.",
             f"Choose your own password to get started (the link works for {days} days)."]
    html = _layout(title, [escape(x) for x in lines], ("Choose my password", link))
    return subject, _text(title, lines, link), html


def trial_ending(name: str, business: str, ends: datetime, days_left: int, link: str) -> tuple[str, str, str]:
    left = "tomorrow" if days_left <= 1 else f"in {days_left} days"
    subject = f"Your free trial ends {left}"
    title = f"{business}'s free trial ends {left}"
    lines = [f"Hi {name.split(' ')[0]}, your trial ends on {day(ends)}.",
             "Choose a plan to keep your enquiry inbox, AI posts and review replies running without a break. "
             "Plans start at ₹999/month and you can cancel any time.",
             "Your enquiries are always kept safe, even if you decide later."]
    html = _layout(title, [escape(x) for x in lines], ("Choose a plan", link))
    return subject, _text(title, lines, link), html


def trial_ended(name: str, business: str, link: str) -> tuple[str, str, str]:
    subject = "Your free trial has ended"
    title = "Your free trial has ended"
    lines = [f"Hi {name.split(' ')[0]}, {business}'s trial is over, so the dashboard is paused.",
             "Good news: we're still saving every new enquiry from WhatsApp, Instagram and your website. "
             "Choose a plan and everything is back instantly, nothing lost."]
    html = _layout(title, [escape(x) for x in lines], ("Choose a plan", link))
    return subject, _text(title, lines, link), html


def receipt(name: str, business: str, plan: str, amount: int, payment_id: str, paid_at: datetime,
            until: datetime, link: str) -> tuple[str, str, str]:
    subject = f"Payment received: {rupees(amount)} for the {plan} plan"
    title = "Thank you, payment received ✅"
    rows = [("Business", business), ("Plan", f"{plan} (monthly)"), ("Amount", rupees(amount)),
            ("Paid on", day(paid_at)), ("Plan active until", day(until)), ("Payment ID", payment_id),
            ("Billed by", settings.company_name)]
    if settings.company_gstin:
        rows.append(("GSTIN", settings.company_gstin))
    table = ('<table style="width:100%;border-collapse:collapse;font-size:14px">' + "".join(
        f'<tr><td style="padding:7px 0;color:#6b7280;border-bottom:1px solid #f3f4f6">{escape(k)}</td>'
        f'<td style="padding:7px 0;text-align:right;color:#111827;border-bottom:1px solid #f3f4f6">{escape(v)}</td></tr>'
        for k, v in rows) + "</table>")
    html = _layout(title, [escape(f"Hi {name.split(' ')[0]}, here is your receipt."), table],
                   ("See billing history", link), "Keep this email for your records.")
    lines = [f"Hi {name.split(' ')[0]}, here is your receipt."] + [f"{k}: {v}" for k, v in rows]
    return subject, _text(title, lines, link), html


def payment_failed(name: str, business: str, message: str, link: str) -> tuple[str, str, str]:
    subject = "Action needed: your payment didn't go through"
    title = "Your payment didn't go through"
    lines = [f"Hi {name.split(' ')[0]}, we couldn't charge the monthly payment for {business}.",
             message, "Usually it's an expired card or a UPI limit. Updating takes a minute."]
    html = _layout(title, [escape(x) for x in lines], ("Update payment", link))
    return subject, _text(title, lines, link), html


def roi_report(name: str, business: str, stats: dict, message: str, link: str) -> tuple[str, str, str]:
    """The monthly "what Lead Intel did for you" report (Task 27)."""
    sales, posts = stats["sales"], stats["posts"]
    subject = f"{business}: your {stats['label']} results"
    if sales["customers"]:
        subject = f"{business}: {rupees(sales['revenue'])} from {sales['customers']} new customer" \
                  f"{'s' if sales['customers'] != 1 else ''} in {stats['label'].split(' ')[0]}"
    title = f"Your {stats['label']} results"
    rows = [("Enquiries", str(stats["enquiries"]["total"])),
            ("New customers", str(sales["customers"])),
            ("Sales", rupees(sales["revenue"])),
            ("From your posts", rupees(posts["revenue"])),
            ("Return on your plan", f"{stats['return_multiple']:g}×" if stats["return_multiple"] else "–")]
    table = "".join(f'<tr><td style="padding:6px 0;color:#6b7280">{escape(k)}</td>'
                    f'<td style="padding:6px 0;text-align:right;font-weight:600;color:#111827">{escape(v)}</td></tr>'
                    for k, v in rows)
    html = _layout(title, [f"Hi {escape(name.split(' ')[0])},", f"<b>{escape(stats['headline'])}</b>",
                           f'<table style="width:100%;border-collapse:collapse;font-size:15px">{table}</table>',
                           "Return on your plan = sales from enquiries handled in your dashboard ÷ your monthly plan price. "
                           "Customers imported from old registers are not counted."],
                   ("See the full report", link))
    lines = [f"Hi {name.split(' ')[0]},", message]
    return subject, _text(title, lines, link), html
