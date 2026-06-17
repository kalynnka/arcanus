"""Test automatic sync-back of server-assigned values after a flush.

The SQLAlchemy materia registers an ``after_flush`` listener that re-validates
each flushed transmuter against its ORM row, so server-assigned column values
(e.g. an autoincrement ``id``) flow back without a manual ``revalidate()``.
Associations are re-deferred by the re-validation but reload without a query
because the backing row stays loaded.
"""

from __future__ import annotations

from sqlalchemy import Engine

from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Author, Book, Publisher


class TestFlushSyncsServerValues:
    def test_flush_syncs_server_generated_id(self, engine: Engine):
        """After a flush the autoincrement id lands on the transmuter directly."""
        with Session(engine) as session:
            author = Author(name="Sync Asimov", field="Science Fiction")
            assert author.id is None
            session.add(author)
            session.flush()
            # No revalidate() — the id is synced by the after_flush listener.
            assert author.id is not None

    def test_commit_syncs_id_without_manual_revalidate(self, engine: Engine):
        """commit() flushes first, so the id is synced before the session closes."""
        with Session(engine) as session:
            author = Author(name="Sync Clarke", field="Science Fiction")
            session.add(author)
            session.commit()
            assert author.id is not None

    def test_flush_syncs_every_new_record(self, engine: Engine):
        """All rows flushed in one batch get their ids synced."""
        with Session(engine) as session:
            authors = [
                Author(name=f"Sync Batch {i}", field="Literature") for i in range(5)
            ]
            session.add_all(authors)
            session.flush()
            ids = [author.id for author in authors]
            assert all(i is not None for i in ids)
            assert len(set(ids)) == len(ids)

    def test_synced_id_is_marked_set(self, engine: Engine):
        """The synced id counts as explicitly set for model_dump(exclude_unset)."""
        with Session(engine) as session:
            author = Author(name="Sync LeGuin", field="Science Fiction")
            session.add(author)
            session.flush()
            dumped = author.model_dump(exclude_unset=True)
            assert dumped["id"] == author.id

    def test_flush_keeps_loaded_relationship_query_free(self, engine: Engine):
        """A re-flush re-syncs scalars and leaves the ORM row's relationship
        loaded, so re-reading it afterwards needs no query.

        The after-flush revalidate re-defers the association on the schema side,
        but the backing row stays loaded — re-access reads it without hitting
        the database.
        """
        with Session(engine) as session:
            author = Author(name="Sync Herbert", field="Science Fiction")
            publisher = Publisher(name="Sync Ace", country="US")
            session.add_all([author, publisher])
            session.flush()
            session.add(
                Book(
                    title="Sync Dune",
                    year=1965,
                    author_id=author.id,
                    publisher_id=publisher.id,
                )
            )
            session.flush()

            assert [book.title for book in author.books] == ["Sync Dune"]

            # Re-flush the author via a scalar mutation.
            author.name = "Sync Frank Herbert"
            session.flush()

            assert author.name == "Sync Frank Herbert"  # scalar synced
            # Row's relationship is still loaded (lives in the instance dict),
            # so re-reading fires no query.
            provided = author.__transmuter_provided__
            assert provided is not None
            assert "books" in provided.__dict__
            assert [book.title for book in author.books] == ["Sync Dune"]
