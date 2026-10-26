"""
Task 22 checks: photo and video uploads (the media library).

Photos are made on the spot with Pillow; files go to a temporary folder.
"""

import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.models import Post, SocialAccount
from app.services.scheduler_service import publish_due
from tests.test_connections import FakePlatforms, connect, fake, real  # noqa: F401  (fixtures)

GPS = 0x8825
ORIENTATION = 0x0112


@pytest.fixture(autouse=True)
def media_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"))
    return tmp_path / "media"


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def phone_photo(size=(3000, 4000), rotate=True, gps=True, fmt="JPEG", mode="RGB", color="red") -> bytes:
    image = Image.new(mode, size, color)
    exif = image.getexif()
    if rotate:
        exif[ORIENTATION] = 6                       # "turn me 90°": how phones store sideways photos
    if gps:
        exif[GPS] = {1: "N", 2: (28.0, 39.0, 0.0), 3: "E", 4: (77.0, 13.0, 0.0)}   # Delhi
    out = io.BytesIO()
    image.save(out, fmt, exif=exif) if fmt == "JPEG" else image.save(out, fmt)
    return out.getvalue()


def upload(client, headers, data: bytes, name="photo.jpg", **params):
    return client.post("/media", headers=headers, params=params, files={"file": (name, data, "application/octet-stream")})


# ---------------------------------------------------------------------------
# Photos are cleaned
# ---------------------------------------------------------------------------
def test_phone_photo_is_cleaned(raw_client):
    gym = login(raw_client)
    r = upload(raw_client, gym, phone_photo())
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["kind"] == "photo" and m["content_type"] == "image/jpeg"
    assert (m["width"], m["height"]) == (1440, 1080)        # turned the right way up, Instagram width
    assert m["url"].startswith("http://127.0.0.1:8000/files/1/") and m["url"].endswith(".jpg")
    assert m["thumbnail_url"].endswith("_thumb.jpg")

    served = raw_client.get(m["url"].removeprefix("http://127.0.0.1:8000"))       # public: no login
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    assert served.headers["x-content-type-options"] == "nosniff"
    clean = Image.open(io.BytesIO(served.content))
    assert clean.format == "JPEG" and GPS not in clean.getexif() and ORIENTATION not in clean.getexif()
    thumb = raw_client.get(m["thumbnail_url"].removeprefix("http://127.0.0.1:8000"))
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 400


def test_transparent_png_gets_a_white_background(raw_client):
    r = upload(raw_client, login(raw_client), phone_photo((1080, 1080), fmt="PNG", mode="RGBA", color=(0, 0, 0, 0)),
               name="logo.png")
    served = raw_client.get(r.json()["url"].removeprefix("http://127.0.0.1:8000"))
    assert Image.open(io.BytesIO(served.content)).getpixel((5, 5)) >= (250, 250, 250)


def _size(client, url):
    return Image.open(io.BytesIO(client.get(url.removeprefix("http://127.0.0.1:8000")).content)).size


def test_instagram_ready_crops(raw_client):
    gym = login(raw_client)
    phone = upload(raw_client, gym, phone_photo((3024, 4032), rotate=False)).json()     # normal phone photo, 3:4
    assert _size(raw_client, phone["url"]) == (1440, 1920)                               # full photo kept
    assert _size(raw_client, phone["instagram_url"]) == (1440, 1800)                     # 4:5 crop for the feed
    assert "4:5" in phone["warnings"][0] and "top and bottom" in phone["warnings"][0]

    banner = upload(raw_client, gym, phone_photo((3000, 1000), rotate=False)).json()
    w, h = _size(raw_client, banner["instagram_url"])
    assert abs(w / h - 1.91) < 0.01 and "sides" in banner["warnings"][0]

    square = upload(raw_client, gym, phone_photo((1080, 1080), rotate=False)).json()
    assert square["warnings"] == [] and square["instagram_url"] is None


# ---------------------------------------------------------------------------
# Only real photos/videos, within limits
# ---------------------------------------------------------------------------
def test_files_are_judged_by_their_contents_not_their_name(raw_client):
    gym = login(raw_client)
    fake_photo = upload(raw_client, gym, b"MZ\x90\x00 definitely not a photo", name="photo.jpg")
    assert fake_photo.status_code == 400 and "isn't a photo or video" in fake_photo.json()["detail"]
    heic = upload(raw_client, gym, b"\x00\x00\x00\x18ftypheic" + b"\x00" * 100, name="IMG_0001.HEIC")
    assert heic.status_code == 400 and "Most Compatible" in heic.json()["detail"]
    gif = upload(raw_client, gym, b"GIF89a" + b"\x00" * 50, name="fun.gif")
    assert gif.status_code == 400 and "GIF" in gif.json()["detail"]
    broken = upload(raw_client, gym, phone_photo()[:5000])                     # cut off half-way
    assert broken.status_code == 400 and "couldn't be opened" in broken.json()["detail"]
    assert upload(raw_client, gym, b"").status_code == 400


