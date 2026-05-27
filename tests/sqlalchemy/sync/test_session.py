"""Test custom Session features.

Tests:
- Session context management
- get_one behavior (raises if not found)
- Object identity and caching
- Session.add and Session.add_all
- Session.delete
- Session.flush and Session.commit
- Session.rollback
- Session.expire and Session.refresh
- Session.expunge
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload as sqlalchemy_selectinload

from arcanus import Criteria
from arcanus.base import BaseTransmuter, Transmuter
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import (
    Author,
    Book,
    BookCategory,
    BookDetail,
    Category,
    Publisher,
    sqlalchemy_materia,
)


class TestSessionContextManagement:
    """Test Session context management."""

    def test_session_context_manager(self, engine: Engine):
        """Test using Session as a context manager."""
        with Session(engine) as session:
            author = Author(name="Context Test", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()

            assert author.id is not None

        # Session should be closed outside context

    def test_session_commit_on_exit(self, engine: Engine):
        """Test that changes are committed on successful context exit."""
        author_id = None
        with Session(engine) as session:
            with session.begin():
                author = Author(name="Auto Commit Test", field="Biology")
                session.add(author)
                session.flush()
                author.revalidate()
                author_id = author.id

        # Verify in new session
        with Session(engine) as session:
            retrieved = session.get_one(Author, author_id)
            assert retrieved.name == "Auto Commit Test"

    def test_session_rollback_on_exception(self, engine: Engine):
        """Test that changes are rolled back on exception."""
        author_id = 999999
        try:
            with Session(engine) as session:
                author = Author(id=author_id, name="Rollback Test", field="Chemistry")
                session.add(author)
                session.flush()
                author_id = author.id

                # Cause an exception
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Changes should be rolled back
        with Session(engine) as session:
            result = session.get(Author, author_id)
            assert result is None

    def test_nested_context_managers(self, engine: Engine):
        """Test nested Session context managers (not recommended but possible)."""
        with Session(engine) as outer_session:
            author = Author(name="Outer", field="Physics")
            outer_session.add(author)
            outer_session.flush()
            author.revalidate()
            outer_session.commit()

            author_id = author.id

            with Session(engine) as inner_session:
                # Inner session can see committed data
                inner_author = inner_session.get_one(Author, author_id)
                assert inner_author.name == "Outer"


class TestSessionHelpers:
    """Test Session helper methods: get, get_one, one, one_or_none, first, bulk, count, list, partitions."""

    def test_get_one_success(self, engine: Engine):
        """Test get_one returns object when found."""
        with Session(engine) as session:
            author = Author(name="Get One Test", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()
            author_id = author.id

            # Retrieve
            retrieved = session.get_one(Author, author_id)
            assert retrieved.id == author_id
            assert retrieved.name == "Get One Test"

    def test_get_one_raises_when_not_found(self, engine: Engine):
        """Test get_one raises NoResultFound when not found."""
        with Session(engine) as session:
            with pytest.raises(NoResultFound):
                session.get_one(Author, 999999)

    def test_get_one_vs_get(self, engine: Engine):
        """Test difference between get_one and get."""
        with Session(engine) as session:
            # get returns None
            result = session.get(Author, 999999)
            assert result is None

            # get_one raises
            with pytest.raises(NoResultFound):
                session.get_one(Author, 999999)

    def test_one_success(self, engine: Engine):
        """Test one returns single matching entity."""
        with Session(engine) as session:
            author1 = Author(name="One Test 1", field="Physics")
            author2 = Author(name="One Test 2", field="Biology")
            session.add_all([author1, author2])
            session.flush()
            author1.revalidate()

            # Query by filter
            result = session.one(Author, name="One Test 1")
            assert result.id == author1.id
            assert result.name == "One Test 1"

    def test_one_with_expressions(self, engine: Engine):
        """Test one with where expressions."""
        with Session(engine) as session:
            author1 = Author(name="Expression Test 1", field="Physics")
            author2 = Author(name="Expression Test 2", field="Physics")
            session.add_all([author1, author2])
            session.flush()
            author1.revalidate()

            # Query with expression
            result = session.one(
                Author, expressions=[Author["name"] == "Expression Test 1"]
            )
            assert result.id == author1.id

    def test_one_raises_when_no_result(self, engine: Engine):
        """Test one raises NoResultFound when no match."""
        with Session(engine) as session:
            with pytest.raises(NoResultFound):
                session.one(Author, name="Nonexistent")

    def test_one_raises_when_multiple_results(self, engine: Engine):
        """Test one raises when multiple results found."""
        from sqlalchemy.exc import MultipleResultsFound

        with Session(engine) as session:
            author1 = Author(name="Multiple Test", field="Physics")
            author2 = Author(name="Multiple Test", field="Biology")
            session.add_all([author1, author2])
            session.flush()

            with pytest.raises(MultipleResultsFound):
                session.one(Author, name="Multiple Test")

    def test_one_or_none_success(self, engine: Engine):
        """Test one_or_none returns entity when found."""
        with Session(engine) as session:
            author = Author(name="One Or None Test", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            result = session.one_or_none(Author, name="One Or None Test")
            assert result is not None
            assert result.id == author.id

    def test_one_or_none_returns_none(self, engine: Engine):
        """Test one_or_none returns None when not found."""
        with Session(engine) as session:
            result = session.one_or_none(Author, name="Nonexistent")
            assert result is None

    def test_one_or_none_with_filters_and_expressions(self, engine: Engine):
        """Test one_or_none with both filters and expressions."""
        with Session(engine) as session:
            author = Author(name="Combined Test", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()

            result = session.one_or_none(
                Author, expressions=[Author["field"] == "Physics"], name="Combined Test"
            )
            assert result is not None
            assert result.id == author.id

    def test_first_returns_first_result(self, engine: Engine):
        """Test first returns first entity."""
        with Session(engine) as session:
            author1 = Author(name="First Test A", field="Physics")
            author2 = Author(name="First Test B", field="Physics")
            session.add_all([author1, author2])
            session.flush()
            author1.revalidate()
            author2.revalidate()

            result = session.first(Author, name="First Test A")
            assert result is not None
            assert result.id == author1.id

    def test_first_with_ordering(self, engine: Engine):
        """Test first respects order_by."""
        with Session(engine) as session:
            author1 = Author(name="Z Author", field="Physics")
            author2 = Author(name="A Author", field="Physics")
            session.add_all([author1, author2])
            session.flush()
            author1.revalidate()
            author2.revalidate()

            # Order by name ascending
            result = session.first(Author, order_bys=[Author["name"]], field="Physics")
            assert result is not None
            assert result.name == "A Author"

    def test_first_returns_none_when_no_match(self, engine: Engine):
        """Test first returns None when no results."""
        with Session(engine) as session:
            result = session.first(Author, name="Nonexistent")
            assert result is None

    def test_bulk_single_pk(self, engine: Engine):
        """Test bulk retrieval with single primary key."""
        with Session(engine) as session:
            authors = [Author(name=f"Bulk Test {i}", field="Physics") for i in range(5)]
            session.add_all(authors)
            session.flush()
            for a in authors:
                a.revalidate()

            ids = [a.id for a in authors]
            results = session.bulk(Author, ids)

            assert len(results) == 5
            assert all(r is not None for r in results)
            assert set(r.id for r in results if r) == set(ids)

    def test_bulk_preserves_order(self, engine: Engine):
        """Test bulk returns results in same order as idents."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Order Test {i}", field="Physics") for i in range(3)
            ]
            session.add_all(authors)
            session.flush()
            for a in authors:
                a.revalidate()

            ids = [a.id for a in authors]
            # Request in reverse order
            reversed_ids = list(reversed(ids))
            results = session.bulk(Author, reversed_ids)

            assert [r.id for r in results if r] == reversed_ids

    def test_bulk_with_missing_ids(self, engine: Engine):
        """Test bulk handles missing IDs with None."""
        with Session(engine) as session:
            author = Author(name="Bulk Missing Test", field="Biology")
            session.add(author)
            session.flush()
            author.revalidate()

            # Request existing and non-existing IDs
            ids = [author.id, 999999, 888888]
            results = session.bulk(Author, ids)

            assert len(results) == 3
            assert results[0] is not None
            assert results[0].id == author.id
            assert results[1] is None
            assert results[2] is None

    def test_bulk_empty_list(self, engine: Engine):
        """Test bulk with empty list returns empty list."""
        with Session(engine) as session:
            results = session.bulk(Author, [])
            assert results == []

    def test_bulk_composite_pk(self, engine: Engine):
        """Test bulk retrieval with composite primary key."""
        with Session(engine) as session:
            # Create authors and publishers first
            author = Author(name="Bulk Comp Author", field="Physics")
            publisher = Publisher(name="Bulk Comp Pub", country="USA")
            session.add_all([author, publisher])
            session.flush()
            author.revalidate()
            publisher.revalidate()

            # Create books and categories
            book1 = Book(title="Book 1", year=2020)
            book1.author.value = author
            book1.publisher.value = publisher
            book2 = Book(title="Book 2", year=2021)
            book2.author.value = author
            book2.publisher.value = publisher
            book3 = Book(title="Book 3", year=2022)
            book3.author.value = author
            book3.publisher.value = publisher
            cat1 = Category(name="Category 1", description="Desc 1")
            cat2 = Category(name="Category 2", description="Desc 2")
            session.add_all([book1, book2, book3, cat1, cat2])
            session.flush()
            book1.revalidate()
            book2.revalidate()
            book3.revalidate()
            cat1.revalidate()
            cat2.revalidate()

            # Create associations via relationships
            book1.categories.append(cat1)
            book2.categories.append(cat1)
            book2.categories.append(cat2)
            session.flush()

            # Bulk retrieve with composite PK tuples
            idents = [
                (book1.id, cat1.id),
                (book2.id, cat1.id),
                (book2.id, cat2.id),
            ]
            results = session.bulk(BookCategory, idents)

            assert len(results) == 3
            assert all(r is not None for r in results)
            # Verify each result matches the expected ident
            assert results[0]
            assert results[0].book_id == book1.id
            assert results[0].category_id == cat1.id
            assert results[1]
            assert results[1].book_id == book2.id
            assert results[1].category_id == cat1.id
            assert results[2]
            assert results[2].book_id == book2.id
            assert results[2].category_id == cat2.id

    def test_bulk_composite_pk_with_missing(self, engine: Engine):
        """Test bulk with composite PK handles missing entries."""
        with Session(engine) as session:
            # Create author and publisher first
            author = Author(name="Bulk Comp Missing Author", field="Biology")
            publisher = Publisher(name="Bulk Comp Missing Pub", country="UK")
            session.add_all([author, publisher])
            session.flush()
            author.revalidate()
            publisher.revalidate()

            # Create one book and category
            book = Book(title="Bulk Comp Missing", year=2023)
            book.author.value = author
            book.publisher.value = publisher
            cat = Category(name="Bulk Comp Cat", description="Desc")
            session.add_all([book, cat])
            session.flush()
            book.revalidate()
            cat.revalidate()

            # Create association via relationship
            book.categories.append(cat)
            session.flush()

            # Request existing and non-existing composite PKs
            idents = [
                (book.id, cat.id),  # exists
                (999999, 888888),  # doesn't exist
                (777777, 666666),  # doesn't exist
            ]
            results = session.bulk(BookCategory, idents)

            assert len(results) == 3
            assert results[0] is not None
            assert results[0].book_id == book.id
            assert results[0].category_id == cat.id
            assert results[1] is None
            assert results[2] is None

    def test_count_all(self, engine: Engine):
        """Test count without filters."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Count Test {i}", field="Physics") for i in range(7)
            ]
            session.add_all(authors)
            session.flush()

            count = session.count(Author, field="Physics")
            assert count >= 7  # At least the ones we added

    def test_count_with_filters(self, engine: Engine):
        """Test count with filter_by."""
        with Session(engine) as session:
            author1 = Author(name="Count Filter 1", field="Physics")
            author2 = Author(name="Count Filter 2", field="Biology")
            author3 = Author(name="Count Filter 3", field="Physics")
            session.add_all([author1, author2, author3])
            session.flush()

            count_physics = session.count(Author, field="Physics")
            count_biology = session.count(Author, field="Biology")

            assert count_physics >= 2
            assert count_biology >= 1

    def test_count_with_expressions(self, engine: Engine):
        """Test count with where expressions."""
        with Session(engine) as session:
            authors = [
                Author(name="Count Expr A", field="Physics"),
                Author(name="Count Expr B", field="Physics"),
                Author(name="Count Expr C", field="Biology"),
            ]
            session.add_all(authors)
            session.flush()

            count = session.count(
                Author,
                expressions=[
                    Author["name"].like("Count Expr%"),
                    Author["field"] == "Physics",
                ],
            )
            assert count >= 2

    def test_sqlalchemy_expression_compiler_translates_operator_tree(
        self, engine: Engine
    ):
        """Test the material compiler translates arcanus expression trees."""
        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Compiler Tree A", field="Physics"),
                    Author(name="Compiler Tree B", field="Chemistry"),
                    Author(name="Compiler Tree Outside", field="Physics"),
                    Author(name="Compiler Tree Biology", field="Biology"),
                ]
            )
            session.flush()

            expression = (
                Author["name"].contains("Compiler Tree")
                & Author["field"].in_(("Physics", "Chemistry"))
                & Author["field"].not_in(("Biology",))
                & ~Author["name"].ends_with("Outside")
            )
            compiled_expression = expression(sqlalchemy_materia.expression_compiler)
            compiled_order = Author["name"].asc()(
                sqlalchemy_materia.expression_compiler
            )

            results = (
                session.execute(
                    select(Author).where(compiled_expression).order_by(compiled_order)
                )
                .scalars()
                .all()
            )

            assert [author.name for author in results] == [
                "Compiler Tree A",
                "Compiler Tree B",
            ]

    def test_column_expression_and_order_interop_with_native_sqlalchemy(
        self, engine: Engine
    ):
        """Test arcanus columns and expressions work in raw SQLAlchemy statements."""
        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Native Interop B", field="Robotics"),
                    Author(name="Native Interop A", field="Robotics"),
                    Author(name="Native Interop Outside", field="Physics"),
                ]
            )
            session.flush()

            names = (
                session.execute(
                    select(Author["name"])
                    .where(Author["name"].starts_with("Native Interop"))
                    .where(Author["field"] == "Robotics")
                    .order_by(Author["name"].asc())
                )
                .scalars()
                .all()
            )

            assert names == ["Native Interop A", "Native Interop B"]

    def test_mixed_native_and_arcanus_expressions_are_accepted(self, engine: Engine):
        """Test native SQLAlchemy expressions can be mixed with arcanus expressions."""
        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Mixed Expression A", field="Physics"),
                    Author(name="Mixed Expression B", field="Biology"),
                    Author(name="Mixed Expression Outside", field="Physics"),
                ]
            )
            session.flush()

            results = session.list(
                Author,
                order_bys=[Author["name"].desc()],
                expressions=[
                    Author["name"].native.like("Mixed Expression%"),
                    Author["name"].native != "Mixed Expression Outside",
                    Author["field"] != "Biology",
                ],
            )

            assert [author.name for author in results] == ["Mixed Expression A"]

    def test_count_accepts_arcanus_boolean_logic_expressions(self, engine: Engine):
        """Test count accepts arcanus expressions with boolean composition."""
        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Count Logic A", field="Physics"),
                    Author(name="Count Logic B", field="Biology"),
                    Author(name="Count Logic C", field="Chemistry"),
                    Author(name="Count Logic Outside", field="History"),
                ]
            )
            session.flush()

            expression = Author["name"].starts_with("Count Logic") & (
                (Author["field"] == "Physics")
                | (Author["field"] == "Biology")
                | (Author["field"] == "Chemistry")
            )
            count = session.count(Author, expressions=[expression])

            assert count == 3

    def test_list_basic(self, engine: Engine):
        """Test list returns multiple entities."""
        with Session(engine) as session:
            authors = [
                Author(name=f"List Test {i}", field="Chemistry") for i in range(5)
            ]
            session.add_all(authors)
            session.flush()
            for a in authors:
                a.revalidate()

            results = session.list(Author, field="Chemistry")
            assert len(results) >= 5

    def test_list_with_limit(self, engine: Engine):
        """Test list respects limit."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Limit Test {i}", field="Chemistry") for i in range(10)
            ]
            session.add_all(authors)
            session.flush()

            results = session.list(Author, limit=3, field="Chemistry")
            assert len(results) == 3

    def test_list_with_offset(self, engine: Engine):
        """Test list respects offset."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Offset Test {i}", field="Literature") for i in range(5)
            ]
            session.add_all(authors)
            session.flush()
            for a in authors:
                a.revalidate()

            # Get all, then with offset
            all_results = session.list(
                Author, limit=100, order_bys=[Author["id"]], field="Literature"
            )
            offset_results = session.list(
                Author,
                limit=100,
                offset=2,
                order_bys=[Author["id"]],
                field="Literature",
            )

            assert len(all_results) >= 5
            assert len(offset_results) >= 3
            assert offset_results[0].id == all_results[2].id

    def test_list_with_ordering(self, engine: Engine):
        """Test list respects order_by."""
        with Session(engine) as session:
            author1 = Author(name="Z List", field="History")
            author2 = Author(name="A List", field="History")
            author3 = Author(name="M List", field="History")
            session.add_all([author1, author2, author3])
            session.flush()

            results = session.list(Author, order_bys=[Author["name"]], field="History")
            names = [r.name for r in results]
            # Should be in ascending order
            assert names.index("A List") < names.index("M List") < names.index("Z List")

    def test_list_with_filters_and_expressions(self, engine: Engine):
        """Test list with both filters and expressions."""
        with Session(engine) as session:
            authors = [
                Author(name="List Filter A", field="Physics"),
                Author(name="List Filter B", field="Physics"),
                Author(name="List Filter C", field="Biology"),
            ]
            session.add_all(authors)
            session.flush()

            results = session.list(
                Author,
                expressions=[Author["name"].like("List Filter%")],
                field="Physics",
            )
            assert len(results) >= 2
            assert all(r.field == "Physics" for r in results)

    def test_list_compiles_arcanus_expressions_and_orders(self, engine: Engine):
        """Test list accepts arcanus expression inputs."""
        with Session(engine) as session:
            authors = [
                Author(name="Expression Order C", field="Robotics"),
                Author(name="Expression Order A", field="Robotics"),
                Author(name="Expression Order B", field="Robotics"),
            ]
            session.add_all(authors)
            session.flush()
            results = session.list(
                Author,
                order_bys=[Author["name"].desc()],
                expressions=[Author["name"].like("Expression Order%")],
                field="Robotics",
            )

            assert [author.name for author in results] == [
                "Expression Order C",
                "Expression Order B",
                "Expression Order A",
            ]

    def test_list_count_and_partitions_with_relationship_expressions(
        self, engine: Engine
    ):
        """Test relationship columns can filter through native SQLAlchemy helpers."""
        with Session(engine) as session:
            publisher = Publisher(name="Relationship Filter Pub", country="USA")
            matching_author = Author(
                name="Relationship Filter Author", field="Astrophysics"
            )
            other_author = Author(name="Relationship Filter Other", field="History")
            category = Category(
                name="Relationship Filter Category", description="Deep space"
            )
            other_category = Category(
                name="Relationship Filter Other Category",
                description="Near ground",
            )
            matching_book = Book(title="Relationship Filter Match", year=2024)
            matching_book.author.value = matching_author
            matching_book.publisher.value = publisher
            matching_book.detail.value = BookDetail(
                isbn="978-8888800001",
                pages=420,
                abstract="Relationship expression match",
            )
            matching_book.categories.append(category)

            wrong_author_book = Book(
                title="Relationship Filter Wrong Author", year=2024
            )
            wrong_author_book.author.value = other_author
            wrong_author_book.publisher.value = publisher
            wrong_author_book.detail.value = BookDetail(
                isbn="978-8888800002",
                pages=520,
                abstract="Wrong author",
            )
            wrong_author_book.categories.append(category)

            wrong_category_book = Book(
                title="Relationship Filter Wrong Category", year=2024
            )
            wrong_category_book.author.value = matching_author
            wrong_category_book.publisher.value = publisher
            wrong_category_book.detail.value = BookDetail(
                isbn="978-8888800003",
                pages=620,
                abstract="Wrong category",
            )
            wrong_category_book.categories.append(other_category)

            short_book = Book(title="Relationship Filter Short", year=2024)
            short_book.author.value = matching_author
            short_book.publisher.value = publisher
            short_book.detail.value = BookDetail(
                isbn="978-8888800004",
                pages=120,
                abstract="Too short",
            )
            short_book.categories.append(category)

            session.add_all(
                [matching_book, wrong_author_book, wrong_category_book, short_book]
            )
            session.flush()

            expression = (
                Book["author"].has(Author["field"] == "Astrophysics")
                & Book["categories"].any(
                    Category["name"] == "Relationship Filter Category"
                )
                & Book["detail"].has(BookDetail["pages"] >= 300)
            )
            results = session.list(
                Book,
                expressions=[expression],
                order_bys=[Book["title"]],
            )
            count = session.count(Book, expressions=[expression])
            partitions = list(
                session.partitions(
                    Book,
                    size=1,
                    expressions=[expression],
                    order_bys=[Book["title"]],
                )
            )

            assert [book.title for book in results] == ["Relationship Filter Match"]
            assert count == 1
            assert [[book.title for book in partition] for partition in partitions] == [
                ["Relationship Filter Match"]
            ]

            exists_results = session.list(
                Book,
                expressions=[
                    Book["categories"].any(
                        Category["name"] == "Relationship Filter Category"
                    ),
                    Book["author"].has(Author["field"] == "Astrophysics"),
                ],
                order_bys=[Book["title"]],
            )
            assert [book.title for book in exists_results] == [
                "Relationship Filter Match",
                "Relationship Filter Short",
            ]

    def test_original_sqlalchemy_loader_options_accept_columns_at_runtime(
        self, engine: Engine
    ):
        """Test SQLAlchemy's own loader functions inspect arcanus columns."""
        with Session(engine) as session:
            author = Author(name="Native Loader Author", field="History")
            publisher = Publisher(name="Native Loader Publisher", country="USA")
            book = Book(title="Native Loader Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher
            session.add(book)
            session.flush()

            result = session.execute(
                select(Book)
                .options(sqlalchemy_selectinload(cast(Any, Book["author"])))
                .where(Book["title"] == "Native Loader Book")
            ).scalar_one()

            assert result.author.value.name == "Native Loader Author"

    def test_list_with_json_criteria_expression_and_compiler_chain(
        self, engine: Engine
    ):
        """Test JSON criteria values can drive arcanus and SQLAlchemy expressions."""
        criteria_model = Criteria[Author]
        payload = {
            "name": {"starts_with": "Criteria Chain"},
            "field": {"eq": "Xenobiology"},
        }
        limit = 2
        orders = (Author["name"].desc(),)

        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Criteria Chain C", field="Xenobiology"),
                    Author(name="Criteria Chain A", field="Xenobiology"),
                    Author(name="Criteria Chain B", field="Xenobiology"),
                    Author(name="Criteria Chain Outside", field="Robotics"),
                ]
            )
            session.flush()

            criteria = criteria_model.model_validate_json(json.dumps(payload))
            restored = criteria_model.model_validate_json(
                criteria.model_dump_json(by_alias=True, exclude_none=True)
            )
            assert restored.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == criteria.model_dump(mode="json", by_alias=True, exclude_none=True)

            assert criteria.expression is not None
            criteria_expression = criteria.expression
            compiled_expression = criteria_expression(
                sqlalchemy_materia.expression_compiler
            )
            compiled_order_bys = tuple(
                order_by(sqlalchemy_materia.expression_compiler) for order_by in orders
            )

            manual_results = (
                session.execute(
                    select(Author)
                    .where(compiled_expression)
                    .order_by(*compiled_order_bys)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            list_results = session.list(
                Author,
                expressions=[criteria_expression],
                order_bys=orders,
                limit=limit,
            )

            assert [author.name for author in manual_results] == [
                "Criteria Chain C",
                "Criteria Chain B",
            ]
            assert [author.name for author in list_results] == [
                author.name for author in manual_results
            ]

    def test_list_with_text_range_criteria(self, engine: Engine):
        """Text criteria range operators compile through SQLAlchemy string columns."""
        criteria_model = Criteria[Author]
        payload = {
            "name": {"gt": "Text Range B", "le": "Text Range G"},
            "field": {"eq": "Astronomy"},
        }
        orders = (Author["name"].asc(),)

        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Text Range A", field="Astronomy"),
                    Author(name="Text Range C", field="Astronomy"),
                    Author(name="Text Range G", field="Astronomy"),
                    Author(name="Text Range Z", field="Astronomy"),
                    Author(name="Text Range C", field="Robotics"),
                ]
            )
            session.flush()

            criteria = criteria_model.model_validate(payload)
            assert criteria.expression is not None
            criteria_expression = criteria.expression
            compiled_expression = criteria_expression(
                sqlalchemy_materia.expression_compiler
            )
            compiled_order_bys = tuple(
                order_by(sqlalchemy_materia.expression_compiler) for order_by in orders
            )

            manual_results = (
                session.execute(
                    select(Author).where(compiled_expression).order_by(*compiled_order_bys)
                )
                .scalars()
                .all()
            )
            list_results = session.list(
                Author,
                expressions=[criteria_expression],
                order_bys=orders,
            )

            assert [author.name for author in manual_results] == [
                "Text Range C",
                "Text Range G",
            ]
            assert [author.name for author in list_results] == [
                author.name for author in manual_results
            ]

    def test_partitions_yields_chunks(self, engine: Engine):
        """Test partitions yields results in chunks."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Partition Test {i}", field="Astronomy") for i in range(15)
            ]
            session.add_all(authors)
            session.flush()

            partitions_list = list(
                session.partitions(Author, size=5, limit=15, field="Astronomy")
            )

            # Should have 3 partitions of size 5
            assert len(partitions_list) >= 3
            for partition in partitions_list[:3]:
                assert len(partition) <= 5

    def test_partitions_respects_limit(self, engine: Engine):
        """Test partitions respects total limit."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Part Limit Test {i}", field="History") for i in range(20)
            ]
            session.add_all(authors)
            session.flush()

            all_results = []
            for partition in session.partitions(
                Author, size=3, limit=7, field="History"
            ):
                all_results.extend(partition)

            assert len(all_results) == 7

    def test_partitions_with_ordering(self, engine: Engine):
        """Test partitions respects ordering."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Part Order {chr(65 + i)}", field="Literature")
                for i in range(10)
            ]
            session.add_all(authors)
            session.flush()

            all_results = []
            for partition in session.partitions(
                Author, size=3, order_bys=[Author["name"]], field="Literature"
            ):
                all_results.extend(partition)

            names = [r.name for r in all_results]
            # Should be in ascending order
            assert names == sorted(names)

    def test_partitions_compiles_arcanus_expressions_and_orders(self, engine: Engine):
        """Test partitions accepts arcanus expression inputs."""
        with Session(engine) as session:
            authors = [
                Author(name="Part Expression C", field="Cybernetics"),
                Author(name="Part Expression A", field="Cybernetics"),
                Author(name="Part Expression B", field="Cybernetics"),
            ]
            session.add_all(authors)
            session.flush()

            all_results = []
            for partition in session.partitions(
                Author,
                size=2,
                order_bys=[Author["name"].asc()],
                expressions=[Author["name"].like("Part Expression%")],
                field="Cybernetics",
            ):
                all_results.extend(partition)

            assert [author.name for author in all_results] == [
                "Part Expression A",
                "Part Expression B",
                "Part Expression C",
            ]

    def test_partitions_with_json_criteria_expression_and_orders(self, engine: Engine):
        """Test partitions accepts criteria-derived arcanus expressions and orders."""
        criteria_model = Criteria[Author]
        payload = {
            "name": {"starts_with": "Criteria Partition"},
            "field": {"eq": "Astrophysics"},
        }
        limit = 3
        orders = (Author["name"].asc(),)

        with Session(engine) as session:
            session.add_all(
                [
                    Author(name="Criteria Partition C", field="Astrophysics"),
                    Author(name="Criteria Partition A", field="Astrophysics"),
                    Author(name="Criteria Partition D", field="Astrophysics"),
                    Author(name="Criteria Partition B", field="Astrophysics"),
                    Author(name="Criteria Partition Outside", field="Astronomy"),
                ]
            )
            session.flush()

            criteria = criteria_model.model_validate_json(json.dumps(payload))
            assert criteria.expression is not None

            all_results = []
            for partition in session.partitions(
                Author,
                size=2,
                limit=limit,
                order_bys=orders,
                expressions=[criteria.expression],
            ):
                all_results.extend(partition)

            assert [author.name for author in all_results] == [
                "Criteria Partition A",
                "Criteria Partition B",
                "Criteria Partition C",
            ]

    def test_partitions_with_filters(self, engine: Engine):
        """Test partitions with filters."""
        with Session(engine) as session:
            authors = [
                Author(name="Part Filter Physics 1", field="Physics"),
                Author(name="Part Filter Physics 2", field="Physics"),
                Author(name="Part Filter Biology 1", field="Biology"),
            ]
            session.add_all(authors)
            session.flush()

            all_results = []
            for partition in session.partitions(Author, size=2, field="Physics"):
                all_results.extend(partition)

            assert len(all_results) >= 2
            assert all(r.field == "Physics" for r in all_results)


class TestObjectIdentity:
    """Test object identity and caching within a Session."""

    def test_identity_map_same_object(self, engine: Engine):
        """Test that fetching the same PK returns the same Python object."""
        with Session(engine) as session:
            author = Author(name="Identity Test", field="Biology")
            session.add(author)
            session.flush()
            author.revalidate()

            # Fetch twice
            fetch1 = session.get_one(Author, author.id)
            fetch2 = session.get_one(Author, author.id)

            # Should be the same object
            assert fetch1 is fetch2

    def test_identity_across_queries(self, engine: Engine):
        """Test identity is maintained across different query methods."""
        with Session(engine) as session:
            author = Author(name="Query Identity Test", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            # Fetch via get_one
            via_get = session.get_one(Author, author.id)

            # Fetch via query
            stmt = select(Author).where(Author["id"] == author.id)
            via_query = session.execute(stmt).scalars().one()

            # Should be the same object
            assert via_get is via_query

    def test_identity_not_shared_across_sessions(self, engine: Engine):
        """Test that different sessions have different object instances."""
        with Session(engine) as session1:
            author = Author(name="Cross Session Test", field="Physics")
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            obj1 = session1.get_one(Author, author.id)

            with Session(engine) as session2:
                obj2 = session2.get_one(Author, author.id)

                # Different objects
                assert obj1 is not obj2
                # But same data
                assert obj1.name == obj2.name

    def test_modified_object_reflects_in_identity_map(self, engine: Engine):
        """Test that modifying an object is visible through identity map."""
        with Session(engine) as session:
            author = Author(name="Original", field="Biology")
            session.add(author)
            session.flush()
            author.revalidate()

            # Get reference
            ref1 = session.get_one(Author, author.id)

            # Modify through first reference
            ref1.name = "Modified"

            # Get another reference
            ref2 = session.get_one(Author, author.id)

            # Should see modification
            assert ref2.name == "Modified"
            assert ref1 is ref2


class TestAddOperations:
    """Test Session.add and add_all operations."""

    def test_add_single_object(self, engine: Engine):
        """Test adding a single object."""
        with Session(engine) as session:
            author = Author(name="Single Add", field="Literature")
            session.add(author)
            session.flush()
            author.revalidate()

            assert author.id is not None

    def test_add_all_multiple_objects(self, engine: Engine):
        """Test adding multiple objects at once."""
        with Session(engine) as session:
            authors = [Author(name=f"Batch {i}", field="Physics") for i in range(5)]
            session.add_all(authors)
            session.flush()
            for a in authors:
                a.revalidate()

            assert all(a.id is not None for a in authors)

    def test_add_with_relationships(self, engine: Engine):
        """Test that adding parent adds related children."""
        with Session(engine) as session:
            author = Author(name="Parent Author", field="Biology")
            publisher = Publisher(name="Parent Publisher", country="USA")

            book = Book(title="Child Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            # Adding book should cascade
            session.add(book)
            session.flush()
            book.revalidate()
            author.revalidate()
            publisher.revalidate()

            assert book.id is not None
            assert author.id is not None
            assert publisher.id is not None


class TestDeleteOperations:
    """Test Session.delete operations."""

    def test_delete_single_object(self, engine: Engine):
        """Test deleting a single object."""
        with Session(engine) as session:
            author = Author(name="To Delete", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            # Delete
            session.delete(author)
            session.flush()

            # Verify
            assert session.get(Author, author.id) is None

    def test_delete_cascades_to_children(self, engine: Engine):
        """Test that deleting parent cascades to children."""
        with Session(engine) as session:
            author = Author(name="Cascade Author", field="Physics")
            publisher = Publisher(name="Cascade Publisher", country="USA")

            book = Book(title="Cascade Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()
            author.revalidate()

            # Delete author (should cascade to book due to ON DELETE CASCADE)
            session.delete(author)
            session.flush()

            # Book should be deleted
            assert session.get(Book, book.id) is None
            assert session.get(Author, author.id) is None


class TestFlushCommitRollback:
    """Test flush, commit, and rollback operations."""

    def test_flush_makes_changes_visible_in_session(self, engine: Engine):
        """Test that flush makes changes visible within the session."""
        with Session(engine) as session:
            author = Author(name="Flush Test", field="Biology")
            session.add(author)

            # Before flush, no ID
            assert author.id is None

            # After flush
            session.flush()
            author.revalidate()
            assert author.id is not None

            # But not yet committed
            # (We can't easily test this in the same session)

    def test_commit_persists_changes(self, engine: Engine):
        """Test that commit persists changes to database."""
        with Session(engine) as session:
            author = Author(name="Commit Test", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()
            author_id = author.id
            session.commit()

        # Verify in new session
        with Session(engine) as session:
            retrieved = session.get_one(Author, author_id)
            assert retrieved.name == "Commit Test"

    def test_rollback_reverts_changes(self, engine: Engine):
        """Test that rollback reverts unflushed/uncommitted changes."""
        with Session(engine) as session:
            author = Author(name="Rollback Test", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()
            session.commit()  # Commit the original insert

            # Modify
            author.name = "Modified"
            session.flush()

            # Rollback only reverts the modification
            session.rollback()

            # Refresh the author object to reload from database
            session.refresh(author)
            author.revalidate()
            assert author.name == "Rollback Test"

    def test_multiple_flush_before_commit(self, engine: Engine):
        """Test multiple flushes before final commit."""
        with Session(engine) as session:
            author = Author(name="Multi Flush", field="Literature")
            session.add(author)
            session.flush()

            author.name = "Multi Flush Updated 1"
            session.flush()

            author.name = "Multi Flush Updated 2"
            session.flush()

            assert author.name == "Multi Flush Updated 2"


class TestExpireRefresh:
    """Test expire and refresh operations."""

    def test_expire_reloads_on_access(self, engine: Engine):
        """Test that expiring an object reloads it on next access."""
        with Session(engine) as session:
            author = Author(name="Expire Test", field="Biology")
            session.add(author)
            session.flush()
            author.revalidate()

            # Modify in database directly (simulate external change)
            stmt = (
                update(Author)
                .where(Author["id"] == author.id)
                .values(name="Externally Modified")
            )
            session.execute(stmt)
            session.commit()

            # Object still has old value in memory
            # (Unless we expire and refresh it)

            # Expire and refresh to reload from database
            session.expire(author)
            session.refresh(author)
            author.revalidate()
            # Next access should show new value
            assert author.name == "Externally Modified"

    def test_refresh_reloads_immediately(self, engine: Engine):
        """Test that refresh reloads object immediately."""
        with Session(engine) as session:
            author = Author(name="Refresh Test", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            # Modify in database
            stmt = (
                update(Author)
                .where(Author["id"] == author.id)
                .values(name="DB Modified")
            )
            session.execute(stmt)
            session.commit()

            # Refresh to load new value
            session.refresh(author)
            assert author.name == "DB Modified"

    def test_expire_all(self, engine: Engine):
        """Test expiring all objects in session."""
        with Session(engine) as session:
            author1 = Author(name="Expire All 1", field="Physics")
            author2 = Author(name="Expire All 2", field="Biology")
            session.add_all([author1, author2])
            session.flush()

            # Expire all
            session.expire_all()

            # Next access should reload
            assert author1.name == "Expire All 1"
            assert author2.name == "Expire All 2"


class TestExpunge:
    """Test expunging objects from session."""

    def test_expunge_removes_from_session(self, engine: Engine):
        """Test that expunge removes object from session."""
        with Session(engine) as session:
            author = Author(name="Expunge Test", field="Literature")
            session.add(author)
            session.flush()
            author.revalidate()

            # Expunge
            session.expunge(author)

            # Object no longer in session
            # Getting it again returns a different instance
            author2 = session.get_one(Author, author.id)
            assert author is not author2

    def test_expunge_all(self, engine: Engine):
        """Test expunging all objects from session."""
        with Session(engine) as session:
            author1 = Author(name="Expunge All 1", field="Physics")
            author2 = Author(name="Expunge All 2", field="Biology")
            session.add_all([author1, author2])
            session.flush()
            author1.revalidate()
            author2.revalidate()

            # Expunge all
            session.expunge_all()

            # Fetching again returns new instances
            new1 = session.get_one(Author, author1.id)
            new2 = session.get_one(Author, author2.id)

            assert new1 is not author1
            assert new2 is not author2


class TestMerge:
    """Test Session.merge functionality."""

    def test_merge_detached_object(self, engine: Engine, test_id: uuid.UUID):
        """Test merging a detached object back into a session."""
        author_id = None
        author_detached = None

        # Create and detach
        with Session(engine) as session1:
            author = Author(name="Merge Test", field="Physics", test_id=test_id)
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            author_id = author.id
            author_detached = author

        # Author is now detached

        # Merge into new session
        with Session(engine) as session2:
            author_merged = session2.merge(author_detached)

            # Verify the merged object is revalidated and works correctly
            assert author_merged.id == author_id
            assert author_merged.name == "Merge Test"
            assert author_merged.field == "Physics"

            # Modify and flush to verify it's properly tracked
            author_merged.name = "Merged and Modified"
            session2.flush()
            session2.commit()

        # Verify changes persisted
        with Session(engine) as session3:
            author_final = session3.get_one(Author, author_id)
            assert author_final.name == "Merged and Modified"

    def test_merge_with_modifications(self, engine: Engine):
        """Test merging an object with pending modifications."""
        # Create original
        with Session(engine) as session1:
            author = Author(name="Original Name", field="Biology")
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            author_id = author.id

        # Get in new session and modify
        with Session(engine) as session2:
            author = session2.get_one(Author, author_id)

        # Now author is detached, modify it
        author.name = "Modified While Detached"

        # Merge back into another session
        with Session(engine) as session3:
            merged = session3.merge(author)
            assert merged.name == "Modified While Detached"
            session3.commit()

        # Verify persistence
        with Session(engine) as session4:
            final = session4.get_one(Author, author_id)
            assert final.name == "Modified While Detached"

    def test_merge_with_load_false(self, engine: Engine):
        """Test merge with load=False parameter."""
        # Create object
        with Session(engine) as session1:
            author = Author(name="Load Test", field="Chemistry")
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            author_id = author.id

        # Get and detach
        with Session(engine) as session2:
            author = session2.get_one(Author, author_id)

        # Merge with load=False
        with Session(engine) as session3:
            merged = session3.merge(author, load=False)
            assert merged.id == author_id
            assert merged.name == "Load Test"

    def test_merge_updates_existing_in_session(self, engine: Engine):
        """Test that merge updates an already-loaded instance."""
        author_id = None

        # Create
        with Session(engine) as session1:
            author = Author(name="Initial Name", field="History")
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            author_id = author.id

        with Session(engine) as session2:
            # Load into session
            author_in_session = session2.get_one(Author, author_id)
            assert author_in_session.name == "Initial Name"

            # Create a detached copy with different data
            author_detached = Author(id=author_id, name="Updated Name", field="History")

            # Merge should update the existing instance
            merged = session2.merge(author_detached)

            # The merged instance should be the same object that was already in session
            assert merged is author_in_session
            assert merged.name == "Updated Name"

    def test_merge_returns_revalidated_transmuter(self, engine: Engine):
        """Test that merge returns a properly revalidated transmuter instance."""
        # Create
        with Session(engine) as session1:
            publisher = Publisher(name="Test Publisher", country="USA")
            session1.add(publisher)
            session1.flush()
            publisher.revalidate()
            session1.commit()
            publisher_id = publisher.id

        # Detach
        with Session(engine) as session2:
            publisher = session2.get_one(Publisher, publisher_id)

        # Merge and verify it's a transmuter with proper proxy
        with Session(engine) as session3:
            merged = session3.merge(publisher)

            # Should be a transmuter instance
            assert isinstance(merged, Publisher)
            assert isinstance(merged, BaseTransmuter)

            # Should have proper ORM backing
            assert merged.__transmuter_provided__ is not None

            # Modify to ensure it's properly tracked
            merged.name = "Updated Publisher"
            session3.flush()
            session3.commit()

        # Verify update persisted
        with Session(engine) as session4:
            final = session4.get_one(Publisher, publisher_id)
            assert final.name == "Updated Publisher"

    def test_merge_maintains_validation_context(self, engine: Engine):
        """Test that merge properly maintains validation context."""
        # Create a simple object
        with Session(engine) as session1:
            author = Author(name="Context Author", field="Physics")
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()
            author_id = author.id

        # Load and detach
        with Session(engine) as session2:
            author = session2.get_one(Author, author_id)

        # Merge into new session
        with Session(engine) as session3:
            merged_author = session3.merge(author)

            # The merged object should be in the validation context
            assert merged_author.__transmuter_provided__ in session3._validation_context
            assert (
                session3._validation_context[merged_author.__transmuter_provided__]
                is merged_author
            )

    def test_merge_with_multiple_objects(self, engine: Engine):
        """Test merging multiple objects."""
        # Create multiple objects
        with Session(engine) as session1:
            author1 = Author(name="Author 1", field="Biology")
            author2 = Author(name="Author 2", field="Chemistry")

            session1.add_all([author1, author2])
            session1.flush()
            author1.revalidate()
            author2.revalidate()
            session1.commit()

            author1_id = author1.id
            author2_id = author2.id

        # Load and detach
        with Session(engine) as session2:
            author1 = session2.get_one(Author, author1_id)
            author2 = session2.get_one(Author, author2_id)

        # Modify while detached
        author1.name = "Modified Author 1"
        author2.field = "Astronomy"

        # Merge both into new session
        with Session(engine) as session3:
            merged1 = session3.merge(author1)
            merged2 = session3.merge(author2)

            # Verify modifications are present
            assert merged1.name == "Modified Author 1"
            assert merged2.field == "Astronomy"

            session3.flush()
            session3.commit()

        # Verify all changes persisted
        with Session(engine) as session4:
            final1 = session4.get_one(Author, author1_id)
            final2 = session4.get_one(Author, author2_id)

            assert final1.name == "Modified Author 1"
            assert final2.field == "Astronomy"

    def test_merge_after_expunge(self, engine: Engine):
        """Test merging an object that was explicitly expunged."""
        with Session(engine) as session1:
            author = Author(name="Expunge Test", field="History")
            session1.add(author)
            session1.flush()
            author.revalidate()
            author_id = author.id

            # Expunge the object
            session1.expunge(author)

            # Merge it back
            merged = session1.merge(author)

            assert merged.id == author_id
            assert merged.name == "Expunge Test"

            # Modify and commit
            merged.field = "Literature"
            session1.commit()

        # Verify changes persisted
        with Session(engine) as session2:
            final = session2.get_one(Author, author_id)
            assert final.field == "Literature"

    def test_merge_revalidates_transmuter(self, engine: Engine):
        """Test that merge properly revalidates the transmuter instance."""
        # Create
        with Session(engine) as session1:
            category = Category(name="Test Category", description="Test Description")
            session1.add(category)
            session1.flush()
            category.revalidate()
            session1.commit()
            category_id = category.id

        # Load and detach
        with Session(engine) as session2:
            category = session2.get_one(Category, category_id)

        # Verify it's detached (no longer in session)
        # Merge into new session
        with Session(engine) as session3:
            merged = session3.merge(category)

            # Verify returned instance is properly setup
            assert isinstance(merged, Category)
            assert isinstance(merged, Transmuter)
            assert merged.id == category_id
            assert merged.name == "Test Category"

            # Modify to confirm tracking
            merged.description = "Updated Description"
            session3.flush()
            session3.commit()

        # Verify update
        with Session(engine) as session4:
            final = session4.get_one(Category, category_id)
            assert final.description == "Updated Description"
