"""
Shared test helpers ("fixtures"). pytest finds this file automatically.

A fixture is something a test asks for by name. For example a test written
as `def test_x(client):` automatically receives a ready-made `client`.

The `client` fixture below gives each test:
    - a fresh database in memory, filled with the demo data (Task 4)
    - a fake browser that can call our API, logged in as the ADMIN
      (so the older tests can look at any business)
`raw_client` is the same fake browser with NO login: it's used to check
that the locks work (tests/test_auth.py).
Your real data/leads.db is never touched by tests.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sqlalchemy import select

from app.auth.access import get_current_user, remember_user
from app.database import Base, get_db, make_engine
from app.models import User
from app.main import app
from app.services import lead_pipeline
from seed.seed_data import seed


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")     # set it to run every check on PostgreSQL


@pytest.fixture
def db_session():
    if TEST_DATABASE_URL:                                     # e.g. postgresql://test@localhost:5433/leadtest
        engine = make_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(bind=engine)
    else:                                                     # default: a fresh SQLite database in memory
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    seed(session, leads_per_business=40)
    yield session
    session.close()
    if TEST_DATABASE_URL:
        engine.dispose()


class _KeepOpen:
    """Wraps the test session so background jobs can't close it mid-test."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def email_outbox(tmp_path, monkeypatch):
    """Emails in tests: mock mode, saved to a temporary folder (never a real send)."""
    from app.config import settings
    from app.services.mailer import MockMailer
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "outbox_dir", str(tmp_path / "outbox"))
    MockMailer.sent.clear()
    return MockMailer.sent


@pytest.fixture
def raw_client(db_session, monkeypatch):
    # "Dependency override": whenever an endpoint asks for get_db,
    # hand it our temporary test database instead of the real one.
    app.dependency_overrides[get_db] = lambda: db_session
    # Background jobs (AI, emails) open their own session: point them at the test database too.
    monkeypatch.setattr(lead_pipeline, "SESSION_FACTORY", lambda: _KeepOpen(db_session))
    from app.services import email_service
    monkeypatch.setattr(email_service, "SESSION_FACTORY", lambda: _KeepOpen(db_session))
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(raw_client, db_session):
    admin = db_session.scalar(select(User).where(User.role == "admin"))

    async def as_admin():
        remember_user(admin)
        return admin

    app.dependency_overrides[get_current_user] = as_admin
    return raw_client
