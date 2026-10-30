"""
Connections: linking a business to its real WhatsApp / Instagram / Facebook / Google.

The "Connect" journey (Instagram, Facebook, Google):
    1. start()        the website asks us for a link → we build the platform's
                      login link with a SIGNED note ("state") saying which business
    2. (the owner approves on instagram.com / facebook.com / google.com)
    3. finish_oauth() the platform sends the owner back to /connections/{platform}/callback
                      with a CODE → we check the note, swap the code for keys,
                      lock the keys in the safe, and save the connection
WhatsApp uses Meta's popup instead (finish_whatsapp), same idea.

MOCK MODE: while a platform's app keys aren't in .env, the same journey runs
with pretend accounts, so the whole website can be built and demoed for free.

Safety rules:
  - keys are always locked (vault.lock) and never sent to the website
  - one platform account can belong to only ONE business (else messages could go to the wrong shop)
  - when a key stops working → status "needs_reconnect" + a live alert for the owner
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import vault
from app.config import settings
from app.integrations import google, instagram, linkedin, meta
from app.integrations.base import IntegrationError, NeedsReconnect
from app.models import Business, Connection, Review, SocialAccount
from app.schemas import ReviewCreate
from app.services import billing_service
from app.services.event_bus import bus

logger = logging.getLogger("connections")
OAUTH_PLATFORMS = ("instagram", "facebook", "google", "linkedin")
LABELS = {"whatsapp": "WhatsApp", "instagram": "Instagram", "facebook": "Facebook Page",
          "google": "Google Business Profile", "linkedin": "LinkedIn Company Page"}


class ConnectError(Exception):
    """Something to tell the owner, e.g. 'this Instagram is already connected to another business'."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def is_real(platform: str) -> bool:
    return {"whatsapp": settings.meta_enabled, "facebook": settings.meta_enabled,
            "instagram": settings.instagram_enabled, "google": settings.google_enabled,
            "linkedin": settings.linkedin_enabled}[platform]


def redirect_uri(platform: str) -> str:
    return f"{settings.public_api_url.rstrip('/')}/connections/{platform}/callback"


def setup_info() -> dict:
    """What the website needs to show the Connect buttons (no secrets)."""
    return {
        "platforms": {p: {"label": LABELS[p], "mode": "real" if is_real(p) else "mock"} for p in LABELS},
        "whatsapp_signup": {"app_id": settings.meta_app_id, "config_id": settings.meta_whatsapp_config_id,
                            "graph_version": settings.meta_graph_version},
    }


# ---------------------------------------------------------------------------
# Finding connections
# ---------------------------------------------------------------------------
def list_for(db: Session, business_id: int) -> list[Connection]:
    return list(db.scalars(select(Connection).where(Connection.business_id == business_id,
                                                    Connection.status != "disconnected").order_by(Connection.id)))


def active(db: Session, business_id: int, platform: str) -> Optional[Connection]:
    return db.scalar(select(Connection).where(Connection.business_id == business_id, Connection.platform == platform,
                                              Connection.status == "connected").order_by(Connection.id.desc()))


def by_external(db: Session, platform: str, external_id: Optional[str]) -> Optional[Connection]:
    """Which business owns this WhatsApp number / Instagram / Page? (for incoming webhooks)"""
    if not external_id:
        return None
    return db.scalar(select(Connection).where(Connection.platform == platform, Connection.external_id == str(external_id),
                                              Connection.status != "disconnected"))


def for_account(db: Session, account: SocialAccount) -> Optional[Connection]:
    return db.scalar(select(Connection).where(Connection.social_account_id == account.id,
                                              Connection.status != "disconnected"))


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------
def token(db: Session, conn: Connection) -> str:
    """The working key for a connection. Google's access key lasts 1 hour, so we
    quietly get a new one with the refresh key when it's about to run out."""
    if conn.platform == "google" and conn.mode == "real":
        expires = _utc(conn.token_expires_at)
        if not expires or expires < _now() + timedelta(minutes=2):
            fresh = google.refresh(vault.unlock(conn.refresh_token_locked))
            conn.access_token_locked = vault.lock(fresh["access_token"])
            conn.token_expires_at = _now() + timedelta(seconds=int(fresh.get("expires_in", 3600)))
            db.commit()
    return vault.unlock(conn.access_token_locked) or ""


