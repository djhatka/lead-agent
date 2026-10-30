"""
Webhook endpoints - the "doorbells".

A webhook is the opposite of a normal request. Instead of US asking
WhatsApp "any new messages?" every minute, WhatsApp RINGS OUR DOORBELL
(calls our address) the moment a customer sends something.

    GET  /webhooks/meta         Meta's one-time "is this really your server?" check
    POST /webhooks/whatsapp     WhatsApp rings here with new messages
    POST /webhooks/instagram    Instagram rings here with new DMs
    POST /webhooks/website      our website's contact form posts here
    POST /webhooks/universal    ANY other platform (Justdial, Practo, Zomato,
                                Google Sheets, Zapier...) in one simple format
    POST /webhooks/calltracking  the call-tracking provider (Task 38) rings here on every
                                call event (ringing, completed, missed...)

What happens when the doorbell rings:
    1. normalizer.py translates the delivery into our standard format
    2. lead_service.receive_message() saves it (new lead / follow-up / duplicate)
    3. we immediately reply "got it" with a small summary
    4. AFTER replying, in the background: the instant AI first reply to a new
       enquiry, if the owner turned it on (Task 29), then the AI workflow
       (Task 10) analyses each new message: intake → tone → scoring → priority → save

    POST /webhooks/email        lead EMAILS (Justdial, Sulekha, Practo...) forwarded to a
                                business's lead address, passed on by an email service
    POST /webhooks/meta         THE REAL ONE: Meta delivers every connected business's
                                WhatsApp, Instagram and Facebook messages here. We check
                                Meta's signature, then find the business by the number /
                                account each message was sent TO (the connections table).

The /whatsapp, /instagram and /website doors take ?business_id=1 in the
address: handy for testing and demos, and for a website form.
"""

import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_db
from app.models import TrackingNumber
from app.routers.businesses import business_or_404
from app.platforms import PLATFORMS
from app.schemas import IncomingMessage, LeadSource, WebhookResult
from app.integrations import meta
from app.services import (auto_reply_service, calltracking_service, connection_service, email_leads, lead_pipeline,
                          lead_service, normalizer)
from app.services.event_bus import bus

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# The sample messages in seed/sample_payloads are shown pre-filled on /docs
SAMPLES = Path(__file__).resolve().parents[2] / "seed" / "sample_payloads"


def _sample(name: str) -> dict:
    try:
        return json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_all(db: Session, messages: list[IncomingMessage], notes: list[str],
              background: BackgroundTasks) -> WebhookResult:
    """Save each translated message, count what happened, and queue the AI."""
    result = WebhookResult(received=len(messages), ignored=len(notes), notes=notes)
    to_analyse: list[int] = []
    new_leads: list[int] = []
    for msg in messages:
        lead, outcome = lead_service.receive_message(db, msg)
        who = lead.name or (f"@{lead.handle}" if lead.handle and not lead.handle.isdigit() else None) \
            or lead.phone or f"a new {PLATFORMS[lead.source].name} contact"
        if outcome == "new_lead":
            result.new_leads += 1
            new_leads.append(lead.id)
            bus.publish(lead.business_id, "lead.new", f"New enquiry from {who}", msg.first_message[:140],
                        {"lead_id": lead.id, "source": lead.source})
        elif outcome == "added_to_existing":
            result.added_to_existing += 1
            bus.publish(lead.business_id, "lead.message", f"{who} sent another message", msg.first_message[:140],
                        {"lead_id": lead.id, "source": lead.source})
        else:
            result.duplicates += 1
            result.notes.append(f"message {msg.external_id} was already received - ignored the copy")
        if lead.id not in result.lead_ids:
            result.lead_ids.append(lead.id)
        if outcome != "duplicate" and lead.id not in to_analyse:
            to_analyse.append(lead.id)

    # Instant first reply (Task 29) BEFORE the AI scoring, so the customer hears back within seconds.
    # It checks the owner's choice (off / always / after hours) itself.
    for lead_id in new_leads:
        background.add_task(auto_reply_service.reply_in_background, lead_id)

    if settings.auto_analyze:
        for lead_id in to_analyse:
            # add_task = "do this AFTER sending the reply"
            background.add_task(lead_pipeline.analyze_in_background, lead_id)
        result.ai_analysis_queued = len(to_analyse)
    return result


