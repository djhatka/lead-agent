"""
Checks for the live feed (Task 18).
"""

import asyncio
import json

import pytest

from app.services.event_bus import EventBus, bus


def events_from(stream_text: str) -> list[dict]:
    """Read the 'data:' lines out of a Server-Sent Events stream."""
    return [json.loads(line[6:]) for line in stream_text.splitlines() if line.startswith("data: ")]


# ----- The bus itself ----------------------------------------------------------------------------
def test_each_business_has_its_own_channel():
    b = EventBus()
    b.publish(1, "test", "for gym")
    b.publish(2, "test", "for garage")
    assert [e["title"] for e in b.recent(1)] == ["for gym"]
    assert [e["title"] for e in b.recent(2)] == ["for garage"]


def test_ids_go_up_and_recent_resumes():
    b = EventBus()
    first = b.publish(1, "test", "a")
    b.publish(1, "test", "b")
    b.publish(1, "test", "c")
    assert [e["title"] for e in b.recent(1, after_id=first["id"])] == ["b", "c"]


def test_memory_is_limited():
    b = EventBus(keep=3)
    for i in range(10):
        b.publish(1, "test", str(i))
    assert [e["title"] for e in b.recent(1)] == ["7", "8", "9"]


def test_listeners_receive_events():
    b = EventBus()

    async def listen():
        queue = b.subscribe(1)
        b.publish(1, "lead.hot", "🔥")
        b.publish(2, "lead.hot", "not for business 1")
        event = await asyncio.wait_for(queue.get(), timeout=1)
        b.unsubscribe(1, queue)
        return event, queue.empty()
    event, nothing_else = asyncio.run(listen())
    assert event["title"] == "🔥" and nothing_else
    assert b.listeners(1) == 0


def test_publish_never_raises():
    b = EventBus()
    assert b.publish(1, "test", "x", data={"bad": object()}) is not None    # weird data is fine in memory


# ----- Events from real actions ----------------------------------------------------------------------
def types_for(business_id: int, after: int) -> list[str]:
    return [e["type"] for e in bus.recent(business_id, after)]


def last_id(business_id: int) -> int:
    events = bus.recent(business_id)
    return events[-1]["id"] if events else 0


def test_new_hot_lead_events(client):
    start = last_id(2)
    client.post("/leads", json={"business_id": 2, "source": "referral", "name": "Rahul", "phone": "9811055001",
                                "first_message": "Need ceramic coating today, can I book a slot?"})
    got = types_for(2, start)
    assert got[0] == "lead.new" and "lead.analyzed" in got and "lead.hot" in got
    hot = next(e for e in bus.recent(2, start) if e["type"] == "lead.hot")
    assert "Rahul" in hot["message"] and hot["data"]["score"] >= 70


def test_whatsapp_followup_event(client):
    import tests.test_webhooks as w
    start = last_id(1)
    client.post("/webhooks/whatsapp", params={"business_id": 1}, json=w.whatsapp_payload("wamid.L1", "Hi", "919811000101"))
    client.post("/webhooks/whatsapp", params={"business_id": 1}, json=w.whatsapp_payload("wamid.L2", "Hello?", "919811000101"))
    got = types_for(1, start)
    assert "lead.new" in got and "lead.message" in got


def test_unhappy_review_event(client):
    start = last_id(3)
    client.post("/reviews", json={"business_id": 3, "rating": 1, "author_name": "Deepak", "text": "Rude staff"})
    assert "review.unhappy" in types_for(3, start)


def test_published_post_and_report_events(client, db_session):
    from app.models import Post
    start = last_id(1)
    draft = db_session.query(Post).filter(Post.business_id == 1, Post.caption != "",
                                          Post.status.in_(["draft", "scheduled"])).first()
    client.post(f"/posts/{draft.id}/publish-now")
    client.post("/growth/review", params={"business_id": 1})
    got = types_for(1, start)
    assert "post.published" in got and "report.ready" in got


# ----- Endpoints -------------------------------------------------------------------------------------------
def test_stream_replays_missed_events(client):
    first = client.post("/live/test", params={"business_id": 2}).json()
    client.post("/live/test", params={"business_id": 2})
    with client.stream("GET", "/live/stream", params={"business_id": 2, "limit": 2},
                       headers={"Last-Event-ID": str(first["id"] - 1)}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())
    received = events_from(text)
    assert [e["id"] for e in received] == [first["id"], first["id"] + 1]
    assert "retry: 3000" in text


def test_recent_and_types_endpoints(client):
    event = client.post("/live/test", params={"business_id": 1}).json()
    recent = client.get("/live/recent", params={"business_id": 1, "after_id": event["id"] - 1}).json()
    assert recent[0]["id"] == event["id"]
    assert "lead.hot" in client.get("/live/types").json()


def test_stream_unknown_business(client):
    assert client.get("/live/stream", params={"business_id": 999}).status_code == 404
