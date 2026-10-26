"""
Uploading photos and videos to a business's media library.

What happens to an upload:
    1. Size check: photos up to 15 MB, videos up to 100 MB (settings), and the
       plan's storage space (Starter 1 GB, Growth 5 GB, Pro 20 GB).
    2. What IS it really? We read the first bytes, its "signature", and ignore
       the file name: a virus renamed "photo.jpg" is still refused.
    3. Photos are CLEANED:
         - turned the right way up (phones store rotation separately)
         - converted to JPEG (Instagram accepts only JPEG photos)
         - made at most 1440 px wide (Instagram's maximum)
         - hidden "EXIF" data removed: phone photos carry the GPS location
           where they were taken, the phone model, the time...
         - a small preview (thumbnail) is made for the library grid
         - Instagram feed posts must be between 4:5 (portrait) and 1.91:1 (wide).
           Normal phone photos are 3:4, a bit too tall! So we ALSO make an
           Instagram-ready crop (centred, trims a little top and bottom). Instagram
           feed posts use the crop; Stories, Facebook and Google use the full photo.
       Videos are kept as they are (MP4 or MOV).
    4. Friendly notes, e.g. "we made a 4:5 crop for Instagram".
"""

import io
import math
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Media, Post
from app.plans import PLANS
from app.services import billing_service, storage

MB = 1024 * 1024
INSTAGRAM_MAX_WIDTH = 1440
THUMB_SIZE = 400
VIDEO_BRANDS = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"MSNV", b"dash", b"qt  "}
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}


class MediaError(Exception):
    """Something to tell the owner, e.g. 'this isn't a photo or video we can use'."""


class TooLarge(MediaError):
    pass


def sniff(data: bytes) -> str:
    """What kind of file is this, judging by its first bytes?"""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in HEIC_BRANDS:
            return "heic"
        if brand in VIDEO_BRANDS:
            return "mov" if brand == b"qt  " else "mp4"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "unknown"


TALLEST, WIDEST = 4 / 5, 1.91            # Instagram feed limits (width ÷ height)


def instagram_crop(image: Image.Image) -> Optional[Image.Image]:
    """A centred crop that fits Instagram's feed, or None if the photo already fits."""
    ratio = image.width / image.height
    if ratio < TALLEST:                                  # too tall → trim top and bottom
        height = round(image.width / TALLEST)
        top = (image.height - height) // 2
        return image.crop((0, top, image.width, top + height))
    if ratio > WIDEST:                                   # too wide → trim the sides
        width = round(image.height * WIDEST)
        left = (image.width - width) // 2
        return image.crop((left, 0, left + width, image.height))
    return None


def _notes(width: int, height: int, cropped: Optional[Image.Image]) -> list[str]:
    notes = []
    if cropped is not None:
        shape = "4:5" if width / height < TALLEST else "1.91:1"
        trimmed = "top and bottom" if width / height < TALLEST else "sides"
        notes.append(f"Instagram feed posts can't be this {'tall' if shape == '4:5' else 'wide'}, so we made a {shape} "
                     f"crop for Instagram (a little trimmed from the {trimmed}). Stories, Facebook and Google "
                     "use the full photo.")
    if width < 320:
        notes.append(f"This photo is small ({width}px wide) and may look blurry. 1080px wide is ideal.")
    return notes


def _jpeg(image: Image.Image, quality: int = 88) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, optimize=True, progressive=True)    # no exif= → location data gone
    return out.getvalue()


def clean_photo(data: bytes) -> tuple[bytes, bytes, Optional[bytes], int, int, list[str]]:
    """→ (clean JPEG, thumbnail JPEG, Instagram crop JPEG or None, width, height, notes)"""
    try:
        with Image.open(io.BytesIO(data)) as check:
            check.verify()                                   # is the file complete and not corrupted?
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)               # right way up
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as problem:
        raise MediaError(f"This photo couldn't be opened ({problem.__class__.__name__}). Try saving it again as JPEG.")

    if image.mode in ("RGBA", "LA", "P"):                    # transparent PNG → white background
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    if image.width > INSTAGRAM_MAX_WIDTH:
        height = round(image.height * INSTAGRAM_MAX_WIDTH / image.width)
        image = image.resize((INSTAGRAM_MAX_WIDTH, height), Image.LANCZOS)

    thumb = image.copy()
    thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
    cropped = instagram_crop(image)
    return (_jpeg(image), _jpeg(thumb, 80), _jpeg(cropped) if cropped is not None else None,
            image.width, image.height, _notes(image.width, image.height, cropped))


# ---------------------------------------------------------------------------
# Storage space (per plan)
# ---------------------------------------------------------------------------
def used_bytes(db: Session, business_id: int) -> int:
    return db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0)).where(Media.business_id == business_id))


