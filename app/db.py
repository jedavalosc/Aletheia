from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

# JSONB on Postgres, plain JSON elsewhere (used only by unit tests on SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def engine(url: str | None = None):
    global _engine, _Session
    if _engine is None or url is not None:
        url = url or get_settings().database_url
        # prepare_threshold=None: the pooled Fly URL goes through a transaction-mode
        # pooler, where server-side prepared statements break.
        args = {"connect_args": {"prepare_threshold": None}} if url.startswith("postgresql+psycopg") else {}
        _engine = create_engine(url, pool_pre_ping=True, future=True, **args)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


@contextmanager
def session(url: str | None = None):
    if _Session is None or url is not None:
        engine(url)
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
