"""Test model_construct with SQLAlchemy materia.

This module tests:
- model_construct with SQLAlchemy ORM instances (provider data)
- model_construct with circular references
- model_construct validation context handling
- model_construct with transmuter_proxy relationships
- model_construct with materia hooks (before_construct/after_construct)
"""

from __future__ import annotations

from sqlalchemy import Engine

from arcanus.base import validation_context
from arcanus.materia.sqlalchemy import Session
from tests import models
from tests.transmuters import Author, Book


class TestModelConstructWithProvider:
    """Test model_construct with SQLAlchemy provider instances."""

    def test_construct_from_orm_instance(self, engine: Engine):
        """Test constructing from an ORM instance."""
        with Session(engine) as session, session.begin():
            # Create ORM instance
            orm_author = models.Author(name="Construct Author", field="Physics")
            session.add(orm_author)
            session.flush()

            # Construct transmuter from ORM instance
            author = Author.model_construct(data=orm_author)

            assert author.name == "Construct Author"
            assert author.field == "Physics"
            assert author.__transmuter_provided__ is orm_author
            assert orm_author.transmuter_proxy is author

    def test_construct_caches_in_context(self, engine: Engine):
        """Test that constructed instances are cached in validation context."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Cached Author", field="Biology")
            session.add(orm_author)
            session.flush()

            with validation_context() as ctx:
                # First construction
                author1 = Author.model_construct(data=orm_author)

                # Second construction of same ORM instance
                author2 = Author.model_construct(data=orm_author)

                # Should return the same cached instance
                assert author1 is author2
                assert ctx[orm_author] is author1

    def test_construct_respects_existing_proxy(self, engine: Engine):
        """Test that existing transmuter_proxy is respected."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Proxy Author", field="Chemistry")
            session.add(orm_author)
            session.flush()

            # First create through validation
            author1 = Author.model_validate(orm_author)

            # Now construct - should use existing proxy
            with validation_context():
                author2 = Author.model_construct(data=orm_author)

                # Should use the existing proxy
                assert author2 is author1

    def test_construct_transmuter_proxy(self, engine: Engine):
        """Test constructing when proxy is None."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="New Author", field="History")
            session.add(orm_author)
            session.flush()

            # Construct should create new instance
            author = Author.model_construct(data=orm_author)

            assert author.name == "New Author"
            assert orm_author.transmuter_proxy is author


class TestModelConstructCircularReferences:
    """Test model_construct with circular references."""

    def test_construct_with_bidirectional_relationship(self, engine: Engine):
        """Test constructing objects with bidirectional relationships."""
        with Session(engine) as session, session.begin():
            orm_publisher = models.Publisher(name="Test Publisher", country="USA")
            orm_author = models.Author(name="Circular Author", field="Physics")
            orm_book = models.Book(
                title="Circular Book",
                year=2024,
                author=orm_author,
                publisher=orm_publisher,
            )
            session.add_all([orm_publisher, orm_author, orm_book])
            session.flush()

            with validation_context() as ctx:
                # Construct author (which has books relationship)
                author = Author.model_construct(data=orm_author)

                # Construct book (which references the same author)
                book = Book.model_construct(data=orm_book)

                # Both should be in context
                assert ctx[orm_author] is author
                assert ctx[orm_book] is book

    def test_construct_prevents_infinite_recursion(self, engine: Engine):
        """Test that circular references don't cause infinite recursion."""
        with Session(engine) as session, session.begin():
            orm_publisher = models.Publisher(name="Test Publisher", country="USA")
            orm_author = models.Author(name="Recursive Author", field="Physics")
            orm_book1 = models.Book(
                title="Book 1",
                year=2024,
                author=orm_author,
                publisher=orm_publisher,
            )
            orm_book2 = models.Book(
                title="Book 2",
                year=2024,
                author=orm_author,
                publisher=orm_publisher,
            )
            session.add_all([orm_publisher, orm_author, orm_book1, orm_book2])
            session.flush()

            with validation_context():
                # This should not cause infinite recursion
                author = Author.model_construct(data=orm_author)

                assert author.name == "Recursive Author"
                # Association should be prepared
                assert hasattr(author, "books")


