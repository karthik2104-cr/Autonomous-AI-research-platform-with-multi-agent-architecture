from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import DATA_DIR

_DB_PATH = DATA_DIR / "research.db"

engine = create_engine(
    URL.create("sqlite", database=_DB_PATH.resolve().as_posix()),
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _ensure_columns() -> None:
    """Lightweight additive migrations for SQLite (create_all will not ALTER)."""
    inspector = inspect(engine)
    if "research_runs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("research_runs")}
    with engine.begin() as conn:
        if "analysis_json" not in existing:
            conn.execute(text("ALTER TABLE research_runs ADD COLUMN analysis_json JSON"))


def init_db() -> None:
    from core import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    _ensure_columns()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        conn.commit()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