def test_video_upload(raw_client):
    mp4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 2000
    m = upload(raw_client, login(raw_client), mp4, name="reel.mp4").json()
    assert m["kind"] == "video" and m["content_type"] == "video/mp4" and m["url"].endswith(".mp4")
    assert m["thumbnail_url"] is None and "9:16" in m["warnings"][0]
    served = raw_client.get(m["url"].removeprefix("http://127.0.0.1:8000"))
    assert served.headers["content-type"] == "video/mp4" and served.content == mp4


def test_size_limit(raw_client, monkeypatch):
    monkeypatch.setattr(settings, "max_photo_mb", 0)
    r = upload(raw_client, login(raw_client), phone_photo((500, 500)))
    assert r.status_code == 413 and "photos can be up to 0 MB" in r.json()["detail"]


def test_library_full(raw_client, monkeypatch):
    from app.services import media_service
    monkeypatch.setattr(media_service, "used_bytes", lambda db, business_id: 5120 * media_service.MB)   # 5 GB used
    r = upload(raw_client, login(raw_client), phone_photo((500, 500)))
    assert r.status_code == 403 and "media library is full" in r.json()["detail"] and "Upgrade to Pro" in r.json()["detail"]


def test_space_used_shows_in_billing(raw_client):
    gym = login(raw_client)
    upload(raw_client, gym, phone_photo())
    assert raw_client.get("/billing/status", headers=gym).json()["used"]["storage_mb"] >= 1
    lib = raw_client.get("/media", headers=gym).json()
    assert lib["limit_mb"] == 5120 and lib["used_mb"] > 0 and len(lib["items"]) == 1


# ---------------------------------------------------------------------------
# Each business has its own library
# ---------------------------------------------------------------------------
def test_libraries_are_private(raw_client):
    m = upload(raw_client, login(raw_client), phone_photo()).json()
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get(f"/media/{m['id']}", headers=garage).status_code == 404
    assert raw_client.delete(f"/media/{m['id']}", headers=garage).status_code == 404
    assert raw_client.get("/media", headers=garage).json()["items"] == []
    staff = login(raw_client, "staff@demo.in")                                   # gym staff can use it
    assert raw_client.get(f"/media/{m['id']}", headers=staff).status_code == 200
    assert upload(raw_client, staff, phone_photo((800, 800))).status_code == 201


def test_no_sneaking_around_the_files_folder(raw_client):
    for bad in ("/files/1/..%2F..%2F.env", "/files/1/notours.txt", "/files/1/" + "a" * 32 + ".html"):
        assert raw_client.get(bad).status_code == 404


# ---------------------------------------------------------------------------
# Using library files on posts
# ---------------------------------------------------------------------------
def _gym_post(db, platform="instagram", kind="photo", **fields) -> Post:
    account = db.scalar(select(SocialAccount).where(SocialAccount.business_id == 1, SocialAccount.platform == platform))
    post = Post(business_id=1, account_id=account.id, platform=platform, kind=kind, caption="Diwali offer 🪔", **fields)
    db.add(post)
    db.commit()
    return post


def test_attach_photo_to_post(raw_client, db_session):
    gym = login(raw_client)
    photo = upload(raw_client, gym, phone_photo()).json()
    post = _gym_post(db_session)
    r = raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]}).json()
    assert r["media_id"] == photo["id"] and r["media_url"] == photo["url"]

    garage_photo = upload(raw_client, login(raw_client, "garage@demo.in"), phone_photo()).json()
    other = raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": garage_photo["id"]})
    assert other.status_code == 400 and "isn't in this business" in other.json()["detail"]

    video = upload(raw_client, gym, b"\x00\x00\x00\x20ftypisom" + b"\x00" * 500, name="v.mp4").json()
    wrong = raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": video["id"]})
    assert wrong.status_code == 400 and "needs a photo" in wrong.json()["detail"]
    reel = _gym_post(db_session, kind="reel")
    assert raw_client.patch(f"/posts/{reel.id}", headers=gym, json={"media_id": photo["id"]}).status_code == 400
    assert raw_client.patch(f"/posts/{reel.id}", headers=gym, json={"media_id": video["id"]}).status_code == 200

    cleared = raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": None}).json()
    assert cleared["media_id"] is None and cleared["media_url"] == ""


