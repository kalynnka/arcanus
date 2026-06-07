"""Axis B — bulk relationship mutations.

The reference here is plain SQLAlchemy ORM collection mutation (Pydantic adds
nothing to mutation), the candidate is the equivalent arcanus association
mutation. Covers 1-M append/remove, M-M associate/disassociate, RelationMap set
and RelationGroupMap set. Every benchmark flushes then rolls back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests import models
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
        self, benchmark, session_factory, seeded_authors, seeded_publisher
    ):
        author_id = seeded_authors[0].id
        pub_id = seeded_publisher.id

        def mutate():
            with session_factory() as session:
                author = session.get(models.Author, author_id)
                author.books.extend(
                    models.Book(title=f"New {i}", year=2024, publisher_id=pub_id)
                    for i in range(N_CHILDREN)
                )
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-append-children-1m")
    def test_arcanus_append(
        self, benchmark, arcanus_session_factory, seeded_authors, seeded_publisher
    ):
        author_id = seeded_authors[0].id
        pub_id = seeded_publisher.id

        def mutate():
            with arcanus_session_factory() as session:
                author = session.get(Author, author_id)
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
        self, benchmark, session_factory, seeded_authors_with_books
    ):
        author_id = seeded_authors_with_books[0].id

        def mutate():
            with session_factory() as session:
                author = session.get(models.Author, author_id)
                for book in list(author.books):
                    author.books.remove(book)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-remove-children-1m")
    def test_arcanus_remove(
        self, benchmark, arcanus_session_factory, seeded_authors_with_books
    ):
        author_id = seeded_authors_with_books[0].id

        def mutate():
            with arcanus_session_factory() as session:
                author = session.get(Author, author_id)
                for book in list(author.books):
                    author.books.remove(book)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestAssociateMM:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-associate-mm")
    def test_pydantic_sqlalchemy_associate(
        self, benchmark, session_factory, seeded_books, seeded_categories
    ):
        book_id = seeded_books[0].id
        cat_ids = [c.id for c in seeded_categories]

        def mutate():
            with session_factory() as session:
                book = session.get(models.Book, book_id)
                cats = session.scalars(
                    select(models.Category).where(models.Category.id.in_(cat_ids))
                ).all()
                book.categories.extend(cats)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-associate-mm")
    def test_arcanus_associate(
        self, benchmark, arcanus_session_factory, seeded_books, seeded_categories
    ):
        book_id = seeded_books[0].id
        cat_ids = [c.id for c in seeded_categories]

        def mutate():
            with arcanus_session_factory() as session:
                book = session.get(Book, book_id)
                cats = [c for c in session.bulk(Category, cat_ids) if c is not None]
                book.categories.extend(cats)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestDisassociateMM:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-disassociate-mm")
    def test_pydantic_sqlalchemy_disassociate(
        self, benchmark, session_factory, seeded_books_with_categories
    ):
        book_id = seeded_books_with_categories[0].id

        def mutate():
            with session_factory() as session:
                book = session.get(models.Book, book_id)
                for cat in list(book.categories):
                    book.categories.remove(cat)
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-disassociate-mm")
    def test_arcanus_disassociate(
        self, benchmark, arcanus_session_factory, seeded_books_with_categories
    ):
        book_id = seeded_books_with_categories[0].id

        def mutate():
            with arcanus_session_factory() as session:
                book = session.get(Book, book_id)
                for cat in list(book.categories):
                    book.categories.remove(cat)
                session.flush()
                session.rollback()

        benchmark(mutate)


class TestSetRelMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="relmut-set-relmap")
    def test_pydantic_sqlalchemy_set_relmap(
        self, benchmark, session_factory, seeded_shelf
    ):
        shelf_id = seeded_shelf.id

        def mutate():
            with session_factory() as session:
                shelf = session.get(models.Shelf, shelf_id)
                for i in range(N_CHILDREN):
                    shelf.items[f"new-{i}"] = models.ShelfItem(
                        label=f"new-{i}", description="bench"
                    )
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-set-relmap")
    def test_arcanus_set_relmap(self, benchmark, arcanus_session_factory, seeded_shelf):
        shelf_id = seeded_shelf.id

        def mutate():
            with arcanus_session_factory() as session:
                shelf = session.get(Shelf, shelf_id)
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
        self, benchmark, session_factory, seeded_warehouse
    ):
        warehouse_id = seeded_warehouse.id

        def mutate():
            with session_factory() as session:
                warehouse = session.get(models.Warehouse, warehouse_id)
                session.add_all(
                    models.WarehouseItem(
                        category="fresh",
                        name=f"item-{i}",
                        quantity=i,
                        warehouse_id=warehouse.id,
                    )
                    for i in range(N_CHILDREN)
                )
                session.flush()
                session.rollback()

        benchmark(mutate)

    @pytest.mark.benchmark(group="relmut-set-groupmap")
    def test_arcanus_set_groupmap(
        self, benchmark, arcanus_session_factory, seeded_warehouse
    ):
        warehouse_id = seeded_warehouse.id

        def mutate():
            with arcanus_session_factory() as session:
                warehouse = session.get(Warehouse, warehouse_id)
                warehouse.items["fresh"] = [
                    WarehouseItem(category="fresh", name=f"item-{i}", quantity=i)
                    for i in range(N_CHILDREN)
                ]
                session.flush()
                session.rollback()

        benchmark(mutate)
