from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload as sqlalchemy_selectinload
from sqlalchemy.orm.strategy_options import _AbstractLoad

from arcanus.materia.sqlalchemy import (
    Session,
    contains_eager,
    defaultload,
    defer,
    joinedload,
    lazyload,
    load_only,
    noload,
    raiseload,
    selectinload,
    subqueryload,
    undefer,
)
from arcanus.materia.sqlalchemy.options import attributes
from tests.transmuters import Author, Book, BookDetail, Category, Publisher


def test_attributes_unwraps_arcanus_columns_and_preserves_native_attributes():
    column = Book["author"]

    assert attributes((column,)) == (column.native,)
    assert attributes((column.native,)) == (column.native,)
    assert attributes((column, column.native)) == (column.native, column.native)


def test_loader_option_wrappers_accept_columns():
    options = [
        contains_eager(Book["author"]),
        defaultload(Book["author"]),
        defer(Book["year"]),
        joinedload(Book["author"]),
        lazyload(Book["author"]),
        load_only(Book["title"], Book["year"]),
        noload(Book["author"]),
        raiseload(Book["author"]),
        selectinload(Book["author"]),
        subqueryload(Book["author"]),
        undefer(Book["year"]),
    ]

    assert all(isinstance(option, _AbstractLoad) for option in options)


def test_loader_option_wrappers_accept_native_sqlalchemy_attributes():
    options = [
        selectinload(Book["author"].native),
        joinedload(Book["author"].native),
        load_only(Book["title"].native),
    ]

    assert all(isinstance(option, _AbstractLoad) for option in options)


def test_chained_loader_options_accept_columns():
    option = selectinload(Author["books"]).selectinload(Book["detail"])
    column_option = defaultload(Author["books"]).load_only(Book["title"])
    strict_option = defaultload(Author["books"]).raiseload(Book["reviews"])

    assert isinstance(option, _AbstractLoad)
    assert isinstance(column_option, _AbstractLoad)
    assert isinstance(strict_option, _AbstractLoad)


def test_wrapped_chained_options_load_relationships(engine: Engine):
    with Session(engine) as session:
        author = Author(name="Options Chain Author", field="History")
        publisher = Publisher(name="Options Chain Publisher", country="USA")
        book = Book(title="Options Chain Book", year=2024)
        book.author.value = author
        book.publisher.value = publisher
        book.detail.value = BookDetail(
            isbn="978-8888820001",
            pages=321,
            abstract="Option chain detail",
        )
        session.add(book)
        session.flush()

        result = session.execute(
            select(Author)
            .options(selectinload(Author["books"]).selectinload(Book["detail"]))
            .where(Author["name"] == "Options Chain Author")
        ).scalar_one()

        assert [loaded.title for loaded in result.books] == ["Options Chain Book"]
        assert result.books[0].detail.value is not None
        assert result.books[0].detail.value.pages == 321


def test_wrapped_scalar_options_work_with_real_session(engine: Engine):
    with Session(engine) as session:
        author = Author(name="Options Scalar Author", field="History")
        publisher = Publisher(name="Options Scalar Publisher", country="USA")
        book = Book(title="Options Scalar Book", year=2024)
        book.author.value = author
        book.publisher.value = publisher
        session.add(book)
        session.flush()

        result = session.execute(
            select(Book)
            .options(load_only(Book["title"]), defer(Book["year"]))
            .where(Book["title"] == "Options Scalar Book")
        ).scalar_one()

        assert result.title == "Options Scalar Book"
        assert result.year == 2024


def test_original_sqlalchemy_loader_uses_inspection_hook_at_runtime(engine: Engine):
    with Session(engine) as session:
        author = Author(name="Options Native Loader Author", field="History")
        publisher = Publisher(name="Options Native Loader Publisher", country="USA")
        book = Book(title="Options Native Loader Book", year=2024)
        book.author.value = author
        book.publisher.value = publisher
        session.add(book)
        session.flush()

        result = session.execute(
            select(Book)
            .options(sqlalchemy_selectinload(cast(Any, Book["author"])))
            .where(Book["title"] == "Options Native Loader Book")
        ).scalar_one()

        assert result.author.value.name == "Options Native Loader Author"


def test_contains_eager_wrapper_works_with_joined_relationship(engine: Engine):
    with Session(engine) as session:
        author = Author(name="Options Contains Author", field="History")
        publisher = Publisher(name="Options Contains Publisher", country="USA")
        category = Category(name="Options Contains Category", description="Wrapped")
        book = Book(title="Options Contains Book", year=2024)
        book.author.value = author
        book.publisher.value = publisher
        book.categories.append(category)
        session.add(book)
        session.flush()

        result = (
            session.execute(
                select(Book)
                .join(Book["categories"])
                .options(contains_eager(Book["categories"]))
                .where(Category["name"] == "Options Contains Category")
            )
            .unique()
            .scalar_one()
        )

        assert result.title == "Options Contains Book"
        assert [loaded.name for loaded in result.categories] == [
            "Options Contains Category"
        ]