def mark_problem(db: Session, conn: Connection, problem: str) -> None:
    conn.status, conn.problem = "needs_reconnect", problem[:500]
    db.commit()
    label = LABELS.get(conn.platform, conn.platform.title())
    bus.publish(conn.business_id, "connection.problem", f"{label} needs reconnecting ⚠️",
                f"{problem[:120]} Open Settings → Connections and click Connect again.",
                {"connection_id": conn.id, "platform": conn.platform})


def guarded(db: Session, conn: Connection, action, *args):
    """Run a platform call; if the key stopped working, flag the connection."""
    try:
        return action(*args)
    except NeedsReconnect as problem:
        mark_problem(db, conn, str(problem))
        raise


# ---------------------------------------------------------------------------
# Saving a connection
# ---------------------------------------------------------------------------
def _social_account(db: Session, business_id: int, platform: str, external_id: str, handle: str,
                    name: str, followers: int) -> SocialAccount:
    """The posting profile behind an Instagram / Facebook / Google connection (reused if it exists)."""
    handle = (handle or name or external_id).lstrip("@")[:100]
    account = db.scalar(select(SocialAccount).where(
        SocialAccount.business_id == business_id, SocialAccount.platform == platform,
        (SocialAccount.external_id == external_id) | (SocialAccount.handle == handle)))
    if account is None:                       # a profile typed in by hand earlier: this is the real one
        account = db.scalar(select(SocialAccount).where(SocialAccount.business_id == business_id,
                                                        SocialAccount.platform == platform,
                                                        SocialAccount.connected.is_(False)))
        if account is not None:
            account.handle = handle
    if account is None:
        billing_service.check_room(db, business_id, "social_accounts")      # plan limit
        account = SocialAccount(business_id=business_id, platform=platform, handle=handle)
        db.add(account)
    account.external_id, account.connected = external_id, True
    account.display_name = name or account.display_name
    account.followers = followers or account.followers
    db.flush()
    return account


def _save(db: Session, business_id: int, platform: str, external_id: str, display: str, mode: str,
          access: Optional[str] = None, refresh: Optional[str] = None, expires_in: Optional[int] = None,
          extra: Optional[dict] = None, handle: str = "", followers: int = 0) -> Connection:
    external_id = str(external_id)
    owner = by_external(db, platform, external_id)
    if owner and owner.business_id != business_id:
        raise ConnectError(f"This {LABELS[platform]} is already connected to another business on our platform")
    conn = owner or Connection(business_id=business_id, platform=platform, external_id=external_id)
    conn.display_name, conn.mode, conn.status, conn.problem = display[:150], mode, "connected", ""
    conn.access_token_locked = vault.lock(access) if access else conn.access_token_locked
    conn.refresh_token_locked = vault.lock(refresh) if refresh else conn.refresh_token_locked
    conn.token_expires_at = _now() + timedelta(seconds=expires_in) if expires_in else None
    conn.extra = {**(conn.extra or {}), **(extra or {})}
    conn.connected_at = _now()
    if platform in OAUTH_PLATFORMS:
        conn.social_account_id = _social_account(db, business_id, platform, external_id, handle,
                                                 display, followers).id
    db.add(conn)
    db.commit()
    return conn


# ---------------------------------------------------------------------------
# The journey
# ---------------------------------------------------------------------------
def start(business_id: int, user_id: int, platform: str) -> str:
    """The link the owner's browser should open."""
    if platform not in OAUTH_PLATFORMS:
        raise ConnectError("WhatsApp connects through Meta's popup on the website (POST /connections/whatsapp)")
    state = vault.sign_state({"b": business_id, "u": user_id, "p": platform})
    if not is_real(platform):
        # Mock: skip the platform and come straight back with a pretend code
        return f"{redirect_uri(platform)}?code=mock&state={state}"
    builder = {"instagram": instagram.login_url, "facebook": meta.pages_login_url,
               "google": google.login_url, "linkedin": linkedin.login_url}
    return builder[platform](state, redirect_uri(platform))


