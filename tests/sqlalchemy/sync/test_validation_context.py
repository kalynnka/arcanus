"""Test validation context management.

Tests:
- Validation context is created within Session
- Same ORM object always validates to same transmuter instance (within session)
- Validation context is session-scoped
- Different sessions create different transmuter instances for same ORM
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, select

from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Author, Book, Publisher


class TestValidationContext:
    """Test validation context behavior."""

    def test_same_orm_same_transmuter_within_session(self, engine: Engine):
        """Test that the same ORM object validates to the same transmuter instance within a session."""
        with Session(engine) as session:
            # Create and persist author
            author = Author(name="Context Author", field="Physics")
            session.add(author)
            session.flush()
            author.revalidate()

            # Get the same author via different queries
            fetch1 = session.get_one(Author, author.id)
            stmt = select(Author).where(Author["id"] == author.id)
            fetch2 = session.execute(stmt).scalars().one()

            # Should be the EXACT same Python object (identity)
            assert author is fetch1 is fetch2
            assert id(author) == id(fetch1) == id(fetch2)

    def test_same_orm_different_sessions_different_transmuters(
        self, engine: Engine, test_id: UUID
    ):
        """Test that the same ORM object in different sessions creates different transmuter instances."""
        author = None

        # Session 1
        with Session(engine) as session1:
            author = Author(
                name="Multi Session Author",
                field="Biology",
                test_id=test_id,
            )
            session1.add(author)
            session1.flush()
            author.revalidate()
            obj1 = session1.get_one(Author, author.id)
            obj1_id = id(obj1)
            session1.commit()

        # Session 2
        with Session(engine) as session2:
            obj2 = session2.get_one(Author, author.id)
            obj2_id = id(obj2)

            # Different Python objects
            assert obj1_id != obj2_id

            # But same data
            assert obj2.name == "Multi Session Author"

    def test_validation_context_relationship_consistency(self, engine: Engine):
        """Test that related objects maintain consistency through validation context."""
        with Session(engine) as session:
            # Create related objects
            author = Author(name="Related Author", field="Chemistry")
            publisher = Publisher(name="Related Pub", country="USA")
            book = Book(title="Related Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            # Fetch book
            fetched_book = session.get_one(Book, book.id)

            # Fetched book should be same instance
            assert fetched_book is book

            # Related objects should also be same instances
            assert fetched_book.author.value is author
            assert fetched_book.publisher.value is publisher

    def test_nested_validation_creates_consistent_graph(self, engine: Engine):
        """Test that validating nested structures maintains object identity."""
        with Session(engine) as session:
            # Create object graph
            author = Author(name="Graph Author", field="Literature")
            publisher = Publisher(name="Graph Pub", country="UK")

            book1 = Book(title="Graph Book 1", year=2023)
            book1.author.value = author
            book1.publisher.value = publisher

            book2 = Book(title="Graph Book 2", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher

            author.books.extend([book1, book2])

            session.add(author)
            session.flush()

            # Both books should reference the SAME author instance
            assert book1.author.value is book2.author.value
            assert book1.author.value is author

    def test_context_isolation_between_sessions(self, engine: Engine, test_id: UUID):
        """Test that validation contexts don't leak between sessions."""
        author = None

        # Create in session 1
        with Session(engine) as session1:
            author = Author(
                name="Isolated Author",
                field="Physics",
                test_id=test_id,
            )
            session1.add(author)
            session1.flush()
            author.revalidate()

            author1 = session1.get_one(Author, author.id)
            author1.name = "Modified in Session 1"
            session1.flush()
            session1.commit()

        # Load in session 2 - should see the committed changes
        with Session(engine) as session2:
            author2 = session2.get_one(Author, author.id)

            # Should see the name as it was committed
            assert author2.name == "Modified in Session 1"

    def test_transmuter_orm_bidirectional_sync(self, engine: Engine):
        """Test that transmuter and ORM stay synchronized."""
        with Session(engine) as session:
            author = Author(name="Sync Test", field="Biology")
            session.add(author)
            session.flush()

            # Modify through transmuter
            author.name = "Updated via Transmuter"
            session.flush()

            # ORM should reflect change
            assert author.__transmuter_provided__.name == "Updated via Transmuter"  # type: ignore

            # Modify ORM directly
            author.__transmuter_provided__.name = "Updated via ORM"  # type: ignore

            # Transmuter need revalidate to reflect change
            author.revalidate()
            assert author.name == "Updated via ORM"

    def test_expunge_breaks_context_association(self, engine: Engine):
        """Test that expunging breaks the session context association."""
        with Session(engine) as session:
            author = Author(name="Expunge Test", field="Chemistry")
            session.add(author)
            session.flush()
            author.revalidate()

            # Expunge
            session.expunge(author)

            # Fetching again should give a different instance
            author2 = session.get_one(Author, author.id)

            assert author is not author2

    def test_refresh_maintains_identity(self, engine: Engine):
        """Test that refreshing maintains object identity."""
        with Session(engine) as session:
            author = Author(name="Refresh Test", field="Literature")
            session.add(author)
            session.flush()

            obj_before = author

            # Refresh
            session.refresh(author)

            obj_after = author

            # Should be same object
            assert obj_before is obj_after


