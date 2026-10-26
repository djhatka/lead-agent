"""
Import customers from Excel or CSV.

    GET  /leads/import/template            a sample CSV with the right headings
    POST /leads/import?dry_run=true        PREVIEW: what would happen (nothing saved)
    POST /leads/import?dry_run=false       import for real

Form fields: file (the .xlsx / .csv), and optionally columns = JSON like
{"Mob": "phone", "Sr No": "skip"} to correct our column guesses.
Fields we understand: name, phone, email, source, service, message, status, value, date, area.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.access import get_current_user
from app.database import get_db
from app.models import User
from app.routers.businesses import business_or_404
from app.services import lead_import

router = APIRouter(prefix="/leads/import", tags=["Import"])


@router.get("/template")
def template():
    return Response(lead_import.template_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="customers-template.csv"'})


@router.post("", response_model=lead_import.ImportReport)
async def import_file(file: UploadFile = File(description="An Excel (.xlsx) or CSV file"),
                      dry_run: bool = True, columns: Optional[str] = Form(default=None),
                      business_id: Optional[int] = None, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        bid = business_or_404(business_id, db).id
    else:
        bid = user.business_id
    data = await file.read(lead_import.MAX_BYTES + 1)
    try:
        corrections = json.loads(columns) if columns else None
        if corrections is not None and not isinstance(corrections, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail='columns must look like {"Mobile No": "phone"}')
    try:
        return lead_import.run(db, bid, data, file.filename or "upload", dry_run=dry_run, columns=corrections)
    except lead_import.ImportError_ as problem:
        raise HTTPException(status_code=400, detail=str(problem))
