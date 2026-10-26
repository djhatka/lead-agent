"""
Restore a nightly backup into an EMPTY database.

    .\.venv\Scripts\python.exe -m seed.restore_backup data\backups\backup-2026-10-19.jsonl.gz

On the live server (e.g. after creating a fresh Railway Postgres):
    railway run python -m seed.restore_backup /data/backups/backup-2026-10-19.jsonl.gz
"""

import argparse

from app.database import engine, migrate
from app.services.backup_service import restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a backup into an empty database")
    parser.add_argument("file")
    args = parser.parse_args()
    migrate()                                            # make sure the (empty) tables exist
    restored = restore_backup(engine, args.file)
    print(f"Restored {sum(restored.values())} rows into {len(restored)} tables.")


if __name__ == "__main__":
    main()
