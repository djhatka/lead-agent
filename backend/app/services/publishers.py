"""
Platform publishers: the one place that knows how to turn a scheduled Post into a real
post on each platform.

    get_publisher(account) → an object with:
        .publish(post, account)     → the platform's id for the new post (str)
        .fetch_stats(post, account) → {"reach": …, "likes": …, …}

Which publisher you get:
    the account has a REAL connection          → that platform's publisher (Instagram, Facebook, Google, LinkedIn)
    no real connection, full mode (laptop)     → MockPublisher: pretend ("practice mode"), ids start with "mock_"
    no real connection, light mode (live site) → ManualPublisher: refuses, because nothing would really be posted.
                                                 The owner posts it by hand and taps "Mark as posted".

PublishError → something the owner can see and fix (no photo, key expired…). The post is
               marked "failed" with this message.
"""

import logging
import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session, object_session

from app import features
from app.integrations.base import IntegrationError
from app.models import Post, SocialAccount
from app.services import connection_service as connections
from app.services import media_service

logger = logging.getLogger("publishers")


class PublishError(Exception):
    """Shown to the owner. Keep messages short and actionable."""


class _BasePublisher(ABC):
    def __init__(self, db: Session = None):
        self.db = db

    @abstractmethod
    def publish(self, post: Post, account: SocialAccount) -> str:
        """Return the external post ID / URN."""

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        """Return a dict of stat fields that should be updated on the Post."""
        return {}


