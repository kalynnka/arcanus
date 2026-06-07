"""Axis B — read paths: get / bulk / list / one / first / count / partitions / nested.

Context = pure ORM (no validation), reference = Pydantic+SQLAlchemy (ORM →
validate), candidate = arcanus Session helpers (query returns transmuters).
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload as sa_joinedload

from arcanus.materia.sqlalchemy import joinedload
from tests import models, schemas
from tests.transmuters import Author, Book

BATCH_SIZE = 50


class TestReadById:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-by-id")
    def test_sqlalchemy_read_by_id(self, benchmark, session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id

        def read():
            with session_factory() as session:
                assert session.get(models.Author, author_id) is not None

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-by-id")
    def test_pydantic_sqlalchemy_read_by_id(
        self, benchmark, session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id

        def read():
            with session_factory() as session:
                orm = session.get(models.Author, author_id)
                assert schemas.AuthorFlat.model_validate(orm) is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-by-id")
    def test_arcanus_read_by_id(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id

        def read():
            with arcanus_session_factory() as session:
                assert session.get(Author, author_id) is not None

        benchmark(read)


class TestReadBulkIds:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-bulk-ids")
    def test_sqlalchemy_read_bulk_ids(self, benchmark, session_factory, seeded_authors):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                by_id = {a.id: a for a in rows}
                ordered = [by_id[i] for i in ids]
                assert len(ordered) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-bulk-ids")
    def test_pydantic_sqlalchemy_read_bulk_ids(
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                by_id = {a.id: a for a in rows}
                ordered = [schemas.AuthorFlat.model_validate(by_id[i]) for i in ids]
                assert len(ordered) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-bulk-ids")
    def test_arcanus_read_bulk_ids(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def read():
            with arcanus_session_factory() as session:
                ordered = session.bulk(Author, ids)
                assert len(ordered) == BATCH_SIZE

        benchmark(read)


class TestReadListPaging:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-list-paging")
    def test_sqlalchemy_read_list_paging(
        self, benchmark, session_factory, seeded_authors
    ):
        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .order_by(models.Author.id)
                    .limit(BATCH_SIZE)
                    .offset(10)
                ).all()
                assert len(rows) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-list-paging")
    def test_pydantic_sqlalchemy_read_list_paging(
        self, benchmark, session_factory, seeded_authors
    ):
        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .order_by(models.Author.id)
                    .limit(BATCH_SIZE)
                    .offset(10)
                ).all()
                validated = [schemas.AuthorFlat.model_validate(a) for a in rows]
                assert len(validated) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-list-paging")
    def test_arcanus_read_list_paging(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        def read():
            with arcanus_session_factory() as session:
                rows = session.list(
                    Author, limit=BATCH_SIZE, offset=10, order_bys=[Author["id"]]
                )
                assert len(rows) == BATCH_SIZE

        benchmark(read)


class TestReadOne:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-one")
    def test_sqlalchemy_read_one(self, benchmark, session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id

        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Author).where(models.Author.id == author_id)
                ).one()
                assert orm is not None

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-one")
    def test_pydantic_sqlalchemy_read_one(
        self, benchmark, session_factory, seeded_authors
    ):
        author_id = random.choice(seeded_authors).id

        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Author).where(models.Author.id == author_id)
                ).one()
                assert schemas.AuthorFlat.model_validate(orm) is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-one")
    def test_arcanus_read_one(self, benchmark, arcanus_session_factory, seeded_authors):
        author_id = random.choice(seeded_authors).id

        def read():
            with arcanus_session_factory() as session:
                assert session.one(Author, id=author_id) is not None

        benchmark(read)


class TestReadFirst:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-first")
    def test_sqlalchemy_read_first(self, benchmark, session_factory, seeded_authors):
        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Author).order_by(models.Author.id)
                ).first()
                assert orm is not None

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-first")
    def test_pydantic_sqlalchemy_read_first(
        self, benchmark, session_factory, seeded_authors
    ):
        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Author).order_by(models.Author.id)
                ).first()
                assert schemas.AuthorFlat.model_validate(orm) is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-first")
    def test_arcanus_read_first(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        def read():
            with arcanus_session_factory() as session:
                assert session.first(Author, order_bys=[Author["id"]]) is not None

        benchmark(read)


class TestReadCount:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-count")
    def test_sqlalchemy_read_count(self, benchmark, session_factory, seeded_authors):
        def read():
            with session_factory() as session:
                count = session.scalar(select(func.count()).select_from(models.Author))
                assert count >= 1

        benchmark(read)

    @pytest.mark.benchmark(group="read-count")
    def test_arcanus_read_count(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        def read():
            with arcanus_session_factory() as session:
                assert session.count(Author) >= 1

        benchmark(read)


class TestReadPartitionsStream:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-partitions-stream")
    def test_sqlalchemy_read_partitions(
        self, benchmark, session_factory, seeded_authors
    ):
        def read():
            with session_factory() as session:
                result = session.scalars(
                    select(models.Author)
                    .order_by(models.Author.id)
                    .limit(BATCH_SIZE)
                    .execution_options(yield_per=20)
                )
                chunks = [list(part) for part in result.partitions()]
                assert sum(len(c) for c in chunks) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-partitions-stream")
    def test_pydantic_sqlalchemy_read_partitions(
        self, benchmark, session_factory, seeded_authors
    ):
        def read():
            with session_factory() as session:
                result = session.scalars(
                    select(models.Author)
                    .order_by(models.Author.id)
                    .limit(BATCH_SIZE)
                    .execution_options(yield_per=20)
                )
                total = sum(
                    len([schemas.AuthorFlat.model_validate(a) for a in part])
                    for part in result.partitions()
                )
                assert total == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-partitions-stream")
    def test_arcanus_read_partitions(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        def read():
            with arcanus_session_factory() as session:
                chunks = list(
                    session.partitions(
                        Author, size=20, limit=BATCH_SIZE, order_bys=[Author["id"]]
                    )
                )
                assert sum(len(c) for c in chunks) == BATCH_SIZE

        benchmark(read)


class TestReadNestedBook:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-nested-book")
    def test_sqlalchemy_read_nested(self, benchmark, session_factory, seeded_books):
        book_id = random.choice(seeded_books).id

        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Book)
                    .where(models.Book.id == book_id)
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).first()
                assert orm.author is not None and orm.publisher is not None

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-nested-book")
    def test_pydantic_sqlalchemy_read_nested(
        self, benchmark, session_factory, seeded_books
    ):
        book_id = random.choice(seeded_books).id

        def read():
            with session_factory() as session:
                orm = session.scalars(
                    select(models.Book)
                    .where(models.Book.id == book_id)
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).first()
                assert schemas.BookFlat.model_validate(orm).author is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-nested-book")
    def test_arcanus_read_nested(
        self, benchmark, arcanus_session_factory, seeded_books
    ):
        book_id = random.choice(seeded_books).id

        def read():
            with arcanus_session_factory() as session:
                book = session.scalars(
                    select(Book)
                    .where(Book["id"] == book_id)
                    .options(joinedload(Book["author"]), joinedload(Book["publisher"]))
                ).first()
                assert book.author.value is not None

        benchmark(read)
