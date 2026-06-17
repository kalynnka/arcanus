"""Axis B — bulk relationship mutations.

Reference = Pydantic+SQLAlchemy: new child data is validated before it reaches
the ORM (mirroring arcanus's transmuter construction), then the collection is
mutated; existing-object mutations (associate/disassociate/remove) add no new
data to validate. Candidate = the equivalent arcanus association mutation.
Covers 1-M append/remove, M-M associate/disassociate, RelationMap set and
RelationGroupMap set. Every benchmark flushes then rolls back.
"""

from __future__ import annotations

import pytest
from pytest_benchmark.fixture import BenchmarkFixture
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from arcanus.materia.sqlalchemy import Session as ArcanusSession
from tests import models, schemas
from tests.transmuters import (
    Author,
    Book,
    Category,
    Shelf,
    ShelfItem,
    Warehouse,
    WarehouseItem,
)

N_CHILDREN = 10


class TestAppendChildren1M:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-append-children-1m")
    def test_pydantic_sqlalchemy_append(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors: list[models.Author],
        seeded_publisher: models.Publisher,
    ):
        author_id = seeded_authors[0].id
        pub_id = seeded_publisher.id

        def mutate() -> None:
            with session_factory() as session:
                author = session.get_one(models.Author, author_id)
                validated = [
                    schemas.BookChildCreate.model_validate(
                        {"title": f"New {i}", "year": 2024, "publisher_id": pub_id}
                    )
                    for i in range(N_CHILDREN)
                ]
                author.books.extend(
                    models.Book(**v.model_dump()) for v in validated
                )
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-append-children-1m")
    def test_arcanus_append(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_authors: list[models.Author],
        seeded_publisher: models.Publisher,
    ):
        author_id = seeded_authors[0].id
        pub_id = seeded_publisher.id

        def mutate() -> None:
            with arcanus_session_factory() as session:
                author = session.get_one(Author, author_id)
                author.books.extend(
                    Book(title=f"New {i}", year=2024, publisher_id=pub_id)
                    for i in range(N_CHILDREN)
                )
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestRemoveChildren1M:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-remove-children-1m")
    def test_pydantic_sqlalchemy_remove(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_authors_with_books: list[models.Author],
    ):
        author_id = seeded_authors_with_books[0].id

        def mutate() -> None:
            with session_factory() as session:
                author = session.get_one(models.Author, author_id)
                for book in list(author.books):
                    author.books.remove(book)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-remove-children-1m")
    def test_arcanus_remove(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_authors_with_books: list[models.Author],
    ):
        author_id = seeded_authors_with_books[0].id

        def mutate() -> None:
            with arcanus_session_factory() as session:
                author = session.get_one(Author, author_id)
                for book in list(author.books):
                    author.books.remove(book)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestAssociateMM:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-associate-mm")
    def test_pydantic_sqlalchemy_associate(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_books: list[models.Book],
        seeded_categories: list[models.Category],
    ):
        book_id = seeded_books[0].id
        cat_ids = [c.id for c in seeded_categories]

        def mutate() -> None:
            with session_factory() as session:
                book = session.get_one(models.Book, book_id)
                cats = session.scalars(
                    select(models.Category).where(models.Category.id.in_(cat_ids))
                ).all()
                book.categories.extend(cats)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-associate-mm")
    def test_arcanus_associate(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_books: list[models.Book],
        seeded_categories: list[models.Category],
    ):
        book_id = seeded_books[0].id
        cat_ids = [c.id for c in seeded_categories]

        def mutate() -> None:
            with arcanus_session_factory() as session:
                book = session.get_one(Book, book_id)
                cats = [c for c in session.bulk(Category, cat_ids) if c is not None]
                book.categories.extend(cats)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestDisassociateMM:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-disassociate-mm")
    def test_pydantic_sqlalchemy_disassociate(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_books_with_categories: list[models.Book],
    ):
        book_id = seeded_books_with_categories[0].id

        def mutate() -> None:
            with session_factory() as session:
                book = session.get_one(models.Book, book_id)
                for cat in list(book.categories):
                    book.categories.remove(cat)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-disassociate-mm")
    def test_arcanus_disassociate(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_books_with_categories: list[models.Book],
    ):
        book_id = seeded_books_with_categories[0].id

        def mutate() -> None:
            with arcanus_session_factory() as session:
                book = session.get_one(Book, book_id)
                for cat in list(book.categories):
                    book.categories.remove(cat)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestSetRelMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-set-relmap")
    def test_pydantic_sqlalchemy_set_relmap(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_shelf: models.Shelf,
    ):
        shelf_id = seeded_shelf.id

        def mutate() -> None:
            with session_factory() as session:
                shelf = session.get_one(models.Shelf, shelf_id)
                for i in range(N_CHILDREN):
                    validated = schemas.ShelfItemCreate.model_validate(
                        {"label": f"new-{i}", "description": "bench"}
                    )
                    shelf.items[f"new-{i}"] = models.ShelfItem(**validated.model_dump())
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-set-relmap")
    def test_arcanus_set_relmap(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_shelf: models.Shelf,
    ):
        shelf_id = seeded_shelf.id

        def mutate() -> None:
            with arcanus_session_factory() as session:
                shelf = session.get_one(Shelf, shelf_id)
                for i in range(N_CHILDREN):
                    shelf.items[f"new-{i}"] = ShelfItem(
                        label=f"new-{i}", description="bench"
                    )
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestSetGroupMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-set-groupmap")
    def test_pydantic_sqlalchemy_set_groupmap(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_warehouse: models.Warehouse,
    ):
        warehouse_id = seeded_warehouse.id

        def mutate() -> None:
            with session_factory() as session:
                warehouse = session.get_one(models.Warehouse, warehouse_id)
                validated = [
                    schemas.WarehouseItemCreate.model_validate(
                        {"category": "fresh", "name": f"item-{i}", "quantity": i}
                    )
                    for i in range(N_CHILDREN)
                ]
                session.add_all(
                    models.WarehouseItem(warehouse_id=warehouse.id, **v.model_dump())
                    for v in validated
                )
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-set-groupmap")
    def test_arcanus_set_groupmap(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_warehouse: models.Warehouse,
    ):
        warehouse_id = seeded_warehouse.id

        def mutate() -> None:
            with arcanus_session_factory() as session:
                warehouse = session.get_one(Warehouse, warehouse_id)
                warehouse.items["fresh"] = [
                    WarehouseItem(category="fresh", name=f"item-{i}", quantity=i)
                    for i in range(N_CHILDREN)
                ]
                session.flush()
                session.rollback()

        benchmark(mutate)
