"""Test SQL operations with transmuters.

Tests:
- CRUD operations (Create, Read, Update, Delete)
- SELECT with various clauses (WHERE, ORDER BY, LIMIT, OFFSET)
- UPDATE and DELETE with RETURNING
- JOIN operations
- Loading strategies (selectinload, joinedload)
- Column expressions and filters
- Complex queries with multiple conditions
"""

from __future__ import annotations

from sqlalchemy import Engine, and_, delete, func, insert, or_, select, update

from arcanus.materia.sqlalchemy import Session, joinedload, selectinload
from tests.transmuters import Author, Book, BookDetail, Category, Publisher


class TestCRUDOperations:
    """Test basic CRUD operations."""

    def test_insert_single_record(self, engine: Engine):
        """Test inserting a single record."""
        with Session(engine) as session:
            author = Author(name="Frank Herbert", field="Literature")
            session.add(author)
            session.flush()
            author.revalidate()
            assert author.id is not None
            assert author.name == "Frank Herbert"

    def test_insert_multiple_records(self, engine: Engine):
        """Test inserting multiple records."""
        with Session(engine) as session:
            authors = [Author(name=f"Author {i}", field="Literature") for i in range(5)]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            # All should have IDs
            assert all(author.id is not None for author in authors)

    def test_select_by_primary_key(self, engine: Engine):
        """Test selecting a record by primary key."""
        with Session(engine) as session:
            # Create author
            author = Author(name="Test Select", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()

            # Retrieve by PK
            retrieved = session.get_one(Author, author.id)
            assert retrieved.name == "Test Select"
            assert retrieved.id == author.id

    def test_update_record(self, engine: Engine):
        """Test updating a record."""
        with Session(engine) as session:
            # Create
            author = Author(name="Original Name", field="Biology")
            session.add(author)
            session.flush()

            # Update
            author.name = "Updated Name"
            session.flush()

            # Verify
            session.refresh(author)
            assert author.name == "Updated Name"

    def test_delete_record(self, engine: Engine):
        """Test deleting a record."""
        with Session(engine) as session:
            # Create
            author = Author(name="To Delete", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            # Delete
            session.delete(author)
            session.flush()

            # Verify deletion
            result = session.get(Author, author.id)
            assert result is None

    def test_bulk_insert_with_core(self, engine: Engine):
        """Test bulk insert using Core insert statement."""
        stmt = insert(Author).values(
            [
                {"name": "Bulk Author 1", "field": "Physics"},
                {"name": "Bulk Author 2", "field": "Biology"},
                {"name": "Bulk Author 3", "field": "Chemistry"},
            ]
        )

        with Session(engine) as session:
            session.execute(stmt)
            session.commit()

            # Verify
            result = session.execute(select(Author))
            authors = result.scalars().all()
            bulk_authors = [a for a in authors if a.name.startswith("Bulk")]
            assert len(bulk_authors) >= 3


class TestSelectQueries:
    """Test SELECT queries with various clauses."""

    def test_select_all(self, engine: Engine):
        """Test selecting all records."""
        with Session(engine) as session:
            # Add test data
            for i in range(3):
                session.add(Author(name=f"Select All {i}", field="Physics"))
            session.flush()

            # Select all
            stmt = select(Author)
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) >= 3

    def test_select_where_simple(self, engine: Engine):
        """Test SELECT with simple WHERE clause."""
        with Session(engine) as session:
            session.add(Author(name="Unique Test Author", field="Quantum Physics"))
            session.flush()

            # Query
            stmt = select(Author).where(Author["name"] == "Unique Test Author")
            result = session.execute(stmt)
            author = result.scalars().one()

            assert author.name == "Unique Test Author"
            assert author.field == "Quantum Physics"

    def test_select_where_multiple_conditions(self, engine: Engine):
        """Test SELECT with multiple WHERE conditions."""
        with Session(engine) as session:
            # Add test data
            session.add(Author(name="Multi Test 1", field="Physics"))
            session.add(Author(name="Multi Test 2", field="Biology"))
            session.flush()

            # Query with AND
            stmt = select(Author).where(
                and_(
                    Author["name"].like("Multi Test%"),
                    Author["field"] == "Physics",
                )
            )
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) == 1
            assert authors[0].name == "Multi Test 1"

    def test_select_with_or_condition(self, engine: Engine):
        """Test SELECT with OR condition."""
        with Session(engine) as session:
            session.add(Author(name="OR Test 1", field="Physics"))
            session.add(Author(name="OR Test 2", field="Biology"))
            session.flush()

            # Query with OR
            stmt = select(Author).where(
                or_(
                    Author["field"] == "Physics",
                    Author["field"] == "Biology",
                )
            )
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) >= 2

    def test_select_order_by(self, engine: Engine):
        """Test SELECT with ORDER BY."""
        with Session(engine) as session:
            # Add in random order
            session.add(Author(name="C Author", field="Physics"))
            session.add(Author(name="A Author", field="Physics"))
            session.add(Author(name="B Author", field="Physics"))
            session.flush()

            # Query ordered
            stmt = (
                select(Author)
                .where(Author["name"].like("_ Author"))
                .order_by(Author["name"].asc())
            )
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) == 3
            assert authors[0].name == "A Author"
            assert authors[1].name == "B Author"
            assert authors[2].name == "C Author"

    def test_select_limit_offset(self, engine: Engine):
        """Test SELECT with LIMIT and OFFSET."""
        with Session(engine) as session:
            # Add multiple records
            for i in range(10):
                session.add(Author(name=f"Paginate {i:02d}", field="Physics"))
            session.flush()

            # Query with limit and offset
            stmt = (
                select(Author)
                .where(Author["name"].like("Paginate%"))
                .order_by(Author["name"])
                .limit(3)
                .offset(2)
            )
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) == 3
            assert authors[0].name == "Paginate 02"
            assert authors[2].name == "Paginate 04"

    def test_select_with_in_clause(self, engine: Engine):
        """Test SELECT with IN clause."""
        with Session(engine) as session:
            session.add(Author(name="IN Test 1", field="Physics"))
            session.add(Author(name="IN Test 2", field="Biology"))
            session.add(Author(name="IN Test 3", field="Chemistry"))
            session.flush()

            # Query with IN
            stmt = select(Author).where(Author["field"].in_(["Physics", "Chemistry"]))
            result = session.execute(stmt)
            authors = result.scalars().all()

            fields = {a.field for a in authors}
            assert "Physics" in fields
            assert "Chemistry" in fields


