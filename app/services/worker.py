from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock, Thread

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import ContentRun, RunStep
from app.services.execution_service import run_image_phase, run_text_phase
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class RunWorker:
    """The sole in-process queue consumer for the local, single-user workbench."""

    def __init__(self) -> None:
        self._claim_lock = Lock()
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if (
            not get_settings().worker_enabled
            or not self._database_ready()
            or (self._thread and self._thread.is_alive())
        ):
            return
        self._stop.clear()
        self.recover_stale()
        self._thread = Thread(target=self._loop, name="xhs-run-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def wake(self) -> None:
        self._wake.set()

    def reset_for_tests(self) -> None:
        self.stop()
        self._stop.clear()
        self._wake.clear()

    def recover_stale(self) -> int:
        threshold = utc_now() - timedelta(seconds=get_settings().stale_worker_seconds)
        recovered = 0
        try:
            with Session(get_engine()) as session:
                rows = session.exec(
                    select(ContentRun).where(
                        ContentRun.status.in_(["running", "image_running"]),
                        (ContentRun.heartbeat_at.is_(None)) | (ContentRun.heartbeat_at < threshold),
                    )
                ).all()
                for run in rows:
                    attempts = session.exec(
                        select(RunStep).where(
                            RunStep.run_id == run.id, RunStep.status == "running"
                        )
                    ).all()
                    now = utc_now()
                    for attempt in attempts:
                        attempt.status = "failed"
                        attempt.error = "interrupted during stale worker recovery"
                        attempt.completed_at = now
                        attempt.heartbeat_at = now
                        if attempt.started_at is not None:
                            comparable_now = (
                                now if attempt.started_at.tzinfo else now.replace(tzinfo=None)
                            )
                            attempt.duration_ms = max(
                                0,
                                int(
                                    (comparable_now - attempt.started_at).total_seconds()
                                    * 1000
                                ),
                            )
                        session.add(attempt)
                    run.status = "queued" if run.status == "running" else "image_queued"
                    run.error = None
                    run.heartbeat_at = None
                    run.updated_at = utc_now()
                    session.add(run)
                    recovered += 1
                session.commit()
        except OperationalError:
            logger.info("worker recovery skipped because the database is not migrated")
        return recovered

    def run_once(self) -> bool:
        with self._claim_lock:
            claimed = self._claim_next()
        if claimed is None:
            return False
        run_id, phase = claimed
        with Session(get_engine()) as session:
            if phase == "text":
                run_text_phase(session, run_id)
            else:
                run_image_phase(session, run_id)
        return True

    def _claim_next(self) -> tuple[int, str] | None:
        try:
            with Session(get_engine()) as session:
                run = session.exec(
                    select(ContentRun)
                    .where(ContentRun.status.in_(["queued", "image_queued"]))
                    .order_by(ContentRun.created_at, ContentRun.id)
                    .limit(1)
                ).first()
                if run is None or run.id is None:
                    return None
                phase = "text" if run.status == "queued" else "image"
                run.status = "running" if phase == "text" else "image_running"
                run.current_step = "text_generation" if phase == "text" else "image_generation"
                run.heartbeat_at = utc_now()
                run.updated_at = utc_now()
                session.add(run)
                session.commit()
                return run.id, phase
        except OperationalError:
            logger.info("worker claim skipped because the database is not migrated")
            return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("unexpected worker loop failure")
                worked = False
            if not worked:
                self._wake.wait(get_settings().worker_poll_seconds)
                self._wake.clear()

    def _database_ready(self) -> bool:
        url = make_url(get_settings().database_url)
        if url.drivername.startswith("sqlite") and url.database not in {None, ":memory:"}:
            if not Path(url.database).expanduser().exists():
                return False
        try:
            return "content_runs" in inspect(get_engine()).get_table_names()
        except OperationalError:
            return False


_worker = RunWorker()


def get_worker() -> RunWorker:
    return _worker
