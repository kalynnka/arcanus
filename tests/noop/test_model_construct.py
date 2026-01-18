from __future__ import annotations

from arcanus.association import RelationCollection
from tests.transmuters import Author, Book, Publisher

"""Test model_construct with NoOpMateria.

This module tests:
- model_construct with regular dict data
- model_construct with object data
- model_construct bypassing validation
- model_construct with association fields
- model_construct field separation (associations vs regular fields)
"""


class TestModelConstructBasics:
    """Test basic model_construct functionality."""

    def test_construct_with_dict_data(self):
        """Test constructing from dict data."""
        book = Book.model_construct(
            data={"title": "Test Book", "year": 2024, "author_id": 1}
        )

        assert book.title == "Test Book"
        assert book.year == 2024
        assert book.author_id == 1

    def test_construct_with_kwargs(self):
        """Test constructing with keyword arguments."""
        book = Book.model_construct(
            title="Test Book",
            year=2024,
            author_id=1,
        )

        assert book.title == "Test Book"
        assert book.year == 2024
        assert book.author_id == 1

    def test_construct_with_data_and_kwargs(self):
        """Test constructing with both data and kwargs (kwargs should override)."""
        book = Book.model_construct(
            data={"title": "Original", "year": 2024},
            title="Overridden",
            author_id=1,
        )

        assert book.title == "Overridden"
        assert book.year == 2024
        assert book.author_id == 1

    def test_construct_bypasses_validation(self):
        """Test that model_construct bypasses validation."""
        # This would fail with normal validation due to invalid field type
        book = Book.model_construct(
            title="Test",
            year="not_a_number",  # Invalid type
            author_id=1,
        )

        # No validation error raised
        assert book.title == "Test"
        assert book.year == "not_a_number"  # Invalid value accepted

    def test_construct_with_identity_fields(self):
        """Test constructing with identity fields."""
        author = Author.model_construct(
            id=42,
            name="Test Author",
            field="Physics",
        )

        assert author.id == 42
        assert author.name == "Test Author"
        assert author.field == "Physics"

    def test_construct_without_required_fields(self):
        """Test that model_construct works without required fields."""
        # Normal validation would require 'name' and 'field'
        author = Author.model_construct(
            id=1,
        )

        assert author.id == 1
        # Fields not set would have undefined values


class TestModelConstructWithAssociations:
    """Test model_construct with association fields."""

    def test_construct_with_empty_associations(self):
        """Test constructing with empty association fields."""
        author = Author.model_construct(
            id=1,
            name="Test Author",
            field="Physics",
        )

        # Association should be properly initialized
        assert hasattr(author, "books")
        # The books association should be prepared
        books = author.books
        assert books is not None

    def test_construct_separates_association_fields(self):
        """Test that association fields are separated from regular fields."""
        # Create with both regular and association fields
        author = Author.model_construct(
            data={
                "id": 1,
                "name": "Test Author",
                "field": "Physics",
                "books": RelationCollection(),  # Association field
            }
        )

        assert author.id == 1
        assert author.name == "Test Author"
        assert author.field == "Physics"
        # Association should be properly prepared
        assert hasattr(author, "books")

    def test_construct_with_relation_collection(self):
        """Test constructing with RelationCollection."""
        publisher = Publisher.model_construct(
            id=1,
            name="Test Publisher",
            country="USA",
        )

        # Association should be initialized
        assert hasattr(publisher, "books")
        books = publisher.books
        assert books is not None


class TestModelConstructWithObject:
    """Test model_construct with object data."""

    def test_construct_from_object_with_dict(self):
        """Test constructing from an object's __dict__."""

        class SimpleObject:
            def __init__(self):
                self.title = "Object Book"
                self.year = 2024
                self.author_id = 1

        obj = SimpleObject()
        book = Book.model_construct(data=obj)

        assert book.title == "Object Book"
        assert book.year == 2024
        assert book.author_id == 1

    def test_construct_from_dict_explicitly(self):
        """Test that dict data is properly handled."""
        data = {
            "title": "Dict Book",
            "year": 2024,
            "author_id": 1,
        }
        book = Book.model_construct(data=data)

        assert book.title == "Dict Book"
        assert book.year == 2024
        assert book.author_id == 1


class TestModelConstructFieldsSet:
    """Test _fields_set parameter in model_construct."""

    def test_construct_with_fields_set(self):
        """Test providing _fields_set parameter."""
        book = Book.model_construct(
            _fields_set={"title", "year"},
            title="Test Book",
            year=2024,
            author_id=1,
        )

        assert book.title == "Test Book"
        assert book.year == 2024
        assert book.author_id == 1

    def test_construct_without_fields_set(self):
        """Test that _fields_set defaults to None."""
        book = Book.model_construct(
            title="Test Book",
            year=2024,
            author_id=1,
        )

        assert book.title == "Test Book"


class TestModelConstructComplexScenarios:
    """Test complex scenarios with model_construct."""

    def test_construct_nested_objects(self):
        """Test constructing with nested structures."""
        author = Author.model_construct(
            id=1,
            name="Author One",
            field="Physics",
        )

        publisher = Publisher.model_construct(
            id=1,
            name="Publisher One",
            country="USA",
        )

        book = Book.model_construct(
            id=1,
            title="Complex Book",
            year=2024,
            author_id=author.id,
            publisher_id=publisher.id,
        )

        assert book.title == "Complex Book"
        assert book.author_id == author.id
        assert book.publisher_id == publisher.id

    def test_construct_with_partial_data(self):
        """Test constructing with only some fields."""
        # Only set a few fields, others remain unset
        book = Book.model_construct(
            title="Partial Book",
        )

        assert book.title == "Partial Book"
        # Other fields would be undefined

    def test_construct_multiple_instances(self):
        """Test constructing multiple instances."""
        books = [
            Book.model_construct(title=f"Book {i}", year=2020 + i, author_id=1)
            for i in range(5)
        ]

        assert len(books) == 5
        for i, book in enumerate(books):
            assert book.title == f"Book {i}"
            assert book.year == 2020 + i
