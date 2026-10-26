"""
Publishers: the ONE place that (1) publishes a post and (2) reads its numbers back.

    MockPublisher       accounts not connected for real (or mock connections):
                        pretends to publish and invents believable numbers
    InstagramPublisher  a connected Instagram (photo/reel/story via a public media link)
    FacebookPublisher   a connected Facebook Page (photo, video or text)
    GooglePublisher     a connected Google Business Profile ("Updates" posts)

    publisher.publish(post, account)     → the platform's id for the new post
    publisher.fetch_stats(post, account) → {"reach": ..., "likes": ..., ...}

get_publisher() picks the right one by looking up the account's connection.
"""

import random
from datetime import datetime, timezone

from sqlalchemy.orm import object_session

from app.integrations import google, instagram, meta
from app.integrations.base import IntegrationError
from app.models import Post, SocialAccount


class PublishError(Exception):
    """Publishing failed, e.g. the platform rejected the post or was down."""


def _caption(post: Post) -> str:
    tags = " ".join(f"#{t}" for t in (post.hashtags or []))
    return f"{post.caption}\n\n{tags}".strip() if tags else post.caption


class MockPublisher:
    """Pretend platform. Deterministic: the same post always gets the same numbers."""

    # How much each format / message type tends to reach (same idea as the demo data)
    KIND_REACH = {"reel": 2.0, "video": 1.5, "carousel": 1.2, "photo": 1.0, "text": 0.6, "story": 0.5}
    PILLAR_REACH = {"trend": 2.2, "transformation": 1.6, "festival": 1.1, "offer": 1.0,
                    "tips": 0.9, "behind_the_scenes": 0.8, "testimonial": 0.7}

    def publish(self, post: Post, account: SocialAccount) -> str:
        if post.kind != "story" and not post.caption.strip():
            raise PublishError("The post has no caption")
        return f"mock_{account.platform}_{post.id}"

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        r = random.Random(post.id)                              # same post → same "final" numbers
        followers = account.followers or 300
        final_reach = (followers * r.uniform(0.15, 0.4) * self.KIND_REACH.get(post.kind, 1.0)
                       * self.PILLAR_REACH.get(post.pillar, 1.0) * r.uniform(0.6, 1.5))

        # Real posts get most of their reach in the first 1-3 days, then slow down
        published = post.published_at if post.published_at.tzinfo else post.published_at.replace(tzinfo=timezone.utc)
        hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        share = 1 - 0.5 ** (hours / 24)                         # 50% after 1 day, 75% after 2...
        reach = int(final_reach * share)
        return {
            "reach": reach,
            "likes": int(reach * r.uniform(0.03, 0.08)),
            "comments": int(reach * r.uniform(0.002, 0.01)),
            "shares": int(reach * r.uniform(0.001, 0.006)),
            "saves": int(reach * r.uniform(0.002, 0.01)),
            "profile_visits": int(reach * r.uniform(0.01, 0.03)),
            "link_clicks": int(reach * r.uniform(0.002, 0.01)),
        }


class _Real:
    """Shared by the real publishers: the connection's key + 'reconnect' handling."""

    def __init__(self, conn):
        self.conn = conn

    def _run(self, action, *args):
        from app.services import connection_service as connections
        db = object_session(self.conn)
        try:
            return connections.guarded(db, self.conn, action, *args)
        except IntegrationError as problem:
            raise PublishError(str(problem)) from problem

    def _key(self) -> str:
        from app.services import connection_service as connections
        try:
            return connections.token(object_session(self.conn), self.conn)
        except IntegrationError as problem:
            raise PublishError(str(problem)) from problem


def _media(post: Post) -> str:
    """The post's photo/video link. Platforms fetch it themselves, so it must be a
    public https address, not this laptop (127.0.0.1 / localhost)."""
    from app.services.media_service import link_for
    link = link_for(post, object_session(post))
    if link and (not link.startswith("https://") or "://localhost" in link or "://127.0.0.1" in link):
        raise PublishError("The platforms can't fetch photos from your computer. Put the server online "
                           "(set PUBLIC_API_URL to its https address) and try again.")
    return link


class InstagramPublisher(_Real):
    def publish(self, post: Post, account: SocialAccount) -> str:
        return self._run(instagram.publish, self.conn.external_id, self._key(), post.kind, _caption(post), _media(post))

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        return self._run(instagram.media_stats, post.external_id, self._key(), post.kind)


class FacebookPublisher(_Real):
    def publish(self, post: Post, account: SocialAccount) -> str:
        if not post.caption.strip() and not post.media_url:
            raise PublishError("The post has no caption")
        return self._run(meta.page_publish, self.conn.external_id, self._key(), _caption(post), _media(post),
                         post.kind in ("reel", "video"))

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        return self._run(meta.page_post_stats, post.external_id, self._key())


class GooglePublisher(_Real):
    def publish(self, post: Post, account: SocialAccount) -> str:
        if not post.caption.strip():
            raise PublishError("The post has no caption")
        return self._run(google.create_post, self.conn.external_id, self._key(), post.caption, _media(post))

    def fetch_stats(self, post: Post, account: SocialAccount) -> dict:
        return {}                     # Google doesn't give per-post numbers through this API


REAL = {"instagram": InstagramPublisher, "facebook": FacebookPublisher, "google": GooglePublisher}


def get_publisher(account: SocialAccount):
    """The real publisher for an account connected for real; otherwise the mock."""
    db = object_session(account)
    if db is not None and account.connected and account.platform in REAL:
        from app.services import connection_service as connections
        conn = connections.for_account(db, account)
        if conn is not None and conn.mode == "real":
            if conn.status != "connected":
                return _NeedsReconnect(account.platform)
            return REAL[account.platform](conn)
    return MockPublisher()


class _NeedsReconnect:
    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, post, account):
        raise PublishError(f"Your {self.platform} connection needs reconnecting (Settings → Connections)")

    def fetch_stats(self, post, account):
        raise PublishError("connection needs reconnecting")
