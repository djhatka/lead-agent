"""
Shared plumbing for the platform clients.

All requests go through request(), so errors look the same everywhere:
    IntegrationError → something went wrong (shown to the owner in plain words)
    NeedsReconnect   → the account's key stopped working (expired, password
                       changed, access removed): the owner must click Connect again

HTTP is one shared "browser" for talking to the platforms. Tests replace it
with a fake one (httpx.MockTransport), so no test ever calls the real internet.
"""

import httpx

HTTP = httpx.Client(timeout=30)


class IntegrationError(Exception):
    pass


class NeedsReconnect(IntegrationError):
    pass


# Meta error codes that mean "this key doesn't work any more"
META_AUTH_CODES = {190, 102, 10, 200, 459, 460, 463, 467}


def _explain(platform: str, status: int, data: dict) -> tuple[str, bool]:
    """(plain message, is it a 'reconnect' problem?)"""
    err = data.get("error")
    if isinstance(err, dict):                                   # Meta and Google both use {"error": {...}}
        message = err.get("error_user_msg") or err.get("message") or "unknown error"
        auth = err.get("code") in META_AUTH_CODES and platform != "google"
        auth = auth or status == 401 or err.get("status") == "UNAUTHENTICATED"
        return f"{platform}: {message}", auth
    if isinstance(err, str):                                    # OAuth token errors: {"error": "invalid_grant"}
        return f"{platform}: {data.get('error_description') or err}", err in ("invalid_grant", "invalid_token")
    if data.get("error_message"):                               # Instagram's login server
        return f"{platform}: {data['error_message']}", status in (400, 401)
    return f"{platform}: HTTP {status}", status == 401


def request(method: str, url: str, platform: str, **kwargs) -> dict:
    try:
        r = HTTP.request(method, url, **kwargs)
    except httpx.HTTPError as problem:
        raise IntegrationError(f"Couldn't reach {platform}: {problem}") from problem
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"error": {"message": r.text[:200]}}
    if r.status_code >= 400:
        message, auth = _explain(platform, r.status_code, data if isinstance(data, dict) else {})
        raise (NeedsReconnect if auth else IntegrationError)(message)
    return data if isinstance(data, dict) else {"data": data}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
