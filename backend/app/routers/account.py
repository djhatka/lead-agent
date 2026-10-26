"""
Your data rights + the go-live checklist.

    GET  /account/export     download everything as a .zip (owner)
    POST /account/delete     delete the business and all its data (owner; password + "DELETE")
    GET  /admin/launch-check (admin) which settings are still on demo values
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import require_admin, require_owner
from app.database import get_db
from app.models import Business, User
from app.routers.businesses import business_or_404
from app.services import account_service, email_service, launch_check

router = APIRouter(tags=["Your data"])


def _business_id(user: User, business_id: Optional[int], db: Session) -> int:
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_or_404(business_id, db).id
    return user.business_id


@router.get("/account/export")
def export(business_id: Optional[int] = None, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    bid = _business_id(owner, business_id, db)
    name = "".join(ch if ch.isalnum() else "-" for ch in db.get(Business, bid).name.lower()).strip("-")
    return Response(account_service.export_zip(db, bid), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}-data-{date.today()}.zip"'})


class DeleteIn(BaseModel):
    password: str = Field(max_length=128)
    confirm: str = Field(max_length=20, description='Type "DELETE"')


@router.post("/account/delete")
def delete_account(body: DeleteIn, background: BackgroundTasks, business_id: Optional[int] = None,
                   owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    bid = _business_id(owner, business_id, db)
    try:
        account_service.delete_business(db, owner, bid, body.password, body.confirm)
    except account_service.AccountError as problem:
        raise HTTPException(status_code=400, detail=str(problem))
    background.add_task(email_service.deliver_in_background)
    return {"deleted": True, "message": "Your account and all its data have been deleted."}


@router.get("/admin/launch-check")
def check(_admin: User = Depends(require_admin)):
    items = launch_check.checks()
    blocking = [i["item"] for i in items if i["must_have"] and not i["ok"]]
    return {"ready": not blocking, "blocking": blocking, "items": items}


@router.get("/admin/backups")
def backups(_admin: User = Depends(require_admin)):
    """The nightly backups on the server (newest first). Download one now and then to keep a copy elsewhere."""
    from app.services import backup_service
    return {"folder": backup_service.settings.backup_dir, "keep_days": backup_service.settings.backup_keep_days,
            "backups": backup_service.list_backups()}


@router.post("/admin/backups/run")
def backup_now(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.services import backup_service
    made = backup_service.create_backup(db.get_bind())
    return {"created": made.name}


@router.get("/admin/backups/{name}")
def download_backup(name: str, _admin: User = Depends(require_admin)):
    import re
    from fastapi.responses import FileResponse
    from app.services import backup_service
    if not re.fullmatch(r"backup-\d{4}-\d{2}-\d{2}\.jsonl\.gz", name):
        raise HTTPException(status_code=404, detail="Backup not found")
    path = backup_service.Path(backup_service.settings.backup_dir) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/gzip", filename=name)

