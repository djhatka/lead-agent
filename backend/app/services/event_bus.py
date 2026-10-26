"""
Event bus - the radio station for live updates.

Anywhere in the backend, something interesting happens ("new lead!",
"post published", "unhappy review") and we call:

    bus.publish(business_id, "lead.hot", "🔥 Hot lead", "Reply to Rahul now...", {"lead_id": 12})

Every dashboard that is "tuned in" to that business (GET /live/stream)
receives it instantly. Each business has its own channel, so Redox Gym
never hears Gloss Garage's news.

Details worth knowing:
  - Events get an increasing id. If a phone loses signal for a moment, the
    browser reconnects saying "the last one I got was 41", and we re-send
    42, 43... from a small memory of recent events (the last 100 per business).
  - publish() is often called from background threads (AI jobs, the
    scheduler). call_soon_threadsafe safely hands the event to the
    server's main loop, which delivers it to the open connections.
  - publish() never raises: a broken live feed must never break saving a lead.
"""

import asyncio
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("event_bus")

# Every kind of event the dashboard can receive
EVENT_TYPES = {
    "lead.new": "A new enquiry arrived",
    "lead.message": "A customer sent a follow-up message",
    "lead.analyzed": "The AI scored a lead",
    "lead.hot": "A hot lead: reply now",
    "lead.auto_reply": "The AI sent the instant first reply to a new enquiry",
    "followup.due": "The daily note: enquiries that need a follow-up today",
    "payment.received": "A customer's payment was marked as received",
    "payment.claimed": "A customer pressed \"I've paid\" on their payment page: check and confirm",
    "post.published": "A scheduled post went live",
    "post.failed": "A post failed to publish",
    "review.new": "A new review arrived",
    "review.unhappy": "An unhappy review needs a reply",
    "report.ready": "The weekly growth review is ready",
    "billing.paid": "A subscription payment was received",
    "billing.problem": "A subscription payment failed",
    "email.confirm": "Gmail sent a forwarding confirmation code (Settings → Leads from email)",
    "connection.problem": "A connected account (WhatsApp/Instagram/Facebook/Google) needs reconnecting",
    "renewal.due": "Renewals are coming up: memberships or services expiring soon",
    "competitor.moved": "A watched competitor's rating or reviews moved",
    "booking.confirmed": "A customer picked a time slot for their booking",
    "test": "A test event",
}


def _put(queue: asyncio.Queue, event: dict) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:          # a very slow listener: skip rather than block everyone
        logger.warning("Live listener too slow, dropped event %s", event["id"])


class EventBus:
    def __init__(self, keep: int = 100):
        self._lock = threading.Lock()
        self._next_id = 1
        self._recent: dict[int, deque] = defaultdict(lambda: deque(maxlen=keep))
        self._listeners: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self.loop: Optional[asyncio.AbstractEventLoop] = None     # set when the server starts

    def publish(self, business_id: int, type: str, title: str, message: str = "", data: Optional[dict] = None) -> Optional[dict]:
        try:
            with self._lock:
                event = {"id": self._next_id, "type": type, "business_id": business_id,
                         "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                         "title": title, "message": message, "data": data or {}}
                self._next_id += 1
                self._recent[business_id].append(event)
                listeners = list(self._listeners[business_id])
            for queue in listeners:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(_put, queue, event)
                else:
                    _put(queue, event)
            return event
        except Exception:  # noqa: BLE001 - never let the live feed break the real work
            logger.exception("Could not publish live event")
            return None

    def recent(self, business_id: int, after_id: int = 0) -> list[dict]:
        with self._lock:
            return [e for e in self._recent[business_id] if e["id"] > after_id]

    def subscribe(self, business_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._listeners[business_id].add(queue)
        return queue

    def unsubscribe(self, business_id: int, queue: asyncio.Queue) -> None:
        with self._lock:
            self._listeners[business_id].discard(queue)

    def listeners(self, business_id: int) -> int:
        with self._lock:
            return len(self._listeners[business_id])


bus = EventBus()
