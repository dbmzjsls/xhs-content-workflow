from __future__ import annotations

import json
import sqlite3
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import reset_engine_for_tests
from app.main import app
from app.migrate import LegacyDatabaseError, migrate_database
from app.services import content_pipeline
from app.services.worker import get_worker


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
            "20260731_0009",
        )
        assert {
            "workflow_name",
            "workflow_version",
            "provider",
            "model",
            "heartbeat_at",
        } <= {row[1] for row in connection.execute("PRAGMA table_info(content_runs)")}
        assert {
            "attempt",
            "started_at",
            "heartbeat_at",
            "completed_at",
            "duration_ms",
            "error",
            "error_type",
        } <= {
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
            "20260731_0009",
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
        assert connection.execute(
            "SELECT status, failed_phase FROM content_runs WHERE id = 1"
        ).fetchone() == ("failed", "text")
        assert connection.execute("SELECT title FROM drafts WHERE id = 1").fetchone() == (
            "versioned title",
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260731_0009",
        )


def _valid_legacy_draft() -> dict:
    result = content_pipeline.generate_candidate_round(
        {
            "topic": "fix an IELTS essay before bed",
            "audience": "IELTS self-study learner",
            "product_function": "Writing Checker",
            "pain_point": "my examples do not support the point",
            "style_preference": "memoir",
        },
        provider=content_pipeline.MockPipelineProvider(),
    )
    return result["candidates"][0]


def test_0007_normalizes_legacy_review_rows_and_allows_legal_continuation(
    tmp_path: Path, monkeypatch
):
    database = tmp_path / "legacy-review.db"
    _upgrade_to_revision(database, "20260706_0002")
    valid = _valid_legacy_draft()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, brief, created_at, updated_at
            ) VALUES (1, 'review_required', 'review', 'topic', 'audience',
                      'Writing Checker', 'pain', NULL,
                      '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO run_steps (
                run_id, name, status, input_payload, output_payload, created_at
            ) VALUES (1, 'legacy_review', 'completed', NULL, NULL,
                      '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, created_at
            ) VALUES (1, 1, 'old null draft', NULL, NULL, NULL, NULL,
                      0, '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, created_at
            ) VALUES (1, 2, ?, ?, ?, NULL, ?, 0,
                      '2026-01-02 00:00:00')
            """,
            (
                valid["title"],
                valid["body"],
                json.dumps(valid["tags"], ensure_ascii=False),
                json.dumps({"passed": True, "issues": []}),
            ),
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, created_at
            ) VALUES (1, 3, 'latest invalid', 'too short', NULL, NULL, NULL, 0,
                      '2026-01-03 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO image_assets (
                run_id, kind, status, title, prompt, reference_reason, file_path,
                qc_report, created_at
            ) VALUES (1, 'cover', 'legacy', 'legacy image', NULL, NULL, NULL, NULL,
                      '2026-01-01 00:00:00')
            """
        )
        connection.commit()

    migrate_database(f"sqlite:///{database.as_posix()}")

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute("SELECT * FROM content_runs WHERE id = 1").fetchone()
        step = connection.execute("SELECT * FROM run_steps WHERE run_id = 1").fetchone()
        drafts = connection.execute(
            "SELECT * FROM drafts WHERE run_id = 1 ORDER BY version"
        ).fetchall()
        image = connection.execute("SELECT * FROM image_assets WHERE run_id = 1").fetchone()
        assert json.loads(run["brief"]) == {
            "topic": "topic",
            "audience": "audience",
            "product_function": "Writing Checker",
            "pain_point": "pain",
        }
        assert json.loads(step["input_payload"]) == {}
        assert json.loads(step["output_payload"]) == {}
        assert drafts[0]["body"] == ""
        assert json.loads(drafts[0]["tags"]) == []
        assert json.loads(drafts[0]["narrative_plan"]) == {}
        assert isinstance(json.loads(drafts[0]["quality_report"])["hard"]["passed"], bool)
        assert json.loads(drafts[1]["quality_report"])["hard"]["passed"] is True
        assert [row["selected"] for row in drafts] == [0, 1, 0]
        assert image["prompt"] == image["reference_reason"] == ""
        assert json.loads(image["qc_report"]) == {}
        assert connection.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM image_assets").fetchone()[0] == 1

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database.as_posix()}")
    get_worker().reset_for_tests()
    client = TestClient(app)

    detail = client.get("/api/runs/1")
    assert detail.status_code == 200, detail.text
    selected = next(draft for draft in detail.json()["drafts"] if draft["selected"])
    assert client.post("/api/runs/1/selection", json={"draft_id": selected["id"]}).status_code == 200
    revised = client.post(
        "/api/runs/1/revisions", json={"instructions": "Make it more conversational."}
    )
    assert revised.status_code == 200, revised.text
    approved = client.post("/api/runs/1/copy-approval")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "image_queued"


