"""Synchronous database fixtures for Axis B (SQLAlchemy materia) benchmarks.

In-memory SQLite keeps measurements free of network I/O so the gap reflects
Python overhead, not the driver. Session-scoped seeds persist across the whole
benchmark run; write benchmarks roll back so they never pollute that state.
Imported (not autoused globally) by ``benchmark/sqlalchemy/conftest.py``.
"""

from __future__ import annotations

from typing import Generator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from arcanus.materia.sqlalchemy import Session as ArcanusSession
from arcanus.materia.sqlalchemy.base import SqlalchemyMateria
from tests.models import Base
from tests.transmuters import sqlalchemy_materia

DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    sync_engine = create_engine(DB_URL, echo=False, future=True)
    try:
        yield sync_engine
    finally:
        sync_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_database(engine: Engine) -> None:
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def arcanus_session_factory(engine: Engine) -> sessionmaker[ArcanusSession]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=ArcanusSession)


@pytest.fixture(scope="module", autouse=True)
def materia() -> Generator[SqlalchemyMateria, None, None]:
    """Activate sqlalchemy_materia for every Axis B test module."""
    with sqlalchemy_materia:
        yield sqlalchemy_materia
