"""Axis B — serialize query results for an API response (dict + JSON).

Context = manual dict/json, reference = Pydantic+SQLAlchemy (validate → dump),
candidate = arcanus ``model_dump`` / ``model_dump_json`` on transmuters. Scalar
and nested (author + publisher) variants. ``test_id`` and unloaded relationships
are excluded so both sides emit the same shape.
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import joinedload as sa_joinedload

from arcanus.materia.sqlalchemy import joinedload
from tests import models, schemas
from tests.transmuters import Author, Book

BATCH_SIZE = 50
_NESTED_EXCLUDE = {
    "test_id": True,
    "translator": True,
    "detail": True,
    "categories": True,
    "reviews": True,
    "author": {"books", "test_id"},
    "publisher": {"books", "test_id"},
}


class TestSerializeDictScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-dict-scalar")
    def test_sqlalchemy_serialize_dict_scalar(
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                return [{"id": a.id, "name": a.name, "field": a.field} for a in rows]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-dict-scalar")
    def test_pydantic_sqlalchemy_serialize_dict_scalar(
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                return [schemas.AuthorFlat.model_validate(a).model_dump() for a in rows]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.benchmark(group="serialize-dict-scalar")
    def test_arcanus_serialize_dict_scalar(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def serialize():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Author).where(Author["id"].in_(ids))
                ).all()
                return [a.model_dump(exclude={"books", "test_id"}) for a in rows]

        assert len(benchmark(serialize)) == BATCH_SIZE


class TestSerializeJsonScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-json-scalar")
    def test_sqlalchemy_serialize_json_scalar(
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                return json.dumps(
                    [{"id": a.id, "name": a.name, "field": a.field} for a in rows]
                )

        assert benchmark(serialize)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-json-scalar")
    def test_pydantic_sqlalchemy_serialize_json_scalar(
        self, benchmark, session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]
        adapter = TypeAdapter(list[schemas.AuthorFlat])

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author).where(models.Author.id.in_(ids))
                ).all()
                return adapter.dump_json(adapter.validate_python(rows))

        assert benchmark(serialize)

    @pytest.mark.benchmark(group="serialize-json-scalar")
    def test_arcanus_serialize_json_scalar(
        self, benchmark, arcanus_session_factory, seeded_authors
    ):
        ids = [a.id for a in seeded_authors[:BATCH_SIZE]]
        adapter = TypeAdapter(list[Author])

        def serialize():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Author).where(Author["id"].in_(ids))
                ).all()
                return adapter.dump_json(
                    rows, exclude={"__all__": {"books", "test_id"}}
                )

        assert benchmark(serialize)


class TestSerializeDictNested:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-dict-nested")
    def test_sqlalchemy_serialize_dict_nested(
        self, benchmark, session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:BATCH_SIZE]]

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).all()
                return [
                    {
                        "id": b.id,
                        "title": b.title,
                        "year": b.year,
                        "author": {"id": b.author.id, "name": b.author.name},
                        "publisher": {"id": b.publisher.id, "name": b.publisher.name},
                    }
                    for b in rows
                ]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-dict-nested")
    def test_pydantic_sqlalchemy_serialize_dict_nested(
        self, benchmark, session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:BATCH_SIZE]]

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).all()
                return [schemas.BookFlat.model_validate(b).model_dump() for b in rows]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.benchmark(group="serialize-dict-nested")
    def test_arcanus_serialize_dict_nested(
        self, benchmark, arcanus_session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:BATCH_SIZE]]

        def serialize():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Book)
                    .where(Book["id"].in_(ids))
                    .options(joinedload(Book["author"]), joinedload(Book["publisher"]))
                ).all()
                return [b.model_dump(exclude=_NESTED_EXCLUDE) for b in rows]

        assert len(benchmark(serialize)) == BATCH_SIZE


class TestSerializeJsonNested:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-json-nested")
    def test_pydantic_sqlalchemy_serialize_json_nested(
        self, benchmark, session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:BATCH_SIZE]]
        adapter = TypeAdapter(list[schemas.BookFlat])

        def serialize():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).all()
                return adapter.dump_json(adapter.validate_python(rows))

        assert benchmark(serialize)

    @pytest.mark.benchmark(group="serialize-json-nested")
    def test_arcanus_serialize_json_nested(
        self, benchmark, arcanus_session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:BATCH_SIZE]]

        def serialize():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Book)
                    .where(Book["id"].in_(ids))
                    .options(joinedload(Book["author"]), joinedload(Book["publisher"]))
                ).all()
                return [b.model_dump_json(exclude=_NESTED_EXCLUDE) for b in rows]

        assert benchmark(serialize)
