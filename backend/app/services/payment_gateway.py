"""
The payment connector: the only file that talks to Razorpay.

Two versions with the same buttons (like publishers.py and messenger.py):
    MockGateway      no keys yet → pretend payments, free, for building and testing
    RazorpayGateway  keys in .env → real Razorpay subscriptions (auto-debit every month)

How a real payment works (Razorpay "Subscriptions"):
    1. We ask Razorpay to create a subscription for the plan → it gives an id (sub_...).
    2. The website opens Razorpay's checkout with that id; the owner pays (UPI/card).
    3. Razorpay gives the browser 3 things: payment id, subscription id, SIGNATURE.
    4. We check the signature: a fingerprint only Razorpay and we can make,
       because it needs our secret key. If it matches, the payment is real.
    5. Every month Razorpay charges again and rings our doorbell (webhook)
       /webhooks/razorpay, also signed, so we know about renewals and failures.

A "signature" here = HMAC-SHA256: mix the message with a secret key into a
64-character fingerprint. Change one letter of the message (or use the wrong
key) and the fingerprint is completely different, so it can't be faked.
"""

import hashlib
import hmac
import secrets

import httpx

from app.config import settings

MOCK_KEY_ID = "rzp_test_mock"
MOCK_KEY_SECRET = "mock_key_secret"
MOCK_WEBHOOK_SECRET = "mock_webhook_secret"
RAZORPAY_API = "https://api.razorpay.com/v1"


class GatewayError(Exception):
    """Razorpay said no, or couldn't be reached."""


def sign(message: str | bytes, secret: str) -> str:
    data = message.encode() if isinstance(message, str) else message
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


def signatures_match(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected, given or "")      # compare_digest: safe against timing tricks


def key_secret() -> str:
    return settings.razorpay_key_secret if settings.payments_enabled else MOCK_KEY_SECRET


def webhook_secret() -> str:
    if settings.payments_enabled:
        return settings.razorpay_webhook_secret            # empty → every webhook is refused (safe default)
    return settings.razorpay_webhook_secret or MOCK_WEBHOOK_SECRET


def payment_signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Step 4: Razorpay signs  payment_id + "|" + subscription_id  with our key secret."""
    return signatures_match(sign(f"{payment_id}|{subscription_id}", key_secret()), signature)


def webhook_signature_ok(raw_body: bytes, signature: str) -> bool:
    """Step 5: Razorpay signs the raw webhook body (exact bytes) with the webhook secret."""
    secret = webhook_secret()
    return bool(secret) and signatures_match(sign(raw_body, secret), signature)


class MockGateway:
    mode = "mock"
    key_id = MOCK_KEY_ID

    def create_subscription(self, plan_code: str, business_id: int) -> dict:
        return {"id": f"sub_mock_{secrets.token_hex(6)}", "short_url": None}

    def cancel(self, subscription_id: str, at_cycle_end: bool = True) -> None:
        return None


class RazorpayGateway:
    mode = "real"

    def __init__(self):
        self.key_id = settings.razorpay_key_id
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)

    def _plan_id(self, plan_code: str) -> str:
        plan_id = getattr(settings, f"razorpay_plan_{plan_code}", "")
        if not plan_id:
            raise GatewayError(f"Payments aren't set up for the {plan_code} plan yet (RAZORPAY_PLAN_{plan_code.upper()})")
        return plan_id

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(f"{RAZORPAY_API}{path}", json=body, auth=self._auth, timeout=20)
        except httpx.HTTPError as problem:
            raise GatewayError(f"Couldn't reach Razorpay: {problem}") from problem
        if r.status_code >= 400:
            detail = r.json().get("error", {}).get("description", r.text) if r.content else r.reason_phrase
            raise GatewayError(f"Razorpay: {detail}")
        return r.json()

    def create_subscription(self, plan_code: str, business_id: int) -> dict:
        data = self._post("/subscriptions", {
            "plan_id": self._plan_id(plan_code),
            "total_count": 120,                  # up to 10 years of monthly charges (cancel any time)
            "quantity": 1,
            "customer_notify": 1,                # Razorpay emails/SMSes the customer about charges
            "notes": {"business_id": str(business_id), "plan": plan_code},
        })
        return {"id": data["id"], "short_url": data.get("short_url")}

    def cancel(self, subscription_id: str, at_cycle_end: bool = True) -> None:
        self._post(f"/subscriptions/{subscription_id}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0})


def get_gateway():
    return RazorpayGateway() if settings.payments_enabled else MockGateway()
