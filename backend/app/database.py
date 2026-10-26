"""
The connection to the database ("the filing cabinet").

Two kinds of database, same code:
    SQLite      a single file (data/leads.db): on your laptop, zero setup
    PostgreSQL  a proper database server: on the live website (Railway gives
                us one and puts its address in DATABASE_URL)

This file sets up three things that the rest of the app reuses:

1. `engine`        - the actual connection to the database.
2. `SessionLocal`  - a factory that hands out "sessions". A session is like
                     opening the cabinet for one job: you read/write, then close it.
3. `Base`          - the parent class every table in models.py inherits from,
                     so SQLAlchemy knows which classes are database tables.

It also has two helpers:
- `get_db()`  - gives each API request its own session and always closes it.
- `init_db()` - creates any missing tables (laptop only; the live site uses
                migrations, see backend/migrations/).
"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _make_sure_folder_exists(database_url: str) -> None:
    """SQLite creates the .db file by itself, but NOT the folder it lives in.
    So if the URL points to ./data/leads.db, we create ./data first."""
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        file_path = database_url[len(prefix):]
        if file_path and file_path != ":memory:":
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def database_url(url: str) -> str:
    """Railway (and Heroku-style hosts) write 'postgres://...' or 'postgresql://...'.
    SQLAlchemy needs to be told which Python driver to use: psycopg (version 3)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str):
    url = database_url(url)
    if url.startswith("sqlite"):
        _make_sure_folder_exists(url)
        new = create_engine(
            url,
            # SQLite normally only lets the thread that opened it use it. FastAPI uses
            # several threads, so we switch that check off (it's safe with sessions).
            connect_args={"check_same_thread": False},
        )
        event.listen(new, "connect", _turn_on_sqlite_rules)
        return new
    # PostgreSQL: a small pool of ready connections; check each one still works
    # before using it (the server may have restarted in between).
    # Every connection talks in UTC, whatever the server's own clock zone is.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800,
                         connect_args={"options": "-c timezone=UTC"})


def _turn_on_sqlite_rules(dbapi_connection, _connection_record):
    """Runs every time a new connection to the file is opened.

    - foreign_keys=ON: SQLite ignores links between tables unless told
      otherwise. With it ON, you can't save a message for a lead that
      doesn't exist, and deleting a lead also deletes its messages.
    - journal_mode=WAL: lets the dashboard read while the AI is writing,
      instead of one waiting for the other.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


engine = make_engine(settings.database_url)
IS_SQLITE = engine.dialect.name == "sqlite"

# autoflush=False: don't send half-finished changes to the database early.
# expire_on_commit=False: after saving, objects keep their values, so we can
# still return them to the frontend without reading the database again.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Every table class in models.py starts with `class X(Base)`."""


def get_db():
    """Give one API request its own database session, then close it.

    Used in routers like:  def list_leads(db: Session = Depends(get_db))
    The `yield` hands the session over; the code after it runs when the
    request is finished, even if something went wrong.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(connection):
    from alembic.config import Config
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["configure_logger"] = False
    config.attributes["connection"] = connection
    return config


FIRST_VERSION = "0001"           # the tables as they were before migrations existed


def migrate() -> None:
    """Bring the database up to the newest version, keeping all data.

    Migrations (backend/migrations/versions/) are numbered instructions like
    "add column X to table Y". This runs every new one, in order, once.
    A laptop database made before migrations existed has exactly the tables
    of the first version (0001), so it is marked as 0001 ("stamped") and then
    brought up to date like any other.
    """
    from alembic import command
    from sqlalchemy import inspect

    from app import models  # noqa: F401  (importing registers the tables)

    with engine.begin() as connection:
        config = _alembic_config(connection)
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            command.stamp(config, FIRST_VERSION)
        command.upgrade(config, "head")


def init_db() -> None:
    """Called when the server starts: create / update the tables (never deletes data)."""
    migrate()


def reset_database() -> None:
    """DEMO ONLY: delete every table and start empty (seed_data --reset)."""
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate()
