"""
The normalizer - a translator.

WhatsApp, Instagram and our website each describe a customer message in a
completely different shape. This file translates all of them into ONE shape
(IncomingMessage), so everything after this point only has to understand
one format.

    WhatsApp:   {"entry":[{"changes":[{"value":{"messages":[{"from":"91981...", "text":{"body":"Hi"}}]}}]}]}
    Instagram:  {"entry":[{"messaging":[{"sender":{"id":"1784..."}, "message":{"text":"Hi"}}]}]}
    Website and every other platform (universal format):
                {"name":"Priya", "phone":"98110...", "message":"Hi"}
                                  │
                                  ▼
    IncomingMessage(source="whatsapp", phone="+91981...", first_message="Hi", ...)

The WhatsApp and Instagram shapes below copy Meta's REAL webhook format.
So when we connect the real APIs later, only the "doorbell" changes;
this translator and everything after it stays the same.

Each function returns two lists:
    messages - the customer messages it understood
    notes    - plain-English reasons for anything it skipped
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.schemas import IncomingMessage


def _from_unix(seconds: Optional[float]) -> Optional[datetime]:
    """Platforms send time as 'seconds since 1 Jan 1970' (Unix time)."""
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _build(notes: list[str], label: str, **fields) -> Optional[IncomingMessage]:
    """Run the translated message through our rules (Task 3).
    If it breaks a rule, skip it and write down why, instead of crashing."""
    try:
        return IncomingMessage(**fields)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'message'}: {e['msg']}" for e in error.errors())
        notes.append(f"{label} skipped - {problems}")
        return None


# ---------------------------------------------------------------------------
# WhatsApp (WhatsApp Business Cloud API format)
# ---------------------------------------------------------------------------
def _whatsapp_text(message: dict) -> str:
    """WhatsApp messages can be text, photos, voice notes, button taps...
    We turn each into readable text."""
    kind = message.get("type", "text")
    if kind == "text":
        return message.get("text", {}).get("body", "")
    if kind in ("image", "video", "document"):
        caption = message.get(kind, {}).get("caption")
        return caption or f"[{kind}]"
    if kind == "button":
        return message.get("button", {}).get("text", "[button]")
    if kind == "interactive":
        reply = message.get("interactive", {})
        chosen = reply.get("button_reply") or reply.get("list_reply") or {}
        return chosen.get("title", "[interactive reply]")
    return f"[{kind} message]"            # audio, sticker, location...


def from_whatsapp(payload: dict, business_id: int) -> tuple[list[IncomingMessage], list[str]]:
    messages, notes = [], []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # WhatsApp sends the customer's profile name in a separate list
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}

            if value.get("statuses") and not value.get("messages"):
                notes.append("delivery/read receipt ignored (not a customer message)")

            for m in value.get("messages", []):
                sender = m.get("from", "")
                msg = _build(
                    notes, f"WhatsApp message {m.get('id', '?')}",
                    business_id=business_id, source="whatsapp",
                    external_id=m.get("id"),
                    # WhatsApp numbers are always international, e.g. 919811000000
                    phone=f"+{sender}" if sender else None,
                    name=names.get(sender),
                    first_message=_whatsapp_text(m),
                    sent_at=_from_unix(m.get("timestamp")),
                )
                if msg:
                    messages.append(msg)
    return messages, notes


# ---------------------------------------------------------------------------
# Instagram (Instagram Messaging API format)
# ---------------------------------------------------------------------------
def from_instagram(payload: dict, business_id: int) -> tuple[list[IncomingMessage], list[str]]:
    return from_messenger(payload, business_id, source="instagram")


def from_messenger(payload: dict, business_id: int, source: str = "instagram") -> tuple[list[IncomingMessage], list[str]]:
    """Instagram DMs and Facebook Messenger use the same shape ("messaging" events)."""
    label = "Instagram" if source == "instagram" else "Facebook"
    messages, notes = [], []
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message")
            if not message:
                notes.append(f"{label} event ignored (seen/reaction, not a message)")
                continue
            if message.get("is_echo"):
                # "echo" = a copy of a message the BUSINESS sent. Not a customer.
                notes.append(f"{label} echo ignored (message sent by the business itself)")
                continue
            text = message.get("text") or ("[photo/attachment]" if message.get("attachments") else "")
            msg = _build(
                notes, f"{label} message {message.get('mid', '?')}",
                business_id=business_id, source=source,
                external_id=message.get("mid"),
                # Instagram only gives a private sender ID, not the username.
                # (The real API can look up the username later.)
                handle=event.get("sender", {}).get("id"),
                first_message=text,
                sent_at=_from_unix((event.get("timestamp") or 0) / 1000 or None),  # Instagram uses milliseconds
            )
            if msg:
                messages.append(msg)
    return messages, notes


# ---------------------------------------------------------------------------
# Simple flat format - used by our website form AND the universal door
# ---------------------------------------------------------------------------
def from_simple_form(payload: dict, business_id: int, source: str) -> tuple[list[IncomingMessage], list[str]]:
    """One flat, easy format that ANY platform or tool can send:

        {"name": "...", "phone": "...", "message": "...", "service": "...",
         "email": "...", "area": "...", "external_id": "...",
         "utm_source": "...", "utm_campaign": "...", "page": "..."}

    Only a name, phone or handle is required. Everything else is optional.
    Works for website forms, Justdial/Practo/Zomato leads, Google Sheets,
    Zapier/Make automations, or anything else that can send a web request.
    UTM fields tell us which ad or post sent the visitor, so we keep them.
    """
    notes: list[str] = []
    details = {k: payload[k] for k in ("email", "utm_source", "page") if payload.get(k)}
    msg = _build(
        notes, f"{source} lead",
        business_id=business_id, source=source,
        external_id=str(payload.get("external_id") or payload.get("submission_id") or uuid.uuid4()),
        name=payload.get("name"),
        phone=payload.get("phone"),
        handle=payload.get("handle"),
        service=payload.get("service"),
        area=payload.get("area"),
        campaign=payload.get("utm_campaign") or payload.get("campaign"),
        details=details,
        first_message=payload.get("message") or f"Enquiry about {payload.get('service') or 'your services'}",
        sent_at=payload.get("sent_at"),
    )
    return ([msg] if msg else []), notes


def from_website(payload: dict, business_id: int) -> tuple[list[IncomingMessage], list[str]]:
    """Our website's contact form uses the simple format."""
    return from_simple_form(payload, business_id, source="website")
