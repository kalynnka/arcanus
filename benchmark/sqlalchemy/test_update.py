"""Axis B — update: single, bulk, and full load→modify→flush roundtrip.

Context = pure ORM setattr, reference = validate-then-apply (Pydantic+SQLAlchemy),
candidate = ``transmuter.absorb(...)``. All write benchmarks roll back.
"""

from __future__ import annotations

import random

import pytest
from pytest_benchmark.fixture import BenchmarkFixture
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from arcanus.materia.sqlalchemy import Session as ArcanusSession
from tests import models, schemas
from tests.transmuters import Author

BATCH_SIZE = 50
AuthorUpdate = Author.Update


class TestUpdateSingleAuthor:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-single-author")
    def test_sqlalchemy_update(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id

        def update() -> None:
            with session_factory() as session:
                orm = session.get_one(models.Author, author_id)
                orm.name = "Updated Name"
                orm.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-single-author")
    def test_pydantic_sqlalchemy_update(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id
        data = {"name": "Updated Name", "write_field": "Physics"}

        def update() -> None:
            with session_factory() as session:
                validated = schemas.AuthorCreate.model_validate(data)
                orm = session.get_one(models.Author, author_id)
                for k, v in validated.model_dump().items():
                    setattr(orm, k, v)
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.benchmark(group="update-single-author")
    def test_arcanus_update(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id
        data = {"name": "Updated Name", "write_field": "Physics"}

        def update() -> None:
            with arcanus_session_factory() as session:
                transmuter = session.get_one(Author, author_id)
                transmuter.absorb(AuthorUpdate(**data))
                session.flush()
                session.rollback()

        benchmark(update)


class TestUpdateBulkAuthors:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-bulk-authors")
    def test_sqlalchemy_update_bulk(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update() -> None:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                for orm in rows:
                    orm.name = f"Bulk {orm.id}"
                    orm.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-bulk-authors")
    def test_pydantic_sqlalchemy_update_bulk(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update() -> None:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                for orm in rows:
                    validated = schemas.AuthorCreate.model_validate(
                        {"name": f"Bulk {orm.id}", "write_field": "Physics"}
                    )
                    for k, v in validated.model_dump().items():
                        setattr(orm, k, v)
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.benchmark(group="update-bulk-authors")
    def test_arcanus_update_bulk(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_authors: list[models.Author],
    ) -> None:
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update() -> None:
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Author).where(Author["id"].in_(ids))
                ).all()
                for transmuter in rows:
                    transmuter.absorb(
                        AuthorUpdate(
                            name=f"Bulk {transmuter.id}", write_field="Physics"
                        )
                    )
                session.flush()
                session.rollback()

        benchmark(update)


class TestRoundtripAuthor:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="roundtrip-author")
    def test_sqlalchemy_roundtrip(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id

        def roundtrip() -> None:
            with session_factory() as session:
                orm = session.get_one(models.Author, author_id)
                orm.name = f"Roundtrip {author_id}"
                orm.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(roundtrip)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="roundtrip-author")
    def test_pydantic_sqlalchemy_roundtrip(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id

        def roundtrip() -> None:
            with session_factory() as session:
                orm = session.get_one(models.Author, author_id)
                validated = schemas.AuthorCreate.model_validate(
                    {"name": f"Roundtrip {author_id}", "write_field": "Physics"}
                )
                orm.name = validated.name
                orm.field = validated.field
                session.flush()
                session.rollback()

        benchmark(roundtrip)

    @pytest.mark.benchmark(group="roundtrip-author")
    def test_arcanus_roundtrip(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_authors: list[models.Author],
    ) -> None:
        author_id = random.choice(seeded_authors).id

        def roundtrip() -> None:
            with arcanus_session_factory() as session:
                transmuter = session.get_one(Author, author_id)
                transmuter.name = f"Roundtrip {author_id}"
                transmuter.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(roundtrip)
