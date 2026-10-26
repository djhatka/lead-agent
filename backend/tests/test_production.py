"""
Task 26 checks: the live-server safety rules and the nightly backups.

The backup test does the real thing: back up the demo database, restore it
into a brand-new empty database, and compare every table. (With
TEST_DATABASE_URL set, it runs on PostgreSQL too.)
"""

import gzip
import json
import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app import database
from app.config import settings
from app.database import Base, make_engine
from app.models import Lead, Payment, Subscription, User
from app.production import startup_problems
from app.services import backup_service


def login(client, email="admin@demo.in", password="admin1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def backups(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    return tmp_path / "backups"


@pytest.fixture
def empty_engine(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if url:                                    # a second, separate PostgreSQL database
        url = url.replace("/leadtest", "/leadtest_restore")
    engine = make_engine(url or f"sqlite:///{tmp_path / 'restored.db'}")
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    monkeypatch.setattr(database, "engine", engine)
    database.migrate()                         # empty tables, like a brand-new server
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
def test_backup_and_restore_round_trip(db_session, backups, empty_engine):
    path = backup_service.create_backup(db_session.get_bind(), day=date(2026, 10, 19))
    assert path.name == "backup-2026-10-19.jsonl.gz"
    restored = backup_service.restore_backup(empty_engine, str(path))

    with empty_engine.connect() as new:
        for table in Base.metadata.sorted_tables:
            before = db_session.execute(select(func.count()).select_from(table)).scalar()
            after = new.execute(select(func.count()).select_from(table)).scalar()
            assert before == after, f"{table.name}: {before} rows before, {after} after"
        original = db_session.scalar(select(Lead).order_by(Lead.id.desc()).limit(1))
        copy = new.execute(select(Lead.__table__).where(Lead.id == original.id)).mappings().one()
        assert copy["name"] == original.name and copy["details"] == original.details
        assert copy["created_at"].replace(tzinfo=None) == original.created_at.replace(tzinfo=None)
    assert restored["leads"] == 120

    # New rows after a restore get fresh ids (no clash with restored ones)
    from sqlalchemy.orm import Session
    with Session(empty_engine) as s:
        user = User(email="new@owner.in", name="New Owner", password_hash="x", role="admin")
        s.add(user)
        s.commit()
        assert user.id > db_session.scalar(select(func.max(User.id)))


def test_restore_refuses_a_database_with_data(db_session, backups):
    path = backup_service.create_backup(db_session.get_bind())
    with pytest.raises(ValueError, match="isn't empty"):
        backup_service.restore_backup(db_session.get_bind(), str(path))


def test_cut_off_backup_is_refused(db_session, backups, empty_engine):
    path = backup_service.create_backup(db_session.get_bind())
    lines = gzip.open(path, "rt", encoding="utf-8").read().splitlines()
    with gzip.open(path, "wt", encoding="utf-8") as broken:
        broken.write("\n".join(lines[: len(lines) // 2]) + "\n")
    with pytest.raises(ValueError, match="incomplete"):
        backup_service.restore_backup(empty_engine, str(path))


def test_nightly_schedule_and_cleanup(db_session, backups):
    engine = db_session.get_bind()
    two_am = datetime(2026, 10, 19, 20, 30, tzinfo=timezone.utc)        # 2am India time (20 Oct)
    assert backup_service.nightly_backup_due(engine, now=two_am) is None
    three_am = datetime(2026, 10, 19, 21, 35, tzinfo=timezone.utc)      # 3:05am India time
    assert backup_service.nightly_backup_due(engine, now=three_am).name == "backup-2026-10-20.jsonl.gz"
    assert backup_service.nightly_backup_due(engine, now=three_am) is None             # once a day
    for old in ("2026-09-01", "2026-10-10"):
        (backups / f"backup-{old}.jsonl.gz").write_bytes(b"x")
    assert backup_service.prune(today=date(2026, 10, 20)) == 1                         # only > 14 days old
    assert sorted(b["name"] for b in backup_service.list_backups()) == [
        "backup-2026-10-10.jsonl.gz", "backup-2026-10-20.jsonl.gz"]


def test_backups_never_contain_plain_keys(db_session, backups):
    path = backup_service.create_backup(db_session.get_bind())
    text = gzip.open(path, "rt", encoding="utf-8").read()
    first = json.loads(text.splitlines()[0])
    assert first["format"] == "lead-agent-backup/1"
    assert "demo1234" not in text                                                     # only password hashes


def test_admin_backup_endpoints(raw_client, backups):
    admin = login(raw_client)
    made = raw_client.post("/admin/backups/run", headers=admin).json()["created"]
    listed = raw_client.get("/admin/backups", headers=admin).json()["backups"]
    assert listed[0]["name"] == made
    download = raw_client.get(f"/admin/backups/{made}", headers=admin)
    assert download.status_code == 200 and download.content[:2] == b"\x1f\x8b"         # a gzip file
    assert raw_client.get("/admin/backups/..%2F.env", headers=admin).status_code == 404
    assert raw_client.get("/admin/backups", headers=login(raw_client, "gym@demo.in", "demo1234")).status_code == 403


# ---------------------------------------------------------------------------
# Live-server safety
# ---------------------------------------------------------------------------
def test_live_server_refuses_unsafe_settings(db_session, monkeypatch):
    problems = startup_problems(db_session)
    assert any("SECRET_KEY" in p for p in problems)
    assert any("PUBLIC_API_URL" in p for p in problems)
    assert any("Demo accounts" in p for p in problems)                                # the demo data is loaded

    monkeypatch.setattr(settings, "secret_key", "k" * 48)
    monkeypatch.setattr(settings, "public_api_url", "https://api.leadintel.in")
    for user in db_session.scalars(select(User).where(User.email.like("%@demo.in"))):
        user.email = user.email.replace("@demo.in", "@ironpulse.in")
    db_session.commit()
    assert startup_problems(db_session) == []


def test_demo_data_script_refuses_the_live_server(monkeypatch):
    from seed import seed_data
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(SystemExit, match="LIVE server"):
        seed_data.main()


def test_security_headers(raw_client, monkeypatch):
    page = raw_client.get("/")
    assert page.headers["x-frame-options"] == "DENY" and page.headers["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" not in page.headers                            # laptop: plain http is fine
    monkeypatch.setattr(settings, "environment", "production")
    assert "max-age=31536000" in raw_client.get("/").headers["strict-transport-security"]


def test_health_checks_the_database(raw_client):
    r = raw_client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "ok" and r.json()["environment"] == "development"


def test_one_time_admin_setup(db_session, monkeypatch):
    from app.auth.passwords import verify_password
    from app.production import bootstrap_admin
    assert bootstrap_admin(db_session) == ""                                          # nothing set: nothing done
    monkeypatch.setattr(settings, "bootstrap_admin_email", " Anmol@LeadIntel.in ")
    monkeypatch.setattr(settings, "bootstrap_admin_password", "short")
    assert "at least 12" in bootstrap_admin(db_session)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "a-long-real-password")
    assert "created" in bootstrap_admin(db_session)
    admin = db_session.scalar(select(User).where(User.email == "anmol@leadintel.in"))
    assert admin.role == "admin" and verify_password("a-long-real-password", admin.password_hash)
    assert "already exists" in bootstrap_admin(db_session)                            # never twice


def test_live_server_makes_its_own_secret_key(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / ".secret_key"))
    live = config.Settings(environment="production")
    config._own_secret_key(live)
    first = live.secret_key
    assert len(first) >= 60 and (tmp_path / ".secret_key").read_text() == first
    again = config.Settings(environment="production")
    config._own_secret_key(again)
    assert again.secret_key == first                          # same key after every restart
    laptop = config.Settings(environment="development")
    config._own_secret_key(laptop)
    assert laptop.secret_key == "dev-only-secret-change-me"   # never on the laptop

