"""
Media library: the business's photos and videos.

    POST   /media                 upload one file (form field "file") → cleaned + saved
    GET    /media                 the library (newest first) + space used
    GET    /media/{id}            one file's details
    DELETE /media/{id}            delete (not while a scheduled post uses it)
    GET    /files/{key}           the file itself: PUBLIC, because Instagram/Facebook/Google
                                  fetch it when we publish (the name is random and unguessable)

Use a file on a post:  PATCH /posts/{id}  {"media_id": 12}
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import can_access, get_current_user
from app.config import settings
from app.database import get_db
from app.models import Media, User
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import billing_service, media_service, storage

public = APIRouter(tags=["Media"])
router = APIRouter(tags=["Media"])
TYPES = {"jpg": "image/jpeg", "mp4": "video/mp4", "mov": "video/quicktime"}


class MediaOut(BaseModel):
    id: int
    business_id: int
    kind: str
    url: str                     # use this as a post's photo/video
    thumbnail_url: Optional[str]
    instagram_url: Optional[str]  # the 4:5 / 1.91:1 crop Instagram feed posts will use (None = not needed)
    content_type: str
    original_name: str
    size_kb: int
    width: Optional[int]
    height: Optional[int]
    warnings: list[str]
    created_at: UTCDateTime


class Library(BaseModel):
    items: list[MediaOut]
    used_mb: float
    limit_mb: int


def _out(m: Media) -> MediaOut:
    return MediaOut(id=m.id, business_id=m.business_id, kind=m.kind, url=storage.public_url(m.key),
                    thumbnail_url=storage.public_url(m.thumb_key) if m.thumb_key else None,
                    instagram_url=storage.public_url(m.instagram_key) if m.instagram_key else None,
                    content_type=m.content_type, original_name=m.original_name, size_kb=-(-m.size_bytes // 1024),
                    width=m.width, height=m.height, warnings=m.warnings or [], created_at=m.created_at)


def _business_id(user: User, business_id: Optional[int], db: Session) -> int:
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_or_404(business_id, db).id
    return user.business_id


def media_or_404(media_id: int, db: Session) -> Media:
    media = db.get(Media, media_id)
    if media is None or not can_access(media.business_id):
        raise HTTPException(status_code=404, detail=f"File {media_id} not found")
    return media


@router.post("/media", response_model=MediaOut, status_code=201)
async def upload(file: UploadFile = File(description="A JPEG/PNG/WEBP photo or an MP4/MOV video"),
                 business_id: Optional[int] = None, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    bid = _business_id(user, business_id, db)
    limit = max(settings.max_photo_mb, settings.max_video_mb) * media_service.MB
    data = await file.read(limit + 1)                       # never read more than the limit into memory
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Too big: the largest allowed file is {limit // media_service.MB} MB")
    try:
        media = media_service.upload(db, bid, data, file.filename or "", user.id)
    except media_service.TooLarge as problem:
        raise HTTPException(status_code=413, detail=str(problem))
    except media_service.MediaError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    except billing_service.PlanLimit as problem:
        raise HTTPException(status_code=403, detail=str(problem))
    return _out(media)


@router.get("/media", response_model=Library)
def library(business_id: Optional[int] = None, kind: Optional[Literal["photo", "video"]] = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bid = _business_id(user, business_id, db)
    query = select(Media).where(Media.business_id == bid)
    if kind:
        query = query.where(Media.kind == kind)
    items = [_out(m) for m in db.scalars(query.order_by(Media.id.desc()))]
    used = media_service.used_bytes(db, bid) / media_service.MB
    return Library(items=items, used_mb=round(used, 2), limit_mb=billing_service.plan_for(db, bid).storage_mb)


@router.get("/media/{media_id}", response_model=MediaOut)
def one(media_id: int, db: Session = Depends(get_db)):
    return _out(media_or_404(media_id, db))


@router.delete("/media/{media_id}", status_code=204)
def delete(media_id: int, db: Session = Depends(get_db)):
    try:
        media_service.delete(db, media_or_404(media_id, db))
    except media_service.MediaError as problem:
        raise HTTPException(status_code=400, detail=str(problem))


@public.get("/files/{business_id}/{name}", include_in_schema=False)
def serve(business_id: int, name: str):
    key = f"{business_id}/{name}"
    try:
        path = storage.get_storage().path(key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type=TYPES[name.rsplit(".", 1)[1]], headers={
        "Cache-Control": "public, max-age=31536000, immutable",    # the name never changes → cache for a year
        "X-Content-Type-Options": "nosniff",                       # browsers must treat it as a photo/video only
        "Content-Disposition": "inline"})
