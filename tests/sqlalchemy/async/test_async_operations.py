"""Test async SQLAlchemy materia support.

Tests:
- AsyncSession context management
- AsyncResult streaming and iteration
- Basic async CRUD operations
- Async relationship loading

Note: These tests are less detailed than sync tests because SQLAlchemy
reuses sync code via greenlet, so comprehensive testing is done in sync tests.
"""

from __future__ import annotations

import json
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine

from arcanus import Criteria
from arcanus.materia.sqlalchemy import AsyncSession, raiseload, selectinload
from tests.transmuters import (
    Author,
    Book,
    BookCategory,
    BookDetail,
    Category,
    Publisher,
    sqlalchemy_materia,
)


class TestAsyncSessionContextManagement:
    """Test AsyncSession context manager behavior."""

    @pytest.mark.asyncio
    async def test_async_session_auto_commit_on_success(
        self, async_engine: AsyncEngine, test_id: UUID
    ):
        """Test that async session auto-commits on successful exit."""
        async with AsyncSession(async_engine) as session, session.begin():
            author = Author(name="Async Author", field="Physics", test_id=test_id)
            session.add(author)
            await session.flush()
            author.revalidate()

        async with AsyncSession(async_engine) as session:
            fetched = await session.get_one(Author, author.id)
            assert fetched.name == "Async Author"

    @pytest.mark.asyncio
    async def test_async_session_rollback_on_exception(self, async_engine: AsyncEngine):
        """Test that async session rolls back on exception."""
        try:
            async with AsyncSession(async_engine) as session:
                author = Author(name="Rollback Test", field="Biology")
                session.add(author)
                await session.flush()

                # Force exception
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Author should not be committed
        async with AsyncSession(async_engine) as session:
            stmt = select(Author).where(Author["name"] == "Rollback Test")
            result = await session.execute(stmt)
            authors = result.scalars().all()
            assert len(authors) == 0


class TestAsyncCRUDOperations:
    """Test basic async CRUD operations."""

    @pytest.mark.asyncio
    async def test_async_create_and_read(self, async_engine: AsyncEngine):
        """Test async insert and select."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Insert Author", field="Chemistry")
            session.add(author)
            await session.flush()

            # Select
            author.revalidate()
            fetched = await session.get_one(Author, author.id)
            assert fetched.name == "Insert Author"

    @pytest.mark.asyncio
    async def test_async_update(self, async_engine: AsyncEngine):
        """Test async update operation."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Update Test", field="Physics")
            session.add(author)
            await session.flush()

            # Update
            author.name = "Updated Async"
            await session.flush()

            # Verify
            author.revalidate()
            fetched = await session.get_one(Author, author.id)
            assert fetched.name == "Updated Async"

    @pytest.mark.asyncio
    async def test_async_update_returning_refreshes_cached_transmuter(
        self, async_engine: AsyncEngine
    ):
        """Async UPDATE ... RETURNING re-syncs a transmuter cached in the session."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Async Returning Before", field="Physics")
            session.add(author)
            await session.flush()  # author cached in the validation context

            result = await session.execute(
                update(Author)
                .where(Author["id"] == author.id)
                .values(name="Async Returning After")
                .returning(Author)
            )
            returned = result.scalar_one()

            assert returned is author
            assert returned.name == "Async Returning After"  # refreshed, not stale
            assert author.name == "Async Returning After"

    @pytest.mark.asyncio
    async def test_async_delete(self, async_engine: AsyncEngine):
        """Test async delete operation."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Delete Test", field="Biology")
            session.add(author)
            await session.flush()

            # Delete
            author.revalidate()
            await session.delete(author)
            await session.flush()

            # Verify deleted
            stmt = select(Author).where(Author["id"] == author.id)
            result = await session.execute(stmt)
            authors = result.scalars().all()
            assert len(authors) == 0


