"""Axis B — update: single, bulk, and full load→modify→flush roundtrip.

Context = pure ORM setattr, reference = validate-then-apply (Pydantic+SQLAlchemy),
candidate = ``transmuter.absorb(...)``. All write benchmarks roll back.
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy import select

from tests import models, schemas
from tests.transmuters import Author

BATCH_SIZE = 50
AuthorUpdate = Author.Update


class TestUpdateSingleAuthor:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-single-author")
    def test_sqlalchemy_update(self, benchmark, session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id

        def update():
            with session_factory() as session:
                orm = session.get(models.Author, author_id)
                orm.name = "Updated Name"
                orm.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-single-author")
    def test_pydantic_sqlalchemy_update(
        self, benchmark, session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id
        data = {"name": "Updated Name", "write_field": "Physics"}

        def update():
            with session_factory() as session:
                validated = schemas.AuthorCreate.model_validate(data)
                orm = session.get(models.Author, author_id)
                for k, v in validated.model_dump().items():
                    setattr(orm, k, v)
                session.flush()
                session.rollback()

        benchmark(update)

    @pytest.mark.benchmark(group="update-single-author")
    def test_arcanus_update(self, benchmark, arcanus_session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id
        data = {"name": "Updated Name", "write_field": "Physics"}

        def update():
            with arcanus_session_factory() as session:
                transmuter = session.get(Author, author_id)
                transmuter.absorb(AuthorUpdate(**data))
                session.flush()
                session.rollback()

        benchmark(update)


class TestUpdateBulkAuthors:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="update-bulk-authors")
    def test_sqlalchemy_update_bulk(self, benchmark, session_factory, seeded_authors):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update():
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
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update():
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
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def update():
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
    def test_sqlalchemy_roundtrip(self, benchmark, session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id

        def roundtrip():
            with session_factory() as session:
                orm = session.get(models.Author, author_id)
                orm.name = f"Roundtrip {author_id}"
                orm.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(roundtrip)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="roundtrip-author")
    def test_pydantic_sqlalchemy_roundtrip(
        self, benchmark, session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id

        def roundtrip():
            with session_factory() as session:
                orm = session.get(models.Author, author_id)
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
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id

        def roundtrip():
            with arcanus_session_factory() as session:
                transmuter = session.get(Author, author_id)
                transmuter.name = f"Roundtrip {author_id}"
                transmuter.field = "Physics"
                session.flush()
                session.rollback()

        benchmark(roundtrip)
