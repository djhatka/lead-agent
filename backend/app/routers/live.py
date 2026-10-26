"""
Live feed endpoints.

    GET  /live/stream?business_id=1    stay connected and receive events the moment they happen (SSE)
    GET  /live/recent?business_id=1    the last events as a normal list (for page load / older browsers)
    POST /live/test?business_id=1      send a test event (handy while building the dashboard)
    GET  /live/types                   every kind of event and what it means

How the dashboard uses it (JavaScript, built into every browser):

    const feed = new EventSource("http://127.0.0.1:8000/live/stream?business_id=1");
    feed.addEventListener("lead.hot", (e) => showAlert(JSON.parse(e.data)));

If the connection drops, the browser reconnects by itself and tells us the
last event id it got (the "Last-Event-ID" header), so nothing is missed.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.businesses import business_or_404
from app.services.event_bus import EVENT_TYPES, bus

router = APIRouter(prefix="/live", tags=["Live feed"])
HEARTBEAT_SECONDS = 15


def _sse(event: dict) -> str:
    """One event in the Server-Sent Events text format."""
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/stream")
async def stream(
    request: Request,
    business_id: int,
    after_id: int = Query(default=0, ge=0, description="Also send stored events newer than this id"),
    limit: Optional[int] = Query(default=None, ge=1, description="Close after this many events (for testing)"),
    last_event_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    business_or_404(business_id, db)          # the stream itself never touches the database

    resume_from = int(last_event_id) if last_event_id and last_event_id.isdigit() else after_id
    queue = bus.subscribe(business_id)

    async def events():
        sent = 0
        try:
            yield "retry: 3000\n\n"                           # "if we disconnect, retry after 3 seconds"
            for event in bus.recent(business_id, resume_from):  # anything missed while disconnected
                yield _sse(event)
                sent += 1
                if limit and sent >= limit:
                    return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": still here\n\n"                   # heartbeat keeps the connection alive
                    continue
                yield _sse(event)
                sent += 1
                if limit and sent >= limit:
                    return
        finally:
            bus.unsubscribe(business_id, queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/recent")
def recent(business_id: int, after_id: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return bus.recent(business_id, after_id)


@router.post("/test")
def test_event(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return bus.publish(business_id, "test", "👋 Test event", "If you can see this, the live feed works!")


@router.get("/types")
def types():
    return EVENT_TYPES
