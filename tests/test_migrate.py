from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.migrate import LegacyDatabaseError, migrate_database


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _upgrade_to_revision(path: Path, revision: str) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, revision)


def _upgrade_to_0001(path: Path) -> None:
    _upgrade_to_revision(path, "20260703_0001")


def _legacy_database(path: Path, *, duplicate_drafts: bool = False) -> None:
    _upgrade_to_0001(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE alembic_version")
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, created_at, updated_at
            ) VALUES (1, 'review_required', 'review', 'topic', 'audience', 'product',
                      'pain', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (run_id, version, title, body, is_final, created_at)
            VALUES (1, 1, 'legacy title', 'legacy body', 0, '2026-01-01 00:00:00')
            """
        )
        if duplicate_drafts:
            connection.execute(
                """
                INSERT INTO drafts (run_id, version, title, body, is_final, created_at)
                VALUES (1, 1, 'duplicate title', 'duplicate body', 0, '2026-01-01 00:00:00')
                """
            )
        connection.commit()


def test_empty_sqlite_database_upgrades_to_head(tmp_path: Path):
    database = tmp_path / "empty.db"

    migrate_database(f"sqlite:///{database.as_posix()}")

    tables = _tables(database)
    assert {"alembic_version", "content_runs", "upload_assets", "idempotency_records"} <= tables
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260730_0003",
        )
        assert {
            "workflow_name",
            "workflow_version",
            "provider",
            "model",
            "heartbeat_at",
        } <= {row[1] for row in connection.execute("PRAGMA table_info(content_runs)")}
        assert {"attempt", "started_at", "completed_at", "duration_ms", "error"} <= {
            row[1] for row in connection.execute("PRAGMA table_info(run_steps)")
        }
        assert {"round", "candidate", "parent_draft_id", "angle", "source", "score", "selected"} <= {
            row[1] for row in connection.execute("PRAGMA table_info(drafts)")
        }


def test_0001_defers_draft_version_uniqueness_to_0002(tmp_path: Path):
    database = tmp_path / "initial.db"
    _upgrade_to_0001(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, created_at, updated_at
            ) VALUES (1, 'running', 'created', 'topic', 'audience', 'product',
                      'pain', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        connection.executemany(
            """
            INSERT INTO drafts (run_id, version, title, body, is_final, created_at)
            VALUES (1, 1, ?, 'body', 0, '2026-01-01 00:00:00')
            """,
            [("first",), ("second",)],
        )
        connection.commit()
        assert connection.execute("SELECT COUNT(*) FROM drafts").fetchone() == (2,)


def test_legacy_database_is_backed_up_and_rows_are_preserved(tmp_path: Path):
    database = tmp_path / "legacy.db"
    _legacy_database(database)

    migrate_database(f"sqlite:///{database.as_posix()}")

    backups = list(tmp_path.glob("legacy.pre-migration-*.db"))
    assert len(backups) == 1
    assert _tables(backups[0]) == {
        "content_runs",
        "drafts",
        "image_assets",
        "reference_assets",
        "review_actions",
        "run_steps",
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT topic FROM content_runs WHERE id = 1").fetchone() == (
            "topic",
        )
        assert connection.execute("SELECT title FROM drafts WHERE id = 1").fetchone() == (
            "legacy title",
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260730_0003",
        )


def test_legacy_wal_database_backup_includes_committed_rows(tmp_path: Path):
    database = tmp_path / "legacy-wal.db"
    _legacy_database(database)

    with sqlite3.connect(database) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, created_at, updated_at
            ) VALUES (2, 'review_required', 'review', 'wal topic', 'audience', 'product',
                      'pain', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        writer.execute(
            """
            INSERT INTO drafts (run_id, version, title, body, is_final, created_at)
            VALUES (2, 1, 'wal title', 'wal body', 0, '2026-01-01 00:00:00')
            """
        )
        writer.commit()
        assert Path(f"{database}-wal").exists()

        migrate_database(f"sqlite:///{database.as_posix()}")

    backups = list(tmp_path.glob("legacy-wal.pre-migration-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("SELECT topic FROM content_runs WHERE id = 2").fetchone() == (
            "wal topic",
        )
        assert connection.execute("SELECT title FROM drafts WHERE run_id = 2").fetchone() == (
            "wal title",
        )


def test_versioned_database_upgrades_from_0002_to_head_preserving_rows(tmp_path: Path):
    database = tmp_path / "versioned.db"
    _upgrade_to_revision(database, "20260706_0002")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, created_at, updated_at
            ) VALUES (1, 'review_required', 'review', 'versioned topic', 'audience', 'product',
                      'pain', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (run_id, version, title, body, is_final, created_at)
            VALUES (1, 1, 'versioned title', 'versioned body', 0, '2026-01-01 00:00:00')
            """
        )
        connection.commit()

    migrate_database(f"sqlite:///{database.as_posix()}")

    assert not list(tmp_path.glob("versioned.pre-migration-*.db"))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT topic FROM content_runs WHERE id = 1").fetchone() == (
            "versioned topic",
        )
        assert connection.execute("SELECT title FROM drafts WHERE id = 1").fetchone() == (
            "versioned title",
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260730_0003",
        )


def test_legacy_duplicate_drafts_abort_before_backup_or_schema_change(tmp_path: Path):
    database = tmp_path / "duplicate.db"
    _legacy_database(database, duplicate_drafts=True)

    with pytest.raises(LegacyDatabaseError, match="duplicate drafts"):
        migrate_database(f"sqlite:///{database.as_posix()}")

    assert not list(tmp_path.glob("duplicate.pre-migration-*.db"))
    assert "alembic_version" not in _tables(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM drafts").fetchone() == (2,)


def test_non_sqlite_urls_are_rejected():
    with pytest.raises(ValueError, match="SQLite"):
        migrate_database("postgresql://localhost/xhs")