class TestAsyncResultStreaming:
    """Test AsyncResult streaming capabilities."""

    @pytest.mark.asyncio
    async def test_async_stream_scalars(self, async_engine: AsyncEngine):
        """Test async streaming scalars."""
        # Create test data
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Stream Author {i}", field="Physics") for i in range(5)
            ]
            session.add_all(authors)
            await session.flush()

            stmt = select(Author).where(Author["name"].startswith("Stream Author"))
            result = await session.stream(stmt)

            count = 0
            async for author in result.scalars():
                assert author.name.startswith("Stream Author")
                count += 1

            assert count == 5

    @pytest.mark.asyncio
    async def test_async_stream_partitions(self, async_engine: AsyncEngine):
        """Test async streaming with partitions."""
        # Create test data
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Partition Author {i}", field="Biology") for i in range(10)
            ]
            session.add_all(authors)
            await session.flush()

            stmt = select(Author).where(Author["name"].startswith("Partition Author"))
            result = await session.stream(stmt)

            partition_count = 0
            async for partition in result.scalars().partitions(3):
                assert len(partition) <= 3
                partition_count += 1

            # Should have 4 partitions (3 + 3 + 3 + 1)
            assert partition_count == 4

    @pytest.mark.asyncio
    async def test_async_stream_with_yield_per_execution_option(
        self, async_engine: AsyncEngine
    ):
        """Test that _yield_per is propagated to adapted result so that
        SQLAlchemy's _manyrow_getter (including C extension on Python 3.13+)
        can access it without raising AttributeError.

        Regression test for: AdaptedResult object has no attribute '_yield_per'
        """
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"YieldPer Author {i}", field="Physics") for i in range(9)
            ]
            session.add_all(authors)
            await session.flush()

            stmt = select(Author).where(Author["name"].startswith("YieldPer Author"))
            # Explicitly pass yield_per via execution_options, mirroring how
            # AsyncSession.partitions() calls stream() internally.
            result = await session.stream(stmt, execution_options={"yield_per": 3})

            all_results = []
            partition_count = 0
            async for partition in result.scalars().partitions(3):
                assert len(partition) <= 3
                all_results.extend(partition)
                partition_count += 1

            assert partition_count == 3
            assert len(all_results) == 9

    @pytest.mark.asyncio
    async def test_async_stream_unique(self, async_engine: AsyncEngine):
        """Test async streaming with unique() to deduplicate joined results."""
        async with AsyncSession(async_engine) as session:
            # Create author and publisher with books
            author = Author(name="Unique Test", field="Chemistry")
            publisher = Publisher(name="Test Publisher", country="USA")
            book1 = Book(title="Book 1", year=2023)
            book2 = Book(title="Book 2", year=2024)
            book1.author.value = author
            book2.author.value = author
            book1.publisher.value = publisher
            book2.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            await session.flush()

            # Join query - without unique() would return author twice
            stmt = (
                select(Author)
                .join(Book)
                .where(Author["name"] == "Unique Test")
                .options(selectinload(Author["books"]))
            )

            result = await session.stream(stmt)
            authors = []
            async for author in result.scalars().unique():
                authors.append(author)

            # Should get only one author despite two books
            assert len(authors) == 1
            assert isinstance(authors[0], Author)
            assert len(authors[0].books) == 2


class TestAsyncRelationships:
    """Test async relationship loading."""

    @pytest.mark.asyncio
    async def test_async_eager_loading_selectinload(self, async_engine: AsyncEngine):
        """Test async eager loading with selectinload."""
        async with AsyncSession(async_engine) as session:
            # Create author and publisher with books
            author = Author(name="Eager Author", field="Literature")
            publisher = Publisher(name="Eager Publisher", country="USA")
            books = [Book(title=f"Eager Book {i}", year=2020 + i) for i in range(3)]
            for book in books:
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            await session.flush()

            author.revalidate()

            session.expunge_all()

            stmt = (
                select(Author)
                .where(Author["id"] == author.id)
                .options(selectinload(Author["books"]))
            )
            result = await session.execute(stmt)
            fetched = result.scalars().one()

            # Books should be loaded without additional query

            # Verify no additional SQL is issued when accessing books
            with patch.object(
                session.sync_session, "execute", wraps=session.sync_session.execute
            ) as mock_execute:
                # Access books - should not trigger additional SQL
                assert len(fetched.books) == 3
                # No execute calls should have been made
                assert mock_execute.call_count == 0

    @pytest.mark.asyncio
    async def test_async_many_to_many_relationship(self, async_engine: AsyncEngine):
        """Test async many-to-many relationship access."""
        from tests.transmuters import Category

        async with AsyncSession(async_engine) as session:
            # Create book with categories
            author = Author(name="M2M Author", field="Physics")
            publisher = Publisher(name="M2M Publisher", country="UK")
            book = Book(title="M2M Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="Async Cat 1")
            cat2 = Category(name="Async Cat 2")
            book.categories.extend([cat1, cat2])

            session.add(book)
            await session.flush()

            book.revalidate()
            session.expunge_all()

            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(selectinload(Book["categories"]))
            )
            result = await session.execute(stmt)
            fetched = result.scalars().one()

            # Categories should be loaded
            assert len(fetched.categories) == 2
            cat_names = {cat.name for cat in fetched.categories}
            assert cat_names == {"Async Cat 1", "Async Cat 2"}

            # Verify no additional SQL is issued when accessing categories
            with patch.object(
                session.sync_session, "execute", wraps=session.sync_session.execute
            ) as mock_execute:
                # Access categories - should not trigger additional SQL
                _ = [cat.name for cat in fetched.categories]
                # No execute calls should have been made
                assert mock_execute.call_count == 0