def check_space(db: Session, business_id: int, new_bytes: int) -> None:
    plan = billing_service.plan_for(db, business_id)
    if used_bytes(db, business_id) + new_bytes > plan.storage_mb * MB:
        bigger = sorted((p for p in PLANS.values() if p.storage_mb > plan.storage_mb), key=lambda p: p.storage_mb)
        tip = f" Upgrade to {bigger[0].name} for {bigger[0].storage_mb // 1024} GB, or delete old files." if bigger \
            else " Delete some old files first."
        raise billing_service.PlanLimit(f"Your media library is full ({plan.storage_mb // 1024} GB on the "
                                        f"{plan.name} plan).{tip}")


# ---------------------------------------------------------------------------
# Upload / delete
# ---------------------------------------------------------------------------
def upload(db: Session, business_id: int, data: bytes, original_name: str = "",
           user_id: Optional[int] = None) -> Media:
    kind = sniff(data)
    if kind == "heic":
        raise MediaError("iPhone HEIC photos aren't supported yet. On the iPhone: Settings → Camera → Formats → "
                         "'Most Compatible', or share the photo as JPEG.")
    if kind == "gif":
        raise MediaError("GIFs can't be posted on Instagram. Upload a JPEG/PNG photo or an MP4 video.")
    if kind == "unknown":
        raise MediaError("This isn't a photo or video we can use. Upload a JPEG, PNG or WEBP photo, or an MP4/MOV video.")

    is_video = kind in ("mp4", "mov")
    limit = (settings.max_video_mb if is_video else settings.max_photo_mb) * MB
    if len(data) > limit:
        raise TooLarge(f"Too big: {'videos' if is_video else 'photos'} can be up to "
                       f"{limit // MB} MB (this one is {math.ceil(len(data) / MB)} MB).")

    store = storage.get_storage()
    if is_video:
        files = {storage.new_key(business_id, kind): data}
        width = height = None
        warnings = ["For Instagram Reels use a vertical (9:16) MP4 between 3 and 90 seconds."]
        content_type, thumb_key, ig_key = ("video/quicktime" if kind == "mov" else "video/mp4"), None, None
    else:
        clean, thumb, fitted, width, height, warnings = clean_photo(data)
        key = storage.new_key(business_id, "jpg")
        thumb_key = storage.new_key(business_id, "jpg", thumb_of=key)
        files = {key: clean, thumb_key: thumb}
        ig_key = None
        if fitted is not None:
            ig_key = storage.new_key(business_id, "jpg", thumb_of=key, suffix="_ig")
            files[ig_key] = fitted
        content_type = "image/jpeg"

    size = sum(len(b) for b in files.values())
    check_space(db, business_id, size)
    for key, blob in files.items():
        store.save(key, blob)
    main_key = next(iter(files))
    media = Media(business_id=business_id, kind="video" if is_video else "photo", key=main_key, thumb_key=thumb_key,
                  instagram_key=ig_key,
                  content_type=content_type, original_name=(original_name or "")[:200], size_bytes=size,
                  width=width, height=height, warnings=warnings, uploaded_by=user_id)
    db.add(media)
    db.commit()
    return media


def delete(db: Session, media: Media) -> None:
    waiting = db.scalar(select(Post.id).where(Post.media_id == media.id, Post.status == "scheduled"))
    if waiting:
        raise MediaError(f"Post #{waiting} is scheduled with this file. Change that post first.")
    for post in db.scalars(select(Post).where(Post.media_id == media.id, Post.status != "published")):
        post.media_id, post.media_url = None, ""
    store = storage.get_storage()
    for key in (media.key, media.thumb_key, media.instagram_key):
        if key:
            store.delete(key)
    db.delete(media)
    db.commit()


def link_for(post: Post, db: Session) -> str:
    """The post's media link right now (library files always use the CURRENT public address).
    Instagram feed posts get the Instagram-ready crop when the photo needed one."""
    if post.media_id:
        media = db.get(Media, post.media_id)
        if media:
            if post.platform == "instagram" and post.kind != "story" and media.instagram_key:
                return storage.public_url(media.instagram_key)
            return storage.public_url(media.key)
    return post.media_url or ""


def attach(db: Session, post: Post, media_id: Optional[int]) -> None:
    """Put a library photo/video on a post (None = remove it)."""
    if media_id is None:
        post.media_id, post.media_url = None, ""
        return
    media = db.get(Media, media_id)
    if media is None or media.business_id != post.business_id:
        raise ValueError("That photo/video isn't in this business's media library")
    if post.kind in ("reel", "video") and media.kind != "video":
        raise ValueError(f"A {post.kind} needs a video, not a photo")
    if post.kind in ("photo", "carousel") and media.kind != "photo":
        raise ValueError(f"A {post.kind} post needs a photo, not a video")
    post.media_id, post.media_url = media.id, storage.public_url(media.key)