def test_create_post_with_a_library_photo(raw_client, db_session):
    gym = login(raw_client)
    photo = upload(raw_client, gym, phone_photo()).json()
    account = db_session.scalar(select(SocialAccount).where(SocialAccount.business_id == 1,
                                                            SocialAccount.platform == "instagram"))
    r = raw_client.post("/posts", headers=gym, json={"account_id": account.id, "caption": "New batch!",
                                                     "media_id": photo["id"]})
    assert r.status_code == 201 and r.json()["media_url"] == photo["url"]


def test_delete_rules(raw_client, db_session, media_folder):
    gym = login(raw_client)
    photo = upload(raw_client, gym, phone_photo()).json()
    post = _gym_post(db_session)
    raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]})
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert raw_client.post(f"/posts/{post.id}/schedule", headers=gym, json={"scheduled_for": when}).status_code == 200

    blocked = raw_client.delete(f"/media/{photo['id']}", headers=gym)
    assert blocked.status_code == 400 and f"Post #{post.id} is scheduled" in blocked.json()["detail"]
    raw_client.post(f"/posts/{post.id}/unschedule", headers=gym)
    assert raw_client.delete(f"/media/{photo['id']}", headers=gym).status_code == 204
    assert raw_client.get(photo["url"].removeprefix("http://127.0.0.1:8000")).status_code == 404   # file gone
    assert list(media_folder.rglob("*.jpg")) == []                                                 # thumbnail too
    assert raw_client.get(f"/posts/{post.id}", headers=gym).json()["media_url"] == ""


# ---------------------------------------------------------------------------
# Publishing with a library photo
# ---------------------------------------------------------------------------
def test_platforms_cant_fetch_from_a_laptop(raw_client, db_session, real):
    gym = login(raw_client)
    connect(raw_client, gym, "instagram")
    photo = upload(raw_client, gym, phone_photo((1080, 1350), rotate=False)).json()
    post = _gym_post(db_session, status="scheduled", scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1))
    raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]})
    publish_due(db_session)
    assert post.status == "failed" and "PUBLIC_API_URL" in post.publish_error
    assert not real.called("POST", "/media")                         # Instagram was never asked


def test_published_with_the_live_address(raw_client, db_session, real, monkeypatch):
    gym = login(raw_client)
    connect(raw_client, gym, "instagram")
    photo = upload(raw_client, gym, phone_photo((1080, 1350), rotate=False)).json()       # already 4:5: no crop
    monkeypatch.setattr(settings, "public_api_url", "https://app.leadagent.in")      # the server is online now
    post = _gym_post(db_session, status="scheduled", scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1))
    raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]})
    publish_due(db_session)
    assert post.status == "published", post.publish_error
    sent = real.called("POST", "/media")[0]["body"]["image_url"]
    assert sent.startswith("https://app.leadagent.in/files/1/") and sent.endswith(photo["url"].rsplit("/", 1)[1])


def test_instagram_gets_the_crop_and_facebook_the_full_photo(raw_client, db_session, real, monkeypatch):
    gym = login(raw_client)
    connect(raw_client, gym, "instagram")
    connect(raw_client, gym, "facebook")
    photo = upload(raw_client, gym, phone_photo((3024, 4032), rotate=False)).json()
    monkeypatch.setattr(settings, "public_api_url", "https://app.leadagent.in")
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    ig = _gym_post(db_session, status="scheduled", scheduled_for=due)
    fb = _gym_post(db_session, platform="facebook", status="scheduled", scheduled_for=due)
    for post in (ig, fb):
        raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]})
    publish_due(db_session)
    assert ig.status == fb.status == "published"
    assert real.called("POST", "/media")[0]["body"]["image_url"].endswith("_ig.jpg")
    assert not real.called("POST", "PAGE1/photos")[0]["body"]["url"].endswith("_ig.jpg")


def test_published_post_keeps_its_photo(raw_client, db_session):
    gym = login(raw_client)
    photo = upload(raw_client, gym, phone_photo((1080, 1080), rotate=False)).json()
    post = _gym_post(db_session, status="published", published_at=datetime.now(timezone.utc))
    r = raw_client.patch(f"/posts/{post.id}", headers=gym, json={"media_id": photo["id"]})
    assert r.status_code == 400 and "already published" in r.json()["detail"]

