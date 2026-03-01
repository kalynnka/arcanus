"""Test relationship handling.

Tests:
- 1-1 relationships (Book <-> BookDetail, Book <-> Translator)
- 1-M relationships (Author <-> Books, Publisher <-> Books)
- M-M relationships (Book <-> Categories)
- Circular relationships (Author -> Book -> Author)
- Lazy loading behaviors
- Eager loading with selectinload/joinedload
- lazy='raise' and raiseload() preventing N+1
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import joinedload, raiseload, selectinload

from arcanus.association import Relation, RelationCollection
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import (
    Author,
    Book,
    BookDetail,
    Category,
    Publisher,
    Review,
    Translator,
)


class TestOneToOneRelationships:
    """Test 1-1 relationship handling."""

    def test_book_to_book_detail_forward(self, engine: Engine):
        """Test accessing BookDetail from Book (1-1 forward)."""
        with Session(engine) as session:
            author = Author(name="1-1 Author", field="Physics")
            publisher = Publisher(name="1-1 Publisher", country="USA")
            book = Book(title="1-1 Test Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-1234567890",
                pages=300,
                abstract="Test abstract",
            )
            book.detail.value = detail

            session.add(book)
            session.flush()

            # Access detail through book
            assert book.detail.value is not None
            assert book.detail.value.isbn == "978-1234567890"
            assert book.detail.value.pages == 300

    def test_book_detail_to_book_backward(self, engine: Engine):
        """Test accessing Book from BookDetail (1-1 backward)."""
        with Session(engine) as session:
            author = Author(name="1-1 Back Author", field="Biology")
            publisher = Publisher(name="1-1 Back Pub", country="UK")
            book = Book(title="1-1 Back Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-0987654321",
                pages=250,
                abstract="Back reference test",
            )
            book.detail.value = detail

            session.add(book)
            session.flush()

            # Access book through detail
            assert detail.book.value is not None
            assert detail.book.value.title == "1-1 Back Book"

    def test_optional_one_to_one_translator(self, engine: Engine):
        """Test optional 1-1 relationship with Translator."""
        with Session(engine) as session:
            # Book without translator
            author = Author(name="No Trans Author", field="Literature")
            publisher = Publisher(name="No Trans Pub", country="USA")
            book1 = Book(title="Original Language", year=2024)
            book1.author.value = author
            book1.publisher.value = publisher

            # Book with translator
            translator = Translator(name="John Translator", language="Spanish")
            book2 = Book(title="Translated Book", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher
            book2.translator.value = translator

            session.add_all([book1, book2])
            session.flush()

            # Book1 has no translator
            assert book1.translator.value is None

            # Book2 has translator
            assert book2.translator.value is not None
            assert book2.translator.value.name == "John Translator"

    def test_one_to_one_bidirectional(self, engine: Engine):
        """Test bidirectional 1-1 relationship consistency."""
        with Session(engine) as session:
            author = Author(name="Bidir Author", field="Chemistry")
            publisher = Publisher(name="Bidir Pub", country="USA")
            book = Book(title="Bidir Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-1111111111",
                pages=200,
                abstract="Bidirectional test",
            )
            book.detail.value = detail

            session.add(book)
            session.flush()

            # Both directions should work
            assert book.detail.value is detail
            assert detail.book.value is book


class TestOneToManyRelationships:
    """Test 1-M relationship handling."""

    def test_author_to_books_forward(self, engine: Engine):
        """Test accessing Books from Author (1-M forward)."""
        with Session(engine) as session:
            author = Author(name="Prolific Author", field="Literature")
            publisher = Publisher(name="1-M Publisher", country="USA")

            for i in range(3):
                book = Book(title="A Book", year=2024)
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()

            # Access books through author
            assert len(author.books) == 3
            assert all(isinstance(b, Book) for b in author.books)

    def test_book_to_author_backward(self, engine: Engine):
        """Test accessing Author from Book (M-1 backward)."""
        with Session(engine) as session:
            author = Author(name="M-1 Author", field="Physics")
            publisher = Publisher(name="M-1 Pub", country="UK")
            book = Book(title="M-1 Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()

            # Access author through book
            assert book.author.value is not None
            assert book.author.value.name == "M-1 Author"

    def test_publisher_to_books(self, engine: Engine):
        """Test Publisher to Books (1-M)."""
        with Session(engine) as session:
            publisher = Publisher(name="Big Publisher", country="USA")
            author = Author(name="Pub Author", field="Biology")

            for i in range(5):
                book = Book(title=f"Published Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            session.flush()
            publisher.revalidate()

            assert len(publisher.books) == 5

    def test_one_to_many_append_and_remove(self, engine: Engine):
        """Test appending and removing items from 1-M relationship."""
        with Session(engine) as session:
            author = Author(name="Modify Author", field="Chemistry")
            publisher = Publisher(name="Modify Pub", country="USA")

            book1 = Book(title="First Book", year=2023)
            book1.author.value = author
            book1.publisher.value = publisher

            book2 = Book(title="Second Book", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher

            # SQLAlchemy backref handles the append automatically

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()
            book1.revalidate()

            assert len(author.books) == 2

            # Remove one
            author.books.remove(book1)
            session.flush()
            author.revalidate()

            assert len(author.books) == 1
            assert author.books[0].title == "Second Book"


class TestManyToManyRelationships:
    """Test M-M relationship handling."""

    def test_book_to_categories_forward(self, engine: Engine):
        """Test accessing Categories from Book (M-M forward)."""
        with Session(engine) as session:
            author = Author(name="M-M Author", field="Literature")
            publisher = Publisher(name="M-M Pub", country="USA")
            book = Book(title="M-M Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="M-M Fiction", description="Fiction books")
            cat2 = Category(name="M-M Drama", description="Drama books")
            cat3 = Category(name="M-M Classic", description="Classic literature")

            book.categories.extend([cat1, cat2, cat3])

            session.add(book)
            session.flush()
            book.revalidate()

            # Access categories through book
            assert len(book.categories) == 3
            cat_names = {c.name for c in book.categories}
            assert "M-M Fiction" in cat_names
            assert "M-M Drama" in cat_names
            assert "M-M Classic" in cat_names

    def test_category_to_books_backward(self, engine: Engine):
        """Test accessing Books from Category (M-M backward)."""
        with Session(engine) as session:
            category = Category(name="Science Fiction", description="Sci-fi books")
            author = Author(name="Sci-Fi Author", field="Literature")
            publisher = Publisher(name="Sci-Fi Pub", country="USA")

            for i in range(4):
                book = Book(
                    title=f"Sci-Fi Book {i}",
                    year=2024,
                    author=Relation(author),
                    publisher=Relation(publisher),
                    categories=RelationCollection([category]),
                )
                session.add(book)

            # session.add(category)
            session.flush()
            category.revalidate()

            # Access books through category
            assert len(category.books) == 4

    def test_many_to_many_bidirectional(self, engine: Engine):
        """Test bidirectional M-M relationship."""
        with Session(engine) as session:
            author = Author(name="Bidir M-M Author", field="History")
            publisher = Publisher(name="Bidir M-M Pub", country="UK")
            category = Category(name="Bidir M-M Cat", description="Test category")

            book = Book(
                title="Bidir M-M Book",
                year=2024,
                author=Relation(author),
                publisher=Relation(publisher),
            )

            book.categories.append(category)

            session.add(book)
            session.flush()
            book.revalidate()
            category.revalidate()

            # Both directions should work
            assert category in book.categories
            assert book in category.books

    def test_many_to_many_remove(self, engine: Engine):
        """Test removing from M-M relationship."""
        with Session(engine) as session:
            author = Author(name="Remove M-M Author", field="Literature")
            publisher = Publisher(name="Remove M-M Pub", country="USA")
            book = Book(title="Remove M-M Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            cat1 = Category(name="Remove Cat 1", description="Cat 1")
            cat2 = Category(name="Remove Cat 2", description="Cat 2")

            book.categories.extend([cat1, cat2])

            session.add(book)
            session.flush()
            book.revalidate()

            assert len(book.categories) == 2

            # Remove one category
            book.categories.remove(cat1)
            session.flush()
            book.revalidate()

            assert len(book.categories) == 1
            assert book.categories[0].name == "Remove Cat 2"


class TestCircularRelationships:
    """Test circular/bidirectional relationships."""

    def test_author_book_circular_reference(self, engine: Engine):
        """Test circular reference: Author -> Book -> Author."""
        with Session(engine) as session:
            author = Author(name="Circular Author", field="Physics")
            publisher = Publisher(name="Circular Pub", country="USA")
            book = Book(title="Circular Book", year=2024)

            # Set up circular reference
            book.author.value = author
            book.publisher.value = publisher
            # SQLAlchemy backref handles author.books

            session.add(author)
            session.flush()
            author.revalidate()
            book.revalidate()

            # Navigate in circle
            assert book.author.value is author
            assert book in author.books
            assert author.books[0].author.value is author

    def test_book_detail_circular(self, engine: Engine):
        """Test circular reference: Book -> BookDetail -> Book."""
        with Session(engine) as session:
            author = Author(name="Detail Circular", field="Biology")
            publisher = Publisher(name="Detail Circular Pub", country="UK")
            book = Book(title="Detail Circular Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-2222222222",
                pages=150,
                abstract="Circular detail",
            )

            book.detail.value = detail
            # SQLAlchemy backref handles detail.book

            session.add(book)
            session.flush()
            book.revalidate()
            detail.revalidate()

            # Navigate in circle
            assert book.detail.value.book.value is book


class TestLazyLoading:
    """Test lazy loading behavior."""

    def test_lazy_load_collection(self, engine: Engine):
        """Test that collections are lazy-loaded by default."""
        with Session(engine) as session:
            author = Author(name="Lazy Author", field="Literature")
            publisher = Publisher(name="Lazy Pub", country="USA")

            for i in range(3):
                book = Book(title=f"Lazy Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                # SQLAlchemy backref handles author.books

            session.add(author)
            session.flush()
            author.revalidate()

            # Clear session to force reload
            session.expunge_all()

            # Load author without books
            loaded_author = session.get_one(Author, author.id)

            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                # Accessing books should trigger lazy load
                books = loaded_author.books
                assert len(books) == 3

                # Should have executed at least one SELECT for lazy loading books
                assert execute_spy.call_count == 1, (
                    "Expected lazy load to trigger SQL execution"
                )

    def test_lazy_load_single_object(self, engine: Engine):
        """Test lazy loading single object (M-1 relation)."""
        with Session(engine) as session:
            author = Author(name="Lazy Single Author", field="Physics")
            publisher = Publisher(name="Lazy Single Pub", country="USA")
            book = Book(title="Lazy Single Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()

            # Load book
            loaded_book = session.get_one(Book, book.id)

            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                # Accessing author should lazy load
                assert loaded_book.author.value.name == "Lazy Single Author"

                # Should have executed at least one SELECT for lazy loading author
                assert execute_spy.call_count == 1, (
                    "Expected lazy load to trigger SQL execution"
                )


class TestEagerLoading:
    """Test eager loading strategies."""

    def test_selectinload_prevents_n_plus_1(self, engine: Engine):
        """Test selectinload prevents N+1 queries."""
        with Session(engine) as session:
            publisher = Publisher(name="Selectin Pub", country="USA")

            # Create multiple authors with books
            books = []
            for i in range(5):
                author = Author(name=f"Selectin Author {i}", field="Physics")
                book = Book(title=f"Selectin Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                # SQLAlchemy backref handles author.books
                books.append(book)

            session.add_all(books)
            session.flush()

            for book in books:
                book.revalidate()

            # Clear session
            session.expunge_all()

            # Load all books with selectinload for author
            stmt = (
                select(Book)
                .where(Book["id"].in_([book.id for book in books]))
                .options(selectinload(Book["author"]))
            )
            books = session.execute(stmt).scalars().all()

            # Verify no implicit SELECT is triggered when accessing pre-loaded relationships
            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                assert len(books) == 5
                for book in books:
                    assert book.author.value is not None

                assert execute_spy.call_count == 0, (
                    "selectinload should prevent implicit SQL when accessing relationships"
                )

    def test_joinedload_loads_in_one_query(self, engine: Engine):
        """Test joinedload loads related objects in one query."""
        with Session(engine) as session:
            author = Author(name="Joined Author", field="Biology")
            publisher = Publisher(name="Joined Pub", country="UK")

            for i in range(3):
                book = Book(title=f"Joined Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                author.books.append(book)

            session.add(author)
            session.flush()
            author.revalidate()

            # Clear session
            session.expunge_all()

            # Load author with joined books
            stmt = (
                select(Author)
                .where(Author["id"] == author.id)
                .options(joinedload(Author["books"]))
            )
            loaded_author = session.execute(stmt).scalars().unique().one()

            # Verify no implicit SELECT is triggered when accessing pre-loaded relationships
            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                # Books should be loaded
                assert len(loaded_author.books) == 3

                assert execute_spy.call_count == 0, (
                    "joinedload should prevent implicit SQL when accessing relationships"
                )

    def test_selectinload_many_to_many(self, engine: Engine):
        """Test selectinload with M-M relationship."""
        with Session(engine) as session:
            author = Author(name="Selectin M-M Author", field="Literature")
            publisher = Publisher(name="Selectin M-M Pub", country="USA")

            book_ids = []
            for i in range(3):
                book = Book(title=f"Selectin M-M Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher

                cat1 = Category(name=f"Selectin Cat {i}-1", description="Category 1")
                cat2 = Category(name=f"Selectin Cat {i}-2", description="Category 2")
                book.categories.extend([cat1, cat2])

                print(id(book))
                session.add(book)

            session.flush()
            # Get book IDs after flush
            for book in author.books:
                book.revalidate()
                book_ids.append(book.id)

            # Clear session
            session.expunge_all()

            # Load books with categories (filter to our books only)
            stmt = (
                select(Book)
                .where(Book["id"].in_(book_ids))
                .options(selectinload(Book["categories"]))
            )
            books = session.execute(stmt).scalars().all()

            # Verify no implicit SELECT is triggered when accessing pre-loaded relationships
            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                assert len(books) == 3
                # Categories should be loaded
                for book in books:
                    assert len(book.categories) == 2

                assert execute_spy.call_count == 0, (
                    "selectinload should prevent implicit SQL when accessing relationships"
                )

    def test_selectinload_many_to_many_with_backref(self, engine: Engine):
        """Test selectinload M-M where backref creates circular validation.

        This tests the scenario where:
        - Book has categories (M-M)
        - Category has books (backref)
        - When loading Book with selectinload(categories), SQLAlchemy also loads
          the Category.books backref which points back to Book
        - This creates a circular validation: Book -> Category -> Book

        The validation context should prevent infinite recursion by caching
        already-validated instances.
        """
        with Session(engine) as session:
            author = Author(name="Backref M-M Author", field="Physics")
            publisher = Publisher(name="Backref M-M Pub", country="USA")

            # Create books that share categories (to test backref loading)
            cat_shared = Category(
                name="Shared Category", description="Shared by multiple books"
            )

            book1 = Book(title="Backref Book 1", year=2024)
            book1.author.value = author
            book1.publisher.value = publisher
            book1.categories.append(cat_shared)

            book2 = Book(title="Backref Book 2", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher
            book2.categories.append(cat_shared)

            session.add(book1)
            session.add(book2)
            session.flush()

            book1.revalidate()
            book2.revalidate()

            # Clear session to force reload and clear validation context
            session.expunge_all()

            # Load book1 with selectinload on categories and nested books backref
            stmt = (
                select(Book)
                .where(Book["id"] == book1.id)
                .options(
                    selectinload(Book["categories"]).selectinload(Category["books"])
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Verify no implicit SELECT is triggered when accessing pre-loaded relationships
            with patch.object(session, "execute", wraps=session.execute) as execute_spy:
                # Should have loaded the shared category
                assert len(loaded_book.categories) == 1
                assert loaded_book.categories[0].name == "Shared Category"

                # The category's books backref should contain both books
                # This tests that circular validation works
                loaded_cat = loaded_book.categories[0]
                assert len(loaded_cat.books) == 2
                book_titles = {b.title for b in loaded_cat.books}
                assert book_titles == {"Backref Book 1", "Backref Book 2"}

                assert execute_spy.call_count == 0, (
                    "selectinload should prevent implicit SQL when accessing relationships"
                )


class TestRaiseOnSQLBehavior:
    """Test lazy='raise' and raiseload() preventing implicit SQL."""

    def test_raiseload_prevents_lazy_loading(self, engine: Engine):
        """Test that raiseload() prevents lazy loading."""
        with Session(engine) as session:
            author = Author(name="Raise Author", field="Chemistry")
            publisher = Publisher(name="Raise Pub", country="USA")
            book = Book(title="Raise Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()

            # Load book with raiseload on author
            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(raiseload(Book["author"]))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Accessing author should raise RuntimeError (Arcanus wraps InvalidRequestError)
            with pytest.raises(
                InvalidRequestError, match="loading strategy is set to 'raise'"
            ):
                _ = loaded_book.author.value

    def test_raiseload_collection(self, engine: Engine):
        """Test raiseload on collection relationships."""
        with Session(engine) as session:
            author = Author(name="Raise Collection Author", field="Physics")
            publisher = Publisher(name="Raise Collection Pub", country="USA")

            for i in range(2):
                book = Book(title=f"Raise Collection Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                author.books.append(book)

            session.add(author)
            session.flush()
            author.revalidate()

            # Clear session
            session.expunge_all()

            # Load author with raiseload on books
            stmt = (
                select(Author)
                .where(Author["id"] == author.id)
                .options(raiseload(Author["books"]))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Accessing books collection should raise RuntimeError (Arcanus wraps InvalidRequestError)
            # We need to iterate or access elements to trigger the lazy load
            with pytest.raises(
                InvalidRequestError, match="loading strategy is set to 'raise'"
            ):
                _ = len(loaded_author.books)


class TestReviewsOneToMany:
    """Test Reviews as another 1-M relationship example."""

    def test_book_to_reviews(self, engine: Engine):
        """Test accessing Reviews from Book."""
        with Session(engine) as session:
            author = Author(name="Review Author", field="Literature")
            publisher = Publisher(name="Review Pub", country="USA")
            book = Book(title="Reviewed Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            review1 = Review(
                reviewer_name="Alice",
                rating=5,
                comment="Excellent!",
            )
            review2 = Review(
                reviewer_name="Bob",
                rating=4,
                comment="Good read",
            )

            book.reviews.extend([review1, review2])

            session.add(book)
            session.flush()

            # Access reviews through book
            assert len(book.reviews) == 2
            ratings = [r.rating for r in book.reviews]
            assert 5 in ratings
            assert 4 in ratings

    def test_review_to_book(self, engine: Engine):
        """Test accessing Book from Review."""
        with Session(engine) as session:
            author = Author(name="Review Back Author", field="History")
            publisher = Publisher(name="Review Back Pub", country="UK")
            book = Book(title="Back Review Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            review = Review(
                reviewer_name="Charlie",
                rating=3,
                comment="Okay",
            )

            book.reviews.append(review)

            session.add(book)
            session.flush()

            # Access book through review
            assert review.book.value is not None
            assert review.book.value.title == "Back Review Book"


class TestComplexRelationshipQueries:
    """Test complex queries involving multiple relationships."""

    def test_query_across_multiple_relationships(self, engine: Engine):
        """Test querying across multiple relationship levels."""
        with Session(engine) as session:
            author = Author(name="Complex Query Author", field="Astronomy")
            publisher = Publisher(name="Complex Query Pub", country="USA")
            book = Book(title="Complex Query Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-3333333333",
                pages=400,
                abstract="Complex query test",
            )
            book.detail.value = detail

            cat = Category(name="Astronomy", description="Space books")
            book.categories.append(cat)

            session.add(book)
            session.flush()

            # Query books with specific author field, category, and page count
            stmt = (
                select(Book)
                .join(Author)
                .join(BookDetail)
                .join(Book["categories"])
                .where(
                    Author["field"] == "Astronomy",
                    Category["name"] == "Astronomy",
                    BookDetail["pages"] >= 300,
                )
            )

            books = session.execute(stmt).scalars().unique().all()

            assert len(books) >= 1
            assert any(b.title == "Complex Query Book" for b in books)

    def test_nested_relationship_loading(self, engine: Engine):
        """Test loading nested relationships."""
        with Session(engine) as session:
            author = Author(name="Nested Load Author", field="Literature")
            publisher = Publisher(name="Nested Load Pub", country="USA")
            book = Book(title="Nested Load Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-4444444444",
                pages=250,
                abstract="Nested loading",
            )
            book.detail.value = detail

            session.add(book)
            session.flush()
            book.revalidate()

            # Clear session
            session.expunge_all()

            # Load book with nested relationships
            stmt = (
                select(Book)
                .where(Book["id"] == book.id)
                .options(
                    selectinload(Book["author"]),
                    selectinload(Book["detail"]),
                    selectinload(Book["publisher"]),
                )
            )

            loaded_book = session.execute(stmt).scalars().one()

            # All relationships should be loaded
            assert loaded_book.author.value.name == "Nested Load Author"
            assert loaded_book.detail.value
            assert loaded_book.detail.value.pages == 250
            assert loaded_book.publisher.value.name == "Nested Load Pub"


class TestAutoflushBeforeRelationshipLoading:
    """Test that auto-fired statements (autoflush) are executed before visiting relationships.

    These tests ensure that when using selectinload or other eager loading strategies,
    pending INSERT/UPDATE operations are flushed before the relationship loading queries
    are executed, preventing stale data issues.
    """

    def test_autoflush_before_selectinload_one_to_many(self, engine: Engine):
        """Test autoflush runs before selectinload on 1-M relationship.

        Ensures that when adding new books to an author and then querying
        with selectinload, the new books are visible in the results.
        """
        with Session(engine) as session:
            author = Author(name="Autoflush 1-M Author", field="Physics")
            publisher = Publisher(name="Autoflush 1-M Pub", country="USA")

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()
            publisher.revalidate()

            # Add books directly to ORM relationship
            for i in range(3):
                book = Book(title=f"Autoflush 1-M Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                session.add(book)

            # Note: Books are in pending state, not yet flushed
            # Query with selectinload - autoflush should fire before relationship loading
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                stmt = (
                    select(Author)
                    .where(Author["id"] == author.id)
                    .options(selectinload(Author["books"]))
                )
                loaded_author = session.execute(stmt).scalars().one()

                # Flush should have been called by autoflush before the query
                assert flush_spy.call_count >= 1

            # All pending books should be loaded
            assert len(loaded_author.books) == 3

    def test_autoflush_before_selectinload_many_to_one(self, engine: Engine):
        """Test autoflush runs before selectinload on M-1 relationship.

        Ensures that pending changes to the related object are visible
        when loading through selectinload.
        """
        with Session(engine) as session:
            author = Author(name="Autoflush M-1 Author", field="Physics")
            publisher = Publisher(name="Autoflush M-1 Pub", country="USA")
            book = Book(title="Autoflush M-1 Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Modify the author (pending change)
            author.name = "Modified Autoflush M-1 Author"

            # Query with selectinload - autoflush should fire before loading
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                stmt = (
                    select(Book)
                    .where(Book["id"] == book.id)
                    .options(selectinload(Book["author"]))
                )
                loaded_book = session.execute(stmt).scalars().one()

                # Flush should have been called
                assert flush_spy.call_count >= 1

            # The modified author name should be visible
            assert loaded_book.author.value.name == "Modified Autoflush M-1 Author"

    def test_autoflush_before_selectinload_many_to_many(self, engine: Engine):
        """Test autoflush runs before selectinload on M-M relationship.

        Ensures that newly added categories are visible when loading
        through selectinload.
        """
        with Session(engine) as session:
            author = Author(name="Autoflush M-M Author", field="History")
            publisher = Publisher(name="Autoflush M-M Pub", country="UK")
            book = Book(title="Autoflush M-M Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Add categories after flush (pending in session)
            cat1 = Category(
                name="Autoflush M-M Category 1", description="Test category 1"
            )
            cat2 = Category(
                name="Autoflush M-M Category 2", description="Test category 2"
            )
            book.categories.extend([cat1, cat2])
            session.add(cat1)
            session.add(cat2)

            # Query with selectinload - autoflush should fire first
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                stmt = (
                    select(Book)
                    .where(Book["id"] == book.id)
                    .options(selectinload(Book["categories"]))
                )
                loaded_book = session.execute(stmt).scalars().one()

                # Flush should have been called
                assert flush_spy.call_count >= 1

            # Both pending categories should be loaded
            assert len(loaded_book.categories) == 2

    def test_autoflush_before_selectinload_one_to_one(self, engine: Engine):
        """Test autoflush runs before selectinload on 1-1 relationship.

        Ensures that a pending BookDetail is visible when loading
        through selectinload.
        """
        with Session(engine) as session:
            author = Author(name="Autoflush 1-1 Author", field="Chemistry")
            publisher = Publisher(name="Autoflush 1-1 Pub", country="USA")
            book = Book(title="Autoflush 1-1 Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Add detail after initial flush (pending change)
            detail = BookDetail(
                isbn="978-AUTOFLUSH-1",
                pages=500,
                abstract="Autoflush test abstract",
            )
            book.detail.value = detail

            # Query with selectinload - autoflush should fire first
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                stmt = (
                    select(Book)
                    .where(Book["id"] == book.id)
                    .options(selectinload(Book["detail"]))
                )
                loaded_book = session.execute(stmt).scalars().one()

                # Flush should have been called
                assert flush_spy.call_count >= 1

            # The pending detail should be loaded
            assert loaded_book.detail.value is not None
            assert loaded_book.detail.value.isbn == "978-AUTOFLUSH-1"

    def test_autoflush_before_joinedload(self, engine: Engine):
        """Test autoflush runs before joinedload.

        Ensures joinedload also benefits from autoflush behavior.
        """
        with Session(engine) as session:
            author = Author(name="Autoflush Joined Author", field="Literature")
            publisher = Publisher(name="Autoflush Joined Pub", country="France")

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()
            publisher.revalidate()

            # Add books (pending)
            for i in range(2):
                book = Book(title=f"Autoflush Joined Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                session.add(book)

            # Query with joinedload - autoflush should fire first
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                stmt = (
                    select(Author)
                    .where(Author["id"] == author.id)
                    .options(joinedload(Author["books"]))
                )
                loaded_author = session.execute(stmt).scalars().unique().one()

                # Flush should have been called
                assert flush_spy.call_count >= 1

            # All pending books should be loaded
            assert len(loaded_author.books) == 2

    def test_autoflush_disabled_does_not_flush_pending(self, engine: Engine):
        """Test that disabling autoflush prevents pending items from being flushed.

        This is a negative test to confirm that our autoflush tests are valid.
        When autoflush is disabled, pending changes should not be written to DB
        before the query executes.
        """
        with Session(engine, autoflush=False) as session:
            author = Author(name="No Autoflush Author", field="Chemistry")
            publisher = Publisher(name="No Autoflush Pub", country="Germany")

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()
            publisher.revalidate()

            # Add a book (pending, won't be flushed automatically)
            book = Book(title="No Autoflush Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher
            session.add(book)

            # Verify the book is pending (not in DB yet)
            with patch.object(session, "flush", wraps=session.flush) as flush_spy:
                # Query - autoflush disabled, flush should NOT be called
                stmt = (
                    select(Author)
                    .where(Author["id"] == author.id)
                    .options(selectinload(Author["books"]))
                )
                session.execute(stmt).scalars().one()

                # Flush should NOT have been called (autoflush disabled)
                assert flush_spy.call_count == 0

            # After manual flush, the book should be persisted
            session.flush()
            book.revalidate()
            assert book.id is not None


class TestSelectinloadWithORMRelationships:
    """Test selectinload behavior with various ORM relationship configurations.

    These tests verify that selectinload works correctly with different
    relationship types and configurations when combined with Arcanus's
    Transmuter validation system.
    """

    def test_selectinload_on_orm_relationship_one_to_many(self, engine: Engine):
        """Test selectinload on ORM 1-M relationship (Author.books)."""
        with Session(engine) as session:
            author = Author(name="ORM Selectin 1-M Author", field="Physics")
            publisher = Publisher(name="ORM Selectin 1-M Pub", country="USA")

            for i in range(4):
                book = Book(title=f"ORM Selectin 1-M Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()

            session.expunge_all()

            # Load with selectinload on the ORM relationship
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Author)
                    .where(Author["id"] == author.id)
                    .options(selectinload(Author["books"]))
                )
                loaded_author = session.execute(stmt).scalars().one()

                # Should have 2 executes: main query + selectin query
                assert spy.call_count == 2

            # Verify books are loaded correctly through Transmuter
            assert len(loaded_author.books) == 4
            for book in loaded_author.books:
                assert isinstance(book, Book)
                assert "ORM Selectin 1-M Book" in book.title

    def test_selectinload_on_orm_relationship_many_to_one(self, engine: Engine):
        """Test selectinload on ORM M-1 relationship (Book.author)."""
        with Session(engine) as session:
            author = Author(name="ORM Selectin M-1 Author", field="Physics")
            publisher = Publisher(name="ORM Selectin M-1 Pub", country="UK")

            book_ids = []
            for i in range(3):
                book = Book(title=f"ORM Selectin M-1 Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                session.add(book)

            session.flush()

            for book in author.books:
                book.revalidate()
                book_ids.append(book.id)

            session.expunge_all()

            # Load with selectinload on ORM M-1 relationship
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Book)
                    .where(Book["id"].in_(book_ids))
                    .options(selectinload(Book["author"]))
                )
                books = session.execute(stmt).scalars().all()

                # Main query + selectin query for authors
                assert spy.call_count == 2

            # All books should have the same author loaded
            assert len(books) == 3
            for book in books:
                assert book.author.value is not None
                assert book.author.value.name == "ORM Selectin M-1 Author"

    def test_selectinload_on_orm_relationship_many_to_many(self, engine: Engine):
        """Test selectinload on ORM M-M relationship (Book.categories)."""
        with Session(engine) as session:
            author = Author(name="ORM Selectin M-M Author", field="Literature")
            publisher = Publisher(name="ORM Selectin M-M Pub", country="USA")

            # Create shared categories
            categories = [
                Category(name=f"ORM Selectin M-M Cat {i}", description=f"Category {i}")
                for i in range(3)
            ]

            book_ids = []
            for i in range(2):
                book = Book(title=f"ORM Selectin M-M Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                book.categories.extend(categories)
                session.add(book)

            session.flush()

            for book in author.books:
                book.revalidate()
                book_ids.append(book.id)

            session.expunge_all()

            # Load with selectinload on ORM M-M relationship
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Book)
                    .where(Book["id"].in_(book_ids))
                    .options(selectinload(Book["categories"]))
                )
                books = session.execute(stmt).scalars().all()

                # Main query + selectin query for categories
                assert spy.call_count == 2

            # Each book should have all 3 categories
            assert len(books) == 2
            for book in books:
                assert len(book.categories) == 3

    def test_selectinload_on_orm_relationship_one_to_one(self, engine: Engine):
        """Test selectinload on ORM 1-1 relationship (Book.detail)."""
        with Session(engine) as session:
            author = Author(name="ORM Selectin 1-1 Author", field="Chemistry")
            publisher = Publisher(name="ORM Selectin 1-1 Pub", country="France")

            book_ids = []
            for i in range(3):
                book = Book(title=f"ORM Selectin 1-1 Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                detail = BookDetail(
                    isbn=f"978-ORM-SELECTIN-{i}",
                    pages=100 + i * 50,
                    abstract=f"ORM Selectin abstract {i}",
                )
                book.detail.value = detail
                session.add(book)

            session.flush()

            for book in author.books:
                book.revalidate()
                book_ids.append(book.id)

            session.expunge_all()

            # Load with selectinload on ORM 1-1 relationship
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Book)
                    .where(Book["id"].in_(book_ids))
                    .options(selectinload(Book["detail"]))
                )
                books = session.execute(stmt).scalars().all()

                # Main query + selectin query for details
                assert spy.call_count == 2

            # Each book should have its detail loaded
            assert len(books) == 3
            for book in books:
                assert book.detail.value is not None
                assert "978-ORM-SELECTIN" in book.detail.value.isbn

    def test_selectinload_chained_relationships(self, engine: Engine):
        """Test chained selectinload for nested relationships."""
        with Session(engine) as session:
            author = Author(name="ORM Chained Selectin Author", field="Literature")
            publisher = Publisher(name="ORM Chained Selectin Pub", country="Italy")

            book = Book(title="ORM Chained Selectin Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-CHAINED-001",
                pages=300,
                abstract="Chained selectin test",
            )
            book.detail.value = detail

            for i in range(2):
                review = Review(
                    reviewer_name=f"Reviewer {i}",
                    rating=4 + (i % 2),
                    comment=f"Great book {i}!",
                )
                book.reviews.append(review)

            session.add(book)
            session.flush()
            author.revalidate()

            session.expunge_all()

            # Load author with chained selectinload
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Author)
                    .where(Author["id"] == author.id)
                    .options(
                        selectinload(Author["books"]).selectinload(Book["reviews"])
                    )
                )
                loaded_author = session.execute(stmt).scalars().one()

                # Main query + books selectin + reviews selectin
                assert spy.call_count == 3

            # Verify chained loading
            assert len(loaded_author.books) == 1
            loaded_book = loaded_author.books[0]
            assert len(loaded_book.reviews) == 2

    def test_selectinload_multiple_relationships(self, engine: Engine):
        """Test selectinload on multiple relationships simultaneously."""
        with Session(engine) as session:
            author = Author(name="ORM Multi Selectin Author", field="Astronomy")
            publisher = Publisher(name="ORM Multi Selectin Pub", country="Greece")

            book = Book(title="ORM Multi Selectin Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-MULTI-001",
                pages=250,
                abstract="Multi selectin test",
            )
            book.detail.value = detail

            categories = [
                Category(name=f"ORM Multi Cat {i}", description=f"Category {i}")
                for i in range(2)
            ]
            book.categories.extend(categories)

            session.add(book)
            session.flush()
            book.revalidate()

            session.expunge_all()

            # Load book with multiple selectinloads
            with patch.object(session, "execute", wraps=session.execute) as spy:
                stmt = (
                    select(Book)
                    .where(Book["id"] == book.id)
                    .options(
                        selectinload(Book["author"]),
                        selectinload(Book["publisher"]),
                        selectinload(Book["detail"]),
                        selectinload(Book["categories"]),
                    )
                )
                loaded_book = session.execute(stmt).scalars().one()

                # Main query + 4 selectin queries
                assert spy.call_count == 5

            # Verify all relationships are loaded
            assert loaded_book.author.value.name == "ORM Multi Selectin Author"
            assert loaded_book.publisher.value.name == "ORM Multi Selectin Pub"
            assert loaded_book.detail.value
            assert loaded_book.detail.value.isbn == "978-MULTI-001"
            assert len(loaded_book.categories) == 2

    def test_selectinload_with_backref_circular_validation(self, engine: Engine):
        """Test selectinload handles circular validation through backrefs.

        When loading Book.categories with selectinload, SQLAlchemy also
        loads Category.books (backref), creating a circular reference.
        The validation context should handle this without infinite recursion.
        """
        with Session(engine) as session:
            author = Author(name="ORM Circular Author", field="Physics")
            publisher = Publisher(name="ORM Circular Pub", country="USA")

            category = Category(
                name="ORM Circular Category", description="Circular test"
            )

            for i in range(3):
                book = Book(title=f"ORM Circular Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher
                book.categories.append(category)
                session.add(book)

            session.flush()

            book_ids = []
            for book in author.books:
                book.revalidate()
                book_ids.append(book.id)

            session.expunge_all()

            # Load one book with selectinload on categories
            stmt = (
                select(Book)
                .where(Book["id"] == book_ids[0])
                .options(selectinload(Book["categories"]))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Category should be loaded
            assert len(loaded_book.categories) == 1
            loaded_category = loaded_book.categories[0]

            # The backref (Category.books) should also work
            # This tests circular validation handling
            assert len(loaded_category.books) == 3

    def test_selectinload_preserves_transmuter_validation(self, engine: Engine):
        """Test that selectinload results go through Transmuter validation.

        Ensures that ORM objects loaded via selectinload are properly
        converted to Transmuter instances.
        """
        with Session(engine) as session:
            author = Author(name="ORM Validation Author", field="Biology")
            publisher = Publisher(name="ORM Validation Pub", country="USA")

            for i in range(2):
                book = Book(title=f"ORM Validation Book {i}", year=2024)
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.add(publisher)
            session.flush()
            author.revalidate()

            session.expunge_all()

            # Load with selectinload
            stmt = (
                select(Author)
                .where(Author["id"] == author.id)
                .options(selectinload(Author["books"]))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Verify loaded objects are Transmuter instances
            assert isinstance(loaded_author, Author)
            for book in loaded_author.books:
                assert isinstance(book, Book)
                # Verify the book has a provider set
                assert book.__transmuter_provided__ is not None
