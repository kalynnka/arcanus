"""Async database fixtures for the Axis B async mini-suite.

pytest-benchmark (used locally and in the gap-gate) times a *sync* callable, so
async work is driven through one dedicated event loop via
``loop.run_until_complete(...)``. The loop, the aiosqlite engine and the seed all
live on that single loop and are session-scoped, which keeps the shared-cache
in-memory DB alive for the whole run.
"""

from __future__ import annotations

import asyncio
import random
from typing import Generator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from benchmark.data import corpus
from tests import models
from tests.models import Base

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:?cache=shared"
N_ASYNC_AUTHORS = 60


@pytest.fixture(scope="session")
def bench_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session")
def async_engine(
    bench_loop: asyncio.AbstractEventLoop,
) -> Generator[AsyncEngine, None, None]:
    engine = create_async_engine(ASYNC_DB_URL, future=True)

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    bench_loop.run_until_complete(_create())
    try:
        yield engine
    finally:
        bench_loop.run_until_complete(engine.dispose())


@pytest.fixture(scope="session")
def async_author_ids(
    bench_loop: asyncio.AbstractEventLoop, async_engine: AsyncEngine
) -> list[int]:
    rng = random.Random(corpus.SEED + 20)

    async def _seed() -> list[int]:
        async with SAAsyncSession(async_engine) as session:
            authors = [
                models.Author(
                    name=f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
                    field=rng.choice(corpus.FIELDS),
                )
                for _ in range(N_ASYNC_AUTHORS)
            ]
            session.add_all(authors)
            await session.flush()
            ids = [a.id for a in authors]
            await session.commit()
            return ids

    return bench_loop.run_until_complete(_seed())
