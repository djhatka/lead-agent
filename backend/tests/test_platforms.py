"""
Checks for the platform list and the universal door.
"""

import json
from pathlib import Path

from app.platforms import CATEGORIES, PLATFORMS

SAMPLES = Path(__file__).resolve().parents[1] / "seed" / "sample_payloads"


def test_every_platform_is_described_properly():
    for key, p in PLATFORMS.items():
        assert key == p.key and len(key) <= 20            # fits the database column
        assert p.category in CATEGORIES
        assert p.connection in ("api", "email", "manual")


def test_list_all_platforms(client):
    keys = [p["key"] for p in client.get("/platforms").json()]
    for expected in ("whatsapp", "instagram", "justdial", "practo", "zomato", "99acres", "walk_in"):
        assert expected in keys


def test_platforms_for_one_industry(client):
    clinic = [p["key"] for p in client.get("/platforms", params={"industry": "clinic"}).json()]
    assert "practo" in clinic and "google" in clinic      # clinic-only + everyone
    assert "zomato" not in clinic                          # restaurants only


def test_universal_door_with_justdial(client):
    payload = json.loads((SAMPLES / "universal_lead.json").read_text(encoding="utf-8"))
    r = client.post("/webhooks/universal", params={"business_id": 1, "platform": "justdial"}, json=payload).json()
    assert r["new_leads"] == 1
    lead = client.get(f"/leads/{r['lead_ids'][0]}").json()
    assert lead["source"] == "justdial"
    assert lead["name"] == "Sanjay Mehta" and lead["phone"] == "+919811077777"


def test_universal_door_any_platform(client):
    for i, platform in enumerate(["practo", "zomato", "99acres", "urbanpro", "sulekha"]):
        r = client.post("/webhooks/universal", params={"business_id": 3, "platform": platform},
                        json={"name": f"Test {i}", "message": "Hi"}).json()
        assert r["new_leads"] == 1, platform


def test_universal_door_rejects_unknown_platform(client):
    r = client.post("/webhooks/universal", params={"business_id": 1, "platform": "myspace"}, json={"name": "X"})
    assert r.status_code == 422


def test_new_platforms_work_in_lead_filters(client):
    client.post("/webhooks/universal", params={"business_id": 1, "platform": "cultfit"}, json={"name": "Gym buddy"})
    r = client.get("/leads", params={"business_id": 1, "source": "cultfit"}).json()
    assert r["total"] == 1