@router.get("/meta", response_class=PlainTextResponse)
def verify_meta_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    """When you connect a webhook in Meta's dashboard, Meta first calls this
    address with a secret word (verify_token) and a random number (challenge).
    If the secret word matches WEBHOOK_VERIFY_TOKEN in our settings, we send the
    number back. That proves to Meta that this server really belongs to us."""
    if mode == "subscribe" and token == settings.webhook_verify_token:
        return challenge
    raise HTTPException(status_code=403, detail="Verify token doesn't match")


def _route_meta(db: Session, payload: dict) -> tuple[list[IncomingMessage], list[str]]:
    """Split one Meta delivery by business, using who each message was sent TO."""
    messages, notes = [], []
    kind = payload.get("object")
    for entry in payload.get("entry", []):
        if kind == "whatsapp_business_account":
            for change in entry.get("changes", []):
                number_id = change.get("value", {}).get("metadata", {}).get("phone_number_id")
                conn = connection_service.by_external(db, "whatsapp", number_id)
                if conn is None:
                    notes.append(f"WhatsApp number {number_id} isn't connected to any business")
                    continue
                found, why = normalizer.from_whatsapp({"entry": [{"changes": [change]}]}, conn.business_id)
                messages += found
                notes += why
        elif kind in ("instagram", "page"):
            platform = "instagram" if kind == "instagram" else "facebook"
            conn = connection_service.by_external(db, platform, entry.get("id"))
            if conn is None:
                notes.append(f"{platform} account {entry.get('id')} isn't connected to any business")
                continue
            found, why = normalizer.from_messenger({"entry": [entry]}, conn.business_id, source=platform)
            messages += found
            notes += why
        else:
            notes.append(f"'{kind}' deliveries aren't used")
    return messages, notes


@router.post("/meta", response_model=WebhookResult)
async def meta_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Meta's doorbell for EVERY connected business. Meta signs each delivery
    (header X-Hub-Signature-256) with our app secret; anything unsigned or
    wrongly signed is refused. (In pure mock mode, with no app secret set,
    unsigned test deliveries are allowed.)"""
    raw = await request.body()
    if (settings.meta_app_secret or settings.instagram_app_secret) and not meta.signature_ok(raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")

    def work():
        found, notes = _route_meta(db, payload)
        return _save_all(db, found, notes, background)
    return await run_in_threadpool(work)


@router.post("/email", response_model=WebhookResult)
async def email_webhook(
    request: Request,
    background: BackgroundTasks,
    key: str = Query(default="", description="Or send the X-Inbound-Key header"),
    x_inbound_key: str = Header(default=""),
    x_envelope_to: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """An email service (Cloudflare Email Routing, Mailgun, Postmark, SendGrid...) passes
    every email sent to leads-<secret>@in.yourdomain.in here. Accepts the raw email
    (Content-Type: message/rfc822), JSON, or a form post. Protected by INBOUND_EMAIL_SECRET."""
    import hmac
    given = x_inbound_key or key
    if not given or not hmac.compare_digest(given, settings.inbound_email_secret):
        raise HTTPException(status_code=401, detail="Wrong or missing inbound key")
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind in ("application/json",):
        parsed = email_leads.from_fields(await request.json())
    elif kind in ("multipart/form-data", "application/x-www-form-urlencoded"):
        form = await request.form()
        parsed = email_leads.from_fields({k: v for k, v in form.items() if isinstance(v, str)})
    else:                                                           # the raw email itself
        raw = await request.body()
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Email too large")
        parsed = email_leads.from_raw(raw, envelope_to=x_envelope_to)

    def work():
        log, incoming = email_leads.handle(db, parsed)
        if log is None:
            return WebhookResult(received=1, ignored=1, notes=["Not addressed to any business's lead address"])
        if incoming is None:
            return WebhookResult(received=1, ignored=1, notes=[f"{log.status}: {log.note}"])
        result = _save_all(db, [incoming], [], background)
        log.lead_id = result.lead_ids[0] if result.lead_ids else None
        log.status = "lead" if result.new_leads else "added" if result.added_to_existing else "duplicate"
        db.commit()
        return result
    return await run_in_threadpool(work)


@router.post("/whatsapp", response_model=WebhookResult)
def whatsapp_webhook(
    background: BackgroundTasks,
    business_id: int = Query(description="Which business received this (mock only)"),
    payload: dict = Body(examples=[_sample("whatsapp_message.json")]),
    db: Session = Depends(get_db),
):
    """Receives WhatsApp messages in the real WhatsApp Cloud API format."""
    business_or_404(business_id, db)
    messages, notes = normalizer.from_whatsapp(payload, business_id)
    return _save_all(db, messages, notes, background)


@router.post("/instagram", response_model=WebhookResult)
def instagram_webhook(
    background: BackgroundTasks,
    business_id: int = Query(description="Which business received this (mock only)"),
    payload: dict = Body(examples=[_sample("instagram_dm.json")]),
    db: Session = Depends(get_db),
):
    """Receives Instagram DMs in the real Instagram Messaging API format."""
    business_or_404(business_id, db)
    messages, notes = normalizer.from_instagram(payload, business_id)
    return _save_all(db, messages, notes, background)


@router.post("/website", response_model=WebhookResult)
def website_webhook(
    background: BackgroundTasks,
    business_id: int = Query(description="Which business's website form this is"),
    payload: dict = Body(examples=[_sample("website_form.json")]),
    db: Session = Depends(get_db),
):
    """Receives a contact form submitted on the business's website."""
    business_or_404(business_id, db)
    messages, notes = normalizer.from_website(payload, business_id)
    return _save_all(db, messages, notes, background)


