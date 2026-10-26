"""
Google Business Profile: reviews in, replies out, posts out.

Connect (Google sign-in, "OAuth"): owner approves on accounts.google.com →
we get a CODE → swap it for an access key (1 hour) + a REFRESH key (lasts
until they remove access) → each hour we use the refresh key for a new
access key. Then we look up their business location(s).

Note: Google must approve your project for the Business Profile APIs first
(a short form on Google's site). Until then every call answers "quota 0".
"""

from urllib.parse import urlencode

from app.config import settings
from app.integrations.base import IntegrationError, bearer, request

SCOPE = "https://www.googleapis.com/auth/business.manage"
ACCOUNTS = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
INFO = "https://mybusinessbusinessinformation.googleapis.com/v1"
V4 = "https://mybusiness.googleapis.com/v4"
STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def login_url(state: str, redirect_uri: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "state": state})


def _token_call(fields: dict) -> dict:
    return request("POST", "https://oauth2.googleapis.com/token", "Google", data={
        "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, **fields})


def exchange_code(code: str, redirect_uri: str) -> dict:
    data = _token_call({"code": code, "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if not data.get("refresh_token"):
        raise IntegrationError("Google didn't give a long-term key: remove the app at "
                               "myaccount.google.com/permissions and connect again")
    return data


def refresh(refresh_token: str) -> dict:
    return _token_call({"refresh_token": refresh_token, "grant_type": "refresh_token"})


def locations(token: str) -> list[dict]:
    """Every business location the owner manages: [{"name": "accounts/1/locations/2", "title": ...}]."""
    found = []
    for account in request("GET", ACCOUNTS, "Google", headers=bearer(token)).get("accounts", []):
        data = request("GET", f"{INFO}/{account['name']}/locations", "Google", headers=bearer(token),
                       params={"readMask": "name,title", "pageSize": 100})
        for loc in data.get("locations", []):
            found.append({"name": f"{account['name']}/{loc['name']}", "title": loc.get("title", "")})
    return found


def reviews(location: str, token: str) -> list[dict]:
    data = request("GET", f"{V4}/{location}/reviews", "Google", headers=bearer(token),
                   params={"pageSize": 50, "orderBy": "updateTime desc"})
    return data.get("reviews", [])


def reply(review_name: str, token: str, text: str) -> None:
    request("PUT", f"{V4}/{review_name}/reply", "Google", headers=bearer(token), json={"comment": text})


def create_post(location: str, token: str, caption: str, media_url: str = "") -> str:
    body = {"languageCode": "en", "summary": caption[:1500], "topicType": "STANDARD"}
    if media_url:
        body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": media_url}]
    return request("POST", f"{V4}/{location}/localPosts", "Google", headers=bearer(token), json=body).get("name", "")
