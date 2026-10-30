"""
LinkedIn Marketing API: connect a company page, publish text / image posts.

Connect journey (OAuth 2.0):
    1. login_url()     → owner approves on linkedin.com
    2. exchange_code() → swap the code for an access token (60 days)
    3. company_pages() → list the company pages the owner administers
    4. publish()       → POST a UGC post on behalf of the company page

Scopes needed (Marketing Developer Platform):
    r_organization_social   read page info + metrics
    w_organization_social   publish UGC posts
    r_basicprofile          read the member's profile to list their pages

LinkedIn access tokens last 60 days (same as Instagram's long-lived token).
There is no refresh token: when the token expires the owner must reconnect.
LinkedIn requires Marketing Developer Platform approval before real use;
while the client_id / client_secret settings are empty, MOCK MODE runs
(pretend connection + pretend post).
"""

from urllib.parse import urlencode

from app.config import settings
from app.integrations.base import IntegrationError, bearer, request

AUTH = "https://www.linkedin.com/oauth/v2"
API = "https://api.linkedin.com/v2"
# 60-day token — reminder to reconnect at day 50
TOKEN_SECONDS = 60 * 24 * 3600


def login_url(state: str, redirect_uri: str) -> str:
    return f"{AUTH}/authorization?" + urlencode({
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri,
        "scope": "r_organization_social w_organization_social r_basicprofile",
        "state": state,
    })


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Swap an auth code for an access token.  Returns the token response dict."""
    return request("POST", f"{AUTH}/accessToken", "LinkedIn",
                   data={
                       "grant_type": "authorization_code",
                       "code": code,
                       "redirect_uri": redirect_uri,
                       "client_id": settings.linkedin_client_id,
                       "client_secret": settings.linkedin_client_secret,
                   })


def me(token: str) -> dict:
    """Basic profile info for the authenticated member (id, localizedFirstName, …)."""
    return request("GET", f"{API}/me", "LinkedIn", headers=bearer(token))


def company_pages(token: str, member_urn: str) -> list[dict]:
    """Company pages the member can administrate.

    Returns [{"id": "12345678", "name": "Iron Pulse Fitness", "followers": 340}, …]
    """
    params = {
        "q": "roleAssignee",
        "role": "ADMINISTRATOR",
        "state": "APPROVED",
        "projection": "(elements*(organizationRole,organization~(id,localizedName,followingInfo)))",
    }
    data = request("GET", f"{API}/organizationAcls", "LinkedIn",
                   headers=bearer(token), params=params)
    pages = []
    for el in data.get("elements", []):
        org = el.get("organization~", {})
        org_id = str(org.get("id", ""))
        if not org_id:
            continue
        followers = (org.get("followingInfo") or {}).get("followerCount", 0)
        pages.append({"id": org_id,
                      "name": org.get("localizedName", org_id),
                      "followers": followers})
    return pages


def publish(token: str, org_id: str, caption: str, media_url: str = "") -> str:
    """Publish a UGC post to a company page.  Returns the post URN."""
    author = f"urn:li:organization:{org_id}"
    share_content: dict = {
        "shareCommentary": {"text": caption[:3000]},
        "shareMediaCategory": "NONE",
    }
    if media_url:
        share_content["shareMediaCategory"] = "IMAGE"
        share_content["media"] = [{
            "status": "READY",
            "originalUrl": media_url,
            "description": {"text": caption[:200]},
        }]
    body = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content,
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    result = request("POST", f"{API}/ugcPosts", "LinkedIn",
                     headers={**bearer(token), "X-Restli-Protocol-Version": "2.0.0"},
                     json=body)
    # LinkedIn returns the post URN in the "id" field or the X-RestLi-Id header
    return result.get("id", "")


def post_stats(post_urn: str, token: str) -> dict:
    """Fetch likes and impressions for a published post."""
    encoded = post_urn.replace(":", "%3A")
    data = request(
        "GET",
        f"{API}/socialMetadata/{encoded}",
        "LinkedIn",
        headers={**bearer(token), "X-Restli-Protocol-Version": "2.0.0"},
    )
    total = data.get("totalSocialActivityCounts", {})
    return {
        "likes": total.get("numLikes", 0),
        "reach": total.get("numImpressions", 0),
    }