class TestModelConstructMateriaHooks:
    """Test materia hooks during model_construct."""

    def test_construct_calls_before_construct(self, engine: Engine):
        """Test that transmuter_before_construct is called."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Hook Author", field="Physics")
            session.add(orm_author)
            session.flush()

            # The before_construct hook should extract data from ORM
            author = Author.model_construct(data=orm_author)

            # Should have extracted the data properly
            assert author.name == "Hook Author"
            assert author.field == "Physics"
            assert author.id is not None

    def test_construct_calls_after_construct(self, engine: Engine):
        """Test that transmuter_after_construct is called."""
        with Session(engine) as session, session.begin():
            orm_book = models.Book(
                title="Hook Book",
                year=2024,
                author=models.Author(name="Author", field="Physics"),
                publisher=models.Publisher(name="Publisher", country="USA"),
            )
            session.add(orm_book)
            session.flush()

            # The after_construct hook should process the instance
            book = Book.model_construct(data=orm_book)

            assert book.title == "Hook Book"
            assert book.year == 2024


class TestModelConstructWithAssociations:
    """Test model_construct with association fields."""

    def test_construct_separates_association_fields(self, engine: Engine):
        """Test that association fields are properly separated."""
        with Session(engine) as session, session.begin():
            orm_publisher = models.Publisher(name="Test Publisher", country="USA")
            orm_author = models.Author(name="Associated Author", field="Physics")
            orm_book = models.Book(
                title="Associated Book",
                year=2024,
                author=orm_author,
                publisher=orm_publisher,
            )
            session.add_all([orm_publisher, orm_author, orm_book])
            session.flush()

            # Construct with associations
            book = Book.model_construct(data=orm_book)

            # Regular fields should be set
            assert book.title == "Associated Book"
            assert book.year == 2024

            # Association should be prepared
            assert hasattr(book, "author")

    def test_construct_prepares_associations(self, engine: Engine):
        """Test that associations are properly prepared after construction."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Prepared Author", field="Biology")
            session.add(orm_author)
            session.flush()

            author = Author.model_construct(data=orm_author)

            # Accessing association should work
            books = author.books
            assert books is not None


class TestModelConstructMixedUsage:
    """Test mixed usage of model_construct."""

    def test_construct_then_validate(self, engine: Engine):
        """Test constructing then validating."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Mixed Author", field="Chemistry")
            session.add(orm_author)
            session.flush()

            # Construct without validation
            author = Author.model_construct(data=orm_author)

            # Now validate
            author.revalidate()

            assert author.name == "Mixed Author"
            assert author.field == "Chemistry"

    def test_construct_with_kwargs_overrides(self, engine: Engine):
        """Test that kwargs can override provider data."""
        with Session(engine) as session, session.begin():
            orm_author = models.Author(name="Original", field="Physics")
            session.add(orm_author)
            session.flush()

            # Construct with overrides
            author = Author.model_construct(
                data=orm_author,
                name="Overridden",
            )

            # The override should take effect
            assert author.name == "Overridden"
            assert author.field == "Physics"

    def test_construct_with_provider(self, engine: Engine):
        """Test normal construction with provider data."""
        author = Author.model_construct(
            id=999,
            name="No Provider",
            field="Literature",
        )

        assert author.__transmuter_provided__
        assert isinstance(author.__transmuter_provided__, models.Author)
        assert author.id == author.__transmuter_provided__.id == 999
        assert author.name == author.__transmuter_provided__.name == "No Provider"
        assert author.field == author.__transmuter_provided__.field == "Literature"


class TestModelConstructEdgeCases:
    """Test edge cases for model_construct."""

    def test_construct_with_empty_data(self):
        """Test constructing with no data."""
        book = Book.model_construct()

        # Should create an instance with undefined fields
        assert isinstance(book, Book)

    def test_construct_with_none_data(self):
        """Test constructing with None as data."""
        book = Book.model_construct(data=None, title="Test", year=2024, author_id=1)

        assert book.title == "Test"
        assert book.year == 2024
