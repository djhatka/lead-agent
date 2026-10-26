"""
Storage: where uploaded photo/video FILES live (the media table only keeps notes about them).

For now: a folder on the server's disk (settings.media_dir, i.e. backend/data/media/).
When the website goes live we can switch to cloud storage (e.g. Cloudflare R2 or
AWS S3) by writing one more class with the same three buttons: save, path, delete.
Nothing else in the app needs to change.

Every file gets an unguessable name like "1/9f2c4b...e1.jpg" (business 1).
Files must be PUBLIC (Instagram/Google fetch them by their link when we publish),
so the random name is what keeps other people from browsing a library.
"""

import os
import re
import uuid
from pathlib import Path

from app.config import settings

KEY_PATTERN = re.compile(r"^\d{1,10}/[0-9a-f]{32}(_thumb|_ig)?\.(jpg|mp4|mov)$")


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def save(self, key: str, data: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")      # write fully first, then rename: never half a file
        temp.write_bytes(data)
        os.replace(temp, path)

    def path(self, key: str) -> Path:
        if not KEY_PATTERN.match(key):                      # blocks tricks like "../../.env"
            raise ValueError("Bad file name")
        return self.root / key

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass


def new_key(business_id: int, extension: str, thumb_of: str | None = None, suffix: str = "_thumb") -> str:
    if thumb_of:                                  # a variant of another file: same name + "_thumb" / "_ig"
        return thumb_of.rsplit(".", 1)[0] + f"{suffix}.jpg"
    return f"{business_id}/{uuid.uuid4().hex}.{extension}"


def public_url(key: str) -> str:
    return f"{settings.public_api_url.rstrip('/')}/files/{key}"


def get_storage() -> LocalStorage:
    return LocalStorage(settings.media_dir)
