"""
Messenger: sends WhatsApp messages: "please review us" to customers, and
alerts to the owner's own phone (Task 28).

    MockMessenger      the business hasn't connected WhatsApp (or mock mode):
                       it just records what it would send
    WhatsAppMessenger  a real WhatsApp number (Cloud API): the business's own,
                       or Lead Intel's own number for owner alerts

WhatsApp only lets a business START a conversation with an approved TEMPLATE
(customers haven't messaged in the last 24 hours). When a business connects
WhatsApp we ask Meta to approve our review template in their account
(integrations/meta.py → whatsapp_create_review_template). The template's blanks:
    {{1}} customer's first name   {{2}} business name   {{3}} Google review link
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.integrations import meta
from app.integrations.base import IntegrationError

logger = logging.getLogger("messenger")


class SendError(Exception):
    pass


class MockMessenger:
    sent: list[dict] = []          # everything "sent", handy for tests and for seeing what happened

    def send_whatsapp(self, phone: str, text: str, template_params: Optional[list[str]] = None,
                      template: Optional[str] = None) -> str:
        if not phone:
            raise SendError("No phone number")
        message_id = f"mock_wa_{len(self.sent) + 1}"
        self.sent.append({"id": message_id, "phone": phone, "text": text})
        logger.info("WhatsApp (mock) to %s: %s", phone, text[:60])
        return message_id


class WhatsAppMessenger:
    def __init__(self, db: Session, conn):
        self.db, self.conn = db, conn

    def send_whatsapp(self, phone: str, text: str, template_params: Optional[list[str]] = None,
                      template: Optional[str] = None) -> str:
        from app.services import connection_service as connections
        if not phone:
            raise SendError("No phone number")
        key = connections.token(self.db, self.conn)
        try:
            if template_params:
                return connections.guarded(self.db, self.conn, meta.whatsapp_send_template, self.conn.external_id,
                                           key, phone, template or settings.whatsapp_review_template,
                                           settings.whatsapp_template_language, template_params)
            return connections.guarded(self.db, self.conn, meta.whatsapp_send_text, self.conn.external_id,
                                       key, phone, text)
        except IntegrationError as problem:
            raise SendError(str(problem)) from problem


def get_messenger(db: Optional[Session] = None, business_id: Optional[int] = None):
    """The business's real WhatsApp if it's connected for real, otherwise the mock."""
    if db is not None and business_id is not None:
        from app.services import connection_service as connections
        conn = connections.active(db, business_id, "whatsapp")
        if conn is not None and conn.mode == "real":
            return WhatsAppMessenger(db, conn)
    return MockMessenger()


class PlatformMessenger:
    """Lead Intel's OWN WhatsApp number (settings.alerts_whatsapp_*), used for alerts to owners."""

    def send_whatsapp(self, phone: str, text: str, template_params: Optional[list[str]] = None,
                      template: Optional[str] = None) -> str:
        if not phone:
            raise SendError("No phone number")
        try:
            return meta.whatsapp_send_template(settings.alerts_whatsapp_phone_id, settings.alerts_whatsapp_token, phone,
                                               template or settings.whatsapp_alert_template,
                                               settings.whatsapp_template_language, template_params or [text])
        except IntegrationError as problem:
            raise SendError(str(problem)) from problem


def alert_messenger(db: Session, business_id: int) -> tuple[object, str]:
    """Who sends an alert to the owner's phone, and how we describe it:
    Lead Intel's own number if set up, else the business's connected WhatsApp, else practice mode."""
    if settings.alerts_whatsapp_phone_id and settings.alerts_whatsapp_token:
        return PlatformMessenger(), "lead_intel"
    messenger = get_messenger(db, business_id)
    return messenger, "practice" if isinstance(messenger, MockMessenger) else "business"
