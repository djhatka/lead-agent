"""Alembic's starter: connects to the app's database and compares it with models.py."""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers every table)
from app.database import Base, engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        with engine.connect() as connection:
            _run(connection)
    else:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite can't change a column in place; "batch" mode rebuilds the table safely instead
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