def test_0007_preserves_but_invalidates_legacy_export_artifacts(tmp_path: Path, monkeypatch):
    database = tmp_path / "legacy-export.db"
    export_root = tmp_path / "exports"
    run_root = export_root / "7"
    run_root.mkdir(parents=True)
    unsafe = r"C:\private\legacy.png and /srv/private/legacy.json"
    (run_root / "package.json").write_text(unsafe, encoding="utf-8")
    (run_root / "发布包.md").write_text(unsafe, encoding="utf-8")
    (run_root / "发布包.zip").write_bytes(unsafe.encode())
    _upgrade_to_revision(database, "20260730_0006")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, brief, final_package, created_at, updated_at
            ) VALUES (7, 'completed', 'export_package', 'topic', 'audience', 'product',
                      'pain', '{}', ?, '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """,
            (json.dumps({"zip_path": r"C:\private\发布包.zip"}),),
        )
        connection.commit()

    migrate_database(f"sqlite:///{database.as_posix()}")

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status, current_step, final_package, legacy_final_package "
            "FROM content_runs WHERE id = 7"
        ).fetchone()
    assert row[:3] == ("failed", "text_generation", None)
    assert json.loads(row[3]) == {"zip_path": r"C:\private\发布包.zip"}

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(export_root))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database.as_posix()}")
    client = TestClient(app)
    detail = client.get("/api/runs/7").json()
    assert detail["final_package"] is None
    assert unsafe not in json.dumps(detail)
    assert client.get("/api/runs/7/exports/json").status_code == 409
    assert (run_root / "package.json").read_text("utf-8") == unsafe
    assert (run_root / "发布包.zip").read_bytes() == unsafe.encode()