def finish_oauth(db: Session, platform: str, code: str, state: str) -> list[Connection]:
    try:
        note = vault.read_state(state)
    except vault.VaultError as problem:
        raise ConnectError(str(problem))
    if note.get("p") != platform:
        raise ConnectError("This connect link is for a different platform")
    business = db.get(Business, note["b"])
    if business is None:
        raise ConnectError("That business no longer exists")
    try:
        if not is_real(platform):
            return [_mock_connect(db, business, platform)]
        return {"instagram": _connect_instagram, "facebook": _connect_facebook,
                "google": _connect_google, "linkedin": _connect_linkedin}[platform](db, business, code)
    except IntegrationError as problem:
        raise ConnectError(str(problem))
    except billing_service.PlanLimit as problem:
        raise ConnectError(str(problem))


def _mock_connect(db: Session, business: Business, platform: str) -> Connection:
    existing = db.scalar(select(SocialAccount).where(SocialAccount.business_id == business.id,
                                                     SocialAccount.platform == platform))
    handle = existing.handle if existing else business.name.lower().replace(" ", "")
    display = {"instagram": f"@{handle}", "facebook": business.name,
               "google": f"{business.name}, {business.city}",
               "linkedin": business.name}[platform]
    return _save(db, business.id, platform, f"mock_{platform}_{business.id}", display, "mock",
                 access="mock-key", handle=handle, followers=existing.followers if existing else 0)


def _connect_instagram(db: Session, business: Business, code: str) -> list[Connection]:
    short = instagram.exchange_code(code, redirect_uri("instagram"))
    key, lasts = instagram.long_lived(short)
    me = instagram.profile(key)
    instagram.subscribe(key)
    return [_save(db, business.id, "instagram", me["user_id"], f"@{me.get('username', '')}", "real",
                  access=key, expires_in=lasts, handle=me.get("username", ""),
                  followers=int(me.get("followers_count") or 0), extra={"app_scoped_id": me.get("id")})]


def _connect_facebook(db: Session, business: Business, code: str) -> list[Connection]:
    user_key = meta.long_lived(meta.exchange_code(code, redirect_uri("facebook")))
    found = meta.pages(user_key)
    if not found:
        raise ConnectError("No Facebook Page was shared. Click Connect again and tick your Page.")
    saved = []
    for page in found:
        meta.subscribe_page(page["id"], page["access_token"])
        saved.append(_save(db, business.id, "facebook", page["id"], page.get("name", ""), "real",
                           access=page["access_token"], handle=page.get("username") or page.get("name", ""),
                           followers=int(page.get("followers_count") or 0)))
    return saved


def _connect_google(db: Session, business: Business, code: str) -> list[Connection]:
    keys = google.exchange_code(code, redirect_uri("google"))
    places = google.locations(keys["access_token"])
    if not places:
        raise ConnectError("No business location found on this Google account")
    return [_save(db, business.id, "google", place["name"], place["title"], "real",
                  access=keys["access_token"], refresh=keys["refresh_token"],
                  expires_in=int(keys.get("expires_in", 3600)), handle=place["title"]) for place in places[:1]]


def _connect_linkedin(db: Session, business: Business, code: str) -> list[Connection]:
    keys = linkedin.exchange_code(code, redirect_uri("linkedin"))
    token = keys["access_token"]
    member = linkedin.me(token)
    member_urn = f"urn:li:person:{member.get('id', '')}"
    pages = linkedin.company_pages(token, member_urn)
    if not pages:
        raise ConnectError("No LinkedIn Company Page was found. Make sure you are an administrator of a company page.")
    saved = []
    for page in pages[:1]:                     # connect the first page (owner can reconnect to pick another)
        saved.append(_save(db, business.id, "linkedin", page["id"], page["name"], "real",
                           access=token, expires_in=linkedin.TOKEN_SECONDS,
                           handle=page["name"], followers=page.get("followers", 0),
                           extra={"member_urn": member_urn}))
    return saved