@router.post("/universal", response_model=WebhookResult)
def universal_webhook(
    background: BackgroundTasks,
    business_id: int = Query(description="Which business this lead is for"),
    platform: LeadSource = Query(description="Where the lead came from, e.g. justdial, practo, zomato"),
    payload: dict = Body(examples=[_sample("universal_lead.json")]),
    db: Session = Depends(get_db),
):
    """The universal door: a lead from ANY platform in our simple format.

    Use it for platforms without their own doorbell: Justdial, Sulekha,
    Practo, Zomato, IndiaMART, 99acres, UrbanPro... or from tools like
    Zapier, Make, or a Google Sheet. The list of platforms is in /platforms.
    """
    business_or_404(business_id, db)
    messages, notes = normalizer.from_simple_form(payload, business_id, source=platform)
    result = _save_all(db, messages, notes, background)
    if PLATFORMS[platform].connection == "api" and platform != "website":
        result.notes.append(f"Tip: {PLATFORMS[platform].name} has its own doorbell; the universal one works too.")
    return result


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


@router.post("/calltracking")
async def calltracking_webhook(request: Request, db: Session = Depends(get_db)):
    """The call-tracking provider (Task 38) rings here on every call event: ringing,
    then completed / missed / failed. Field names vary by provider, so this reads the
    usual aliases for each one (CallSid/call_sid, From/CallFrom, To/CallTo,
    Status/CallStatus/DialCallStatus, Duration/CallDuration/DialCallDuration,
    RecordingUrl, Transcript), as form-encoded (most providers) or JSON."""
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind == "application/json":
        raw = await request.json()
    else:
        form = await request.form()
        raw = {k: v for k, v in form.items() if isinstance(v, str)}

    def field(*keys: str) -> str:
        return next((str(raw[k]) for k in keys if raw.get(k)), "")

    def work():
        to = _digits(field("To", "CallTo", "to", "call_to"))
        if not to:
            raise HTTPException(status_code=400, detail="No 'To' number in the payload")
        # Match on the last 10 digits, ignoring spaces/formatting/country code: a plain SQL
        # LIKE on the stored number would miss when it's formatted with a space in the middle.
        tn = next((t for t in db.scalars(select(TrackingNumber)) if _digits(t.number)[-10:] == to[-10:]), None)
        if tn is None:
            return {"ignored": True, "note": f"No business is using a tracking number ending {to[-10:]}"}
        business = business_or_404(tn.business_id, db)
        duration = field("Duration", "CallDuration", "DialCallDuration", "duration")
        call = calltracking_service.record_call(
            db, business, external_id=field("CallSid", "call_sid", "CallSID", "Sid") or secrets.token_hex(8),
            from_number=field("From", "CallFrom", "from", "call_from"),
            provider_status=field("Status", "CallStatus", "DialCallStatus", "status"),
            duration_seconds=int(duration) if duration.isdigit() else 0,
            recording_url=field("RecordingUrl", "recording_url"), transcript=field("Transcript", "transcript"))
        return {"call_id": call.id, "status": call.status}
    return await run_in_threadpool(work)
