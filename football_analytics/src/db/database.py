"""
Gestión de conexiones a la base de datos.
Soporta PostgreSQL (producción) y SQLite (desarrollo/testing).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from .models import Base


def _build_url() -> str:
    """Construye la URL de conexión desde variables de entorno."""
    db_type = os.getenv("DB_TYPE", "sqlite")

    if db_type == "postgresql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "analytics")
        password = os.getenv("DB_PASSWORD", "")
        dbname = os.getenv("DB_NAME", "football_analytics")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"

    # SQLite — útil para desarrollo local y CI
    db_path = os.getenv("SQLITE_PATH", "football_analytics.db")
    return f"sqlite:///{db_path}"


def create_db_engine(echo: bool = False):
    url = _build_url()
    is_sqlite = url.startswith("sqlite")

    kwargs = dict(echo=echo)
    if is_sqlite:
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["poolclass"] = QueuePool
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True  # reconectar si la conexión cayó

    engine = create_engine(url, **kwargs)

    if is_sqlite:
        # Activar WAL y foreign keys en SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, _conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


_engine = None
_SessionLocal = None


def init_db(echo: bool = False, create_tables: bool = False) -> None:
    """Inicializar engine y opcionalmente crear tablas (útil en SQLite/dev)."""
    global _engine, _SessionLocal
    _engine = create_db_engine(echo=echo)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    if create_tables:
        Base.metadata.create_all(_engine)


def get_engine():
    if _engine is None:
        init_db()
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager que entrega una sesión con commit/rollback automático."""
    if _SessionLocal is None:
        init_db()
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_raw(sql: str, params: dict | None = None) -> list[dict]:
    """Ejecuta SQL crudo y devuelve lista de dicts (para queries analíticas)."""
    with get_session() as session:
        result = session.execute(text(sql), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]