def finish_whatsapp(db: Session, business_id: int, code: str, waba_id: str = "", phone_number_id: str = "") -> Connection:
    business = db.get(Business, business_id)
    if not is_real("whatsapp"):
        number = business.phone or f"+91 90000 0000{business_id}"
        return _save(db, business_id, "whatsapp", f"mock_whatsapp_{business_id}", number, "mock", access="mock-key")
    if not (code and waba_id and phone_number_id):
        raise ConnectError("Meta's popup didn't finish: code, waba_id and phone_number_id are all needed")
    try:
        done = meta.whatsapp_finish_signup(code, waba_id, phone_number_id)
    except IntegrationError as problem:
        raise ConnectError(str(problem))
    conn = _save(db, business_id, "whatsapp", phone_number_id, done["display"], "real", access=done["token"],
                 extra={"waba_id": waba_id, "verified_name": done["name"], "pin_locked": vault.lock(done["pin"])})
    for name, create in (("review_template", meta.whatsapp_create_review_template),      # best effort: all
                         ("alert_template", meta.whatsapp_create_alert_template),          # need Meta's approval
                         ("payment_template", meta.whatsapp_create_payment_template)):
        try:
            create(waba_id, done["token"])
            conn.extra = {**conn.extra, name: "submitted"}
        except IntegrationError as problem:
            conn.extra = {**conn.extra, name: f"not created: {str(problem)[:120]}"}
    db.commit()
    return conn


def disconnect(db: Session, conn: Connection) -> None:
    conn.status = "disconnected"
    conn.access_token_locked = conn.refresh_token_locked = None
    if conn.social_account_id:
        account = db.get(SocialAccount, conn.social_account_id)
        if account:
            account.connected = False
    db.commit()


# ---------------------------------------------------------------------------
# Background jobs: Google reviews in, keys kept fresh
# ---------------------------------------------------------------------------
def sync_google_reviews(db: Session, conn: Connection) -> int:
    """Fetch the latest Google reviews. New ones get an AI draft reply (owner approves)."""
    from app.services.reputation_service import add_review     # here: reputation also uses this module
    conn.last_synced_at = _now()
    db.commit()
    if conn.mode != "real":
        return 0
    added = 0
    for item in guarded(db, conn, google.reviews, conn.external_id, token(db, conn)):
        rating = google.STARS.get(item.get("starRating", ""), 0)
        if not rating:
            continue
        posted_reply = (item.get("reviewReply") or {}).get("comment")
        review, created = add_review(db, ReviewCreate(
            business_id=conn.business_id, platform="google", external_id=item["name"][:150],
            author_name=(item.get("reviewer") or {}).get("displayName", "")[:100], rating=rating,
            text=(item.get("comment") or "")[:5000], reviewed_at=item.get("createTime")), draft=not posted_reply)
        if created and posted_reply:                         # already answered on Google: keep that answer
            review.reply_text, review.reply_status, review.needs_attention = posted_reply, "posted", False
            db.commit()
        added += created
    return added


def sync_due(db: Session) -> int:
    """Called by the scheduler every minute; each Google connection is read every `reviews_sync_minutes`."""
    due_before = _now() - timedelta(minutes=settings.reviews_sync_minutes)
    paused = billing_service.paused_business_ids(db)
    added = 0
    for conn in db.scalars(select(Connection).where(Connection.platform == "google", Connection.status == "connected")):
        if conn.business_id in paused or (_utc(conn.last_synced_at) and _utc(conn.last_synced_at) > due_before):
            continue
        try:
            added += sync_google_reviews(db, conn)
        except IntegrationError as problem:
            logger.warning("Google reviews for business %s: %s", conn.business_id, problem)
    return added


def refresh_expiring(db: Session) -> int:
    """Instagram keys last 60 days: renew any that end within 10 days."""
    soon = _now() + timedelta(days=10)
    renewed = 0
    for conn in db.scalars(select(Connection).where(Connection.platform == "instagram", Connection.mode == "real",
                                                    Connection.status == "connected")):
        if not conn.token_expires_at or _utc(conn.token_expires_at) > soon:
            continue
        try:
            key, lasts = guarded(db, conn, instagram.refresh, token(db, conn))
        except IntegrationError as problem:
            logger.warning("Instagram key refresh for business %s: %s", conn.business_id, problem)
            continue
        conn.access_token_locked = vault.lock(key)
        conn.token_expires_at = _now() + timedelta(seconds=lasts)
        renewed += 1
    db.commit()
    return renewed