def test_invalid_only_legacy_review_run_migrates_to_publicly_retryable_text_phase(
    tmp_path: Path, monkeypatch
):
    database = tmp_path / "invalid-legacy-review.db"
    _upgrade_to_revision(database, "20260706_0002")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, style_preference, brief, created_at, updated_at
            ) VALUES (9, 'review_required', 'review', 'retry topic', 'retry audience',
                      'Writing Checker', 'retry pain', 'memoir', NULL,
                      '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO run_steps (
                run_id, name, status, input_payload, output_payload, created_at
            ) VALUES (9, 'candidate_round', 'completed', NULL, NULL,
                      '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, created_at
            ) VALUES (9, 1, 'invalid legacy', 'too short', NULL, NULL, NULL,
                      0, '2026-01-01 00:00:00')
            """
        )
        connection.commit()

    migrate_database(f"sqlite:///{database.as_posix()}")

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute("SELECT * FROM content_runs WHERE id = 9").fetchone()
        draft = connection.execute("SELECT * FROM drafts WHERE run_id = 9").fetchone()
        cached = connection.execute(
            "SELECT * FROM run_steps WHERE run_id = 9 AND name = 'candidate_round'"
        ).fetchone()
        assert run["status"] == "failed"
        assert run["current_step"] == "text_generation"
        assert run["failed_phase"] == "text"
        assert json.loads(run["brief"]) == {
            "topic": "retry topic",
            "audience": "retry audience",
            "product_function": "Writing Checker",
            "pain_point": "retry pain",
            "style_preference": "memoir",
        }
        assert draft["selected"] == 0
        assert json.loads(draft["quality_report"])["hard"]["passed"] is False
        assert cached["status"] == "failed"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database.as_posix()}")
    get_worker().reset_for_tests()
    client = TestClient(app)

    detail = client.get("/api/runs/9")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "failed"
    retried = client.post("/api/runs/9/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"
    assert get_worker().run_once() is True
    recovered = client.get("/api/runs/9").json()
    assert recovered["status"] == "copy_review_required"
    assert any(draft["selected"] for draft in recovered["drafts"])
    approved = client.post("/api/runs/9/copy-approval")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "image_queued"


def test_ineligible_legacy_asset_state_is_cleared_before_public_retry_and_new_export(
    tmp_path: Path, monkeypatch
):
    database = tmp_path / "stale-image-legacy.db"
    export_root = tmp_path / "exports"
    invalid_asset_root = export_root / "11" / "assets"
    eligible_asset_root = export_root / "12" / "assets"
    invalid_asset_root.mkdir(parents=True)
    eligible_asset_root.mkdir(parents=True)
    stale_image = invalid_asset_root / "legacy-only.png"
    eligible_image = eligible_asset_root / "eligible.png"
    stale_image.write_bytes(b"legacy image bytes")
    eligible_image.write_bytes(b"eligible image bytes")
    valid = _valid_legacy_draft()
    _upgrade_to_revision(database, "20260730_0006")
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO content_runs (
                id, status, current_step, topic, audience, product_function,
                pain_point, style_preference, brief, final_package, created_at, updated_at
            ) VALUES (?, 'completed', 'export_package', ?, 'audience', 'Writing Checker',
                      'pain', 'memoir', NULL, ?,
                      '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """,
            [
                (11, "invalid retry topic", json.dumps({"zip_path": r"C:\old\invalid.zip"})),
                (12, "eligible topic", json.dumps({"zip_path": r"C:\old\eligible.zip"})),
            ],
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, selected, created_at
            ) VALUES (11, 1, 'invalid legacy', 'too short', NULL, NULL, NULL,
                      1, 1, '2026-01-01 00:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO drafts (
                run_id, version, title, body, tags, narrative_plan, quality_report,
                is_final, selected, created_at
            ) VALUES (12, 1, ?, ?, ?, '{}', ?, 1, 1, '2026-01-01 00:00:00')
            """,
            (
                valid["title"],
                valid["body"],
                json.dumps(valid["tags"], ensure_ascii=False),
                json.dumps({"passed": True, "issues": []}),
            ),
        )
        connection.executemany(
            """
            INSERT INTO image_assets (
                run_id, kind, status, title, prompt, reference_reason, file_path,
                qc_report, created_at
            ) VALUES (?, 'cover', 'generated', ?, ?, 'legacy reason', ?, ?,
                      '2026-01-01 00:00:00')
            """,
            [
                (
                    11,
                    "stale image",
                    "OLD_DRAFT_PROMPT",
                    str(stale_image),
                    json.dumps({"passed": True}),
                ),
                (
                    12,
                    "eligible image",
                    "ELIGIBLE_PROMPT",
                    str(eligible_image),
                    json.dumps({"passed": True}),
                ),
            ],
        )
        old_steps = [
            ("text_generation", {"old": True}),
            ("candidate_round", {"old": True}),
            ("prompt_rewrite", {"items": [{"prompt": "OLD_DRAFT_PROMPT"}]}),
            (
                "image_generate",
                {"items": [{"file_path": str(stale_image), "prompt": "OLD_DRAFT_PROMPT"}]},
            ),
            ("image_qc", {"passed": True, "old": True}),
            ("image_generation", {"asset_count": 1, "old": True}),
        ]
        connection.executemany(
            """
            INSERT INTO run_steps (
                run_id, name, status, input_payload, output_payload, created_at
            ) VALUES (11, ?, 'completed', '{}', ?, '2026-01-01 00:00:00')
            """,
            [(name, json.dumps(output)) for name, output in old_steps],
        )
        connection.execute(
            """
            INSERT INTO run_steps (
                run_id, name, status, input_payload, output_payload, created_at
            ) VALUES (12, 'image_generate', 'completed', '{}', ?,
                      '2026-01-01 00:00:00')
            """,
            (json.dumps({"items": [{"file_path": str(eligible_image)}]}),),
        )
        connection.commit()

    migrate_database(f"sqlite:///{database.as_posix()}")

    with sqlite3.connect(database) as connection:
        invalid_run = connection.execute(
            "SELECT status, failed_phase, final_package FROM content_runs WHERE id = 11"
        ).fetchone()
        invalid_draft = connection.execute(
            "SELECT selected, is_final FROM drafts WHERE run_id = 11"
        ).fetchone()
        invalid_images = connection.execute(
            "SELECT COUNT(*) FROM image_assets WHERE run_id = 11"
        ).fetchone()[0]
        invalid_steps = dict(
            connection.execute(
                "SELECT name, status FROM run_steps WHERE run_id = 11"
            ).fetchall()
        )
        eligible_run = connection.execute(
            "SELECT status, failed_phase FROM content_runs WHERE id = 12"
        ).fetchone()
        eligible_draft = connection.execute(
            "SELECT selected, is_final FROM drafts WHERE run_id = 12"
        ).fetchone()
        eligible_images = connection.execute(
            "SELECT COUNT(*) FROM image_assets WHERE run_id = 12"
        ).fetchone()[0]
        eligible_step = connection.execute(
            "SELECT status FROM run_steps WHERE run_id = 12 AND name = 'image_generate'"
        ).fetchone()[0]
    assert invalid_run == ("failed", "text", None)
    assert invalid_draft == (0, 0)
    assert invalid_images == 0
    assert all(
        invalid_steps[name] == "failed"
        for name in (
            "text_generation",
            "candidate_round",
            "prompt_rewrite",
            "image_generate",
            "image_qc",
            "image_generation",
        )
    )
    assert stale_image.is_file()
    assert eligible_run == ("asset_review_required", None)
    assert eligible_draft == (1, 1)
    assert eligible_images == 1
    assert eligible_step == "completed"

    reference_png = b"\x89PNG\r\n\x1a\nlegacy-retry-test"
    cover_dir = tmp_path / "covers" / "memoir"
    product_dir = tmp_path / "product" / "screenshots"
    cover_dir.mkdir(parents=True)
    product_dir.mkdir(parents=True)
    (cover_dir / "cover.png").write_bytes(reference_png)
    (product_dir / "ui.png").write_bytes(reference_png)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(export_root))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("CATHOVEN_COVER_REFERENCE_DIR", str(tmp_path / "covers"))
    monkeypatch.setenv("CATHOVEN_PRODUCT_REFERENCE_DIR", str(tmp_path / "product"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database.as_posix()}")
    get_worker().reset_for_tests()
    client = TestClient(app)

    assert client.post("/api/runs/11/retry").json()["status"] == "queued"
    assert get_worker().run_once() is True
    copy_ready = client.get("/api/runs/11").json()
    selected_id = next(draft["id"] for draft in copy_ready["drafts"] if draft["selected"])
    assert client.post("/api/runs/11/copy-approval").json()["status"] == "image_queued"
    assert get_worker().run_once() is True
    assets_ready = client.get("/api/runs/11").json()
    assert assets_ready["status"] == "asset_review_required"
    assert assets_ready["images"]
    assert all("OLD_DRAFT_PROMPT" not in image["prompt"] for image in assets_ready["images"])
    completed_prompts = [
        step
        for step in assets_ready["steps"]
        if step["name"] == "prompt_rewrite" and step["status"] == "completed"
    ]
    assert completed_prompts
    assert "OLD_DRAFT_PROMPT" not in json.dumps(completed_prompts[-1]["output_payload"])
    completed = client.post("/api/runs/11/asset-approval")
    assert completed.status_code == 200, completed.text
    package_json = client.get(completed.json()["final_package"]["json_url"]).json()
    archive = client.get(completed.json()["final_package"]["zip_url"]).content
    assert package_json["draft"]["id"] == selected_id
    assert "OLD_DRAFT_PROMPT" not in json.dumps(package_json)
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        assert all("legacy-only.png" not in name for name in bundle.namelist())

    eligible_completed = client.post("/api/runs/12/asset-approval")
    assert eligible_completed.status_code == 200, eligible_completed.text
    assert eligible_completed.json()["status"] == "completed"


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
