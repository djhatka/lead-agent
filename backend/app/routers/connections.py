"""
Connections: "Connect your WhatsApp / Instagram / Facebook / Google".

    GET    /connections                    what's connected for my business (never the keys)
    GET    /connections/setup              which platforms are real or mock + what Meta's popup needs
    POST   /connections/{platform}/start   instagram / facebook / google → {"url"}: open it in the browser
    GET    /connections/{platform}/callback   the platform sends the owner back here (no login needed:
                                           the signed "state" says which business) → back to the website
    POST   /connections/whatsapp           finish Meta's WhatsApp popup {code, waba_id, phone_number_id}
    POST   /connections/{id}/sync          fetch Google reviews now
    DELETE /connections/{id}               disconnect (keys are deleted)

In mock mode (no app keys in .env) every Connect works instantly with a pretend account.
"""

from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import can_access, get_current_user, require_owner
from app.config import settings
from app.database import get_db
from app.integrations.base import IntegrationError
from app.models import Connection, User
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import connection_service as connections

public = APIRouter(tags=["Connections"])
router = APIRouter(tags=["Connections"])


class ConnectionOut(BaseModel):
    id: int
    business_id: int
    platform: str
    label: str
    display_name: str
    external_id: str
    mode: str
    status: str
    problem: str
    social_account_id: Optional[int]
    connected_at: UTCDateTime
    last_synced_at: Optional[UTCDateTime]
    token_expires_at: Optional[UTCDateTime]
    details: dict


def _out(conn: Connection) -> ConnectionOut:
    safe = {k: v for k, v in (conn.extra or {}).items() if not k.endswith("_locked")}   # never any key
    return ConnectionOut(id=conn.id, business_id=conn.business_id, platform=conn.platform,
                         label=connections.LABELS[conn.platform], display_name=conn.display_name,
                         external_id=conn.external_id, mode=conn.mode, status=conn.status, problem=conn.problem,
                         social_account_id=conn.social_account_id, connected_at=conn.connected_at,
                         last_synced_at=conn.last_synced_at, token_expires_at=conn.token_expires_at, details=safe)


def _business_id(user: User, business_id: Optional[int], db: Session) -> int:
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_or_404(business_id, db).id
    return user.business_id


def _connection_or_404(connection_id: int, db: Session) -> Connection:
    conn = db.get(Connection, connection_id)
    if conn is None or not can_access(conn.business_id) or conn.status == "disconnected":
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    return conn


def _back_to_website(**params) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_origin}/settings/connections?{urlencode(params)}", status_code=302)


# ---------------------------------------------------------------------------
# The platform sends the owner back here (a plain browser visit, no login header)
# ---------------------------------------------------------------------------
@public.get("/connections/{platform}/callback", include_in_schema=False)
def callback(platform: str, state: str = "", code: str = "", error: str = "", error_description: str = "",
             db: Session = Depends(get_db)):
    if platform not in connections.OAUTH_PLATFORMS:
        return _back_to_website(error="Unknown platform")
    if error or not code:
        reason = error_description or ("You cancelled the connection" if error else "No code came back")
        return _back_to_website(platform=platform, error=reason)
    try:
        saved = connections.finish_oauth(db, platform, code, state)
    except connections.ConnectError as problem:
        return _back_to_website(platform=platform, error=str(problem))
    return _back_to_website(platform=platform, connected=", ".join(c.display_name for c in saved))


# ---------------------------------------------------------------------------
# Logged in
# ---------------------------------------------------------------------------
@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(business_id: Optional[int] = None, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return [_out(c) for c in connections.list_for(db, _business_id(user, business_id, db))]


@router.get("/connections/setup")
def setup():
    return connections.setup_info()


class StartOut(BaseModel):
    url: str
    mode: str


@router.post("/connections/{platform}/start", response_model=StartOut)
def start(platform: Literal["instagram", "facebook", "google", "linkedin"], business_id: Optional[int] = None,
          owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Then: window.location = url. The owner approves on the platform and comes back."""
    bid = _business_id(owner, business_id, db)
    return StartOut(url=connections.start(bid, owner.id, platform),
                    mode="real" if connections.is_real(platform) else "mock")


class WhatsAppIn(BaseModel):
    code: str = Field(default="", max_length=1000, description="From Meta's popup (FB.login response). 'mock' in mock mode")
    waba_id: str = Field(default="", max_length=50)
    phone_number_id: str = Field(default="", max_length=50)


@router.post("/connections/whatsapp", response_model=ConnectionOut, status_code=201)
def connect_whatsapp(body: WhatsAppIn, business_id: Optional[int] = None, owner: User = Depends(require_owner),
                     db: Session = Depends(get_db)):
    try:
        conn = connections.finish_whatsapp(db, _business_id(owner, business_id, db), body.code,
                                           body.waba_id, body.phone_number_id)
    except connections.ConnectError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    return _out(conn)


class SyncOut(BaseModel):
    new_reviews: int
    synced_at: Optional[datetime]


@router.post("/connections/{connection_id}/sync", response_model=SyncOut)
def sync(connection_id: int, db: Session = Depends(get_db)):
    conn = _connection_or_404(connection_id, db)
    if conn.platform != "google":
        raise HTTPException(status_code=400, detail="Only Google reviews are fetched; messages arrive by themselves")
    try:
        added = connections.sync_google_reviews(db, conn)
    except IntegrationError as problem:
        raise HTTPException(status_code=502, detail=str(problem))
    return SyncOut(new_reviews=added, synced_at=conn.last_synced_at)


@router.delete("/connections/{connection_id}", status_code=204)
def disconnect(connection_id: int, _owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    connections.disconnect(db, _connection_or_404(connection_id, db))
