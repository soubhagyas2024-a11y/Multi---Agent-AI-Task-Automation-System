"""SQLAlchemy engine, sessions and database initialisation."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import settings
from utils.logger import get_logger

logger = get_logger("database")
_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {})

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error")
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables and seed the agent catalogue (idempotent)."""
    from agents.agent_state import AGENT_CATALOG
    from backend import models

    Base.metadata.create_all(bind=engine)
    with session_scope() as db:
        have = {a.agent_name for a in db.query(models.Agent).all()}
        for name, desc in AGENT_CATALOG.items():
            if name not in have:
                db.add(models.Agent(agent_name=name, description=desc, status="idle"))
    logger.info("Database ready at %s", settings.database_url.split("///")[-1])
