"""
Passwords and login tokens - kept safe with Python's own built-in tools.

PASSWORDS are never stored. We store a "hash": a scrambled fingerprint made
with scrypt (a deliberately slow algorithm, so guessing millions of passwords
is impractically slow). At login we scramble what was typed the same way and
compare the fingerprints.

    "demo1234"  →  scrypt$16384$8$1$<random salt>$<fingerprint>

The random "salt" makes two people with the same password get different
fingerprints.

LOGIN TOKENS are long random strings (like a temporary key card) given out at
login. The browser sends it with every request. We store only a SHA-256
fingerprint of it, so even someone who stole the database couldn't log in.
"""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2 ** 14, 8, 1           # scrypt settings: how much work each guess costs


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return "scrypt${}${}${}${}${}".format(N, R, P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                               n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(check, base64.b64decode(digest))   # compare safely (no timing hints)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)          # 43 random characters


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
