"""
Nightly backups: a full copy of the database, every night at 3am (India time).

A backup is ONE compressed file, e.g. data/backups/backup-2026-10-19.jsonl.gz:
every row of every table, written as plain text (JSON lines). Plain text means
it works for SQLite and PostgreSQL alike, and any version can read it back.
The last BACKUP_KEEP_DAYS (14) days are kept; older files are deleted.

To restore (into an EMPTY database, e.g. a new Railway Postgres):
    python -m seed.restore_backup data/backups/backup-2026-10-19.jsonl.gz

Railway's own Postgres backups (Backups tab) are a second safety net: turn them on too.
"""

import gzip
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Date, DateTime, func, insert, select, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.database import Base

logger = logging.getLogger("backups")
IST = ZoneInfo("Asia/Kolkata")
FORMAT = "lead-agent-backup/1"


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _tables():
    from app import models  # noqa: F401  (registers every table)
    return Base.metadata.sorted_tables                    # parents before children


def create_backup(engine: Engine, folder: Optional[str] = None, day: Optional[date] = None) -> Path:
    folder_path = Path(folder or settings.backup_dir)
    folder_path.mkdir(parents=True, exist_ok=True)
    day = day or datetime.now(IST).date()
    final = folder_path / f"backup-{day.isoformat()}.jsonl.gz"
    temp = final.with_suffix(".part")
    counts = {}
    with engine.connect() as connection, gzip.open(temp, "wt", encoding="utf-8") as out:
        out.write(json.dumps({"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                              "database": engine.dialect.name}) + "\n")
        for table in _tables():
            rows = 0
            for row in connection.execute(select(table).order_by(*table.primary_key.columns)):
                out.write(json.dumps({"t": table.name, "r": {k: _plain(v) for k, v in row._mapping.items()}},
                                     ensure_ascii=False) + "\n")
                rows += 1
            counts[table.name] = rows
        out.write(json.dumps({"end": True, "counts": counts}) + "\n")   # proof the file is complete
    temp.replace(final)
    logger.info("Backup written: %s (%s rows)", final.name, sum(counts.values()))
    return final


def prune(folder: Optional[str] = None, keep_days: Optional[int] = None, today: Optional[date] = None) -> int:
    folder_path = Path(folder or settings.backup_dir)
    if not folder_path.exists():
        return 0
    cutoff = (today or datetime.now(IST).date()) - timedelta(days=keep_days or settings.backup_keep_days)
    removed = 0
    for file in folder_path.glob("backup-*.jsonl.gz"):
        try:
            made = date.fromisoformat(file.name[7:17])
        except ValueError:
            continue
        if made < cutoff:
            file.unlink()
            removed += 1
    return removed


def _convert(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    return value


def restore_backup(engine: Engine, path: str) -> dict[str, int]:
    """Load a backup into an EMPTY database (same tables, e.g. right after migrations)."""
    tables = {t.name: t for t in _tables()}
    with engine.begin() as connection:
        for table in tables.values():
            if connection.execute(select(func.count()).select_from(table)).scalar():
                raise ValueError(f"The database isn't empty (table '{table.name}' has rows). Restore into an empty one.")
        restored: dict[str, int] = {}
        finished = False
        with gzip.open(path, "rt", encoding="utf-8") as backup:
            header = json.loads(backup.readline())
            if header.get("format") != FORMAT:
                raise ValueError("This isn't one of our backup files")
            batch_table, batch = None, []

            def flush():
                if batch:
                    connection.execute(insert(tables[batch_table]), batch)
                    restored[batch_table] = restored.get(batch_table, 0) + len(batch)
                    batch.clear()

            for line in backup:
                item = json.loads(line)
                if item.get("end"):
                    finished = True
                    break
                if item["t"] != batch_table or len(batch) >= 500:
                    flush()
                    batch_table = item["t"]
                table = tables[item["t"]]
                batch.append({k: _convert(table.c[k], v) for k, v in item["r"].items() if k in table.c})
            flush()
        if not finished:
            raise ValueError("This backup file is incomplete (it was cut off)")
        if engine.dialect.name == "postgresql":           # make new ids continue after the restored ones
            for table in tables.values():
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement and restored.get(table.name):
                    connection.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"(SELECT MAX({pk[0].name}) FROM {table.name}))"))
    return restored


def nightly_backup_due(engine: Engine, now: Optional[datetime] = None) -> Optional[Path]:
    """Scheduler job: after 3am India time, make today's backup once, then tidy old ones."""
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    if local.hour < 3:
        return None
    if (Path(settings.backup_dir) / f"backup-{local.date().isoformat()}.jsonl.gz").exists():
        return None
    made = create_backup(engine, day=local.date())
    prune(today=local.date())
    return made


def list_backups(folder: Optional[str] = None) -> list[dict]:
    folder_path = Path(folder or settings.backup_dir)
    if not folder_path.exists():
        return []
    return [{"name": f.name, "size_kb": -(-f.stat().st_size // 1024)}
            for f in sorted(folder_path.glob("backup-*.jsonl.gz"), reverse=True)]
