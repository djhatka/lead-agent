"""
Meta: WhatsApp Cloud API + Facebook Pages (+ the webhook signature check).

WhatsApp ("Embedded Signup"):
    The owner clicks "Connect WhatsApp" → Meta's popup on OUR website → they pick
    or create their WhatsApp Business account and number → the popup gives the
    website a short-lived CODE + the waba_id + phone_number_id → our server:
        1. swaps the code for a business token   (GET  /oauth/access_token)
        2. subscribes our app to their webhooks   (POST /{waba_id}/subscribed_apps)
        3. registers the number for the Cloud API (POST /{phone_number_id}/register)
Facebook Page (Facebook Login): owner approves on facebook.com → we get a code →
    swap for a user token → make it long-lived → list their Pages (each Page has
    its own key) → subscribe each Page to Messenger webhooks.

Rule to remember: WhatsApp / Messenger only allow FREE-TEXT replies within
24 hours of the customer's last message. Starting a conversation (like the
"please review us" message) needs an approved TEMPLATE.
"""

import hashlib
import hmac
import secrets
from urllib.parse import urlencode

from app.config import settings
from app.integrations.base import IntegrationError, bearer, request

GRAPH = "https://graph.facebook.com"
PAGE_SCOPES = "pages_show_list,pages_manage_metadata,pages_messaging,pages_manage_posts,pages_read_engagement,read_insights"


def _url(path: str) -> str:
    return f"{GRAPH}/{settings.meta_graph_version}/{path.lstrip('/')}"


def call(method: str, path: str, token: str | None = None, **kwargs) -> dict:
    headers = bearer(token) if token else {}
    return request(method, _url(path), "Meta", headers=headers, **kwargs)


# ---------------------------------------------------------------------------
# Webhook signature: Meta signs every delivery with our app secret
# ---------------------------------------------------------------------------
def signature_ok(raw_body: bytes, header: str) -> bool:
    """Header looks like 'sha256=<64 hex>'. Instagram-Login deliveries are signed with
    the Instagram app secret, the rest with the Meta app secret, so we accept either."""
    given = (header or "").removeprefix("sha256=")
    for secret in (settings.meta_app_secret, settings.instagram_app_secret):
        if secret and hmac.compare_digest(hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest(), given):
            return True
    return False


