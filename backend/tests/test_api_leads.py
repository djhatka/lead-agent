"""
Checks for the business and lead endpoints (Task 5).

`client.get("/leads?...")` works like typing the address in a browser.
`.status_code` is the server's answer code:
    200 OK    201 Created    400 Broken business rule
    404 Not found            422 Data failed the schema rules
"""


# ----- Businesses -------------------------------------------------------------
def test_list_businesses(client):
    r = client.get("/businesses")
    assert r.status_code == 200
    assert [b["name"] for b in r.json()] == ["Iron Pulse Fitness", "Gloss Garage Detailing", "SmileCare Dental Clinic"]


def test_create_and_update_business(client):
    r = client.post("/businesses", json={"name": "Glow Salon", "industry": "Salon", "phone": "98110 22222"})
    assert r.status_code == 201
    salon = r.json()
    assert salon["industry"] == "salon" and salon["phone"] == "+919811022222"

    r = client.patch(f"/businesses/{salon['id']}", json={"brand_voice": "warm and elegant"})
    assert r.status_code == 200
    assert r.json()["brand_voice"] == "warm and elegant"
    assert r.json()["name"] == "Glow Salon"          # untouched fields stay the same


def test_bad_business_gets_422(client):
    r = client.post("/businesses", json={"name": "X", "industry": "spaceship"})
    assert r.status_code == 422


# ----- Dashboard language (Task 39) --------------------------------------------
def test_new_business_defaults_to_english(client):
    r = client.post("/businesses", json={"name": "Shine Detailing", "industry": "car_detailing"})
    assert r.status_code == 201
    assert r.json()["language"] == "en"


def test_switching_to_hindi_sticks(client):
    created = client.post("/businesses", json={"name": "Namaste Salon", "industry": "Salon"}).json()
    r = client.patch(f"/businesses/{created['id']}", json={"language": "hi"})
    assert r.status_code == 200 and r.json()["language"] == "hi"
    assert client.get(f"/businesses/{created['id']}").json()["language"] == "hi"


def test_unknown_language_gets_422(client):
    created = client.post("/businesses", json={"name": "Test Biz", "industry": "Gym"}).json()
    r = client.patch(f"/businesses/{created['id']}", json={"language": "fr"})
    assert r.status_code == 422


def test_missing_business_gets_404(client):
    assert client.get("/businesses/999").status_code == 404


# ----- Listing leads ------------------------------------------------------------
def test_list_leads_for_one_business_only(client):
    r = client.get("/leads", params={"business_id": 1, "limit": 200})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 40
    assert all(lead["business_id"] == 1 for lead in page["items"])


def test_pages(client):
    first = client.get("/leads", params={"business_id": 1, "limit": 10}).json()
    second = client.get("/leads", params={"business_id": 1, "limit": 10, "offset": 10}).json()
    assert len(first["items"]) == 10 and len(second["items"]) == 10
    assert {l["id"] for l in first["items"]}.isdisjoint({l["id"] for l in second["items"]})


def test_filter_by_source_and_status(client):
    r = client.get("/leads", params={"business_id": 1, "source": "instagram"}).json()
    assert r["total"] > 0 and all(l["source"] == "instagram" for l in r["items"])
    r = client.get("/leads", params={"business_id": 1, "status": "won"}).json()
    assert all(l["status"] == "won" and l["job_value"] > 0 for l in r["items"])


def test_newest_first(client):
    items = client.get("/leads", params={"business_id": 2}).json()["items"]
    dates = [l["created_at"] for l in items]
    assert dates == sorted(dates, reverse=True)


def test_search(client):
    r = client.get("/leads", params={"business_id": 2, "search": "creta"}).json()
    assert r["total"] > 0
    for lead in r["items"]:
        assert "creta" in (lead["first_message"] + str(lead["details"])).lower()


def test_unknown_filter_value_gets_422(client):
    assert client.get("/leads", params={"business_id": 1, "source": "pigeon"}).status_code == 422


# ----- One lead ------------------------------------------------------------------
def test_create_lead_by_hand(client):
    r = client.post("/leads", json={
        "business_id": 3, "source": "walk_in", "name": "Meera Kapoor", "phone": "9811033333",
        "service": "Braces", "first_message": "Came in asking about braces for my daughter",
    })
    assert r.status_code == 201
    lead = r.json()
    assert lead["status"] == "new"
    assert lead["messages"][0]["text"].startswith("Came in asking")


def test_same_webhook_twice_makes_one_lead(client):
    body = {"business_id": 1, "source": "whatsapp", "external_id": "wamid.ABC", "phone": "9811044444"}
    first = client.post("/leads", json=body).json()
    second = client.post("/leads", json=body).json()
    assert first["id"] == second["id"]


def test_lead_detail_has_conversation(client):
    r = client.get("/leads/1")
    assert r.status_code == 200
    assert len(r.json()["messages"]) >= 1


def test_mark_lead_won(client):
    new_lead = client.post("/leads", json={"business_id": 1, "source": "walk_in", "name": "Yash"}).json()
    r = client.patch(f"/leads/{new_lead['id']}", json={"status": "won", "job_value": 12000})
    assert r.status_code == 200
    assert r.json()["status"] == "won" and r.json()["job_value"] == 12000
    assert r.json()["first_response_at"] is not None     # reply time recorded


def test_won_without_money_gets_400(client):
    new_lead = client.post("/leads", json={"business_id": 1, "source": "walk_in", "name": "Isha"}).json()
    r = client.patch(f"/leads/{new_lead['id']}", json={"status": "won"})
    assert r.status_code == 400
    assert "job_value" in r.json()["detail"]


def test_reply_moves_new_lead_to_contacted(client):
    new_lead = client.post("/leads", json={"business_id": 2, "source": "instagram", "handle": "@car.guy"}).json()
    r = client.post(f"/leads/{new_lead['id']}/messages", json={"direction": "outbound", "text": "Hi! Which car?"})
    assert r.status_code == 201
    lead = client.get(f"/leads/{new_lead['id']}").json()
    assert lead["status"] == "contacted"
    assert lead["first_response_at"] is not None
    assert [m["direction"] for m in lead["messages"]] == ["outbound"]   # no first message was sent


def test_missing_lead_gets_404(client):
    assert client.get("/leads/99999").status_code == 404


def test_times_are_sent_with_timezone(client):
    lead = client.get("/leads/1").json()
    assert lead["created_at"].endswith("Z") or lead["created_at"].endswith("+00:00")
