"""
Task 26 checks: migrations (safe, numbered database changes).

The most important check: after running every migration on an EMPTY database,
the tables must match models.py exactly. If someone changes models.py and
forgets to write a migration, this test fails and says what's missing:
    alembic revision --autogenerate -m "what changed"
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app import database
from app.database import Base, make_engine


@pytest.fixture
def empty_database(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = make_engine(url)
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_migrations_build_exactly_the_tables_in_models(empty_database):
    database.migrate()
    with empty_database.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == [], f"models.py and the migrations differ: {differences}"
    assert "alembic_version" in inspect(empty_database).get_table_names()


def test_running_migrations_twice_changes_nothing(empty_database):
    database.migrate()
    database.migrate()                                  # every server start does this
    assert len(inspect(empty_database).get_table_names()) == len(Base.metadata.tables) + 1


def test_old_laptop_database_is_brought_up_to_date(empty_database):
    added_later = {"roi_reports", "owner_alerts", "dues", "renewals", "competitors", "competitor_alerts",
                   "bookings", "tracking_numbers", "calls"} # tables from migrations 0002+
    with empty_database.begin() as connection:          # made before migrations existed: the 0001 tables
        for table in Base.metadata.sorted_tables:
            if table.name not in added_later:
                table.create(connection)
        connection.exec_driver_sql("DROP INDEX ix_leads_won_at")
        connection.exec_driver_sql("ALTER TABLE leads DROP COLUMN won_at")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN alert_phone")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN alert_settings")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN auto_reply_settings")
        connection.exec_driver_sql("ALTER TABLE messages DROP COLUMN auto_reply")
        connection.exec_driver_sql("ALTER TABLE messages DROP COLUMN followup")
        connection.exec_driver_sql("ALTER TABLE leads DROP COLUMN followup_snoozed_until")
        connection.exec_driver_sql("ALTER TABLE leads DROP COLUMN followup_stopped")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN followup_settings")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN payment_settings")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN renewal_settings")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN slow_hours_settings")
        connection.exec_driver_sql("ALTER TABLE leads DROP COLUMN last_slow_offer_at")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN booking_settings")
        connection.exec_driver_sql("ALTER TABLE businesses DROP COLUMN language")
    database.migrate()
    with empty_database.connect() as connection:
        version = connection.exec_driver_sql("select version_num from alembic_version").scalar()
    assert version == "2a6c9f0d3b5e" and added_later <= set(inspect(empty_database).get_table_names())
    assert "won_at" in {c["name"] for c in inspect(empty_database).get_columns("leads")}
    assert "alert_phone" in {c["name"] for c in inspect(empty_database).get_columns("businesses")}
    assert "auto_reply" in {c["name"] for c in inspect(empty_database).get_columns("messages")}
    assert "followup_stopped" in {c["name"] for c in inspect(empty_database).get_columns("leads")}
    assert "last_slow_offer_at" in {c["name"] for c in inspect(empty_database).get_columns("leads")}


def test_demo_reset_starts_clean(empty_database):
    database.migrate()
    database.reset_database()
    tables = inspect(empty_database).get_table_names()
    assert "alembic_version" in tables and "leads" in tables
