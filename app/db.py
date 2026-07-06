from collections.abc import Generator
from threading import Lock

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None
_engine_lock = Lock()


def _create_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = _create_engine(get_settings().database_url)
    return _engine


def init_db() -> None:
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def reset_engine_for_tests(database_url: str) -> None:
    global _engine
    get_settings.cache_clear()
    new_engine = _create_engine(database_url)
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = new_engine
