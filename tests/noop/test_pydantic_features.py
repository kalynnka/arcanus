"""Test basic Pydantic features and transmuter fundamentals with NoOpMateria.

This module tests:
- Basic model instantiation and attribute access
- Pydantic validation behavior
- Serialization (dict, JSON)
- Model copying and updating
- Field defaults and frozen fields
- Transmuter-specific attributes (__transmuter_provided__)
- Nested type compatibility (BaseModel, TypedDict, dataclass)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Generic, NotRequired, TypeVar

import pytest
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing_extensions import TypedDict

from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
from arcanus.base import BaseTransmuter, Identity
from tests.transmuters import Author, Book, Publisher, Review

T = TypeVar("T")


# Regular Pydantic BaseModel for testing nested compatibility
class Address(BaseModel):
    """A regular Pydantic model to test nesting in Transmuters."""

    street: str
    city: str
    country: str
    zip_code: str | None = None


class Contact(BaseModel):
    """Another regular Pydantic model."""

    email: str
    phone: str | None = None
    address: Address | None = None


# TypedDict for testing nested compatibility
class AddressDict(TypedDict):
    """A TypedDict to test nesting in Transmuters."""

    street: str
    city: str
    country: str
    zip_code: NotRequired[str | None]


class ContactDict(TypedDict):
    """Another TypedDict for testing."""

    email: str
    phone: NotRequired[str | None]
    address: NotRequired[AddressDict | None]


# Dataclass for testing nested compatibility
@dataclass
class AddressData:
    """A dataclass to test nesting in Transmuters."""

    street: str
    city: str
    country: str
    zip_code: str | None = None


@dataclass
class ContactData:
    """Another dataclass for testing."""

    email: str
    phone: str | None = None
    address: AddressData | None = None


class TestBasicModelBehavior:
    """Test that transmuters work as normal Pydantic models."""

    def test_model_instantiation(self):
        """Test basic model creation with valid data."""
        author = Author(name="J.K. Rowling", field="Literature")

        assert author.name == "J.K. Rowling"
        assert author.field == "Literature"
        assert author.id is None

    def test_model_with_all_fields(self):
        """Test model creation with all fields including optional ones."""
        book = Book(
            id=1,
            title="Harry Potter",
            year=1997,
            author_id=1,
            publisher_id=2,
        )

        assert book.id == 1
        assert book.title == "Harry Potter"
        assert book.year == 1997
        assert book.author_id == 1
        assert book.publisher_id == 2

    def test_attribute_access_and_mutation(self):
        """Test getting and setting attributes."""
        author = Author(name="J.K. Rowling", field="Literature")

        # Read attribute
        assert author.name == "J.K. Rowling"

        # Update attribute
        author.name = "Joanne Rowling"
        assert author.name == "Joanne Rowling"

        # Update another attribute
        author.field = "History"
        assert author.field == "History"

    def test_transmuter_provided_is_none_with_noop(self):
        """Test that __transmuter_provided__ is None when using NoOpMateria."""
        author = Author(name="Isaac Asimov", field="Chemistry")
        assert author.__transmuter_provided__ is None

        book = Book(id=1, title="Foundation", year=1951)
        assert book.__transmuter_provided__ is None


class TestPydanticValidation:
    """Test Pydantic validation features."""

    def test_field_validation(self):
        """Test that field validation works correctly."""
        # Valid field value
        author = Author(name="George Orwell", field="Literature")
        assert author.field == "Literature"

        # Invalid field value should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Author(name="Test Author", field="InvalidField")  # pyright: ignore[reportArgumentType]

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "field" in errors[0]["loc"]
        assert "literal_error" in errors[0]["type"]

    def test_required_fields(self):
        """Test that required fields must be provided."""
        # Missing required field 'name'
        with pytest.raises(ValidationError) as exc_info:
            Author(field="Physics")  # pyright: ignore[reportCallIssue]

        errors = exc_info.value.errors()
        assert any("name" in str(error["loc"]) for error in errors)

        # Missing required field 'title'
        with pytest.raises(ValidationError) as exc_info:
            Book(year=2000)  # pyright: ignore[reportCallIssue]

        errors = exc_info.value.errors()
        assert any("title" in str(error["loc"]) for error in errors)

    def test_type_validation(self):
        """Test that field types are validated."""
        # Invalid type for year (should be int)
        with pytest.raises(ValidationError) as exc_info:
            Book(title="Test Book", year="not a number")  # pyright: ignore[reportArgumentType]

        errors = exc_info.value.errors()
        assert any("year" in str(error["loc"]) for error in errors)

    def test_frozen_field_identity(self):
        """Test that Identity-marked fields are frozen after creation."""
        author = Author(id=1, name="Arthur C. Clarke", field="Physics")

        # ID is frozen, cannot be changed
        with pytest.raises(ValidationError):
            author.id = 2

        # Other fields can be changed
        author.name = "Sir Arthur C. Clarke"
        assert author.name == "Sir Arthur C. Clarke"

    def test_model_validate_with_nested_dict(self):
        """Test creating models from nested dictionaries (standard Pydantic feature)."""
        # Create author with nested books from dict
        author_data = {
            "id": 1,
            "name": "J.R.R. Tolkien",
            "field": "Literature",
            "books": [
                {"id": 100, "title": "The Hobbit", "year": 1937},
                {"id": 101, "title": "The Fellowship of the Ring", "year": 1954},
            ],
        }

        author = Author.model_validate(author_data)

        # Verify author fields
        assert author.id == 1
        assert author.name == "J.R.R. Tolkien"
        assert author.field == "Literature"

        # Verify nested books were created
        assert len(author.books) == 2
        assert isinstance(author.books[0], Book)
        assert author.books[0].title == "The Hobbit"
        assert author.books[0].year == 1937
        assert isinstance(author.books[1], Book)
        assert author.books[1].title == "The Fellowship of the Ring"
        assert author.books[1].year == 1954

    def test_nested_model_validation(self):
        """Test that nested models are validated correctly."""
        # Valid nested data
        book_data = {
            "id": 1,
            "title": "1984",
            "year": 1949,
            "author": {
                "id": 10,
                "name": "George Orwell",
                "field": "Literature",
            },
        }

        book = Book.model_validate(book_data)
        assert book.title == "1984"
        assert book.author.value is not None
        assert book.author.value.name == "George Orwell"

        # Invalid nested data - should raise ValidationError
        invalid_book_data = {
            "id": 1,
            "title": "Test",
            "year": 2000,
            "author": {
                "name": "Test Author",
                "field": "InvalidField",  # Invalid literal value
            },
        }

        with pytest.raises(ValidationError) as exc_info:
            Book.model_validate(invalid_book_data)

        errors = exc_info.value.errors()
        # Should have error in nested author field
        assert any("author" in str(error["loc"]) for error in errors)

    def test_model_validate_json_basic(self):
        """Test model_validate_json() creates model from JSON string."""

        json_str = json.dumps({"id": 1, "name": "Isaac Asimov", "field": "Chemistry"})
        author = Author.model_validate_json(json_str)

        assert author.id == 1
        assert author.name == "Isaac Asimov"
        assert author.field == "Chemistry"

    def test_model_validate_json_with_nested_collection(self):
        """Test model_validate_json with nested RelationCollection data."""

        json_str = json.dumps(
            {
                "id": 1,
                "name": "J.R.R. Tolkien",
                "field": "Literature",
                "books": [
                    {"id": 100, "title": "The Hobbit", "year": 1937},
                    {"id": 101, "title": "The Fellowship of the Ring", "year": 1954},
                ],
            }
        )

        author = Author.model_validate_json(json_str)

        assert author.id == 1
        assert author.name == "J.R.R. Tolkien"
        assert len(author.books) == 2
        assert isinstance(author.books[0], Book)
        assert author.books[0].title == "The Hobbit"
        assert author.books[1].title == "The Fellowship of the Ring"

    def test_model_validate_json_with_nested_relation(self):
        """Test model_validate_json with nested Relation data."""

        json_str = json.dumps(
            {
                "id": 1,
                "title": "1984",
                "year": 1949,
                "author": {"id": 10, "name": "George Orwell", "field": "Literature"},
                "publisher": {"id": 20, "name": "Secker & Warburg", "country": "UK"},
            }
        )

        book = Book.model_validate_json(json_str)

        assert book.id == 1
        assert book.title == "1984"
        assert book.year == 1949
        assert book.author.value is not None
        assert book.author.value.id == 10
        assert book.author.value.name == "George Orwell"
        assert book.publisher.value is not None
        assert book.publisher.value.name == "Secker & Warburg"

    def test_model_validate_json_with_deeply_nested(self):
        """Test model_validate_json with deeply nested relationships."""

        json_str = json.dumps(
            {
                "id": 1,
                "name": "Douglas Adams",
                "field": "Literature",
                "books": [
                    {
                        "id": 10,
                        "title": "The Hitchhiker's Guide",
                        "year": 1979,
                        "reviews": [
                            {
                                "id": 100,
                                "reviewer_name": "Reviewer1",
                                "rating": 5,
                                "comment": "Excellent!",
                            },
                            {
                                "id": 101,
                                "reviewer_name": "Reviewer2",
                                "rating": 4,
                                "comment": "Great read!",
                            },
                        ],
                    }
                ],
            }
        )

        author = Author.model_validate_json(json_str)

        assert author.name == "Douglas Adams"
        assert len(author.books) == 1
        assert author.books[0].title == "The Hitchhiker's Guide"
        assert len(author.books[0].reviews) == 2
        assert author.books[0].reviews[0].reviewer_name == "Reviewer1"
        assert author.books[0].reviews[0].rating == 5
        assert author.books[0].reviews[1].reviewer_name == "Reviewer2"

    def test_model_validate_json_invalid_nested(self):
        """Test model_validate_json raises ValidationError for invalid nested data."""

        json_str = json.dumps(
            {
                "id": 1,
                "title": "Test Book",
                "year": 2000,
                "author": {
                    "name": "Test Author",
                    "field": "InvalidField",  # Invalid literal value
                },
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            Book.model_validate_json(json_str)

        errors = exc_info.value.errors()
        assert any("author" in str(error["loc"]) for error in errors)

    def test_model_validate_json_with_null_relations(self):
        """Test model_validate_json handles null/None relations correctly."""

        json_str = json.dumps(
            {
                "id": 1,
                "title": "Orphan Book",
                "year": 2000,
                "author": None,
                "publisher": None,
            }
        )

        book = Book.model_validate_json(json_str)

        assert book.id == 1
        assert book.title == "Orphan Book"
        assert book.author.value is None
        assert book.publisher.value is None

    def test_model_validate_json_partial_nested(self):
        """Test model_validate_json with partial nested data (missing optional fields)."""

        json_str = json.dumps(
            {
                "id": 1,
                "title": "Minimal Book",
                "year": 2020,
                "author": {"name": "Minimal Author", "field": "Literature"},
            }
        )

        book = Book.model_validate_json(json_str)

        assert book.title == "Minimal Book"
        assert book.author.value is not None
        assert book.author.value.name == "Minimal Author"
        assert book.author.value.id is None  # Optional field not provided


class TestSerialization:
    """Test model serialization features."""

    def test_model_dump(self):
        """Test model_dump() returns correct dictionary."""
        author = Author(id=1, name="Isaac Asimov", field="Chemistry")
        data = author.model_dump()

        assert data == {
            "id": 1,
            "name": "Isaac Asimov",
            "field": "Chemistry",
            "books": [],
        }

    def test_model_dump_all_fields(self):
        """Test serialization with all fields including foreign keys."""
        book = Book(
            id=1,
            title="Foundation",
            year=1951,
            author_id=10,
            publisher_id=20,
        )
        data = book.model_dump()

        assert data["id"] == 1
        assert data["title"] == "Foundation"
        assert data["year"] == 1951
        assert data["author_id"] == 10
        assert data["publisher_id"] == 20

    def test_model_dump_with_nested_associations(self):
        """Test serialization with nested models including associations."""
        # Create author with nested books
        author = Author(id=1, name="Isaac Asimov", field="Chemistry")
        book1 = Book(id=10, title="Foundation", year=1951)
        book2 = Book(id=11, title="I, Robot", year=1950)
        author.books.extend([book1, book2])

        data = author.model_dump()

        # Check author fields
        assert data["id"] == 1
        assert data["name"] == "Isaac Asimov"
        assert data["field"] == "Chemistry"

        # Check nested books are serialized
        assert len(data["books"]) == 2
        assert data["books"][0]["title"] == "Foundation"
        assert data["books"][0]["year"] == 1951
        assert data["books"][1]["title"] == "I, Robot"
        assert data["books"][1]["year"] == 1950

    def test_model_dump_with_relation_value(self):
        """Test serialization with Relation field containing a value."""
        author = Author(id=1, name="George Orwell", field="Literature")
        publisher = Publisher(id=2, name="Secker & Warburg", country="United Kingdom")

        book = Book(id=10, title="1984", year=1949)
        book.author.value = author
        book.publisher.value = publisher

        data = book.model_dump()

        # Check book fields
        assert data["id"] == 10
        assert data["title"] == "1984"
        assert data["year"] == 1949

        # Check nested author is serialized
        assert data["author"]["id"] == 1
        assert data["author"]["name"] == "George Orwell"
        assert data["author"]["field"] == "Literature"

        # Check nested publisher is serialized
        assert data["publisher"]["id"] == 2
        assert data["publisher"]["name"] == "Secker & Warburg"
        assert data["publisher"]["country"] == "United Kingdom"

    def test_model_dump_json(self):
        """Test model_dump_json() returns valid JSON string."""
        author = Author(id=1, name="Frank Herbert", field="Literature")
        json_str = author.model_dump_json()

        assert isinstance(json_str, str)
        assert (
            '"name":"Frank Herbert"' in json_str
            or '"name": "Frank Herbert"' in json_str
        )

    def test_model_dump_exclude(self):
        """Test model_dump with exclude parameter."""
        author = Author(id=1, name="Ursula K. Le Guin", field="Literature")
        data = author.model_dump(exclude={"id"})

        assert "id" not in data
        assert data["name"] == "Ursula K. Le Guin"
        assert data["field"] == "Literature"

    def test_model_dump_include(self):
        """Test model_dump with include parameter."""
        author = Author(id=1, name="Ray Bradbury", field="Literature")
        data = author.model_dump(include={"name", "field"})

        assert len(data) == 2
        assert data["name"] == "Ray Bradbury"
        assert data["field"] == "Literature"

    def test_model_dump_exclude_relationships(self):
        """Test model_dump excluding relationship fields."""
        # Create author with books
        author = Author(id=1, name="Terry Pratchett", field="Literature")
        book1 = Book(id=10, title="Guards! Guards!", year=1989)
        book2 = Book(id=11, title="Small Gods", year=1992)
        author.books.extend([book1, book2])

        # Exclude the books relationship
        data = author.model_dump(exclude={"books"})

        assert "books" not in data
        assert data["id"] == 1
        assert data["name"] == "Terry Pratchett"
        assert data["field"] == "Literature"

    def test_model_dump_include_relationships(self):
        """Test model_dump including only relationship fields."""
        # Create author with books
        author = Author(id=1, name="Neil Gaiman", field="Literature")
        book1 = Book(id=10, title="American Gods", year=2001)
        book2 = Book(id=11, title="Neverwhere", year=1996)
        author.books.extend([book1, book2])

        # Include only name and books
        data = author.model_dump(include={"name", "books"})

        assert len(data) == 2
        assert data["name"] == "Neil Gaiman"
        assert len(data["books"]) == 2
        assert data["books"][0]["title"] == "American Gods"
        assert data["books"][1]["title"] == "Neverwhere"
        # id and field should not be included
        assert "id" not in data
        assert "field" not in data

    def test_model_dump_exclude_nested_relationship_fields(self):
        # Create book with author relation
        author = Author(id=1, name="Douglas Adams", field="Literature")
        book = Book(id=42, title="The Hitchhiker's Guide to the Galaxy", year=1979)
        book.author.value = author
        book.reviews.extend(
            [
                Review(
                    id=1,
                    reviewer_name="Reviewer1",
                    rating=5,
                    comment="Excellent read!",
                ),
                Review(
                    id=2,
                    reviewer_name="Reviewer2",
                    rating=4,
                    comment="Enjoyed it.",
                ),
            ]
        )
        author.books.append(book)

        # Exclude specific fields from the nested author
        # Must also exclude author.books to break circular reference
        data = book.model_dump(
            exclude={
                "author": {"field", "books"},
                "reviews": {"__all__": {"id", "book"}},
            }
        )

        assert data["id"] == 42
        assert data["title"] == "The Hitchhiker's Guide to the Galaxy"
        assert data["author"]["id"] == 1
        assert data["author"]["name"] == "Douglas Adams"

        # These should be excluded from nested author
        assert "field" not in data["author"]
        assert "books" not in data["author"]

        # Verify reviews are serialized with id excluded
        assert len(data["reviews"]) == 2
        assert "id" not in data["reviews"][0]
        assert data["reviews"][0]["reviewer_name"] == "Reviewer1"
        assert data["reviews"][1]["reviewer_name"] == "Reviewer2"

    def test_model_dump_include_nested_relationship_fields(self):
        """Test model_dump with include on nested relationship data."""
        # Create book with author and publisher
        author = Author(id=1, name="Terry Pratchett", field="Literature")
        publisher = Publisher(id=2, name="Victor Gollancz", country="UK")
        book = Book(id=10, title="The Colour of Magic", year=1983)
        book.author.value = author
        book.publisher.value = publisher

        # Include only specific nested fields
        data = book.model_dump(include={"title": True, "author": {"name"}})

        assert data["title"] == "The Colour of Magic"
        assert data["author"]["name"] == "Terry Pratchett"
        # Only name should be in author
        assert len(data["author"]) == 1
        # Other fields should not be included
        assert "id" not in data
        assert "year" not in data
        assert "publisher" not in data

    def test_model_dump_exclude_all_relationships(self):
        """Test model_dump excluding all relationship fields from a model."""
        # Create book with relations
        author = Author(id=1, name="Test Author", field="Literature")
        publisher = Publisher(id=2, name="Test Publisher", country="USA")
        book = Book(
            id=10,
            title="Test Book",
            year=2000,
            author_id=1,
            publisher_id=2,
        )
        book.author.value = author
        book.publisher.value = publisher

        # Exclude all relationship fields
        data = book.model_dump(exclude={"author", "publisher"})

        # Only scalar fields should remain
        assert data["id"] == 10
        assert data["title"] == "Test Book"
        assert data["year"] == 2000
        assert data["author_id"] == 1
        assert data["publisher_id"] == 2
        assert "author" not in data
        assert "publisher" not in data

    def test_model_dump_json_basic(self):
        """Test model_dump_json() returns valid JSON string."""

        author = Author(id=1, name="Frank Herbert", field="Literature")
        json_str = author.model_dump_json()

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["id"] == 1
        assert data["name"] == "Frank Herbert"
        assert data["field"] == "Literature"

    def test_model_dump_json_exclude(self):
        """Test model_dump_json with exclude parameter."""

        author = Author(id=1, name="Ursula K. Le Guin", field="Literature")
        json_str = author.model_dump_json(exclude={"id", "books"})

        data = json.loads(json_str)
        assert "id" not in data
        assert "books" not in data
        assert data["name"] == "Ursula K. Le Guin"
        assert data["field"] == "Literature"

    def test_model_dump_json_include(self):
        """Test model_dump_json with include parameter."""

        author = Author(id=1, name="Ray Bradbury", field="Literature")
        json_str = author.model_dump_json(include={"name", "field"})

        data = json.loads(json_str)
        assert "id" not in data
        assert "books" not in data
        assert data["name"] == "Ray Bradbury"
        assert data["field"] == "Literature"

    def test_model_dump_json_exclude_relationships(self):
        """Test model_dump_json excluding relationship fields."""

        author = Author(id=1, name="Terry Pratchett", field="Literature")
        book1 = Book(id=10, title="Guards! Guards!", year=1989)
        book2 = Book(id=11, title="Small Gods", year=1992)
        author.books.extend([book1, book2])

        json_str = author.model_dump_json(exclude={"books"})

        data = json.loads(json_str)
        assert "books" not in data
        assert data["name"] == "Terry Pratchett"

    def test_model_dump_json_include_relationships(self):
        """Test model_dump_json including only specific fields with relationships."""

        author = Author(id=1, name="Neil Gaiman", field="Literature")
        book1 = Book(id=10, title="American Gods", year=2001)
        book2 = Book(id=11, title="Neverwhere", year=1996)
        author.books.extend([book1, book2])

        json_str = author.model_dump_json(include={"name", "books"})

        data = json.loads(json_str)
        assert data["name"] == "Neil Gaiman"
        assert len(data["books"]) == 2
        assert data["books"][0]["title"] == "American Gods"
        assert data["books"][1]["title"] == "Neverwhere"
        # Author's id and field should not be at the top level
        assert "id" not in data
        assert "field" not in data

    def test_model_dump_json_exclude_nested_relationship_fields(self):
        """Test model_dump_json with exclude on nested relationship data.

        Note: Circular references must be manually excluded to avoid
        PydanticSerializationError.
        """

        author = Author(id=1, name="Douglas Adams", field="Literature")
        book = Book(id=42, title="The Hitchhiker's Guide", year=1979)
        book.author.value = author
        book.reviews.extend(
            [
                Review(id=1, reviewer_name="Reviewer1", rating=5, comment="Great!"),
                Review(id=2, reviewer_name="Reviewer2", rating=4, comment="Good!"),
            ]
        )
        author.books.append(book)

        # Must exclude author.books to break circular reference
        json_str = book.model_dump_json(
            exclude={
                "author": {"field", "books"},
                "reviews": {"__all__": {"id", "book"}},
            }
        )

        data = json.loads(json_str)
        assert data["id"] == 42
        assert data["title"] == "The Hitchhiker's Guide"
        assert data["author"]["id"] == 1
        assert data["author"]["name"] == "Douglas Adams"
        assert "field" not in data["author"]
        assert "books" not in data["author"]
        assert len(data["reviews"]) == 2
        assert "id" not in data["reviews"][0]
        assert data["reviews"][0]["reviewer_name"] == "Reviewer1"
        assert data["reviews"][1]["reviewer_name"] == "Reviewer2"

    def test_model_dump_json_include_nested_relationship_fields(self):
        """Test model_dump_json with include on nested relationship data."""

        author = Author(id=1, name="Terry Pratchett", field="Literature")
        publisher = Publisher(id=2, name="Victor Gollancz", country="UK")
        book = Book(id=10, title="The Colour of Magic", year=1983)
        book.author.value = author
        book.publisher.value = publisher

        json_str = book.model_dump_json(include={"title": True, "author": {"name"}})

        data = json.loads(json_str)
        assert data["title"] == "The Colour of Magic"
        assert data["author"]["name"] == "Terry Pratchett"
        assert len(data["author"]) == 1  # Only name in author
        assert "id" not in data
        assert "year" not in data
        assert "publisher" not in data


class TestNestedTypeCompatibility:
    """Test that various Python types can be nested in Transmuters.

    Tests compatibility with:
    - Pydantic BaseModel
    - TypedDict
    - dataclass
    - Mixed types with relationships
    """

    # --- BaseModel tests ---

    def test_transmuter_with_basemodel_field(self):
        """Test that a Transmuter can have a regular BaseModel as a field."""

        # Create a Transmuter with BaseModel fields
        class PublisherWithContact(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            contact: Contact | None = None

        # Create publisher with nested BaseModel
        address = Address(
            street="123 Main St", city="New York", country="USA", zip_code="10001"
        )
        contact = Contact(
            email="info@publisher.com", phone="+1-555-0100", address=address
        )
        publisher = PublisherWithContact(
            id=1, name="Example Press", country="USA", contact=contact
        )

        # Verify fields
        assert publisher.id == 1
        assert publisher.name == "Example Press"
        assert publisher.contact is not None
        assert publisher.contact.email == "info@publisher.com"
        assert publisher.contact.address is not None
        assert publisher.contact.address.city == "New York"

    def test_transmuter_serialize_with_basemodel(self):
        """Test serialization of Transmuter with nested BaseModel."""

        class AuthorWithContact(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            contact: Contact | None = None

        address = Address(street="456 Oak Ave", city="London", country="UK")
        contact = Contact(email="author@example.com", address=address)
        author = AuthorWithContact(
            id=1, name="Test Author", field="Literature", contact=contact
        )

        # Serialize to dict
        data = author.model_dump()

        assert data["id"] == 1
        assert data["name"] == "Test Author"
        assert data["contact"]["email"] == "author@example.com"
        assert data["contact"]["address"]["city"] == "London"
        assert data["contact"]["address"]["country"] == "UK"

    def test_transmuter_validate_with_basemodel(self):
        """Test validation of Transmuter with nested BaseModel from dict."""

        class PublisherWithAddress(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            address: Address | None = None

        # Create from dict
        publisher_data = {
            "id": 1,
            "name": "Oxford Press",
            "country": "UK",
            "address": {
                "street": "Oxford Street",
                "city": "Oxford",
                "country": "UK",
                "zip_code": "OX1 1XX",
            },
        }

        publisher = PublisherWithAddress.model_validate(publisher_data)

        assert publisher.name == "Oxford Press"
        assert publisher.address is not None
        assert isinstance(publisher.address, Address)
        assert publisher.address.street == "Oxford Street"
        assert publisher.address.zip_code == "OX1 1XX"

    def test_basemodel_validation_in_transmuter(self):
        """Test that validation works for nested BaseModel in Transmuter."""

        class ContactInfo(BaseModel):
            email: str

            @field_validator("email")
            @classmethod
            def validate_email(cls, v: str) -> str:
                if "@" not in v:
                    raise ValueError("Invalid email format")
                return v

        class AuthorWithValidation(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            contact_info: ContactInfo | None = None

        # Rebuild model to resolve locally-defined ContactInfo
        AuthorWithValidation.model_rebuild()

        # Valid email
        author = AuthorWithValidation(
            name="Test",
            field="Physics",
            contact_info=ContactInfo(email="test@example.com"),
        )
        assert author.contact_info
        assert author.contact_info.email == "test@example.com"

        # Invalid email should raise error
        with pytest.raises(ValidationError):
            AuthorWithValidation(
                name="Test",
                field="Physics",
                contact_info=ContactInfo(email="invalid-email"),
            )

    # --- TypedDict tests ---

    def test_transmuter_with_typeddict_field(self):
        """Test that a Transmuter can have a TypedDict as a field."""

        class PublisherWithContactDict(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            contact: ContactDict | None = None

        # Create publisher with nested TypedDict
        address_dict: AddressDict = {
            "street": "123 Main St",
            "city": "New York",
            "country": "USA",
            "zip_code": "10001",
        }
        contact_dict: ContactDict = {
            "email": "info@publisher.com",
            "phone": "+1-555-0100",
            "address": address_dict,
        }
        publisher = PublisherWithContactDict(
            id=1, name="Example Press", country="USA", contact=contact_dict
        )

        # Verify fields
        assert publisher.id == 1
        assert publisher.name == "Example Press"
        assert publisher.contact is not None
        assert publisher.contact["email"] == "info@publisher.com"
        address = publisher.contact.get("address")
        assert address is not None
        assert address["city"] == "New York"

    def test_transmuter_serialize_with_typeddict(self):
        """Test serialization of Transmuter with nested TypedDict."""

        class AuthorWithContactDict(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            contact: ContactDict | None = None

        address_dict: AddressDict = {
            "street": "456 Oak Ave",
            "city": "London",
            "country": "UK",
        }
        contact_dict: ContactDict = {
            "email": "author@example.com",
            "address": address_dict,
        }
        author = AuthorWithContactDict(
            id=1, name="Test Author", field="Literature", contact=contact_dict
        )

        # Serialize to dict
        data = author.model_dump()

        assert data["id"] == 1
        assert data["name"] == "Test Author"
        assert data["contact"]["email"] == "author@example.com"
        assert data["contact"]["address"]["city"] == "London"

    def test_transmuter_validate_with_typeddict(self):
        """Test validation of Transmuter with nested TypedDict from dict."""

        class PublisherWithAddressDict(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            address: AddressDict | None = None

        # Create from dict
        publisher_data = {
            "id": 1,
            "name": "Oxford Press",
            "country": "UK",
            "address": {
                "street": "Oxford Street",
                "city": "Oxford",
                "country": "UK",
                "zip_code": "OX1 1XX",
            },
        }

        publisher = PublisherWithAddressDict.model_validate(publisher_data)

        assert publisher.name == "Oxford Press"
        assert publisher.address is not None
        assert publisher.address["street"] == "Oxford Street"
        assert publisher.address.get("zip_code") == "OX1 1XX"

    # --- Dataclass tests ---

    def test_transmuter_with_dataclass_field(self):
        """Test that a Transmuter can have a dataclass as a field."""

        class PublisherWithContactData(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            contact: ContactData | None = None

        # Create publisher with nested dataclass
        address_data = AddressData(
            street="123 Main St", city="New York", country="USA", zip_code="10001"
        )
        contact_data = ContactData(
            email="info@publisher.com", phone="+1-555-0100", address=address_data
        )
        publisher = PublisherWithContactData(
            id=1, name="Example Press", country="USA", contact=contact_data
        )

        # Verify fields
        assert publisher.id == 1
        assert publisher.name == "Example Press"
        assert publisher.contact is not None
        assert publisher.contact.email == "info@publisher.com"
        assert publisher.contact.address is not None
        assert publisher.contact.address.city == "New York"

    def test_transmuter_serialize_with_dataclass(self):
        """Test serialization of Transmuter with nested dataclass."""

        class AuthorWithContactData(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            contact: ContactData | None = None

        address_data = AddressData(street="456 Oak Ave", city="London", country="UK")
        contact_data = ContactData(email="author@example.com", address=address_data)
        author = AuthorWithContactData(
            id=1, name="Test Author", field="Literature", contact=contact_data
        )

        # Serialize to dict
        data = author.model_dump()

        assert data["id"] == 1
        assert data["name"] == "Test Author"
        assert data["contact"]["email"] == "author@example.com"
        assert data["contact"]["address"]["city"] == "London"

    def test_transmuter_validate_with_dataclass(self):
        """Test validation of Transmuter with nested dataclass from dict."""

        class PublisherWithAddressData(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            country: str
            address: AddressData | None = None

        # Create from dict - Pydantic should convert dict to dataclass
        publisher_data = {
            "id": 1,
            "name": "Oxford Press",
            "country": "UK",
            "address": {
                "street": "Oxford Street",
                "city": "Oxford",
                "country": "UK",
                "zip_code": "OX1 1XX",
            },
        }

        publisher = PublisherWithAddressData.model_validate(publisher_data)

        assert publisher.name == "Oxford Press"
        assert publisher.address is not None
        assert isinstance(publisher.address, AddressData)
        assert publisher.address.street == "Oxford Street"
        assert publisher.address.zip_code == "OX1 1XX"

    # --- Mixed types with relationships tests ---

    def test_transmuter_with_mixed_nested_types(self):
        """Test Transmuter with BaseModel, TypedDict, and dataclass fields together."""

        class MixedNestedTransmuter(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            # BaseModel field
            contact_model: Contact | None = None
            # TypedDict field
            contact_dict: ContactDict | None = None
            # Dataclass field
            contact_data: ContactData | None = None

        # Create with all three types
        contact_model = Contact(
            email="model@example.com",
            address=Address(street="1", city="A", country="X"),
        )
        contact_dict: ContactDict = {
            "email": "dict@example.com",
            "address": {"street": "2", "city": "B", "country": "Y"},
        }
        contact_data = ContactData(
            email="data@example.com",
            address=AddressData(street="3", city="C", country="Z"),
        )

        mixed = MixedNestedTransmuter(
            id=1,
            name="Mixed Test",
            contact_model=contact_model,
            contact_dict=contact_dict,
            contact_data=contact_data,
        )

        # Verify all types work
        assert mixed.contact_model is not None
        assert mixed.contact_model.email == "model@example.com"
        assert mixed.contact_dict is not None
        assert mixed.contact_dict["email"] == "dict@example.com"
        assert mixed.contact_data is not None
        assert mixed.contact_data.email == "data@example.com"

    def test_serialize_mixed_nested_types(self):
        """Test serialization with mixed nested types."""

        class MixedNestedTransmuter(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            contact_model: Contact | None = None
            contact_dict: ContactDict | None = None
            contact_data: ContactData | None = None

        contact_model = Contact(email="model@test.com")
        contact_dict: ContactDict = {"email": "dict@test.com"}
        contact_data = ContactData(email="data@test.com")

        mixed = MixedNestedTransmuter(
            id=1,
            name="Serialize Test",
            contact_model=contact_model,
            contact_dict=contact_dict,
            contact_data=contact_data,
        )

        data = mixed.model_dump()

        assert data["contact_model"]["email"] == "model@test.com"
        assert data["contact_dict"]["email"] == "dict@test.com"
        assert data["contact_data"]["email"] == "data@test.com"

    def test_validate_mixed_nested_types_from_dict(self):
        """Test validation of mixed nested types from dict."""

        class MixedNestedTransmuter(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            contact_model: Contact | None = None
            contact_dict: ContactDict | None = None
            contact_data: ContactData | None = None

        mixed_data = {
            "id": 1,
            "name": "Validate Test",
            "contact_model": {"email": "model@test.com", "phone": "+1-111"},
            "contact_dict": {"email": "dict@test.com", "phone": "+1-222"},
            "contact_data": {"email": "data@test.com", "phone": "+1-333"},
        }

        mixed = MixedNestedTransmuter.model_validate(mixed_data)

        assert mixed.contact_model is not None
        assert isinstance(mixed.contact_model, Contact)
        assert mixed.contact_model.email == "model@test.com"

        assert mixed.contact_dict is not None
        assert mixed.contact_dict["email"] == "dict@test.com"

        assert mixed.contact_data is not None
        assert isinstance(mixed.contact_data, ContactData)
        assert mixed.contact_data.email == "data@test.com"

    def test_transmuter_with_nested_types_and_relationships(self):
        """Test Transmuter combining nested types with Relation fields."""

        class BookWithMetadata(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            title: str
            year: int
            # Nested BaseModel
            publisher_contact: Contact | None = None
            # Nested TypedDict
            location: AddressDict | None = None
            # Relation field
            author: Relation[Author | None] = Relationship()

        # Create with mixed types and relation
        book = BookWithMetadata(
            id=1,
            title="Test Book",
            year=2024,
            publisher_contact=Contact(email="pub@example.com"),
            location={
                "street": "123 Bookstore Lane",
                "city": "Boston",
                "country": "USA",
            },
        )
        book.author.value = Author(id=10, name="Test Author", field="Literature")

        # Verify all types work together
        assert book.title == "Test Book"
        assert book.publisher_contact is not None
        assert book.publisher_contact.email == "pub@example.com"
        assert book.location is not None
        assert book.location["city"] == "Boston"
        assert book.author.value is not None
        assert book.author.value.name == "Test Author"

    def test_serialize_nested_types_with_relationships(self):
        """Test serialization of mixed nested types with relationships."""

        class AuthorWithMetadata(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            # Nested types
            contact: Contact | None = None
            office_address: AddressData | None = None
            # Relation collection
            books: RelationCollection[Book] = Relationships()

        author = AuthorWithMetadata(
            id=1,
            name="Famous Author",
            field="Literature",
            contact=Contact(email="author@books.com"),
            office_address=AddressData(
                street="Writer's Lane", city="London", country="UK"
            ),
        )
        author.books.extend(
            [
                Book(id=10, title="First Book", year=2020),
                Book(id=11, title="Second Book", year=2022),
            ]
        )

        data = author.model_dump()

        # Verify nested types are serialized
        assert data["contact"]["email"] == "author@books.com"
        assert data["office_address"]["city"] == "London"
        # Verify relationships are serialized
        assert len(data["books"]) == 2
        assert data["books"][0]["title"] == "First Book"
        assert data["books"][1]["title"] == "Second Book"

    def test_validate_nested_types_with_relationships_from_json(self):
        """Test model_validate_json with mixed nested types and relationships."""

        class AuthorWithMetadata(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            contact: Contact | None = None
            books: RelationCollection[Book] = Relationships()

        json_str = json.dumps(
            {
                "id": 1,
                "name": "JSON Author",
                "field": "Literature",
                "contact": {"email": "json@author.com", "phone": "+1-555-1234"},
                "books": [
                    {"id": 100, "title": "JSON Book One", "year": 2023},
                    {"id": 101, "title": "JSON Book Two", "year": 2024},
                ],
            }
        )

        author = AuthorWithMetadata.model_validate_json(json_str)

        assert author.name == "JSON Author"
        assert author.contact is not None
        assert isinstance(author.contact, Contact)
        assert author.contact.email == "json@author.com"
        assert len(author.books) == 2
        assert author.books[0].title == "JSON Book One"

    def test_deeply_nested_basemodel_with_transmuter_and_relationships(self):
        """Test deeply nested structure: BaseModel -> Transmuter -> Relationships.

        This test verifies that a regular BaseModel can contain a Transmuter,
        and that Transmuter can have Relation fields, with mixed TypedDict and
        dataclass fields throughout the hierarchy.
        """

        # Inner Transmuter with relationships
        # Note: Using forward references for bidirectional relationship
        class InnerBook(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            title: str
            year: int
            # Nested TypedDict
            warehouse_location: AddressDict | None = None
            # Relationship - forward reference using string
            author: Relation[InnerAuthor | None] = Relationship()

        class InnerAuthor(BaseTransmuter):
            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str
            # Nested dataclass
            office: AddressData | None = None
            # Relationship
            books: RelationCollection[InnerBook] = Relationships()

        # Middle BaseModel containing Transmuter
        class LibrarySection(BaseModel):
            """A BaseModel that contains Transmuters with relationships."""

            section_name: str
            # Contains Transmuter
            featured_book: InnerBook | None = None
            curator: InnerAuthor | None = None
            # Nested TypedDict
            location: AddressDict | None = None

        # Outer BaseModel containing the middle layer
        class Library(BaseModel):
            """Outer BaseModel containing nested BaseModels with Transmuters."""

            name: str
            # Nested dataclass
            main_address: AddressData | None = None
            # Nested BaseModel containing Transmuter
            fiction_section: LibrarySection | None = None
            nonfiction_section: LibrarySection | None = None
            # Nested Contact (BaseModel)
            contact: Contact | None = None

        # Rebuild both models to resolve forward references to each other
        InnerBook.model_rebuild()
        InnerAuthor.model_rebuild()

        # Create deeply nested structure
        author = InnerAuthor(
            id=1,
            name="Isaac Asimov",
            field="Literature",
            office=AddressData(
                street="Columbia University", city="New York", country="USA"
            ),
        )
        book = InnerBook(
            id=10,
            title="Foundation",
            year=1951,
            warehouse_location={
                "street": "123 Storage Lane",
                "city": "Chicago",
                "country": "USA",
            },
        )
        book.author.value = author
        author.books.append(book)

        fiction = LibrarySection(
            section_name="Science Fiction",
            featured_book=book,
            curator=author,
            location={"street": "Floor 2", "city": "Building A", "country": "Campus"},
        )

        library = Library(
            name="Central Library",
            main_address=AddressData(
                street="100 Library Plaza",
                city="Boston",
                country="USA",
                zip_code="02101",
            ),
            fiction_section=fiction,
            contact=Contact(email="library@example.com", phone="+1-555-1000"),
        )

        # Verify the deeply nested structure
        assert library.name == "Central Library"
        assert library.main_address is not None
        assert library.main_address.city == "Boston"
        assert library.fiction_section is not None
        assert library.fiction_section.section_name == "Science Fiction"
        assert library.fiction_section.featured_book is not None
        assert library.fiction_section.featured_book.title == "Foundation"
        assert library.fiction_section.featured_book.author.value is not None
        assert library.fiction_section.featured_book.author.value.name == "Isaac Asimov"
        assert library.fiction_section.curator is not None
        assert library.fiction_section.curator.office is not None
        assert library.fiction_section.curator.office.city == "New York"
        assert library.contact is not None
        assert library.contact.email == "library@example.com"

        # Test serialization of the deeply nested structure
        # Need to exclude circular references
        data = library.model_dump(
            exclude={
                "fiction_section": {
                    "featured_book": {"author": {"books"}},
                    "curator": {"books"},
                }
            }
        )

        assert data["name"] == "Central Library"
        assert data["main_address"]["city"] == "Boston"
        assert data["fiction_section"]["featured_book"]["title"] == "Foundation"
        assert (
            data["fiction_section"]["featured_book"]["author"]["name"] == "Isaac Asimov"
        )
        assert data["fiction_section"]["curator"]["office"]["city"] == "New York"
        assert data["contact"]["email"] == "library@example.com"

        # Test validation from dict (simulating JSON round-trip)
        # Create minimal data without circular refs
        library_dict = {
            "name": "Branch Library",
            "main_address": {
                "street": "200 Branch Ave",
                "city": "Cambridge",
                "country": "USA",
            },
            "fiction_section": {
                "section_name": "Classics",
                "featured_book": {
                    "id": 20,
                    "title": "1984",
                    "year": 1949,
                    "warehouse_location": {
                        "street": "Warehouse B",
                        "city": "Storage",
                        "country": "US",
                    },
                },
                "location": {
                    "street": "Floor 1",
                    "city": "West Wing",
                    "country": "Campus",
                },
            },
            "contact": {"email": "branch@example.com"},
        }

        validated_library = Library.model_validate(library_dict)
        assert validated_library.name == "Branch Library"
        assert validated_library.fiction_section is not None
        assert validated_library.fiction_section.featured_book is not None
        assert validated_library.fiction_section.featured_book.title == "1984"
        assert (
            validated_library.fiction_section.featured_book.warehouse_location
            is not None
        )
        assert (
            validated_library.fiction_section.featured_book.warehouse_location["city"]
            == "Storage"
        )

        # Test JSON validation
        json_str = json.dumps(library_dict)
        json_validated = Library.model_validate_json(json_str)
        assert json_validated.name == "Branch Library"
        assert json_validated.fiction_section is not None
        assert json_validated.fiction_section.featured_book is not None
        assert isinstance(json_validated.fiction_section.featured_book, InnerBook)


class TestModelCopyAndUpdate:
    """Test model copying and updating operations."""

    def test_model_copy(self):
        """Test model_copy() creates a new instance."""
        original = Author(id=1, name="Philip K. Dick", field="Literature")
        copied = original.model_copy()

        assert copied is not original
        assert copied.id == original.id
        assert copied.name == original.name
        assert copied.field == original.field

    def test_model_copy_update(self):
        """Test model_copy(update=...) creates modified copy."""
        original = Author(id=1, name="William Gibson", field="Literature")
        updated = original.model_copy(update={"name": "Bruce Sterling"})

        # Original unchanged
        assert original.name == "William Gibson"

        # Copy has updated value
        assert updated.name == "Bruce Sterling"
        assert updated.id == original.id
        assert updated.field == original.field

    def test_model_copy_deep(self):
        """Test deep copy behavior."""
        original = Author(id=1, name="Neal Stephenson", field="Literature")
        copied = original.model_copy(deep=True)

        assert copied is not original
        assert copied.name == original.name

        # Modify copy shouldn't affect original
        copied.name = "Modified Name"
        assert original.name == "Neal Stephenson"
        assert copied.name == "Modified Name"


class TestFieldDefaults:
    """Test field default values and factories."""

    def test_optional_fields_default_to_none(self):
        """Test that optional fields have None as default."""
        author = Author(name="Test Author", field="Physics")

        assert author.id is None

    def test_collection_fields_default_to_empty(self):
        """Test that collection fields default to empty collections."""
        author = Author(name="Test Author", field="Literature")

        assert len(author.books) == 0
        assert isinstance(author.books, list)

    def test_explicit_none_for_optional_fields(self):
        """Test explicitly setting None for optional fields."""
        book = Book(id=None, title="Test Book", year=2000)

        assert book.id is None

    def test_partial_model_creation(self):
        """Test creating models with only required fields."""
        # Only required fields
        publisher = Publisher(name="Test Publisher", country="USA")

        assert publisher.name == "Test Publisher"
        assert publisher.country == "USA"
        assert publisher.id is None
        assert len(publisher.books) == 0


class TestModelComparison:
    """Test model equality and comparison operations."""

    def test_model_equality(self):
        """Transmuters compare by identity, matching their identity __hash__.

        Transmuters are mutable, provider-backed proxies, so equality is identity
        rather than pydantic's structural value-equality: two distinct instances
        holding the same data are NOT equal. This keeps __eq__ consistent with
        __hash__ (id-based) so they behave correctly in sets/dicts.
        """
        author1 = Author(id=1, name="Test Author", field="Physics")
        author2 = Author(id=1, name="Test Author", field="Physics")

        assert author1 == author1  # noqa: PLR0124 — reflexivity is the point
        assert author1 != author2  # same data, different instance
        assert {author1, author2, author1} == {author1, author2}

    def test_model_inequality_different_values(self):
        """Test that models with different data are not equal."""
        author1 = Author(id=1, name="Author One", field="Physics")
        author2 = Author(id=2, name="Author Two", field="Biology")

        assert author1 != author2

    def test_model_inequality_different_types(self):
        """Test that different model types are not equal."""
        author = Author(id=1, name="Test", field="Physics")
        publisher = Publisher(id=1, name="Test", country="USA")

        assert author != publisher


class TestGenericTransmuter:
    """Test Pydantic generic behavior on transmuters."""

    def test_class_getitem_still_handles_type_parameters(self):
        class Box(BaseTransmuter, Generic[T]):
            value: T

        typed_box = Box[int]

        assert typed_box.model_validate({"value": 1}).value == 1
        with pytest.raises(ValidationError):
            typed_box.model_validate({"value": "not an int"})
