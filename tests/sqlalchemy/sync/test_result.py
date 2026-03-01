"""Test Result adaptation and iteration.

Tests:
- Result.scalars() - get scalar values
- Result.unique() - deduplicate results
- Result.partitions() - iterate in chunks
- Result.mappings() - get dict-like rows
- Result.all(), one(), one_or_none(), first()
- Result iteration and consumption
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import selectinload

from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Author, Book, Category, Publisher


class TestResultScalars:
    """Test Result.scalars() method."""

    def test_scalars_returns_first_column(self, engine: Engine):
        """Test that scalars() returns values from first column."""
        with Session(engine) as session:
            # Add test data
            for i in range(3):
                session.add(Author(name=f"Scalar Test {i}", field="Physics"))
            session.flush()

            # Query
            stmt = select(Author).where(Author["name"].like("Scalar Test%"))
            result = session.execute(stmt)

            # Get scalars
            authors = result.scalars().all()

            assert len(authors) == 3
            assert all(isinstance(a, Author) for a in authors)

    def test_scalars_with_multiple_columns(self, engine: Engine):
        """Test scalars() with multi-column select."""
        with Session(engine) as session:
            session.add(Author(name="Multi Col Test", field="Biology"))
            session.flush()

            # Select multiple columns
            stmt = select(Author["id"], Author["name"]).where(
                Author["name"] == "Multi Col Test"
            )
            result = session.execute(stmt)

            # scalars() should return first column (id)
            ids = result.scalars().all()

            assert len(ids) == 1
            assert isinstance(ids[0], int)

    def test_scalars_one(self, engine: Engine):
        """Test scalars().one() returns exactly one result."""
        with Session(engine) as session:
            session.add(Author(name="Unique Scalar", field="Chemistry"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Unique Scalar")
            result = session.execute(stmt)

            author = result.scalars().one()
            assert author.name == "Unique Scalar"

    def test_scalars_one_raises_on_no_result(self, engine: Engine):
        """Test scalars().one() raises when no results."""
        with Session(engine) as session:
            stmt = select(Author).where(Author["name"] == "NonExistent")
            result = session.execute(stmt)

            with pytest.raises(NoResultFound):
                result.scalars().one()

    def test_scalars_one_raises_on_multiple(self, engine: Engine):
        """Test scalars().one() raises when multiple results."""
        with Session(engine) as session:
            session.add(Author(name="Duplicate", field="Physics"))
            session.add(Author(name="Duplicate", field="Biology"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Duplicate")
            result = session.execute(stmt)

            with pytest.raises(MultipleResultsFound):
                result.scalars().one()

    def test_scalars_one_or_none(self, engine: Engine):
        """Test scalars().one_or_none()."""
        with Session(engine) as session:
            session.add(Author(name="Maybe Exists", field="Literature"))
            session.flush()

            # Exists
            stmt = select(Author).where(Author["name"] == "Maybe Exists")
            result = session.execute(stmt)
            author = result.scalars().one_or_none()
            assert author is not None

            # Doesn't exist
            stmt = select(Author).where(Author["name"] == "Definitely Not")
            result = session.execute(stmt)
            author = result.scalars().one_or_none()
            assert author is None

    def test_scalars_first(self, engine: Engine):
        """Test scalars().first() returns first result."""
        with Session(engine) as session:
            session.add(Author(name="First A", field="Physics"))
            session.add(Author(name="First B", field="Biology"))
            session.flush()

            stmt = (
                select(Author)
                .where(Author["name"].like("First%"))
                .order_by(Author["name"])
            )
            result = session.execute(stmt)

            first = result.scalars().first()
            assert first is not None
            assert first.name == "First A"


class TestResultUnique:
    """Test Result.unique() for deduplication."""

    def test_unique_removes_duplicates(self, engine: Engine):
        """Test that unique() removes duplicate rows."""
        with Session(engine) as session:
            # Create book with multiple categories
            author = Author(name="Unique Test Author", field="Literature")
            publisher = Publisher(name="Unique Test Pub", country="USA")
            book = Book(title="Unique Test Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="Unique Cat 1", description="Category 1")
            cat2 = Category(name="Unique Cat 2", description="Category 2")
            book.categories.extend([cat1, cat2])

            session.add(book)
            session.flush()

            # Query with joined load creates duplicates
            stmt = (
                select(Book)
                .join(Book["categories"])
                .where(Book["title"] == "Unique Test Book")
            )
            result = session.execute(stmt)

            # Without unique()
            books_with_dups = result.scalars().all()
            # May have duplicates

            # With unique()
            result = session.execute(stmt)
            books_unique = result.unique().scalars().all()

            # unique() should remove duplicates
            assert len(books_unique) <= len(books_with_dups)

    def test_unique_with_selectinload(self, engine: Engine):
        """Test unique() with selectinload (already unique)."""
        with Session(engine) as session:
            author = Author(name="Selectin Unique", field="Physics")
            publisher = Publisher(name="Selectin Unique Pub", country="UK")
            book = Book(title="Selectin Unique Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()

            # Query with selectinload (no duplicates)
            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(selectinload(Book["categories"]))
            )
            result = session.execute(stmt)

            books = result.unique().scalars().all()
            assert len(books) == 1


class TestResultPartitions:
    """Test Result.partitions() for chunked iteration."""

    def test_partitions_returns_chunks(self, engine: Engine):
        """Test that partitions() returns results in chunks."""
        with Session(engine) as session:
            # Add 10 authors
            for i in range(10):
                session.add(Author(name=f"Partition {i:02d}", field="Physics"))
            session.flush()

            # Query
            stmt = (
                select(Author)
                .where(Author["name"].like("Partition%"))
                .order_by(Author["name"])
            )
            result = session.execute(stmt)

            # Get partitions of size 3
            chunks = list(result.scalars().partitions(3))

            # Should have 4 chunks: [3, 3, 3, 1]
            assert len(chunks) == 4
            assert len(chunks[0]) == 3
            assert len(chunks[1]) == 3
            assert len(chunks[2]) == 3
            assert len(chunks[3]) == 1

    def test_partitions_with_exact_division(self, engine: Engine):
        """Test partitions when count divides evenly."""
        with Session(engine) as session:
            # Add 9 authors (divisible by 3)
            for i in range(9):
                session.add(Author(name=f"Even Partition {i}", field="Biology"))
            session.flush()

            stmt = (
                select(Author)
                .where(Author["name"].like("Even Partition%"))
                .order_by(Author["name"])
            )
            result = session.execute(stmt)

            chunks = list(result.scalars().partitions(3))

            # Should have exactly 3 chunks of 3
            assert len(chunks) == 3
            assert all(len(chunk) == 3 for chunk in chunks)

    def test_partitions_iteration(self, engine: Engine):
        """Test iterating over partitions."""
        with Session(engine) as session:
            for i in range(5):
                session.add(Author(name=f"Iterate Partition {i}", field="Chemistry"))
            session.flush()

            stmt = (
                select(Author)
                .where(Author["name"].like("Iterate Partition%"))
                .order_by(Author["name"])
            )
            result = session.execute(stmt)

            count = 0
            for partition in result.scalars().partitions(2):
                count += len(partition)

            assert count == 5


class TestResultMappings:
    """Test Result.mappings() for dict-like access."""

    def test_mappings_returns_dict_like(self, engine: Engine):
        """Test that mappings() returns dict-like rows."""
        with Session(engine) as session:
            session.add(Author(name="Mapping Test", field="Literature"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Mapping Test")
            result = session.execute(stmt)

            rows = result.mappings().all()

            assert len(rows) == 1
            row = rows[0]

            # Access by column name
            assert "Author" in row.keys()

    def test_mappings_with_specific_columns(self, engine: Engine):
        """Test mappings() with specific column selection."""
        with Session(engine) as session:
            session.add(Author(name="Column Mapping", field="History"))
            session.flush()

            stmt = select(
                Author["id"],
                Author["name"],
                Author["field"],
            ).where(Author["name"] == "Column Mapping")
            result = session.execute(stmt)

            rows = result.mappings().all()
            assert len(rows) == 1

            row = rows[0]
            # Should be able to access by column
            assert row[Author["name"]] == "Column Mapping"
            assert row[Author["field"]] == "History"

    def test_mappings_one(self, engine: Engine):
        """Test mappings().one()."""
        with Session(engine) as session:
            session.add(Author(name="One Mapping", field="Physics"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "One Mapping")
            result = session.execute(stmt)

            row = result.mappings().one()
            assert row is not None


class TestResultConsumption:
    """Test consuming results in different ways."""

    def test_result_all(self, engine: Engine):
        """Test Result.all() returns all rows."""
        with Session(engine) as session:
            for i in range(3):
                session.add(Author(name=f"All Test {i}", field="Physics"))
            session.flush()

            stmt = select(Author).where(Author["name"].like("All Test%"))
            result = session.execute(stmt)

            # all() returns list of Row objects
            rows = result.all()
            assert len(rows) == 3

    def test_result_iteration(self, engine: Engine):
        """Test iterating over Result."""
        with Session(engine) as session:
            for i in range(5):
                session.add(Author(name=f"Iter Test {i}", field="Biology"))
            session.flush()

            stmt = select(Author).where(Author["name"].like("Iter Test%"))
            result = session.execute(stmt)

            # Iterate directly
            count = 0
            for row in result:
                count += 1

            assert count == 5

    def test_result_consumed_once(self, engine: Engine):
        """Test that Result can only be consumed once."""
        with Session(engine) as session:
            session.add(Author(name="Consume Test", field="Chemistry"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Consume Test")
            result = session.execute(stmt)

            # Consume once
            authors1 = result.scalars().all()
            assert len(authors1) == 1

            # Try to consume again - should be empty
            authors2 = result.scalars().all()
            assert len(authors2) == 0

    def test_result_one_or_none_with_none(self, engine: Engine):
        """Test one_or_none returns None when no results."""
        with Session(engine) as session:
            stmt = select(Author).where(Author["name"] == "Does Not Exist")
            result = session.execute(stmt)

            author = result.scalars().one_or_none()
            assert author is None

    def test_result_first_with_no_results(self, engine: Engine):
        """Test first() returns None when no results."""
        with Session(engine) as session:
            stmt = select(Author).where(Author["name"] == "No Results")
            result = session.execute(stmt)

            author = result.scalars().first()
            assert author is None


class TestResultChaining:
    """Test chaining Result methods."""

    def test_unique_scalars_chain(self, engine: Engine):
        """Test chaining unique() and scalars()."""
        with Session(engine) as session:
            author = Author(name="Chain Test", field="Literature")
            publisher = Publisher(name="Chain Pub", country="USA")
            book = Book(title="Chain Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="Chain Cat 1", description="Cat 1")
            cat2 = Category(name="Chain Cat 2", description="Cat 2")
            book.categories.extend([cat1, cat2])

            session.add(book)
            session.flush()

            # Join creates duplicates
            stmt = (
                select(Book)
                .join(Book["categories"])
                .where(Book["title"] == "Chain Book")
            )
            result = session.execute(stmt)

            # Chain unique().scalars()
            books = result.unique().scalars().all()
            assert len(books) == 1

    def test_scalars_first_chain(self, engine: Engine):
        """Test chaining scalars().first()."""
        with Session(engine) as session:
            session.add(Author(name="Chain First", field="Physics"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Chain First")
            result = session.execute(stmt)

            author = result.scalars().first()
            assert author is not None
            assert author.name == "Chain First"

    def test_mappings_all_chain(self, engine: Engine):
        """Test chaining mappings().all()."""
        with Session(engine) as session:
            session.add(Author(name="Chain Mapping", field="Biology"))
            session.flush()

            stmt = select(Author).where(Author["name"] == "Chain Mapping")
            result = session.execute(stmt)

            rows = result.mappings().all()
            assert len(rows) == 1
