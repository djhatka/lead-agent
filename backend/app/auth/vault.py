"""
The safe: locking secrets and signing links.

1. lock(text) / unlock(text)
   Each business's platform keys (their Instagram / WhatsApp / Google tokens)
   are LOCKED before we save them. Locking = encryption with "Fernet"
   (AES, a standard lock). Without SECRET_KEY the saved text is useless,
   so a stolen copy of the database doesn't give anyone their accounts.

2. sign_state(...) / read_state(...)
   When an owner clicks "Connect Instagram", we send them to Instagram with a
   little note ("state") saying which business this is. Instagram hands the
   note back when it sends them back to us. We SIGN the note (like a wax seal),
   so nobody can change "business 1" into "business 2", and it expires after
   15 minutes, so an old link can't be reused.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class VaultError(Exception):
    pass


def _fernet() -> Fernet:
    # Fernet needs a 32-byte key: we make one from SECRET_KEY (same secret → same key)
    key = hashlib.sha256(("vault:" + settings.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def lock(text: Optional[str]) -> Optional[str]:
    return _fernet().encrypt(text.encode()).decode() if text else None


def unlock(locked: Optional[str]) -> Optional[str]:
    if not locked:
        return None
    try:
        return _fernet().decrypt(locked.encode()).decode()
    except InvalidToken as problem:
        raise VaultError("Can't unlock this key (was SECRET_KEY changed?)") from problem


def _seal(body: str) -> str:
    return hmac.new(("state:" + settings.secret_key).encode(), body.encode(), hashlib.sha256).hexdigest()


def sign_state(data: dict, minutes: int = 15) -> str:
    payload = dict(data, exp=int(time.time()) + minutes * 60, nonce=secrets.token_hex(4))
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_seal(body)}"


def read_state(state: str) -> dict:
    try:
        body, seal = state.rsplit(".", 1)
    except (AttributeError, ValueError):
        raise VaultError("This connect link is broken")
    if not hmac.compare_digest(_seal(body), seal):
        raise VaultError("This connect link was changed or isn't ours")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if data.get("exp", 0) < time.time():
        raise VaultError("This connect link has expired: please click Connect again")
    return data
