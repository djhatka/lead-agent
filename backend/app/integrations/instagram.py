"""
Instagram (the "Instagram API with Instagram Login"): no Facebook Page needed.

Connect: owner approves on instagram.com → we get a CODE → swap it for a
short key (1 hour) → swap that for a LONG key (60 days) → we refresh it
before it runs out (scheduler) → read the profile → subscribe to DMs.

Posting is two steps: 1) give Instagram the photo/video link → it makes a
"container" (and processes videos for a while)  2) publish the container.
Instagram fetches the file itself, so the link must be public (JPEG photos).
"""

import time
from urllib.parse import urlencode

from app.config import settings
from app.integrations.base import IntegrationError, bearer, request

API = "https://graph.instagram.com"
SCOPES = ("instagram_business_basic,instagram_business_manage_messages,"
          "instagram_business_content_publish,instagram_business_manage_insights")
SLEEP = time.sleep           # tests replace this so they don't wait
INSIGHTS = {                  # which numbers Instagram gives for each kind of post
    "reel": "reach,likes,comments,shares,saved",
    "story": "reach,shares,profile_visits",
    "default": "reach,likes,comments,shares,saved,profile_visits",
}


def _url(path: str) -> str:
    return f"{API}/{settings.meta_graph_version}/{path.lstrip('/')}"


def call(method: str, path: str, token: str, **kwargs) -> dict:
    return request(method, _url(path), "Instagram", headers=bearer(token), **kwargs)


def login_url(state: str, redirect_uri: str) -> str:
    return "https://www.instagram.com/oauth/authorize?" + urlencode({
        "client_id": settings.instagram_app_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPES, "state": state})


def exchange_code(code: str, redirect_uri: str) -> str:
    data = request("POST", "https://api.instagram.com/oauth/access_token", "Instagram", data={
        "client_id": settings.instagram_app_id, "client_secret": settings.instagram_app_secret,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        "code": code.removesuffix("#_")})                 # Instagram adds "#_" to the code: not part of it
    first = (data.get("data") or [data])[0]
    if not first.get("access_token"):
        raise IntegrationError("Instagram didn't return a key for this login")
    return first["access_token"]


def long_lived(short_token: str) -> tuple[str, int]:
    data = request("GET", f"{API}/access_token", "Instagram", params={
        "grant_type": "ig_exchange_token", "client_secret": settings.instagram_app_secret,
        "access_token": short_token})
    return data["access_token"], int(data.get("expires_in", 5_184_000))


def refresh(token: str) -> tuple[str, int]:
    data = request("GET", f"{API}/refresh_access_token", "Instagram",
                   params={"grant_type": "ig_refresh_token", "access_token": token})
    return data["access_token"], int(data.get("expires_in", 5_184_000))


def profile(token: str) -> dict:
    """user_id = the professional account id that webhooks and the API use."""
    return call("GET", "me", token, params={"fields": "user_id,username,name,followers_count"})


def subscribe(token: str) -> None:
    call("POST", "me/subscribed_apps", token, params={"subscribed_fields": "messages"})


def send_text(ig_id: str, token: str, igsid: str, text: str) -> str:
    data = call("POST", f"{ig_id}/messages", token, json={"recipient": {"id": igsid}, "message": {"text": text}})
    return data.get("message_id", "")


def publish(ig_id: str, token: str, kind: str, caption: str, media_url: str) -> str:
    if not media_url:
        raise IntegrationError("Instagram needs a photo or video: add a public media link to this post")
    is_video = kind in ("reel", "video") or media_url.lower().split("?")[0].endswith((".mp4", ".mov"))
    body = {"caption": caption}
    if kind == "story":
        body = {"media_type": "STORIES", ("video_url" if is_video else "image_url"): media_url}
    elif is_video:
        body.update(media_type="REELS", video_url=media_url)
    else:
        body["image_url"] = media_url
    container = call("POST", f"{ig_id}/media", token, data=body)["id"]

    for _ in range(10):                                    # wait for Instagram to process it (videos take a while)
        status = call("GET", container, token, params={"fields": "status_code"}).get("status_code", "FINISHED")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise IntegrationError(f"Instagram couldn't process the media ({status}): check the link and format")
        SLEEP(6)
    else:
        raise IntegrationError("Instagram is still processing the video: it will be retried")
    return call("POST", f"{ig_id}/media_publish", token, data={"creation_id": container})["id"]


def media_stats(media_id: str, token: str, kind: str) -> dict:
    metrics = INSIGHTS.get(kind, INSIGHTS["default"])
    data = call("GET", f"{media_id}/insights", token, params={"metric": metrics})
    rename = {"saved": "saves"}
    return {rename.get(m["name"], m["name"]): (m.get("values") or [{}])[0].get("value", 0)
            for m in data.get("data", [])}
