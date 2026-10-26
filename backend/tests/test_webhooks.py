"""
Checks for the webhook "doorbells" (Task 6).

Uses the same sample messages you see on the /docs page
(seed/sample_payloads/*.json), so the examples are tested too.
"""

import copy
import json
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / "seed" / "sample_payloads"


def sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def whatsapp_payload(message_id: str, text: str, phone: str = "919811055555", kind: str = "text") -> dict:
    """The sample WhatsApp delivery, with a different message ID/text."""
    payload = sample("whatsapp_message.json")
    value = payload["entry"][0]["changes"][0]["value"]
    value["contacts"][0]["wa_id"] = phone
    msg = value["messages"][0]
    msg.update({"id": message_id, "from": phone, "type": kind})
    if kind == "text":
        msg["text"] = {"body": text}
    else:
        msg.pop("text", None)
        msg[kind] = {"caption": text} if text else {}
    return payload


# ----- Meta's verification handshake ---------------------------------------------------
def test_meta_verification_with_right_token(client):
    r = client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "change-me", "hub.challenge": "12345"})
    assert r.status_code == 200 and r.text == "12345"


def test_meta_verification_with_wrong_token(client):
    r = client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"})
    assert r.status_code == 403


# ----- WhatsApp ----------------------------------------------------------------------------
def test_whatsapp_message_creates_lead(client):
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json"))
    assert r.status_code == 200
    result = r.json()
    assert result["received"] == 1 and result["new_leads"] == 1

    lead = client.get(f"/leads/{result['lead_ids'][0]}").json()
    assert lead["source"] == "whatsapp"
    assert lead["name"] == "Riya Arora"
    assert lead["phone"] == "+919811055555"
    assert "Zumba" in lead["first_message"]
    assert lead["status"] == "new"


def test_same_whatsapp_delivery_twice_is_ignored(client):
    client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json"))
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json")).json()
    assert r["duplicates"] == 1 and r["new_leads"] == 0


def test_follow_up_message_joins_the_same_lead(client):
    first = client.post("/webhooks/whatsapp", params={"business_id": 1},
                        json=whatsapp_payload("wamid.A1", "Zumba fees?")).json()
    second = client.post("/webhooks/whatsapp", params={"business_id": 1},
                         json=whatsapp_payload("wamid.A2", "Also do you have parking?")).json()
    assert second["added_to_existing"] == 1
    assert first["lead_ids"] == second["lead_ids"]
    lead = client.get(f"/leads/{first['lead_ids'][0]}").json()
    assert [m["text"] for m in lead["messages"]] == ["Zumba fees?", "Also do you have parking?"]


def test_photo_with_caption(client):
    r = client.post("/webhooks/whatsapp", params={"business_id": 2},
                    json=whatsapp_payload("wamid.P1", "Scratch on my door, can you fix?", phone="919811077777", kind="image")).json()
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["first_message"] == "Scratch on my door, can you fix?"


def test_voice_note_becomes_readable_text(client):
    payload = whatsapp_payload("wamid.V1", "", phone="919811088888", kind="audio")
    r = client.post("/webhooks/whatsapp", params={"business_id": 2}, json=payload).json()
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["first_message"] == "[audio message]"


def test_read_receipts_are_ignored(client):
    payload = sample("whatsapp_message.json")
    value = payload["entry"][0]["changes"][0]["value"]
    value.pop("messages"); value.pop("contacts")
    value["statuses"] = [{"id": "wamid.X", "status": "read"}]
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=payload).json()
    assert r["received"] == 0 and r["ignored"] == 1


def test_several_messages_in_one_delivery(client):
    payload = whatsapp_payload("wamid.M1", "Hi")
    value = payload["entry"][0]["changes"][0]["value"]
    extra = copy.deepcopy(value["messages"][0])
    extra.update({"id": "wamid.M2", "from": "919811099999", "text": {"body": "Hello"}})
    value["messages"].append(extra)
    r = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=payload).json()
    assert r["received"] == 2 and r["new_leads"] == 2


# ----- Instagram ---------------------------------------------------------------------------
def test_instagram_dm_creates_lead(client):
    r = client.post("/webhooks/instagram", params={"business_id": 2}, json=sample("instagram_dm.json")).json()
    assert r["new_leads"] == 1
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["source"] == "instagram"
    assert lead["handle"] == "6624512983309871"
    assert "Creta" in lead["first_message"]


def test_instagram_echo_is_ignored(client):
    payload = sample("instagram_dm.json")
    payload["entry"][0]["messaging"][0]["message"]["is_echo"] = True
    r = client.post("/webhooks/instagram", params={"business_id": 2}, json=payload).json()
    assert r["new_leads"] == 0 and r["ignored"] == 1


# ----- Website -----------------------------------------------------------------------------
def test_website_form_creates_lead(client):
    r = client.post("/webhooks/website", params={"business_id": 3}, json=sample("website_form.json")).json()
    assert r["new_leads"] == 1
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["source"] == "website"
    assert lead["phone"] == "+919811066666"
    assert lead["campaign"] == "diwali-offer"
    assert lead["details"]["email"] == "ankit.bansal@example.com"
    assert lead["details"]["utm_source"] == "instagram"


def test_website_form_with_bad_phone_is_explained(client):
    form = sample("website_form.json") | {"phone": "12345", "submission_id": "form-bad"}
    r = client.post("/webhooks/website", params={"business_id": 3}, json=form).json()
    assert r["new_leads"] == 0 and r["ignored"] == 1
    assert "phone" in r["notes"][0]


# ----- Safety ------------------------------------------------------------------------------
def test_unknown_business_gets_404(client):
    r = client.post("/webhooks/whatsapp", params={"business_id": 999}, json=sample("whatsapp_message.json"))
    assert r.status_code == 404


def test_messages_stay_with_their_business(client):
    """The same WhatsApp delivery sent to two businesses makes two separate leads."""
    a = client.post("/webhooks/whatsapp", params={"business_id": 1}, json=sample("whatsapp_message.json")).json()
    b = client.post("/webhooks/whatsapp", params={"business_id": 3}, json=sample("whatsapp_message.json")).json()
    assert a["new_leads"] == 1 and b["new_leads"] == 1
    assert a["lead_ids"] != b["lead_ids"]