class TestSessionScopedValidation:
    """Test that validation behavior is scoped to the session."""

    def test_adding_to_session_enables_persistence(self, engine: Engine):
        """Test that adding transmuter to session enables persistence."""
        with Session(engine) as session:
            # Create transmuter outside session
            author = Author(name="Add Test", field="Physics")

            # Has ORM object but not in session yet
            assert author.__transmuter_provided__ is not None

            # Add to session
            session.add(author)
            session.flush()
            author.revalidate()  # Sync ID from ORM to transmuter

            # Now has ID
            assert author.id is not None

    def test_detached_transmuter_reattachment(self, engine: Engine, test_id: UUID):
        """Test reattaching a detached transmuter to a new session."""
        author = None

        # Create in session 1
        with Session(engine) as session1:
            author = Author(
                name="Detach Test",
                field="Biology",
                test_id=test_id,
            )
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()

        # author is now detached (session closed)

        # Reattach to session 2
        with Session(engine) as session2:
            # Get fresh instance
            author2 = session2.get_one(Author, author.id)

            # Modify
            author2.name = "Modified in Session 2"
            session2.flush()

            # Verify
            assert author2.name == "Modified in Session 2"

    def test_merge_brings_detached_into_session(self, engine: Engine, test_id: UUID):
        """Test using merge to bring detached objects into session."""
        author = None

        # Create in session 1
        with Session(engine) as session1:
            author = Author(
                name="Merge Test",
                field="Chemistry",
                test_id=test_id,
            )
            session1.add(author)
            session1.flush()
            author.revalidate()
            session1.commit()

        # Author is detached now

        # Use merge in session 2
        with Session(engine) as session2:
            # Load the author fresh
            author_fresh = session2.get_one(Author, author.id)
            author_fresh.name = "Merged and Modified"
            session2.flush()

            # Verify
            assert author_fresh.name == "Merged and Modified"

    def test_validation_with_complex_object_graph(self, engine: Engine):
        """Test validation context with complex object graphs."""
        with Session(engine) as session:
            # Create complex graph
            author1 = Author(name="Complex Author 1", field="Physics")
            author2 = Author(name="Complex Author 2", field="Biology")
            publisher = Publisher(name="Complex Pub", country="USA")

            book1 = Book(title="Complex Book 1", year=2023)
            book1.author.value = author1
            book1.publisher.value = publisher

            book2 = Book(title="Complex Book 2", year=2024)
            book2.author.value = author2
            book2.publisher.value = publisher

            session.add_all([book1, book2])
            session.flush()

            # Revalidate to sync IDs from ORM to transmuters
            book1.revalidate()
            book2.revalidate()

            # All objects should be in the same session
            # Verify by fetching and checking identity
            book1_id = book1.id
            book2_id = book2.id

            fetched1 = session.get_one(Book, book1_id)
            fetched2 = session.get_one(Book, book2_id)

            assert fetched1 is book1
            assert fetched2 is book2

            # Publisher should be same instance
            assert fetched1.publisher.value is fetched2.publisher.value

    @pytest.mark.skip(
        reason="Currently, transumter lack a way to be automatically synced when provided materia's state changes, in this case they are rollbacked."
    )
    def test_session_rollback_reverts_validation_state(
        self, engine: Engine, test_id: UUID
    ):
        """Test that rolling back session reverts validation state."""
        author_id = None

        # First, create and commit the author so we have a persistent record
        with Session(engine) as session:
            author = Author(
                name="Rollback Test",
                field="Literature",
                test_id=test_id,
            )
            session.add(author)
            session.flush()
            author.revalidate()
            author_id = author.id
            session.commit()

        # Now test rollback behavior in a new session
        with Session(engine) as session:
            author = session.get_one(Author, author_id)
            original_name = author.name

            # Modify
            author.name = "Modified Name"
            session.flush()

            # Rollback
            session.rollback()

            # After rollback, the object is expired. Refresh to reload from DB.
            author = session.get_one(Author, author_id)

            # Should be back to original
            assert author.name == original_name