class TestUpdateDelete:
    """Test UPDATE and DELETE operations."""

    def test_update_with_returning(self, engine: Engine):
        """Test UPDATE with RETURNING clause."""
        with Session(engine) as session:
            # Create author
            author = Author(name="Before Update", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()

            session.expunge_all()

            # Update with RETURNING
            stmt = (
                update(Author)
                .where(Author["id"] == author.id)
                .values(name="After Update")
                .returning(Author)
            )
            updated_author = session.execute(stmt).scalar_one()

            # Verify
            assert updated_author.name == "After Update"

            # Check via transmuter
            session.expire_all()

            author_retrieved = session.get_one(Author, author.id)
            assert author_retrieved.name == "After Update"

    def test_update_returning_refreshes_cached_transmuter(self, engine: Engine):
        """UPDATE ... RETURNING re-syncs a transmuter already cached in the session.

        SQLAlchemy refreshes the ORM row from RETURNING, but the validation
        context would otherwise hand back the cached (pre-update) transmuter — so
        without the forced re-sync its scalar fields would read the old value.
        """
        with Session(engine) as session:
            author = Author(name="Returning Before", field="Physics")
            session.add(author)
            session.flush()  # author is now cached in the validation context

            returned = session.execute(
                update(Author)
                .where(Author["id"] == author.id)
                .values(name="Returning After")
                .returning(Author)
            ).scalar_one()

            assert returned is author  # same cached identity
            assert returned.name == "Returning After"  # refreshed, not stale
            assert author.name == "Returning After"
            session.rollback()

    def test_delete_with_returning(self, engine: Engine):
        """Test DELETE with RETURNING clause."""
        with Session(engine) as session:
            # Create author
            author = Author(name="To Delete RETURNING", field="Biology")
            session.add(author)
            session.flush()
            author.revalidate()

            session.expunge_all()

            # Delete with RETURNING
            stmt = delete(Author).where(Author["id"] == author.id).returning(Author)
            deleted_author = session.execute(stmt).scalar_one()

            # Verify returned data
            assert deleted_author.name == "To Delete RETURNING"
            assert deleted_author.field == "Biology"

            # Verify deletion
            assert (
                session.execute(
                    select(Author).where(Author["id"] == author.id)
                ).scalar_one_or_none()
                is None
            )

    def test_bulk_update(self, engine: Engine):
        """Test bulk UPDATE operation."""
        with Session(engine) as session:
            # Create multiple authors
            for i in range(3):
                session.add(Author(name=f"Bulk Update {i}", field="Physics"))
            session.flush()

            # Bulk update
            stmt = (
                update(Author)
                .where(Author["name"].like("Bulk Update%"))
                .values(field="Quantum Physics")
            )
            result = session.execute(stmt)
            assert result.rowcount == 3

            session.expunge_all()

            # Verify
            stmt = select(Author).where(Author["name"].like("Bulk Update%"))
            authors = session.execute(stmt).scalars().all()
            assert all(a.field == "Quantum Physics" for a in authors)


class TestJoinOperations:
    """Test JOIN operations."""

    def test_simple_join(self, engine: Engine):
        """Test simple JOIN between Book and Author."""
        with Session(engine) as session:
            # Create test data
            author = Author(name="Join Test Author", field="Literature")
            publisher = Publisher(name="Join Test Pub", country="USA")
            book = Book(title="Join Test Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()

            # Join query
            stmt = select(Book).join(Author).where(Author["name"] == "Join Test Author")
            result = session.execute(stmt)
            found_book = result.scalars().one()

            assert found_book.title == "Join Test Book"

    def test_multiple_joins(self, engine: Engine):
        """Test query with multiple JOINs."""
        with Session(engine) as session:
            # Create test data
            author = Author(name="Multi Join Author", field="Physics")
            publisher = Publisher(name="Multi Join Pub", country="UK")
            book = Book(title="Multi Join Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()

            # Multi-join query
            stmt = (
                select(Book)
                .join(Author)
                .join(Publisher)
                .where(
                    and_(
                        Author["field"] == "Physics",
                        Publisher["country"] == "UK",
                    )
                )
            )
            result = session.execute(stmt)
            books = result.scalars().all()

            assert len(books) >= 1
            assert any(b.title == "Multi Join Book" for b in books)

    def test_left_outer_join(self, engine: Engine):
        """Test LEFT OUTER JOIN."""
        with Session(engine) as session:
            # Create book without detail
            author = Author(name="LOJ Author", field="Biology")
            publisher = Publisher(name="LOJ Pub", country="USA")
            book = Book(title="Book Without Detail", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()

            # Left join with BookDetail
            stmt = select(Book).outerjoin(BookDetail)
            result = session.execute(stmt)
            books = result.scalars().all()

            # Should include book without detail
            assert any(b.title == "Book Without Detail" for b in books)


class TestLoadingStrategies:
    """Test different loading strategies."""

    def test_selectinload_one_to_many(self, engine: Engine):
        """Test selectinload for 1-M relationship."""
        with Session(engine) as session:
            # Create author with multiple books
            author = Author(name="Selectin Author", field="Literature")
            publisher = Publisher(name="Selectin Pub", country="USA")

            for i in range(3):
                book = Book(title=f"Selectin Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                author.books.append(book)

            session.add(author)
            session.flush()
            author.revalidate()

            # Clear session
            session.expunge_all()

            # Query with selectinload
            stmt = (
                select(Author)
                .where(Author["id"] == author.id)
                .options(selectinload(Author["books"]))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Books should be loaded
            assert len(loaded_author.books) == 3
            # Access should not trigger additional query
            for book in loaded_author.books:
                assert book.title.startswith("Selectin Book")

    def test_joinedload_many_to_one(self, engine: Engine):
        """Test joinedload for M-1 relationship."""
        with Session(engine) as session:
            # Create book with author
            author = Author(name="Joined Author", field="Physics")
            publisher = Publisher(name="Joined Pub", country="UK")
            book = Book(title="Joined Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()

            # Query with joinedload
            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(joinedload(Book["author"]))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Author should be loaded
            assert loaded_book.author.value.name == "Joined Author"

    def test_selectinload_many_to_many(self, engine: Engine):
        """Test selectinload for M-M relationship."""
        with Session(engine) as session:
            # Create book with categories
            author = Author(name="M2M Author", field="Literature")
            publisher = Publisher(name="M2M Pub", country="USA")
            book = Book(title="M2M Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="M2M Cat1", description="Category 1")
            cat2 = Category(name="M2M Cat2", description="Category 2")
            book.categories.extend([cat1, cat2])

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()
            # Query with selectinload
            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(selectinload(Book["categories"]))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Categories should be loaded
            assert len(loaded_book.categories) == 2
            cat_names = {c.name for c in loaded_book.categories}
            assert "M2M Cat1" in cat_names
            assert "M2M Cat2" in cat_names


class TestComplexExpressions:
    """Test complex SQL expressions and filters."""

    def test_column_expression_via_getitem(self, engine: Engine):
        """Test using transmuter[column] for expressions."""
        with Session(engine) as session:
            session.add(Author(name="Expression Test", field="Physics"))
            session.flush()

            # Use transmuter[column] syntax
            stmt = select(Author).where(Author["name"] == "Expression Test")
            result = session.execute(stmt)
            author = result.scalars().one()

            assert author.name == "Expression Test"

    def test_aggregate_functions(self, engine: Engine):
        """Test aggregate functions like COUNT, MAX, MIN."""
        with Session(engine) as session:
            # Add test data
            for i in range(5):
                session.add(Author(name=f"Aggregate Test {i}", field="Physics"))
            session.flush()

            # Count
            stmt = (
                select(func.count())
                .select_from(Author)
                .where(Author["name"].like("Aggregate Test%"))
            )
            count = session.execute(stmt).scalar()
            assert count == 5

            # Max ID
            stmt = select(func.max(Author["id"])).where(
                Author["name"].like("Aggregate Test%")
            )
            max_id = session.execute(stmt).scalar()
            assert max_id is not None

    def test_like_pattern_matching(self, engine: Engine):
        """Test LIKE pattern matching."""
        with Session(engine) as session:
            session.add(Author(name="Pattern ABC", field="Physics"))
            session.add(Author(name="Pattern XYZ", field="Biology"))
            session.add(Author(name="Different", field="Chemistry"))
            session.flush()

            # LIKE query
            stmt = select(Author).where(Author["name"].like("Pattern%"))
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) >= 2
            assert all(a.name.startswith("Pattern") for a in authors)

    def test_complex_nested_conditions(self, engine: Engine):
        """Test complex nested AND/OR conditions."""
        with Session(engine) as session:
            # Add test data
            session.add(Author(name="Complex 1", field="Physics"))
            session.add(Author(name="Complex 2", field="Biology"))
            session.add(Author(name="Simple 1", field="Physics"))
            session.flush()

            # Complex condition: (name LIKE 'Complex%' AND field='Physics') OR (name='Simple 1')
            stmt = select(Author).where(
                or_(
                    and_(
                        Author["name"].like("Complex%"),
                        Author["field"] == "Physics",
                    ),
                    Author["name"] == "Simple 1",
                )
            )
            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) >= 2
            names = {a.name for a in authors}
            assert "Complex 1" in names
            assert "Simple 1" in names

    def test_subquery(self, engine: Engine):
        """Test using subqueries."""
        with Session(engine) as session:
            # Create authors with books
            author1 = Author(name="Subquery Author 1", field="Physics")
            author2 = Author(name="Subquery Author 2", field="Biology")
            publisher = Publisher(name="Subquery Pub", country="USA")

            book1 = Book(title="Subquery Book 1", year=2020)
            book1.author.value = author1
            book1.publisher.value = publisher

            book2 = Book(title="Subquery Book 2", year=2021)
            book2.author.value = author2
            book2.publisher.value = publisher

            session.add_all([book1, book2])
            session.flush()

            # Subquery: authors who have books
            subq = select(Author["id"]).join(Book).subquery()
            stmt = select(Author).where(Author["id"].in_(select(subq)))

            result = session.execute(stmt)
            authors = result.scalars().all()

            assert len(authors) >= 2
            names = {a.name for a in authors}
            assert "Subquery Author 1" in names
            assert "Subquery Author 2" in names
