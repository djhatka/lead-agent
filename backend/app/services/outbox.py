"""
The outbox: sending the business's replies to customers for real.

When the owner types a reply on a lead and presses Send:
    WhatsApp lead  → sent from their connected WhatsApp number
    Instagram lead → sent as an Instagram DM
    Facebook lead  → sent as a Messenger message
    anything else (Justdial, website form, walk-in...) → only noted down
      ("logged"): the owner replies by phone, and the reply time still counts.

The 24-hour rule (WhatsApp, Instagram and Messenger): a business may send a
free-text message only within 24 hours of the customer's LAST message. After
that the platforms block it, so we say so clearly instead of failing silently.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import instagram, meta
from app.integrations.base import IntegrationError
from app.models import Lead
from app.services import connection_service as connections

CHAT_PLATFORMS = ("whatsapp", "instagram", "facebook")
MOCK_SENT: list[dict] = []          # what mock connections "sent" (handy for tests and demos)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _last_customer_message(lead: Lead) -> Optional[datetime]:
    times = [_utc(m.sent_at) for m in lead.messages if m.direction == "inbound"]
    return max(times) if times else (_utc(lead.created_at) if lead.created_at else None)


def send_reply(db: Session, lead: Lead, text: str) -> tuple[str, str, Optional[str]]:
    """Returns (delivery, problem, platform message id). delivery = sent / failed / logged."""
    platform = lead.source if lead.source in CHAT_PLATFORMS else None
    conn = connections.active(db, lead.business_id, platform) if platform else None
    if conn is None:
        where = connections.LABELS.get(platform, lead.source) if platform else lead.source
        return "logged", (f"Noted only: {where} isn't connected, so reply to them from your phone."
                          if platform else ""), None

    last = _last_customer_message(lead)
    if last and datetime.now(timezone.utc) - last > timedelta(hours=24):
        return "failed", (f"Not sent: it's been more than 24 hours since {lead.name or 'the customer'}'s last "
                          f"message, and {connections.LABELS[platform]} only allows replies within 24 hours. "
                          f"Call them, or reply when they message again."), None

    to = lead.phone if platform == "whatsapp" else lead.handle
    if not to:
        return "failed", "Not sent: we don't have this customer's WhatsApp number / account id", None
    if conn.mode == "mock":
        MOCK_SENT.append({"platform": platform, "to": to, "text": text, "business_id": lead.business_id})
        return "sent", "", f"mock_{platform}_{len(MOCK_SENT)}"

    try:
        key = connections.token(db, conn)
        if platform == "whatsapp":
            message_id = connections.guarded(db, conn, meta.whatsapp_send_text, conn.external_id, key, to, text)
        elif platform == "instagram":
            message_id = connections.guarded(db, conn, instagram.send_text, conn.external_id, key, to, text)
        else:
            message_id = connections.guarded(db, conn, meta.page_send_text, conn.external_id, key, to, text)
    except IntegrationError as problem:
        return "failed", f"Not sent: {problem}", None
    return "sent", "", message_id
