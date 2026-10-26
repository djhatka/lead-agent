"""
The mailer: the ONE place that actually sends an email.

    MockMailer  no SMTP_HOST in .env → saves each email as an .html file in
                data/outbox/ (open it in a browser to see it) and remembers it
    SmtpMailer  SMTP_HOST set → sends through your email provider

SMTP = the standard "post office" language every email provider speaks, so
switching provider later only means changing .env (host, port, username, password).
"""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from app.config import settings

logger = logging.getLogger("mailer")


class MailError(Exception):
    pass


def build_message(to: str, subject: str, text: str, html: str) -> EmailMessage:
    """One email with a plain-text version and a nicer HTML version (the inbox picks)."""
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=settings.email_from.rsplit("@", 1)[-1].strip("> ") or None)
    if settings.email_reply_to:
        msg["Reply-To"] = settings.email_reply_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


class MockMailer:
    mode = "mock"
    sent: list[dict] = []            # handy for tests and for seeing what would have gone out

    def send(self, email_id: int, kind: str, to: str, subject: str, text: str, html: str) -> None:
        folder = Path(settings.outbox_dir)
        folder.mkdir(parents=True, exist_ok=True)
        safe_kind = re.sub(r"[^a-z_]", "", kind)
        (folder / f"{email_id:05d}-{safe_kind}.html").write_text(
            f"<!-- To: {to} | Subject: {subject} -->\n{html}", encoding="utf-8")
        self.sent.append({"id": email_id, "kind": kind, "to": to, "subject": subject, "text": text, "html": html})
        logger.info("Email (mock) to %s: %s", to, subject)


class SmtpMailer:
    mode = "real"

    def send(self, email_id: int, kind: str, to: str, subject: str, text: str, html: str) -> None:
        msg = build_message(to, subject, text, html)
        context = ssl.create_default_context()
        try:
            if settings.smtp_ssl:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=context)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
            with server:
                if settings.smtp_starttls and not settings.smtp_ssl:
                    server.starttls(context=context)        # lock the connection before sending the password
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as problem:
            raise MailError(f"{problem.__class__.__name__}: {problem}") from problem


def get_mailer():
    return SmtpMailer() if settings.email_enabled else MockMailer()
