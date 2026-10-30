"""
What this copy of Lead Intel really offers right now.

Why this exists: several features need an account or an approval that takes weeks
(Meta for WhatsApp / Instagram / Facebook, Google Business Profile, LinkedIn, Razorpay KYC, a call-tracking
provider, a paid map-data service). Until their real keys are in `.env`, those features run in
pretend ("mock") mode: fine on your laptop, but on the live site it would show owners fake
connections, fake competitor numbers and posts "published" that were never posted.

LAUNCH_MODE decides what to do about that (see config.py):

    full   everything is on; missing keys mean pretend mode      (laptop, tests)
    light  a feature is on ONLY when its real keys exist         (the live site, automatic)

So the launch version needs no approvals, and each feature switches itself on the moment you add
its keys. Nothing else has to change.

    features.snapshot()            -> {"mode": ..., "connect_apps": ..., ...} for GET /features
    features.require("calls")      -> a router dependency: 404 "not available yet" while it's off
    features.on("whatsapp")        -> True / False
"""

from fastapi import Depends, HTTPException

from app.config import settings


def _real_keys() -> dict[str, bool]:
    """Which real services have their keys in .env."""
    return {
        "whatsapp": settings.meta_enabled,          # WhatsApp rides on the Meta app
        "facebook": settings.meta_enabled,
        "instagram": settings.instagram_enabled,
        "google": settings.google_enabled,
        "linkedin": settings.linkedin_enabled,
        "payments": settings.payments_enabled,      # Razorpay
        "competitors": settings.mapsearch_enabled,  # DataForSEO
        "calls": settings.calltracking_enabled,     # Exotel
    }


def is_light() -> bool:
    return settings.is_light


def on(feature: str) -> bool:
    """Is this feature really available right now?"""
    keys = _real_keys()
    if not is_light():
        return True                                  # full mode: everything (pretend mode fills the gaps)
    if feature == "connect_apps":                    # the Connections page: is there anything to connect?
        return any(keys[p] for p in ("whatsapp", "facebook", "instagram", "google", "linkedin"))
    if feature == "auto_posting":                    # posts that go out by themselves
        return any(keys[p] for p in ("facebook", "instagram", "google", "linkedin"))
    if feature == "whatsapp_messaging":              # owner alerts, instant replies, review requests, dues reminders
        return keys["whatsapp"]
    if feature == "google_reviews":                  # reviews that arrive by themselves
        return keys["google"]
    return keys[feature]


# The names the dashboard and the routers use
FEATURES = ("connect_apps", "auto_posting", "whatsapp_messaging", "google_reviews", "whatsapp", "facebook",
            "instagram", "google", "linkedin", "payments", "competitors", "calls")


def snapshot() -> dict:
    return {"mode": "light" if is_light() else "full", **{name: on(name) for name in FEATURES}}


MANUAL_POST_MESSAGE = ("Posts don't go out by themselves yet. Copy the caption, post it on your own account at the "
                       "scheduled time, then tap \"Mark as posted\".")


def not_available(feature: str) -> HTTPException:
    return HTTPException(status_code=404, detail="This isn't available yet. It switches on when its account is "
                                                 f"connected to Lead Intel ({feature.replace('_', ' ')}).")


def require(feature: str):
    """For include_router(..., dependencies=[...]): the whole router answers 404 while the feature is off."""
    def check() -> None:
        if not on(feature):
            raise not_available(feature)
    return Depends(check)


def highlights(plan) -> list[str]:
    """The plan's bullet points, minus any promise we can't keep yet (e.g. WhatsApp messages)."""
    if on("whatsapp_messaging"):
        return list(plan.highlights)
    return [line for line in plan.highlights if "whatsapp" not in line.lower()]
