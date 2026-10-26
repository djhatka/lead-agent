"""
Alerts to the owner's own phone (Task 28): "🔥 New hot lead: call Rahul now".

When the AI marks an enquiry HOT, the owner gets a WhatsApp message within
seconds, so they can call while the customer is still interested.

    queue_hot_lead     called by the lead workflow when a lead turns hot
    send               tries to send one alert (practice mode, the business's
                       WhatsApp, or Lead Intel's own number: messenger.alert_messenger)
    send_due           scheduler job: retries failed sends, and sends alerts held
                       during quiet hours once it's 8am
    settings_for / update_settings / send_test   the Settings card on the dashboard

Rules:
    - one alert per lead, ever (no repeats if the AI re-scores it)
    - nothing is sent if alerts are off, there's no phone, or the plan has ended
    - quiet hours (optional, 10pm-8am India time): alerts wait until 8am
    - 3 tries at most, then "failed" with the reason shown in Settings
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Business, Lead, OwnerAlert
from app.platforms import PLATFORMS
from app.services import billing_service
from app.services.messenger import SendError, alert_messenger

logger = logging.getLogger("alerts")
IST = ZoneInfo("Asia/Kolkata")
QUIET_FROM, QUIET_UNTIL = 22, 8          # 10pm to 8am India time
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=2)
GIVE_UP_AFTER = timedelta(hours=12)      # an alert older than this is no use any more
DEFAULTS = {"hot_leads": True, "quiet_hours": False}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def settings_for(business: Business) -> dict:
    return {**DEFAULTS, **(business.alert_settings or {})}


def quiet_now(business: Business, now: datetime) -> bool:
    hour = now.astimezone(IST).hour
    return settings_for(business)["quiet_hours"] and (hour >= QUIET_FROM or hour < QUIET_UNTIL)


def lead_link(lead_id: int) -> str:
    from app.services.email_service import link
    return link(f"/leads/{lead_id}")


def describe(lead: Lead, score: Optional[int]) -> str:
    """'Rahul (WhatsApp) wants CrossFit, score 82' (the middle of the alert)."""
    who = lead.name or lead.phone or (f"@{lead.handle}" if lead.handle else "A new customer")
    where = PLATFORMS[lead.source].name if lead.source in PLATFORMS else lead.source
    wants = f" wants {lead.service}" if lead.service else " sent an enquiry"
    return f"{who} ({where}){wants}" + (f", score {score}" if score is not None else "")


def make_alert(business: Business, kind: str, lead_id: Optional[int], middle: str) -> OwnerAlert:
    """The WhatsApp template has 3 blanks: business name, what happened, link. Keep them with the alert."""
    from app.services.email_service import link
    params = [business.name, middle, lead_link(lead_id) if lead_id else link("/")]
    text = f"🔥 New hot lead for {params[0]}: {params[1]}. Reply quickly to win it: {params[2]}"
    return OwnerAlert(business_id=business.id, kind=kind, lead_id=lead_id, phone=business.alert_phone or "",
                      text=text, params=params)


# ---------------------------------------------------------------------------
# Making and sending alerts
# ---------------------------------------------------------------------------
def queue_hot_lead(db: Session, lead: Lead, score: Optional[int] = None,
                   now: Optional[datetime] = None) -> Optional[OwnerAlert]:
    """The lead workflow found a hot lead: alert the owner (once per lead). Sends right away
    unless it's quiet hours. Never raises: a failed alert must never break saving a lead."""
    try:
        business = db.get(Business, lead.business_id)
        if not settings_for(business)["hot_leads"] or not business.alert_phone:
            return None                                # alerts off, or no phone to send to yet
        now = now or _now()
        alert = make_alert(business, "hot_lead", lead.id, describe(lead, score))
        alert.created_at = now
        db.add(alert)
        try:
            db.commit()
        except IntegrityError:                         # already alerted about this lead
            db.rollback()
            return None
        if not quiet_now(business, now):
            send(db, alert, now)
        return alert
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Couldn't make the hot-lead alert for lead %s", lead.id)
        return None


def send(db: Session, alert: OwnerAlert, now: Optional[datetime] = None) -> bool:
    now = now or _now()
    business = db.get(Business, alert.business_id)
    alert.phone = business.alert_phone or ""
    if not alert.phone:
        alert.status, alert.error = "skipped", "No alert phone number in Settings"
    elif alert.kind != "test" and alert.business_id in billing_service.paused_business_ids(db):
        alert.status, alert.error = "skipped", "Plan ended"
    else:
        messenger, sent_by = alert_messenger(db, business.id)
        alert.attempts += 1
        try:
            messenger.send_whatsapp(alert.phone, alert.text, template_params=alert.params, template=_alert_template())
            alert.status, alert.sent_at, alert.sent_by, alert.error = "sent", now, sent_by, ""
        except SendError as problem:
            alert.error = str(problem)[:300]
            alert.status = "failed" if alert.attempts >= MAX_ATTEMPTS else "pending"
            logger.warning("Alert %s not sent (try %s): %s", alert.id, alert.attempts, problem)
    db.commit()
    return alert.status == "sent"


def _alert_template() -> str:
    from app.config import settings
    return settings.whatsapp_alert_template


def send_due(db: Session, now: Optional[datetime] = None) -> int:
    """Scheduler job: send alerts that are waiting (quiet hours over, or a retry is due)."""
    now = now or _now()
    sent = 0
    for alert in db.scalars(select(OwnerAlert).where(OwnerAlert.status == "pending")):
        business = db.get(Business, alert.business_id)
        if _utc(alert.created_at) < now - GIVE_UP_AFTER:
            alert.status, alert.error = "skipped", "Too old to be useful"
            db.commit()
            continue
        if business is None or quiet_now(business, now):
            continue
        if alert.attempts and _utc(alert.created_at) + RETRY_AFTER * alert.attempts > now:
            continue                                   # wait a little longer between tries
        sent += send(db, alert, now)
    return sent


# ---------------------------------------------------------------------------
# The Settings card
# ---------------------------------------------------------------------------
def update_settings(db: Session, business: Business, phone: Optional[str], hot_leads: Optional[bool],
                    quiet_hours: Optional[bool], phone_given: bool) -> Business:
    if phone_given:
        business.alert_phone = phone
    choices = settings_for(business)
    if hot_leads is not None:
        choices["hot_leads"] = hot_leads
    if quiet_hours is not None:
        choices["quiet_hours"] = quiet_hours
    business.alert_settings = choices
    db.commit()
    return business


def send_test(db: Session, business: Business) -> OwnerAlert:
    alert = make_alert(business, "test", None, "this is a test. Real alerts show the customer, what they want "
                                               "and their score")
    db.add(alert)
    db.commit()
    send(db, alert)
    return alert


def recent(db: Session, business_id: int, limit: int = 20) -> list[OwnerAlert]:
    return list(db.scalars(select(OwnerAlert).where(OwnerAlert.business_id == business_id)
                           .order_by(OwnerAlert.id.desc()).limit(limit)))
