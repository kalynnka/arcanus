"""Test model_dump and model_dump_json with selectinload relationships.

Tests:
- model_dump() correctly includes selectin-loaded relationships
- model_dump_json() correctly serializes selectin-loaded relationships
- 1-1, 1-M, M-M relationships are properly included
- Nested selectinload relationships are serialized
- Circular references are handled correctly
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from arcanus.materia.sqlalchemy import Session
from tests import models
from tests.transmuters import (
    Author,
    Book,
    BookDetail,
    Category,
    Publisher,
    Review,
    Translator,
)


class TestModelDumpWithSelectinload:
    """Test model_dump() with selectinload relationships."""

    def test_dump_with_selectinload_one_to_one(self, engine: Engine):
        """Test model_dump includes selectinload 1-1 relationship (Book -> BookDetail)."""
        with Session(engine) as session:
            author = Author(name="1-1 Dump Author", field="Physics")
            publisher = Publisher(name="1-1 Dump Publisher", country="USA")
            book = Book(title="1-1 Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-1111111111",
                pages=300,
                abstract="Test abstract for dump",
            )
            book.detail.value = detail

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for detail
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(selectinload(models.Book.detail))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model
            data = loaded_book.model_dump()

            # Verify book fields
            assert data["id"] == book_id
            assert data["title"] == "1-1 Dump Book"
            assert data["year"] == 2024

            # Verify detail is included
            assert data["detail"] is not None
            assert data["detail"]["isbn"] == "978-1111111111"
            assert data["detail"]["pages"] == 300
            assert data["detail"]["abstract"] == "Test abstract for dump"

    def test_dump_with_selectinload_many_to_one(self, engine: Engine):
        """Test model_dump includes selectinload M-1 relationship (Book -> Author)."""
        with Session(engine) as session:
            author = Author(name="M-1 Dump Author", field="Biology")
            publisher = Publisher(name="M-1 Dump Publisher", country="UK")
            book = Book(title="M-1 Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for author and publisher
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.publisher),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model
            data = loaded_book.model_dump()

            # Verify author is included
            assert data["author"] is not None
            assert data["author"]["name"] == "M-1 Dump Author"
            assert data["author"]["field"] == "Biology"

            # Verify publisher is included
            assert data["publisher"] is not None
            assert data["publisher"]["name"] == "M-1 Dump Publisher"
            assert data["publisher"]["country"] == "UK"

    def test_dump_with_selectinload_one_to_many(self, engine: Engine):
        """Test model_dump includes selectinload 1-M relationship (Author -> Books)."""
        with Session(engine) as session:
            author = Author(name="1-M Dump Author", field="Chemistry")
            publisher = Publisher(name="1-M Dump Publisher", country="USA")

            books = []
            for i in range(3):
                book = Book(title=f"1-M Dump Book {i}", year=2020 + i)
                book.author.value = author
                book.publisher.value = publisher
                books.append(book)

            session.add(author)
            session.flush()
            author.revalidate()

            author_id = author.id

            # Clear session to force reload
            session.expunge_all()

            # Load author with selectinload for books
            stmt = (
                select(Author)
                .where(Author["id"] == author_id)
                .options(selectinload(models.Author.books))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Dump the model, excluding author from books to avoid circular dump
            data = loaded_author.model_dump(
                exclude={"books": {"__all__": {"author", "publisher"}}}
            )

            # Verify author fields
            assert data["id"] == author_id
            assert data["name"] == "1-M Dump Author"
            assert data["field"] == "Chemistry"

            # Verify books are included
            assert len(data["books"]) == 3
            book_titles = {b["title"] for b in data["books"]}
            assert book_titles == {
                "1-M Dump Book 0",
                "1-M Dump Book 1",
                "1-M Dump Book 2",
            }

    def test_dump_with_selectinload_many_to_many(self, engine: Engine):
        """Test model_dump includes selectinload M-M relationship (Book -> Categories)."""
        with Session(engine) as session:
            author = Author(name="M-M Dump Author", field="Literature")
            publisher = Publisher(name="M-M Dump Publisher", country="USA")
            book = Book(title="M-M Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            categories = [
                Category(name="Fiction", description="Fiction books"),
                Category(name="Adventure", description="Adventure books"),
            ]
            book.categories.extend(categories)

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for categories
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(selectinload(models.Book.categories))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model
            data = loaded_book.model_dump(
                exclude={"categories": {"__all__": {"books"}}}
            )

            # Verify categories are included
            assert len(data["categories"]) == 2
            category_names = {c["name"] for c in data["categories"]}
            assert category_names == {"Fiction", "Adventure"}

    def test_dump_with_selectinload_optional_one_to_one_present(self, engine: Engine):
        """Test model_dump with optional 1-1 relationship present (Book -> Translator)."""
        with Session(engine) as session:
            author = Author(name="Optional 1-1 Dump Author", field="Physics")
            publisher = Publisher(name="Optional 1-1 Dump Publisher", country="USA")
            translator = Translator(name="John Translator", language="Spanish")

            book = Book(title="Translated Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher
            book.translator.value = translator

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for translator
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(selectinload(models.Book.translator))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model
            data = loaded_book.model_dump()

            # Verify translator is included
            assert data["translator"] is not None
            assert data["translator"]["name"] == "John Translator"
            assert data["translator"]["language"] == "Spanish"

    def test_dump_with_selectinload_optional_one_to_one_absent(self, engine: Engine):
        """Test model_dump with optional 1-1 relationship absent (Book without Translator)."""
        with Session(engine) as session:
            author = Author(name="No Translator Dump Author", field="Biology")
            publisher = Publisher(name="No Translator Dump Publisher", country="UK")

            book = Book(title="Original Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher
            # No translator set

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for translator
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(selectinload(models.Book.translator))
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model
            data = loaded_book.model_dump()

            # Verify translator is None
            assert data["translator"] is None

    def test_dump_with_nested_selectinload(self, engine: Engine):
        """Test model_dump with nested selectinload relationships."""
        with Session(engine) as session:
            author = Author(name="Nested Dump Author", field="Literature")
            publisher = Publisher(name="Nested Dump Publisher", country="USA")

            book = Book(title="Nested Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-2222222222",
                pages=250,
                abstract="Nested test abstract",
            )
            book.detail.value = detail

            reviews = [
                Review(reviewer_name="Reviewer 1", rating=5, comment="Excellent!"),
                Review(reviewer_name="Reviewer 2", rating=4, comment="Great read."),
            ]
            book.reviews.extend(reviews)

            session.add(book)
            session.flush()
            author.revalidate()

            author_id = author.id

            # Clear session to force reload
            session.expunge_all()

            # Load author with nested selectinload: author -> books -> detail, reviews
            stmt = (
                select(Author)
                .where(Author["id"] == author_id)
                .options(
                    selectinload(models.Author.books).selectinload(models.Book.detail),
                    selectinload(models.Author.books).selectinload(models.Book.reviews),
                )
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Dump the model, excluding circular references
            data = loaded_author.model_dump(
                exclude={
                    "books": {
                        "__all__": {
                            "author": True,
                            "detail": {"book"},
                            "reviews": {"__all__": {"book"}},
                        }
                    }
                }
            )

            # Verify nested structure
            assert len(data["books"]) == 1
            book_data = data["books"][0]
            assert book_data["title"] == "Nested Dump Book"

            # Verify detail is nested
            assert book_data["detail"] is not None
            assert book_data["detail"]["isbn"] == "978-2222222222"

            # Verify reviews are nested
            assert len(book_data["reviews"]) == 2
            reviewer_names = {r["reviewer_name"] for r in book_data["reviews"]}
            assert reviewer_names == {"Reviewer 1", "Reviewer 2"}

    def test_dump_with_multiple_selectinload(self, engine: Engine):
        """Test model_dump with multiple selectinload options at same level."""
        with Session(engine) as session:
            author = Author(name="Multi Select Author", field="History")
            publisher = Publisher(name="Multi Select Publisher", country="UK")

            book = Book(title="Multi Select Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            detail = BookDetail(
                isbn="978-3333333333",
                pages=400,
                abstract="Multi select abstract",
            )
            book.detail.value = detail

            categories = [
                Category(name="History", description="History books"),
                Category(name="Non-fiction", description="Non-fiction books"),
            ]
            book.categories.extend(categories)

            reviews = [
                Review(reviewer_name="Multi Reviewer", rating=5, comment="Amazing!"),
            ]
            book.reviews.extend(reviews)

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with multiple selectinload options
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.publisher),
                    selectinload(models.Book.detail),
                    selectinload(models.Book.categories),
                    selectinload(models.Book.reviews),
                    selectinload(models.Book.translator),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump the model, excluding circular references
            data = loaded_book.model_dump(
                exclude={
                    "author": {"books"},
                    "publisher": {"books"},
                    "detail": {"book"},
                    "categories": {"__all__": {"books"}},
                    "reviews": {"__all__": {"book"}},
                    "translator": {"book"},
                }
            )

            # Verify all relationships are included
            assert data["author"]["name"] == "Multi Select Author"
            assert data["publisher"]["name"] == "Multi Select Publisher"
            assert data["detail"]["isbn"] == "978-3333333333"
            assert len(data["categories"]) == 2
            assert len(data["reviews"]) == 1
            assert data["translator"] is None


class TestModelDumpJsonWithSelectinload:
    """Test model_dump_json() with selectinload relationships."""

    def test_dump_json_with_selectinload_basic(self, engine: Engine):
        """Test model_dump_json produces valid JSON with selectinload relationships."""
        with Session(engine) as session:
            author = Author(name="JSON Dump Author", field="Physics")
            publisher = Publisher(name="JSON Dump Publisher", country="USA")
            book = Book(title="JSON Dump Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload for author and publisher
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.publisher),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump to JSON
            json_str = loaded_book.model_dump_json()

            # Verify valid JSON
            assert isinstance(json_str, str)
            parsed = json.loads(json_str)

            # Verify structure
            assert parsed["title"] == "JSON Dump Book"
            assert parsed["author"]["name"] == "JSON Dump Author"
            assert parsed["publisher"]["name"] == "JSON Dump Publisher"

    def test_dump_json_with_selectinload_collections(self, engine: Engine):
        """Test model_dump_json with selectinload collection relationships."""
        with Session(engine) as session:
            author = Author(name="JSON Collection Author", field="Chemistry")
            publisher = Publisher(name="JSON Collection Publisher", country="UK")

            for i in range(2):
                book = Book(title=f"JSON Collection Book {i}", year=2020 + i)
                book.author.value = author
                book.publisher.value = publisher

            session.add(author)
            session.flush()
            author.revalidate()

            author_id = author.id

            # Clear session to force reload
            session.expunge_all()

            # Load author with selectinload for books
            stmt = (
                select(Author)
                .where(Author["id"] == author_id)
                .options(selectinload(models.Author.books))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Dump to JSON
            json_str = loaded_author.model_dump_json()

            # Verify valid JSON
            parsed = json.loads(json_str)

            # Verify structure
            assert parsed["name"] == "JSON Collection Author"
            assert len(parsed["books"]) == 2

    def test_dump_json_with_nested_selectinload(self, engine: Engine):
        """Test model_dump_json with nested selectinload relationships."""
        with Session(engine) as session:
            author = Author(name="JSON Nested Author", field="Literature")
            publisher = Publisher(name="JSON Nested Publisher", country="USA")

            book = Book(title="JSON Nested Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            categories = [
                Category(name="JSON Cat 1", description="Category 1"),
                Category(name="JSON Cat 2", description="Category 2"),
            ]
            book.categories.extend(categories)

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.categories),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump to JSON
            json_str = loaded_book.model_dump_json()

            # Verify valid JSON
            parsed = json.loads(json_str)

            # Verify nested structure
            assert parsed["author"]["name"] == "JSON Nested Author"
            assert len(parsed["categories"]) == 2
            category_names = {c["name"] for c in parsed["categories"]}
            assert category_names == {"JSON Cat 1", "JSON Cat 2"}

    def test_dump_json_with_selectinload_m2m_backref(self, engine: Engine):
        """Test model_dump_json with M-M relationship and backref.

        Tests that circular M-M relationships are handled correctly in JSON serialization.
        """
        with Session(engine) as session:
            author = Author(name="JSON M2M Author", field="Biology")
            publisher = Publisher(name="JSON M2M Publisher", country="USA")

            # Create category shared by multiple books
            shared_category = Category(
                name="Shared JSON Category", description="Shared"
            )

            book1 = Book(title="JSON M2M Book 1", year=2024)
            book1.author.value = author
            book1.publisher.value = publisher
            book1.categories.append(shared_category)

            book2 = Book(title="JSON M2M Book 2", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher
            book2.categories.append(shared_category)

            session.add_all([book1, book2])
            session.flush()
            book1.revalidate()

            book1_id = book1.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with nested selectinload for categories and their books
            stmt = (
                select(Book)
                .where(Book["id"] == book1_id)
                .options(
                    selectinload(models.Book.categories).selectinload(
                        models.Category.books
                    )
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump to JSON, excluding circular references
            # The nested books share the same category object, so we must exclude categories entirely
            json_str = loaded_book.model_dump_json(
                exclude={"categories": {"__all__": {"books"}}}
            )

            # Verify valid JSON (should not fail due to circular references)
            parsed = json.loads(json_str)

            # Verify structure
            assert parsed["title"] == "JSON M2M Book 1"
            assert len(parsed["categories"]) == 1
            assert parsed["categories"][0]["name"] == "Shared JSON Category"


class TestModelDumpWithExcludeInclude:
    """Test model_dump with exclude/include on selectinload relationships."""

    def test_dump_exclude_relationship(self, engine: Engine):
        """Test model_dump excluding selectinload relationship."""
        with Session(engine) as session:
            author = Author(name="Exclude Rel Author", field="Physics")
            publisher = Publisher(name="Exclude Rel Publisher", country="USA")
            book = Book(title="Exclude Rel Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.publisher),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump excluding author relationship
            data = loaded_book.model_dump(exclude={"author"})

            assert "author" not in data
            assert data["title"] == "Exclude Rel Book"
            assert data["publisher"]["name"] == "Exclude Rel Publisher"

    def test_dump_include_only_relationships(self, engine: Engine):
        """Test model_dump including only relationship fields."""
        with Session(engine) as session:
            author = Author(name="Include Only Author", field="Biology")
            publisher = Publisher(name="Include Only Publisher", country="UK")
            book = Book(title="Include Only Book", year=2024)
            book.author.value = author
            book.publisher.value = publisher

            session.add(book)
            session.flush()
            book.revalidate()

            book_id = book.id

            # Clear session to force reload
            session.expunge_all()

            # Load book with selectinload
            stmt = (
                select(Book)
                .where(Book["id"] == book_id)
                .options(
                    selectinload(models.Book.author),
                    selectinload(models.Book.publisher),
                )
            )
            loaded_book = session.execute(stmt).scalars().one()

            # Dump including only title and author
            data = loaded_book.model_dump(include={"title", "author"})

            assert len(data) == 2
            assert data["title"] == "Include Only Book"
            assert data["author"]["name"] == "Include Only Author"
            assert "publisher" not in data

    def test_dump_exclude_nested_relationship_fields(self, engine: Engine):
        """Test model_dump excluding specific fields from nested relationships."""
        with Session(engine) as session:
            author = Author(name="Nested Exclude Author", field="Chemistry")
            publisher = Publisher(name="Nested Exclude Publisher", country="USA")

            book1 = Book(title="Nested Exclude Book 1", year=2024)
            book1.author.value = author
            book1.publisher.value = publisher

            book2 = Book(title="Nested Exclude Book 2", year=2024)
            book2.author.value = author
            book2.publisher.value = publisher

            session.add(author)
            session.flush()
            author.revalidate()

            author_id = author.id

            # Clear session to force reload
            session.expunge_all()

            # Load author with selectinload for books
            stmt = (
                select(Author)
                .where(Author["id"] == author_id)
                .options(selectinload(models.Author.books))
            )
            loaded_author = session.execute(stmt).scalars().one()

            # Dump excluding certain fields from nested books
            data = loaded_author.model_dump(
                exclude={
                    "books": {"__all__": {"author", "publisher", "year"}},
                }
            )

            # Verify nested exclusion
            assert data["name"] == "Nested Exclude Author"
            assert len(data["books"]) == 2
            for book_data in data["books"]:
                assert "title" in book_data
                assert "author" not in book_data
                assert "publisher" not in book_data
                assert "year" not in book_data
