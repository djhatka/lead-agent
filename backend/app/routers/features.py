"""
What this copy of Lead Intel really offers (no login needed: it holds no secrets, and the
dashboard asks for it before anyone has signed in).

    GET /features   {"mode": "light", "connect_apps": false, "auto_posting": false, "whatsapp_messaging": false, ...}

The dashboard hides every button that would lead to something that isn't switched on yet.
See app/features.py for how each flag is decided.
"""

from fastapi import APIRouter

from app import features

router = APIRouter(tags=["System"])


@router.get("/features")
def what_is_on():
    return features.snapshot()