class TestAsyncComplexQueries:
    """Test async complex query patterns."""

    @pytest.mark.asyncio
    async def test_async_join_with_filter(self, async_engine: AsyncEngine):
        """Test async join with filtering."""
        async with AsyncSession(async_engine) as session:
            # Create test data
            author1 = Author(name="Join Author 1", field="Physics")
            author2 = Author(name="Join Author 2", field="Biology")
            publisher = Publisher(name="Join Publisher", country="USA")

            book1 = Book(title="Join Book 1", year=2020)
            book2 = Book(title="Join Book 2", year=2023)
            book1.author.value = author1
            book2.author.value = author2
            book1.publisher.value = publisher
            book2.publisher.value = publisher

            session.add_all([book1, book2])
            await session.flush()

            # Join query with filter
            stmt = select(Book).join(Author).where(Author["field"] == "Physics")
            result = await session.execute(stmt)
            books = result.scalars().all()

            assert len(books) == 1
            assert books[0].title == "Join Book 1"

    @pytest.mark.asyncio
    async def test_async_aggregate_query(self, async_engine: AsyncEngine):
        """Test async aggregate query."""
        from sqlalchemy import func

        async with AsyncSession(async_engine) as session:
            # Create test data
            author = Author(name="Agg Author", field="History")
            publisher = Publisher(name="Agg Publisher", country="UK")
            books = [Book(title=f"Agg Book {i}", year=2020 + i) for i in range(5)]
            for book in books:
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            await session.flush()

            # Aggregate query
            author.revalidate()
            stmt = (
                select(Author, func.count(Book["id"]))
                .join(Book)
                .where(Author["id"] == author.id)
                .group_by(Author["id"])
            )
            result = await session.execute(stmt)
            row = result.one()

            assert row[1] == 5  # Book count

    @pytest.mark.asyncio
    async def test_async_subquery(self, async_engine: AsyncEngine):
        """Test async query with subquery."""
        from sqlalchemy import func

        async with AsyncSession(async_engine) as session:
            # Create test data
            publisher = Publisher(name="Subquery Pub", country="USA")
            books = [Book(title=f"Subquery Book {i}", year=2020 + i) for i in range(3)]
            author = Author(name="Subquery Author", field="Literature")
            for book in books:
                book.publisher.value = publisher
                book.author.value = author

            session.add(publisher)
            await session.flush()

            # Subquery to get publishers with more than 2 books
            subq = (
                select(Publisher["id"])
                .join(Book)
                .group_by(Publisher["id"])
                .having(func.count(Book["id"]) > 2)
                .scalar_subquery()
            )
            stmt = select(Publisher).where(Publisher["id"].in_(subq))
            result = await session.execute(stmt)
            publishers = result.scalars().all()

            publisher.revalidate()
            assert len(publishers) == 1
            assert publishers[0].id == publisher.id


