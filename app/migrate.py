"""Safe, explicit schema migration entry point for the local workbench."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.config import get_settings

INITIAL_BUSINESS_TABLES = frozenset(
    {
        "content_runs",
        "run_steps",
        "drafts",
        "image_assets",
        "reference_assets",
        "review_actions",
    }
)
INITIAL_REVISION = "20260703_0001"


class LegacyDatabaseError(RuntimeError):
    """Raised when an unversioned database cannot be safely adopted."""


def _sqlite_path(database_url: str) -> Path:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        raise ValueError("v1 migrations only support SQLite database URLs")
    if not url.database or url.database == ":memory:":
        raise ValueError("v1 migrations require a file-backed SQLite database")
    return Path(url.database).expanduser().resolve()


def _alembic_config(database_url: str) -> Config:
    project_root = Path(__file__).resolve().parent.parent
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _next_backup_path(database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = database_path.with_name(
        f"{database_path.stem}.pre-migration-{timestamp}{database_path.suffix}"
    )
    suffix = 1
    while candidate.exists():
        candidate = database_path.with_name(
            f"{database_path.stem}.pre-migration-{timestamp}-{suffix}{database_path.suffix}"
        )
        suffix += 1
    return candidate


def _create_verified_backup(database_path: Path) -> Path:
    backup_path = _next_backup_path(database_path)
    # A filesystem copy omits committed pages that are still in SQLite's WAL.
    # SQLite's backup API takes a consistent snapshot that includes those pages.
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        raise LegacyDatabaseError("legacy database backup verification failed")
    with sqlite3.connect(backup_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity != ("ok",):
        raise LegacyDatabaseError("legacy database backup failed integrity check")
    return backup_path


def _validate_legacy_drafts(engine) -> None:
    with engine.connect() as connection:
        duplicate = connection.execute(
            text(
                """
                SELECT run_id, version, COUNT(*) AS count
                FROM drafts
                GROUP BY run_id, version
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).first()
    if duplicate:
        raise LegacyDatabaseError(
            f"legacy database has duplicate drafts for run_id={duplicate.run_id}, "
            f"version={duplicate.version}"
        )


def migrate_database(database_url: str) -> None:
    """Upgrade a SQLite database, safely adopting the known pre-Alembic schema."""
    database_path = _sqlite_path(database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url)
    try:
        table_names = set(inspect(engine).get_table_names())
        config = _alembic_config(database_url)

        if "alembic_version" in table_names:
            command.upgrade(config, "head")
            return

        business_tables = table_names & INITIAL_BUSINESS_TABLES
        if not business_tables:
            if table_names:
                raise LegacyDatabaseError("unversioned SQLite database has unrecognized tables")
            command.upgrade(config, "head")
            return

        if not INITIAL_BUSINESS_TABLES <= table_names:
            raise LegacyDatabaseError("unversioned SQLite database is not a recognized legacy schema")

        _validate_legacy_drafts(engine)
        _create_verified_backup(database_path)
        command.stamp(config, INITIAL_REVISION)
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def main() -> None:
    migrate_database(get_settings().database_url)


if __name__ == "__main__":
    main()