# ---------------------------------------------------------------------------
# Login and keys
# ---------------------------------------------------------------------------
def pages_login_url(state: str, redirect_uri: str) -> str:
    params = {"client_id": settings.meta_app_id, "redirect_uri": redirect_uri, "state": state,
              "response_type": "code"}
    if settings.meta_pages_config_id:
        params["config_id"] = settings.meta_pages_config_id
    else:
        params["scope"] = PAGE_SCOPES
    return f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str | None = None) -> str:
    params = {"client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret, "code": code}
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    token = call("GET", "oauth/access_token", params=params).get("access_token")
    if not token:
        raise IntegrationError("Meta didn't return a key for this login")
    return token


def long_lived(user_token: str) -> str:
    data = call("GET", "oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret, "fb_exchange_token": user_token})
    return data.get("access_token") or user_token


def pages(user_token: str) -> list[dict]:
    """The Facebook Pages the owner allowed us to use, each with its own Page key."""
    data = call("GET", "me/accounts", user_token,
                params={"fields": "id,name,username,access_token,followers_count", "limit": 50})
    return data.get("data", [])


def subscribe_page(page_id: str, page_token: str) -> None:
    call("POST", f"{page_id}/subscribed_apps", page_token, params={"subscribed_fields": "messages"})


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------
def whatsapp_finish_signup(code: str, waba_id: str, phone_number_id: str) -> dict:
    token = exchange_code(code)
    call("POST", f"{waba_id}/subscribed_apps", token)
    pin = f"{secrets.randbelow(1_000_000):06d}"            # the number's 2-step verification PIN
    try:
        call("POST", f"{phone_number_id}/register", token, json={"messaging_product": "whatsapp", "pin": pin})
    except IntegrationError as problem:
        if "already" not in str(problem).lower():           # already registered = fine
            raise
    info = call("GET", phone_number_id, token, params={"fields": "display_phone_number,verified_name"})
    return {"token": token, "pin": pin, "display": info.get("display_phone_number", phone_number_id),
            "name": info.get("verified_name", "")}


def whatsapp_send_text(phone_number_id: str, token: str, to: str, text: str) -> str:
    data = call("POST", f"{phone_number_id}/messages", token, json={
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+"),
        "type": "text", "text": {"preview_url": True, "body": text}})
    return data.get("messages", [{}])[0].get("id", "")


def whatsapp_send_template(phone_number_id: str, token: str, to: str, name: str, language: str,
                           params: list[str]) -> str:
    data = call("POST", f"{phone_number_id}/messages", token, json={
        "messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
        "template": {"name": name, "language": {"code": language},
                     "components": [{"type": "body",
                                     "parameters": [{"type": "text", "text": p} for p in params]}]}})
    return data.get("messages", [{}])[0].get("id", "")


REVIEW_TEMPLATE_TEXT = ("Hi {{1}}, thank you for choosing {{2}}! 🙏 If you were happy with us, "
                        "could you leave a quick Google review? It really helps a small business: {{3}}")


def whatsapp_create_review_template(waba_id: str, token: str) -> None:
    """Ask Meta to approve our 'please review us' template in the owner's WhatsApp account.
    Approval usually takes minutes to a day; until then review requests wait."""
    call("POST", f"{waba_id}/message_templates", token, json={
        "name": settings.whatsapp_review_template, "language": settings.whatsapp_template_language,
        "category": "MARKETING",
        "components": [{"type": "BODY", "text": REVIEW_TEMPLATE_TEXT,
                        "example": {"body_text": [["Priya", "Iron Pulse Fitness", "https://g.page/r/example/review"]]}}]})


ALERT_TEMPLATE_TEXT = "🔥 New hot lead for {{1}}: {{2}}. Reply quickly to win it: {{3}}"


def whatsapp_create_alert_template(waba_id: str, token: str) -> None:
    """Ask Meta to approve the owner-alert template (a UTILITY message: it's about the owner's own account)."""
    call("POST", f"{waba_id}/message_templates", token, json={
        "name": settings.whatsapp_alert_template, "language": settings.whatsapp_template_language,
        "category": "UTILITY",
        "components": [{"type": "BODY", "text": ALERT_TEMPLATE_TEXT,
                        "example": {"body_text": [["Iron Pulse Fitness", "Rahul wants CrossFit (score 82)",
                                                   "https://app.example.com/leads/12"]]}}]})


PAYMENT_TEMPLATE_TEXT = ("Hi {{1}}, a gentle reminder from {{2}}: {{3}}. You can pay securely here: {{4}} "
                         "Please ignore this if you have already paid. Thank you!")


def whatsapp_create_payment_template(waba_id: str, token: str) -> None:
    """Ask Meta to approve the payment-reminder template (Task 31). UTILITY: it's about a payment the
    customer already agreed to, not marketing."""
    call("POST", f"{waba_id}/message_templates", token, json={
        "name": settings.whatsapp_payment_template, "language": settings.whatsapp_template_language,
        "category": "UTILITY",
        "components": [{"type": "BODY", "text": PAYMENT_TEMPLATE_TEXT,
                        "example": {"body_text": [["Rahul", "Gloss Garage Detailing",
                                                   "₹2,000 for the ceramic coating advance is due today",
                                                   "https://app.example.com/pay/abc123"]]}}]})


# ---------------------------------------------------------------------------
# Facebook Page: Messenger replies, posts, numbers
# ---------------------------------------------------------------------------
def page_send_text(page_id: str, page_token: str, psid: str, text: str) -> str:
    data = call("POST", f"{page_id}/messages", page_token, json={
        "recipient": {"id": psid}, "messaging_type": "RESPONSE", "message": {"text": text}})
    return data.get("message_id", "")


def page_publish(page_id: str, page_token: str, caption: str, media_url: str = "", video: bool = False) -> str:
    if media_url and video:
        data = call("POST", f"{page_id}/videos", page_token, data={"file_url": media_url, "description": caption})
    elif media_url:
        data = call("POST", f"{page_id}/photos", page_token, data={"url": media_url, "caption": caption})
    else:
        data = call("POST", f"{page_id}/feed", page_token, data={"message": caption})
    return data.get("post_id") or data.get("id", "")


def page_post_stats(post_id: str, page_token: str) -> dict:
    data = call("GET", post_id, page_token,
                params={"fields": "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),shares"})
    numbers = {"likes": data.get("reactions", {}).get("summary", {}).get("total_count", 0),
               "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
               "shares": data.get("shares", {}).get("count", 0)}
    try:                                                     # reach: Meta renames page metrics often → best effort
        insights = call("GET", f"{post_id}/insights", page_token, params={"metric": "post_impressions_unique"})
        numbers["reach"] = insights["data"][0]["values"][0]["value"]
    except (IntegrationError, KeyError, IndexError, TypeError):
        pass
    return numbers
