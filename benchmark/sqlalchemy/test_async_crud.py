"""Axis B (async) — AsyncSession read/bulk/list/stream/create.

pytest-benchmark times a sync callable, so each coroutine runs via
``bench_loop.run_until_complete(...)`` on one dedicated loop (see
``benchmark/fixtures/db_async.py``). Reference = plain SQLAlchemy AsyncSession +
Pydantic; candidate = arcanus AsyncSession returning transmuters.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

from arcanus.materia.sqlalchemy import AsyncSession as ArcanusAsyncSession
from tests import models, schemas
from tests.transmuters import Author

BATCH = 30


class TestAsyncReadOne:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="async-read-one")
    def test_pydantic_sqlalchemy_async_read_one(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        author_id = async_author_ids[0]

        async def op():
            async with SAAsyncSession(async_engine) as session:
                orm = (
                    await session.execute(
                        select(models.Author).where(models.Author.id == author_id)
                    )
                ).scalar_one()
                return schemas.AuthorFlat.model_validate(orm)

        assert benchmark(lambda: bench_loop.run_until_complete(op())) is not None

    @pytest.mark.benchmark(group="async-read-one")
    def test_arcanus_async_read_one(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        author_id = async_author_ids[0]

        async def op():
            async with ArcanusAsyncSession(async_engine) as session:
                return await session.one(Author, id=author_id)

        assert benchmark(lambda: bench_loop.run_until_complete(op())) is not None


class TestAsyncBulkIds:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="async-bulk-ids")
    def test_pydantic_sqlalchemy_async_bulk(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        ids = async_author_ids[:BATCH]

        async def op():
            async with SAAsyncSession(async_engine) as session:
                rows = (
                    (
                        await session.execute(
                            select(models.Author).where(models.Author.id.in_(ids))
                        )
                    )
                    .scalars()
                    .all()
                )
                by_id = {a.id: a for a in rows}
                return [schemas.AuthorFlat.model_validate(by_id[i]) for i in ids]

        assert len(benchmark(lambda: bench_loop.run_until_complete(op()))) == BATCH

    @pytest.mark.benchmark(group="async-bulk-ids")
    def test_arcanus_async_bulk(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        ids = async_author_ids[:BATCH]

        async def op():
            async with ArcanusAsyncSession(async_engine) as session:
                return await session.bulk(Author, ids)

        assert len(benchmark(lambda: bench_loop.run_until_complete(op()))) == BATCH


class TestAsyncList:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="async-list")
    def test_pydantic_sqlalchemy_async_list(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        async def op():
            async with SAAsyncSession(async_engine) as session:
                rows = (
                    (
                        await session.execute(
                            select(models.Author)
                            .order_by(models.Author.id)
                            .limit(BATCH)
                        )
                    )
                    .scalars()
                    .all()
                )
                return [schemas.AuthorFlat.model_validate(a) for a in rows]

        assert len(benchmark(lambda: bench_loop.run_until_complete(op()))) == BATCH

    @pytest.mark.benchmark(group="async-list")
    def test_arcanus_async_list(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        async def op():
            async with ArcanusAsyncSession(async_engine) as session:
                return await session.list(Author, limit=BATCH, order_bys=[Author["id"]])

        assert len(benchmark(lambda: bench_loop.run_until_complete(op()))) == BATCH


class TestAsyncStreamPartitions:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="async-stream-partitions")
    def test_pydantic_sqlalchemy_async_stream(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        async def op():
            async with SAAsyncSession(async_engine) as session:
                result = await session.stream_scalars(
                    select(models.Author)
                    .order_by(models.Author.id)
                    .limit(BATCH)
                    .execution_options(yield_per=10)
                )
                total = 0
                async for part in result.partitions():
                    total += len([schemas.AuthorFlat.model_validate(a) for a in part])
                return total

        assert benchmark(lambda: bench_loop.run_until_complete(op())) == BATCH

    @pytest.mark.benchmark(group="async-stream-partitions")
    def test_arcanus_async_stream(
        self, benchmark, bench_loop, async_engine, async_author_ids
    ):
        async def op():
            async with ArcanusAsyncSession(async_engine) as session:
                total = 0
                async for part in session.partitions(
                    Author, size=10, limit=BATCH, order_bys=[Author["id"]]
                ):
                    total += len(part)
                return total

        assert benchmark(lambda: bench_loop.run_until_complete(op())) == BATCH


class TestAsyncCreate:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="async-create-author")
    def test_pydantic_sqlalchemy_async_create(
        self, benchmark, bench_loop, async_engine
    ):
        async def op():
            async with SAAsyncSession(async_engine) as session:
                validated = schemas.AuthorCreate.model_validate(
                    {"name": "Async New", "write_field": "Physics"}
                )
                session.add(models.Author(**validated.model_dump()))
                await session.flush()
                await session.rollback()

        benchmark(lambda: bench_loop.run_until_complete(op()))

    @pytest.mark.benchmark(group="async-create-author")
    def test_arcanus_async_create(self, benchmark, bench_loop, async_engine):
        async def op():
            async with ArcanusAsyncSession(async_engine) as session:
                session.add(Author(name="Async New", field="Physics"))
                await session.flush()
                await session.rollback()

        benchmark(lambda: bench_loop.run_until_complete(op()))
