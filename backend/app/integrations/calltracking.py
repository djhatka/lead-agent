"""
Phone call tracking (Task 38): buys/releases the per-business tracking number that
customers call instead of the owner's real number.

No single calling provider is used everywhere in India, so this module talks to
Exotel's API (exotel.com) as the reference implementation - swap this file for
another provider (MyOperator, Knowlarity...) if you pick someone else; the shape
calltracking_service.py expects (buy_number / release_number) stays the same.

While CALLTRACKING_SID / CALLTRACKING_TOKEN / CALLTRACKING_SUBDOMAIN are empty,
callers use a free mock number instead of this module (see calltracking_service.py) -
this file is only reached once real credentials are set.
"""

import base64

from app.config import settings
from app.integrations.base import IntegrationError, request

NUMBERS_PATH = "IncomingPhoneNumbers.json"


def _auth() -> dict:
    token = base64.b64encode(f"{settings.calltracking_sid}:{settings.calltracking_token}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _base_url() -> str:
    return f"https://{settings.calltracking_subdomain}.exotel.com/v1/Accounts/{settings.calltracking_sid}"


def buy_number(area_code: str = "") -> dict:
    """Buy (provision) a new virtual number. Returns {"number": "+91...", "sid": "..."}."""
    body = {"AreaCode": area_code} if area_code else {}
    data = request("POST", f"{_base_url()}/{NUMBERS_PATH}", "Exotel", headers=_auth(), data=body)
    number = data.get("IncomingPhoneNumber") or data.get("incoming_phone_number") or {}
    phone = number.get("PhoneNumber") or number.get("phone_number")
    sid = number.get("Sid") or number.get("sid") or ""
    if not phone:
        raise IntegrationError("Exotel: no number returned")
    return {"number": phone, "sid": sid}


def release_number(sid: str) -> None:
    """Stop renting a number that's no longer needed (e.g. account deleted)."""
    if not sid:
        return
    request("DELETE", f"{_base_url()}/IncomingPhoneNumbers/{sid}.json", "Exotel", headers=_auth())
