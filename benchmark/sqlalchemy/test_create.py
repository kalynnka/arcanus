"""Axis B — create: pure ORM (context), Pydantic+SQLAlchemy (reference), materia.

Every benchmark opens its own session and ``rollback()``s so the shared seeds
are never mutated. The gap = arcanus / (Pydantic+SQLAlchemy).
"""

from __future__ import annotations

import random

import pytest

from tests import models, schemas
from tests.transmuters import Author, Book


class TestCreateSingleAuthor:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-single-author")
    def test_sqlalchemy_create(self, benchmark, session_factory, create_author_data):
        data = random.choice(create_author_data)

        def create():
            with session_factory() as session:
                session.add(models.Author(name=data["name"], field=data["write_field"]))
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-single-author")
    def test_pydantic_sqlalchemy_create(
        self, benchmark, session_factory, create_author_data
    ):
        data = random.choice(create_author_data)

        def create():
            with session_factory() as session:
                validated = schemas.AuthorCreate.model_validate(data)
                session.add(models.Author(**validated.model_dump()))
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.benchmark(group="create-single-author")
    def test_arcanus_create(
        self, benchmark, arcanus_session_factory, create_author_data
    ):
        data = random.choice(create_author_data)

        def create():
            with arcanus_session_factory() as session:
                session.add(Author(name=data["name"], field=data["write_field"]))
                session.flush()
                session.rollback()

        benchmark(create)


class TestCreateNestedBook:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-nested-book")
    def test_sqlalchemy_create_nested(
        self, benchmark, session_factory, create_nested_book_data
    ):
        data = random.choice(create_nested_book_data)

        def create():
            with session_factory() as session:
                book = models.Book(
                    title=data["title"],
                    year=data["year"],
                    author=models.Author(**data["author"]),
                    publisher=models.Publisher(**data["publisher"]),
                )
                session.add(book)
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-nested-book")
    def test_pydantic_sqlalchemy_create_nested(
        self, benchmark, session_factory, create_nested_book_data
    ):
        data = random.choice(create_nested_book_data)

        def create():
            with session_factory() as session:
                validated = schemas.BookCreate.model_validate(data)
                book = models.Book(
                    title=validated.title,
                    year=validated.year,
                    author=models.Author(**validated.author.model_dump()),
                    publisher=models.Publisher(**validated.publisher.model_dump()),
                )
                session.add(book)
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.benchmark(group="create-nested-book")
    def test_arcanus_create_nested(
        self, benchmark, arcanus_session_factory, create_nested_book_data
    ):
        data = random.choice(create_nested_book_data)

        def create():
            with arcanus_session_factory() as session:
                session.add(Book(**data))
                session.flush()
                session.rollback()

        benchmark(create)


@pytest.mark.parametrize("n", [10, 100], ids=["n10", "n100"])
class TestCreateBulkAuthors:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-bulk-authors")
    def test_sqlalchemy_create_bulk(
        self, benchmark, session_factory, create_author_data, n
    ):
        rows = create_author_data[:n]

        def create():
            with session_factory() as session:
                session.add_all(
                    models.Author(name=d["name"], field=d["write_field"]) for d in rows
                )
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="create-bulk-authors")
    def test_pydantic_sqlalchemy_create_bulk(
        self, benchmark, session_factory, create_author_data, n
    ):
        rows = create_author_data[:n]

        def create():
            with session_factory() as session:
                validated = [schemas.AuthorCreate.model_validate(d) for d in rows]
                session.add_all(models.Author(**v.model_dump()) for v in validated)
                session.flush()
                session.rollback()

        benchmark(create)

    @pytest.mark.benchmark(group="create-bulk-authors")
    def test_arcanus_create_bulk(
        self, benchmark, arcanus_session_factory, create_author_data, n
    ):
        rows = create_author_data[:n]

        def create():
            with arcanus_session_factory() as session:
                session.add_all(
                    Author(name=d["name"], field=d["write_field"]) for d in rows
                )
                session.flush()
                session.rollback()

        benchmark(create)