class TestAsyncSessionHelpers:
    """Test AsyncSession helper methods: one, one_or_none, first, bulk, count, list, partitions."""

    @pytest.mark.asyncio
    async def test_async_one_success(self, async_engine: AsyncEngine):
        """Test one returns single matching entity."""
        async with AsyncSession(async_engine) as session:
            author1 = Author(name="Async One Test 1", field="Physics")
            author2 = Author(name="Async One Test 2", field="Biology")
            session.add_all([author1, author2])
            await session.flush()
            author1.revalidate()

            result = await session.one(Author, name="Async One Test 1")
            assert result.id == author1.id
            assert result.name == "Async One Test 1"

    @pytest.mark.asyncio
    async def test_async_one_or_none_success(self, async_engine: AsyncEngine):
        """Test one_or_none returns entity when found."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Async One Or None", field="Chemistry")
            session.add(author)
            await session.flush()
            author.revalidate()

            result = await session.one_or_none(Author, name="Async One Or None")
            assert result is not None
            assert result.id == author.id

    @pytest.mark.asyncio
    async def test_async_one_or_none_returns_none(self, async_engine: AsyncEngine):
        """Test one_or_none returns None when not found."""
        async with AsyncSession(async_engine) as session:
            result = await session.one_or_none(Author, name="Nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_async_first_with_ordering(self, async_engine: AsyncEngine):
        """Test first respects order_by."""
        async with AsyncSession(async_engine) as session:
            author1 = Author(name="Z Async Author", field="Physics")
            author2 = Author(name="A Async Author", field="Physics")
            session.add_all([author1, author2])
            await session.flush()
            author1.revalidate()
            author2.revalidate()

            result = await session.first(
                Author, order_bys=[Author["name"]], field="Physics"
            )
            assert result is not None
            assert result.name == "A Async Author"

    @pytest.mark.asyncio
    async def test_async_first_returns_none_when_no_match(
        self, async_engine: AsyncEngine
    ):
        """Test first returns None when no results."""
        async with AsyncSession(async_engine) as session:
            result = await session.first(Author, name="Nonexistent Async")
            assert result is None

    @pytest.mark.asyncio
    async def test_async_bulk_single_pk(self, async_engine: AsyncEngine):
        """Test bulk retrieval with single primary key."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Bulk Test {i}", field="Physics") for i in range(5)
            ]
            session.add_all(authors)
            await session.flush()
            for a in authors:
                a.revalidate()

            ids = [a.id for a in authors]
            results = await session.bulk(Author, ids)

            assert len(results) == 5
            assert all(r is not None for r in results)
            assert {r.id for r in results if r} == set(ids)

    @pytest.mark.asyncio
    async def test_async_bulk_preserves_order(self, async_engine: AsyncEngine):
        """Test bulk returns results in same order as idents."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Order Test {i}", field="Physics") for i in range(3)
            ]
            session.add_all(authors)
            await session.flush()
            for a in authors:
                a.revalidate()

            ids = [a.id for a in authors]
            reversed_ids = list(reversed(ids))
            results = await session.bulk(Author, reversed_ids)

            assert [r.id for r in results if r] == reversed_ids

    @pytest.mark.asyncio
    async def test_async_bulk_with_missing_ids(self, async_engine: AsyncEngine):
        """Test bulk handles missing IDs with None."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Async Bulk Missing", field="Biology")
            session.add(author)
            await session.flush()
            author.revalidate()

            ids = [author.id, 999999, 888888]
            results = await session.bulk(Author, ids)

            assert len(results) == 3
            assert results[0] is not None
            assert results[0].id == author.id
            assert results[1] is None
            assert results[2] is None

    @pytest.mark.asyncio
    async def test_async_bulk_empty_list(self, async_engine: AsyncEngine):
        """Test bulk with empty list returns empty list."""
        async with AsyncSession(async_engine) as session:
            results = await session.bulk(Author, [])
            assert results == []

    @pytest.mark.asyncio
    async def test_async_bulk_composite_pk(self, async_engine: AsyncEngine):
        """Test bulk retrieval with composite primary key."""
        async with AsyncSession(async_engine) as session:
            # Create authors and publishers first
            author = Author(name="Async Bulk Comp Author", field="Physics")
            publisher = Publisher(name="Async Bulk Comp Pub", country="USA")
            session.add_all([author, publisher])
            await session.flush()
            author.revalidate()
            publisher.revalidate()

            # Create books and categories
            book1 = Book(title="Async Book 1", year=2020)
            book1.author.value = author
            book1.publisher.value = publisher
            book2 = Book(title="Async Book 2", year=2021)
            book2.author.value = author
            book2.publisher.value = publisher
            cat1 = Category(name="Async Category 1", description="Desc 1")
            cat2 = Category(name="Async Category 2", description="Desc 2")
            session.add_all([book1, book2, cat1, cat2])
            await session.flush()
            book1.revalidate()
            book2.revalidate()
            cat1.revalidate()
            cat2.revalidate()

            # Create associations via relationships
            # Need to await to load the collection in async context
            await book1.categories
            await book2.categories
            book1.categories.append(cat1)
            book2.categories.append(cat1)
            book2.categories.append(cat2)
            await session.flush()

            # Bulk retrieve with composite PK tuples
            idents = [
                (book1.id, cat1.id),
                (book2.id, cat1.id),
                (book2.id, cat2.id),
            ]
            results = await session.bulk(BookCategory, idents)

            assert len(results) == 3
            assert all(r is not None for r in results)
            assert results[0]
            assert results[0].book_id == book1.id
            assert results[0].category_id == cat1.id
            assert results[1]
            assert results[1].book_id == book2.id
            assert results[1].category_id == cat1.id
            assert results[2]
            assert results[2].book_id == book2.id
            assert results[2].category_id == cat2.id

    @pytest.mark.asyncio
    async def test_async_bulk_composite_pk_with_missing(
        self, async_engine: AsyncEngine
    ):
        """Test bulk with composite PK handles missing entries."""
        async with AsyncSession(async_engine) as session:
            # Create author and publisher first
            author = Author(name="Async Bulk Missing Author", field="Biology")
            publisher = Publisher(name="Async Bulk Missing Pub", country="UK")
            session.add_all([author, publisher])
            await session.flush()
            author.revalidate()
            publisher.revalidate()

            # Create one book and category
            book = Book(title="Async Bulk Comp Missing", year=2023)
            book.author.value = author
            book.publisher.value = publisher
            cat = Category(name="Async Bulk Comp Cat", description="Desc")
            session.add_all([book, cat])
            await session.flush()
            book.revalidate()
            cat.revalidate()

            # Create association via relationship
            await book.categories  # Load collection first
            book.categories.append(cat)
            await session.flush()

            # Request existing and non-existing composite PKs
            idents = [
                (book.id, cat.id),  # exists
                (999999, 888888),  # doesn't exist
                (777777, 666666),  # doesn't exist
            ]
            results = await session.bulk(BookCategory, idents)

            assert len(results) == 3
            assert results[0] is not None
            assert results[0].book_id == book.id
            assert results[0].category_id == cat.id
            assert results[1] is None
            assert results[2] is None

    @pytest.mark.asyncio
    async def test_async_count_with_filters(self, async_engine: AsyncEngine):
        """Test count with filter_by."""
        async with AsyncSession(async_engine) as session:
            author1 = Author(name="Async Count Filter 1", field="Physics")
            author2 = Author(name="Async Count Filter 2", field="Biology")
            author3 = Author(name="Async Count Filter 3", field="Physics")
            session.add_all([author1, author2, author3])
            await session.flush()

            count_physics = await session.count(Author, field="Physics")
            count_biology = await session.count(Author, field="Biology")

            assert count_physics >= 2
            assert count_biology >= 1

    @pytest.mark.asyncio
    async def test_async_sqlalchemy_expression_compiler_translates_operator_tree(
        self, async_engine: AsyncEngine
    ):
        """Test the material compiler translates arcanus expression trees."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Compiler Tree A", field="Physics"),
                    Author(name="Async Compiler Tree B", field="Chemistry"),
                    Author(name="Async Compiler Tree Outside", field="Physics"),
                    Author(name="Async Compiler Tree Biology", field="Biology"),
                ]
            )
            await session.flush()

            expression = (
                Author["name"].contains("Async Compiler Tree")
                & Author["field"].in_(("Physics", "Chemistry"))
                & Author["field"].not_in(("Biology",))
                & ~Author["name"].ends_with("Outside")
            )
            compiled_expression = expression(sqlalchemy_materia.expression_compiler)
            compiled_order = Author["name"].asc()(
                sqlalchemy_materia.expression_compiler
            )

            result = await session.execute(
                select(Author).where(compiled_expression).order_by(compiled_order)
            )

            assert [author.name for author in result.scalars().all()] == [
                "Async Compiler Tree A",
                "Async Compiler Tree B",
            ]

    @pytest.mark.asyncio
    async def test_async_column_expression_and_order_interop_with_native_sqlalchemy(
        self, async_engine: AsyncEngine
    ):
        """Test arcanus columns and expressions work in raw SQLAlchemy statements."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Native Interop B", field="Robotics"),
                    Author(name="Async Native Interop A", field="Robotics"),
                    Author(name="Async Native Interop Outside", field="Physics"),
                ]
            )
            await session.flush()

            result = await session.execute(
                select(Author["name"])
                .where(Author["name"].starts_with("Async Native Interop"))
                .where(Author["field"] == "Robotics")
                .order_by(Author["name"].asc())
            )

            assert result.scalars().all() == [
                "Async Native Interop A",
                "Async Native Interop B",
            ]

    @pytest.mark.asyncio
    async def test_async_mixed_native_and_arcanus_expressions_are_accepted(
        self, async_engine: AsyncEngine
    ):
        """Test native SQLAlchemy expressions can be mixed with arcanus expressions."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Mixed Expression A", field="Physics"),
                    Author(name="Async Mixed Expression B", field="Biology"),
                    Author(name="Async Mixed Expression Outside", field="Physics"),
                ]
            )
            await session.flush()

            results = await session.list(
                Author,
                order_bys=[Author["name"].desc()],
                expressions=[
                    Author["name"].native.like("Async Mixed Expression%"),
                    Author["name"].native != "Async Mixed Expression Outside",
                    Author["field"] != "Biology",
                ],
            )

            assert [author.name for author in results] == ["Async Mixed Expression A"]

    @pytest.mark.asyncio
    async def test_async_count_accepts_arcanus_boolean_logic_expressions(
        self, async_engine: AsyncEngine
    ):
        """Test count accepts arcanus expressions with boolean composition."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Count Logic A", field="Physics"),
                    Author(name="Async Count Logic B", field="Biology"),
                    Author(name="Async Count Logic C", field="Chemistry"),
                    Author(name="Async Count Logic Outside", field="History"),
                ]
            )
            await session.flush()

            expression = Author["name"].starts_with("Async Count Logic") & (
                (Author["field"] == "Physics")
                | (Author["field"] == "Biology")
                | (Author["field"] == "Chemistry")
            )
            count = await session.count(Author, expressions=[expression])

            assert count == 3

    @pytest.mark.asyncio
    async def test_async_list_basic(self, async_engine: AsyncEngine):
        """Test list returns multiple entities."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async List Test {i}", field="Chemistry") for i in range(5)
            ]
            session.add_all(authors)
            await session.flush()
            for a in authors:
                a.revalidate()

            results = await session.list(Author, field="Chemistry")
            assert len(results) >= 5

    @pytest.mark.asyncio
    async def test_async_list_with_limit(self, async_engine: AsyncEngine):
        """Test list respects limit."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Limit Test {i}", field="History") for i in range(10)
            ]
            session.add_all(authors)
            await session.flush()

            results = await session.list(Author, limit=3, field="History")
            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_async_list_with_ordering(self, async_engine: AsyncEngine):
        """Test list respects order_by."""
        async with AsyncSession(async_engine) as session:
            author1 = Author(name="Z Async List", field="Literature")
            author2 = Author(name="A Async List", field="Literature")
            author3 = Author(name="M Async List", field="Literature")
            session.add_all([author1, author2, author3])
            await session.flush()

            results = await session.list(
                Author, order_bys=[Author["name"]], field="Literature"
            )
            names = [r.name for r in results]
            assert (
                names.index("A Async List")
                < names.index("M Async List")
                < names.index("Z Async List")
            )

    @pytest.mark.asyncio
    async def test_async_list_compiles_arcanus_expressions_and_orders(
        self, async_engine: AsyncEngine
    ):
        """Test list accepts arcanus expression inputs."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Expression Order C", field="Robotics"),
                    Author(name="Async Expression Order A", field="Robotics"),
                    Author(name="Async Expression Order B", field="Robotics"),
                ]
            )
            await session.flush()

            results = await session.list(
                Author,
                order_bys=[Author["name"].desc()],
                expressions=[Author["name"].like("Async Expression Order%")],
                field="Robotics",
            )

            assert [author.name for author in results] == [
                "Async Expression Order C",
                "Async Expression Order B",
                "Async Expression Order A",
            ]

    @pytest.mark.asyncio
    async def test_async_list_count_and_partitions_with_relationship_expressions(
        self, async_engine: AsyncEngine
    ):
        """Test relationship columns can filter through native SQLAlchemy helpers."""
        async with AsyncSession(async_engine) as session:
            publisher = Publisher(name="Async Relationship Filter Pub", country="USA")
            matching_author = Author(
                name="Async Relationship Filter Author", field="Astrophysics"
            )
            other_author = Author(
                name="Async Relationship Filter Other", field="History"
            )
            category = Category(
                name="Async Relationship Filter Category", description="Deep space"
            )
            other_category = Category(
                name="Async Relationship Filter Other Category",
                description="Near ground",
            )
            matching_book = Book(title="Async Relationship Filter Match", year=2024)
            matching_book.author.value = matching_author
            matching_book.publisher.value = publisher
            matching_book.detail.value = BookDetail(
                isbn="978-8888810001",
                pages=420,
                abstract="Relationship expression match",
            )
            matching_book.categories.append(category)

            wrong_author_book = Book(
                title="Async Relationship Filter Wrong Author", year=2024
            )
            wrong_author_book.author.value = other_author
            wrong_author_book.publisher.value = publisher
            wrong_author_book.detail.value = BookDetail(
                isbn="978-8888810002",
                pages=520,
                abstract="Wrong author",
            )
            wrong_author_book.categories.append(category)

            wrong_category_book = Book(
                title="Async Relationship Filter Wrong Category", year=2024
            )
            wrong_category_book.author.value = matching_author
            wrong_category_book.publisher.value = publisher
            wrong_category_book.detail.value = BookDetail(
                isbn="978-8888810003",
                pages=620,
                abstract="Wrong category",
            )
            wrong_category_book.categories.append(other_category)

            short_book = Book(title="Async Relationship Filter Short", year=2024)
            short_book.author.value = matching_author
            short_book.publisher.value = publisher
            short_book.detail.value = BookDetail(
                isbn="978-8888810004",
                pages=120,
                abstract="Too short",
            )
            short_book.categories.append(category)

            session.add_all(
                [matching_book, wrong_author_book, wrong_category_book, short_book]
            )
            await session.flush()

            expression = (
                Book["author"].has(Author["field"] == "Astrophysics")
                & Book["categories"].any(
                    Category["name"] == "Async Relationship Filter Category"
                )
                & Book["detail"].has(BookDetail["pages"] >= 300)
            )
            results = await session.list(
                Book,
                expressions=[expression],
                order_bys=[Book["title"]],
            )
            count = await session.count(Book, expressions=[expression])
            partitions = [
                partition
                async for partition in session.partitions(
                    Book,
                    size=1,
                    expressions=[expression],
                    order_bys=[Book["title"]],
                )
            ]

            assert [book.title for book in results] == [
                "Async Relationship Filter Match"
            ]
            assert count == 1
            assert [[book.title for book in partition] for partition in partitions] == [
                ["Async Relationship Filter Match"]
            ]

    @pytest.mark.asyncio
    async def test_async_list_with_json_criteria_expression(
        self, async_engine: AsyncEngine
    ):
        """Test JSON criteria values can drive AsyncSession list expressions."""
        criteria_model = Criteria[Author]
        payload = {
            "name": {"starts_with": "Async Criteria Chain"},
            "field": {"eq": "Xenobiology"},
        }
        limit = 2
        orders = (Author["name"].desc(),)

        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Criteria Chain C", field="Xenobiology"),
                    Author(name="Async Criteria Chain A", field="Xenobiology"),
                    Author(name="Async Criteria Chain B", field="Xenobiology"),
                    Author(name="Async Criteria Chain Outside", field="Robotics"),
                ]
            )
            await session.flush()

            criteria = criteria_model.model_validate_json(json.dumps(payload))
            restored = criteria_model.model_validate_json(
                criteria.model_dump_json(by_alias=True, exclude_none=True)
            )
            assert restored.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == criteria.model_dump(mode="json", by_alias=True, exclude_none=True)

            list_results = await session.list(
                Author,
                expressions=criteria.expressions,
                order_bys=orders,
                limit=limit,
            )

            assert [author.name for author in list_results] == [
                "Async Criteria Chain C",
                "Async Criteria Chain B",
            ]

    @pytest.mark.asyncio
    async def test_async_partitions_basic(self, async_engine: AsyncEngine):
        """Test partitions returns entities in batches."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Partition Test {i}", field="Physics")
                for i in range(25)
            ]
            session.add_all(authors)
            await session.flush()
            for a in authors:
                a.revalidate()

            all_results = []
            partition_count = 0
            async for partition in session.partitions(
                Author,
                limit=25,
                size=10,
                expressions=[Author["name"].startswith("Async Partition Test")],
            ):
                assert len(partition) <= 10
                all_results.extend(partition)
                partition_count += 1

            # Should have 3 partitions (10 + 10 + 5)
            assert partition_count == 3
            assert len(all_results) == 25

    @pytest.mark.asyncio
    async def test_async_partitions_with_ordering(self, async_engine: AsyncEngine):
        """Test partitions respects order_by."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Partition Order {i:02d}", field="Biology")
                for i in range(15)
            ]
            session.add_all(authors)
            await session.flush()

            all_names = []
            async for partition in session.partitions(
                Author,
                limit=15,
                size=5,
                order_bys=[Author["name"]],
                expressions=[Author["name"].startswith("Async Partition Order")],
            ):
                for author in partition:
                    all_names.append(author.name)

            # Verify ordering is maintained across partitions
            assert all_names == sorted(all_names)

    @pytest.mark.asyncio
    async def test_async_partitions_with_limit(self, async_engine: AsyncEngine):
        """Test partitions respects limit."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Partition Limit {i}", field="Chemistry")
                for i in range(20)
            ]
            session.add_all(authors)
            await session.flush()

            all_results = []
            async for partition in session.partitions(
                Author,
                limit=12,
                size=5,
                expressions=[Author["name"].startswith("Async Partition Limit")],
            ):
                all_results.extend(partition)

            # Should only get 12 results due to limit
            assert len(all_results) == 12

    @pytest.mark.asyncio
    async def test_async_partitions_with_offset(self, async_engine: AsyncEngine):
        """Test partitions respects offset."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Partition Offset {i:02d}", field="Literature")
                for i in range(10)
            ]
            session.add_all(authors)
            await session.flush()

            all_results = []
            async for partition in session.partitions(
                Author,
                limit=10,
                offset=5,
                size=3,
                order_bys=[Author["name"]],
                expressions=[Author["name"].startswith("Async Partition Offset")],
            ):
                all_results.extend(partition)

            # Should skip first 5, get remaining 5
            assert len(all_results) == 5

    @pytest.mark.asyncio
    async def test_async_partitions_with_options(self, async_engine: AsyncEngine):
        """Test partitions respects options like selectinload."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Async Partition Options Author", field="History")
            publisher = Publisher(name="Async Partition Options Pub", country="USA")

            books = []
            for i in range(6):
                book = Book(title=f"Async Partition Opt Book {i}", year=2020 + i)
                book.author.value = author
                book.publisher.value = publisher
                books.append(book)

            session.add(author)
            session.add(publisher)
            await session.flush()
            author.revalidate()
            for b in books:
                b.revalidate()

            session.expunge_all()

            all_results = []
            async for partition in session.partitions(
                Book,
                limit=6,
                size=2,
                options=[selectinload(Book["author"])],
                expressions=[Book["title"].startswith("Async Partition Opt Book")],
            ):
                for book in partition:
                    # Author should be loaded without additional query
                    assert book.author.value.name == "Async Partition Options Author"
                all_results.extend(partition)

            assert len(all_results) == 6

    @pytest.mark.asyncio
    async def test_async_partitions_with_expressions(self, async_engine: AsyncEngine):
        """Test partitions respects filter expressions."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Partition Expr {i}", field="Astronomy")
                for i in range(10)
            ]
            # Add some authors with different field
            other_authors = [
                Author(name=f"Async Partition Other {i}", field="Robotics")
                for i in range(5)
            ]
            session.add_all(authors + other_authors)
            await session.flush()

            all_results = []
            async for partition in session.partitions(
                Author,
                limit=15,
                size=4,
                expressions=[Author["field"] == "Astronomy"],
            ):
                for author in partition:
                    assert author.field == "Astronomy"
                all_results.extend(partition)

            assert len(all_results) == 10

    @pytest.mark.asyncio
    async def test_async_partitions_compile_arcanus_expressions_and_orders(
        self, async_engine: AsyncEngine
    ):
        """Test partitions accepts arcanus expression and order inputs."""
        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Part Expression C", field="Cybernetics"),
                    Author(name="Async Part Expression A", field="Cybernetics"),
                    Author(name="Async Part Expression B", field="Cybernetics"),
                ]
            )
            await session.flush()

            all_results = []
            async for partition in session.partitions(
                Author,
                size=2,
                order_bys=[Author["name"].asc()],
                expressions=[Author["name"].like("Async Part Expression%")],
                field="Cybernetics",
            ):
                all_results.extend(partition)

            assert [author.name for author in all_results] == [
                "Async Part Expression A",
                "Async Part Expression B",
                "Async Part Expression C",
            ]

    @pytest.mark.asyncio
    async def test_async_partitions_with_json_criteria_expression_and_orders(
        self, async_engine: AsyncEngine
    ):
        """Test partitions accepts criteria-derived arcanus expressions and orders."""
        criteria_model = Criteria[Author]
        payload = {
            "name": {"starts_with": "Async Criteria Partition"},
            "field": {"eq": "Astrophysics"},
        }
        limit = 3
        orders = (Author["name"].asc(),)

        async with AsyncSession(async_engine) as session:
            session.add_all(
                [
                    Author(name="Async Criteria Partition C", field="Astrophysics"),
                    Author(name="Async Criteria Partition A", field="Astrophysics"),
                    Author(name="Async Criteria Partition D", field="Astrophysics"),
                    Author(name="Async Criteria Partition B", field="Astrophysics"),
                    Author(name="Async Criteria Partition Outside", field="Astronomy"),
                ]
            )
            await session.flush()

            criteria = criteria_model.model_validate_json(json.dumps(payload))
            assert criteria.expressions

            all_results = []
            async for partition in session.partitions(
                Author,
                size=2,
                limit=limit,
                order_bys=orders,
                expressions=criteria.expressions,
            ):
                all_results.extend(partition)

            assert [author.name for author in all_results] == [
                "Async Criteria Partition A",
                "Async Criteria Partition B",
                "Async Criteria Partition C",
            ]

    @pytest.mark.asyncio
    async def test_async_partitions_empty_result(self, async_engine: AsyncEngine):
        """Test partitions with no matching results."""
        async with AsyncSession(async_engine) as session:
            partition_count = 0
            async for partition in session.partitions(
                Author,
                limit=10,
                size=5,
                expressions=[Author["name"] == "NonexistentAuthorName12345"],
            ):
                partition_count += 1

            assert partition_count == 0

    @pytest.mark.asyncio
    async def test_async_partitions_single_partition(self, async_engine: AsyncEngine):
        """Test partitions when results fit in single partition."""
        async with AsyncSession(async_engine) as session:
            authors = [
                Author(name=f"Async Single Partition {i}", field="Cybernetics")
                for i in range(3)
            ]
            session.add_all(authors)
            await session.flush()

            all_results = []
            partition_count = 0
            async for partition in session.partitions(
                Author,
                limit=10,
                size=10,
                expressions=[Author["name"].startswith("Async Single Partition")],
            ):
                all_results.extend(partition)
                partition_count += 1

            assert partition_count == 1
            assert len(all_results) == 3


class TestAsyncLazyLoadingErrors:
    """Test proper error handling for lazy loading in async context."""

    @pytest.mark.asyncio
    async def test_lazy_select_relationship_raises_missing_greenlet_error(
        self, async_engine: AsyncEngine, test_id: UUID
    ):
        """Test that accessing lazy='select' relationship in async raises MissingGreenlet.

        SQLAlchemy's default lazy loading uses synchronous IO which is not allowed
        in async contexts. Attempting to access such a relationship should raise
        MissingGreenlet error with a helpful message.
        """
        from sqlalchemy.exc import MissingGreenlet

        async with AsyncSession(async_engine) as session:
            # Create author with a book
            author = Author(name="Lazy Test Author", field="Physics", test_id=test_id)
            publisher = Publisher(
                name="Lazy Test Publisher", country="USA", test_id=test_id
            )
            book = Book(title="Lazy Test Book", year=2023, test_id=test_id)
            book.author.value = author
            book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            await session.flush()
            author.revalidate()
            await session.commit()
            author_id = author.id

        # Start new session and load author without eagerly loading relationships
        async with AsyncSession(async_engine) as session:
            # Get author but don't load relationships
            author = await session.get_one(Author, author_id)

            # Accessing the lazy-loaded relationship without await should raise
            with pytest.raises(MissingGreenlet) as exc_info:
                # This will attempt synchronous IO in async context
                _ = len(author.books)

            # Verify the error message mentions the issue
            error_msg = str(exc_info.value)
            assert "greenlet" in error_msg.lower() or "async" in error_msg.lower()


class TestAsyncRaiseOnSQLBehavior:
    """Test lazy='raise' and raiseload() preventing implicit SQL in async."""

    @pytest.mark.asyncio
    async def test_raiseload_prevents_lazy_loading(
        self, async_engine: AsyncEngine, test_id: UUID
    ):
        """Test that raiseload() prevents lazy loading in async context."""
        async with AsyncSession(async_engine) as session:
            author = Author(name="Raise Author", field="Chemistry", test_id=test_id)
            publisher = Publisher(name="Raise Pub", country="USA", test_id=test_id)
            book = Book(title="Raise Book", year=2024, test_id=test_id)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            await session.flush()
            book.revalidate()
            book_id = book.id

            # Clear session
            session.expunge_all()

            # Load book with raiseload on author
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(raiseload(Book["author"]))
            )
            result = await session.execute(stmt)
            loaded_book = result.scalars().one()

            # Accessing author should raise InvalidRequestError
            with pytest.raises(
                InvalidRequestError, match="loading strategy is set to 'raise'"
            ):
                _ = loaded_book.author.value

    @pytest.mark.asyncio
    async def test_raiseload_collection(self, async_engine: AsyncEngine, test_id: UUID):
        """Test raiseload on collection relationships in async context."""
        async with AsyncSession(async_engine) as session:
            author = Author(
                name="Raise Collection Author", field="Physics", test_id=test_id
            )
            publisher = Publisher(
                name="Raise Collection Pub", country="USA", test_id=test_id
            )

            for i in range(2):
                book = Book(
                    title=f"Raise Collection Book {i}", year=2024, test_id=test_id
                )
                book.author.value = author
                book.publisher.value = publisher
                author.books.append(book)

            session.add(author)
            await session.flush()
            author.revalidate()
            author_id = author.id

            # Clear session
            session.expunge_all()

            # Load author with raiseload on books
            stmt = (
                select(Author)
                .where(Author["id"] == author_id)
                .options(raiseload(Author["books"]))
            )
            result = await session.execute(stmt)
            loaded_author = result.scalars().one()

            # Accessing books collection should raise InvalidRequestError
            # We need to iterate or access elements to trigger the lazy load
            with pytest.raises(
                InvalidRequestError, match="loading strategy is set to 'raise'"
            ):
                _ = len(loaded_author.books)

    @pytest.mark.asyncio
    async def test_raiseload_with_explicit_load(
        self, async_engine: AsyncEngine, test_id: UUID
    ):
        """Test that raiseload doesn't prevent explicitly loaded relationships."""
        async with AsyncSession(async_engine) as session:
            author = Author(
                name="Explicit Load Author", field="Biology", test_id=test_id
            )
            publisher = Publisher(
                name="Explicit Load Pub", country="USA", test_id=test_id
            )
            book = Book(title="Explicit Load Book", year=2024, test_id=test_id)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            await session.flush()
            book.revalidate()
            book_id = book.id

            # Clear session
            session.expunge_all()

            # Load book with raiseload on author BUT also selectinload on publisher
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    raiseload(Book["author"]),
                    selectinload(Book["publisher"]),
                )
            )
            result = await session.execute(stmt)
            loaded_book = result.scalars().one()

            # Accessing publisher should work (was explicitly loaded)
            assert loaded_book.publisher.value.name == "Explicit Load Pub"

            # But accessing author should still raise
            with pytest.raises(
                InvalidRequestError, match="loading strategy is set to 'raise'"
            ):
                _ = loaded_book.author.value