# ---------------------------------------------------------------------------
# Practice mode (laptop) and manual mode (live site, nothing connected)
# ---------------------------------------------------------------------------
class MockPublisher(_BasePublisher):
    """Pretends to publish, and invents numbers that grow over the first days, like a real post's do."""

    SHORT = {"instagram": "ig", "facebook": "fb", "google": "google", "linkedin": "li"}

    def publish(self, post: Post, account: SocialAccount) -> str:
        return f"mock_{self.SHORT.get(post.platform, post.platform)}_{post.id}"

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        published = post.published_at or datetime.now(timezone.utc)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        hours = max(1.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        growth = 1 - math.exp(-hours / 36)                     # fast at first, then it levels off
        base = 600 + (post.id or 0) * 37 % 900                 # a steady "size" per post
        reach = max(1, int(base * growth))
        return {"reach": reach, "likes": int(reach * 0.08), "comments": int(reach * 0.01),
                "shares": int(reach * 0.005), "saves": int(reach * 0.015),
                "profile_visits": int(reach * 0.02), "link_clicks": int(reach * 0.01)}


class ManualPublisher(_BasePublisher):
    """Live site with this platform not connected: never pretend a post went out."""

    def publish(self, post: Post, account: SocialAccount) -> str:
        raise PublishError(features.MANUAL_POST_MESSAGE)


# ---------------------------------------------------------------------------
# Helpers for the real publishers
# ---------------------------------------------------------------------------
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def _media_link(db: Session, post: Post, platform_label: str) -> str:
    """The post's photo/video link, checked: Instagram/Facebook/Google fetch it from the internet."""
    link = media_service.link_for(post, db)
    host = (urlparse(link).hostname or "") if link else ""
    if link and (host in LOCAL_HOSTS or host.startswith(("192.168.", "10."))):
        raise PublishError(f"{platform_label} can't fetch photos stored on this computer. Set PUBLIC_API_URL to "
                           f"your live https address first, then reschedule the post.")
    return link


def _with_hashtags(post: Post) -> str:
    caption = post.caption
    if post.hashtags:
        caption += "\n" + " ".join(f"#{h.lstrip('#')}" for h in post.hashtags)
    return caption


def _is_video(post: Post, link: str) -> bool:
    return post.kind in ("reel", "video") or link.lower().split("?")[0].endswith((".mp4", ".mov"))


def _call(db: Session, conn, action, *args):
    """Run a platform call; turn the platform's errors into messages the owner can read."""
    try:
        return connections.guarded(db, conn, action, *args)
    except IntegrationError as problem:
        raise PublishError(str(problem)) from problem


# ---------------------------------------------------------------------------
# Real publishers
# ---------------------------------------------------------------------------
class _InstagramPublisher(_BasePublisher):
    def publish(self, post: Post, account: SocialAccount) -> str:
        from app.integrations import instagram
        conn = connections.for_account(self.db, account)
        link = _media_link(self.db, post, "Instagram")
        if not link:
            raise PublishError("Instagram needs a photo or video. Add one and reschedule.")
        return _call(self.db, conn, instagram.publish, conn.external_id, connections.token(self.db, conn),
                     post.kind, _with_hashtags(post), link)

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        from app.integrations import instagram
        conn = connections.for_account(self.db, account)
        if conn is None or not post.external_id or post.external_id.startswith("mock_"):
            return {}
        try:
            return _call(self.db, conn, instagram.media_stats, post.external_id, connections.token(self.db, conn),
                         post.kind)
        except PublishError:
            return {}


class _FacebookPublisher(_BasePublisher):
    def publish(self, post: Post, account: SocialAccount) -> str:
        from app.integrations import meta
        conn = connections.for_account(self.db, account)
        link = _media_link(self.db, post, "Facebook")
        return _call(self.db, conn, meta.page_publish, conn.external_id, connections.token(self.db, conn),
                     _with_hashtags(post), link, _is_video(post, link))

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        from app.integrations import meta
        conn = connections.for_account(self.db, account)
        if conn is None or not post.external_id or post.external_id.startswith("mock_"):
            return {}
        try:
            return _call(self.db, conn, meta.page_post_stats, post.external_id, connections.token(self.db, conn))
        except PublishError:
            return {}


class _GooglePublisher(_BasePublisher):
    def publish(self, post: Post, account: SocialAccount) -> str:
        from app.integrations import google
        conn = connections.for_account(self.db, account)
        link = _media_link(self.db, post, "Google")
        return _call(self.db, conn, google.create_post, conn.external_id, connections.token(self.db, conn),
                     post.caption, link)


class _LinkedInPublisher(_BasePublisher):
    def publish(self, post: Post, account: SocialAccount) -> str:
        from app.integrations import linkedin
        conn = connections.for_account(self.db, account)
        link = _media_link(self.db, post, "LinkedIn")
        return _call(self.db, conn, linkedin.publish, connections.token(self.db, conn), conn.external_id,
                     post.caption, link)

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        from app.integrations import linkedin
        conn = connections.for_account(self.db, account)
        if conn is None or not post.external_id or post.external_id.startswith("mock_"):
            return {}
        try:
            return _call(self.db, conn, linkedin.post_stats, post.external_id, connections.token(self.db, conn))
        except PublishError:
            return {}


class _ReconnectPublisher(_BasePublisher):
    """The platform stopped accepting our key: say so, instead of trying and failing."""

    def __init__(self, db: Session, label: str):
        super().__init__(db)
        self.label = label

    def publish(self, post: Post, account: SocialAccount) -> str:
        raise PublishError(f"{self.label} needs reconnecting. Go to Settings → Connections and click Connect again.")


_REAL = {
    "instagram": _InstagramPublisher,
    "facebook": _FacebookPublisher,
    "google": _GooglePublisher,
    "linkedin": _LinkedInPublisher,
}


def get_publisher(account: SocialAccount, db: Session = None) -> _BasePublisher:
    """Return the right publisher for this social account (see the top of this file)."""
    _db = db or object_session(account)
    if _db is None:
        raise PublishError("Database session not available for publisher")
    real = _REAL.get(account.platform)
    conn = connections.for_account(_db, account)
    if real is not None and conn is not None and conn.mode == "real":
        if conn.status != "connected":
            return _ReconnectPublisher(_db, connections.LABELS.get(account.platform, account.platform.title()))
        return real(_db)
    if features.is_light():
        return ManualPublisher(_db)
    return MockPublisher(_db)
