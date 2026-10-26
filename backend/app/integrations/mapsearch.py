"""
Map-search data (Tasks 34-35): looks up a business's own listing, or a competitor's,
on Google Maps - so we can see where it ranks and how it compares with rivals.

Google has no official "what's my ranking" API, so this calls a paid map-search data
service instead. DataForSEO's Google Maps API is one option: priced per search (about
$0.0006-0.002), no approval needed - open an account and add credit (dataforseo.com).

While DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are empty, callers use realistic mock data
instead of this module (see app/services/competitor_service.py) - this file is only
reached once real credentials are set.
"""

import base64
from typing import Optional

from app.config import settings
from app.integrations.base import IntegrationError, request

LIVE_MAPS = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"


def _auth() -> dict:
    token = base64.b64encode(f"{settings.dataforseo_login}:{settings.dataforseo_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def search_listing(name: str, area: str) -> Optional[dict]:
    """The best-matching Google Maps listing for `name` near `area`, or None if nothing
    close enough turned up. Raises IntegrationError if the service itself failed."""
    keyword = f"{name} {area}".strip()
    body = [{"keyword": keyword, "language_code": "en", "location_name": area or "India", "depth": 10}]
    data = request("POST", LIVE_MAPS, "DataForSEO", headers=_auth(), json=body)

    tasks = data.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        problem = tasks[0].get("status_message") if tasks else "no response"
        raise IntegrationError(f"DataForSEO: {problem}")

    results = tasks[0].get("result") or [{}]
    items = results[0].get("items") or []
    if not items:
        return None

    # Prefer an item whose title actually contains the name we searched for;
    # fall back to the top result if none matches closely.
    needle = name.strip().lower()
    match = next((it for it in items if needle in (it.get("title") or "").lower()), items[0])

    rating = match.get("rating") or {}
    return {
        "place_id": match.get("place_id") or match.get("cid") or "",
        "rating": rating.get("value"),
        "review_count": rating.get("votes_count"),
        "category": match.get("category") or "",
        "address": match.get("address") or "",
    }
