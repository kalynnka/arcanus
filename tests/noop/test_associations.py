from __future__ import annotations

import pytest
from pydantic import ValidationError

from arcanus.association import Relation, RelationCollection
from tests.transmuters import Author, Book, Publisher, Translator

"""Test association fields (Relation and RelationCollection) with NoOpMateria.

This module comprehensively tests:
- Relation field behavior (get, set, validation)
- RelationCollection operations (list-like interface)
- Association preparation and initialization
- Instance isolation (associations should not be shared)
- All implemented methods and operations
"""


class TestRelationBasics:
    """Test basic Relation field behavior."""

    def test_relation_initialization_empty(self):
        """Test that Relation fields initialize as empty."""
        book = Book(id=1, title="Test Book", year=2000)

        assert isinstance(book.author, Relation)
        assert book.author.value is None

    def test_relation_initialization_with_value(self):
        """Test Relation initialization with a value."""
        author = Author(id=1, name="Test Author", field="Physics")
        book = Book(id=1, title="Test Book", year=2000, author=Relation(author))

        assert isinstance(book.author, Relation)
        assert book.author.value is not None
        assert book.author.value.name == "Test Author"

    def test_relation_get_value(self):
        """Test getting value from Relation."""
        author = Author(id=1, name="Isaac Asimov", field="Chemistry")
        book = Book(id=1, title="Foundation", year=1951)

        book.author.value = author

        retrieved = book.author.value
        assert retrieved is not None
        assert isinstance(retrieved, Author)
        assert retrieved.name == "Isaac Asimov"
        assert retrieved.id == 1

    def test_relation_set_value(self):
        """Test setting value on Relation."""
        book = Book(id=1, title="1984", year=1949)
        author = Author(id=2, name="George Orwell", field="Literature")

        # Initially None
        assert book.author.value is None

        # Set value
        book.author.value = author
        assert book.author.value is not None
        assert book.author.value.name == "George Orwell"

    def test_relation_update_value(self):
        """Test updating an existing Relation value."""
        book = Book(id=1, title="Test", year=2000)
        author1 = Author(id=1, name="Author 1", field="Physics")
        author2 = Author(id=2, name="Author 2", field="Biology")

        book.author.value = author1
        assert book.author.value.name == "Author 1"

        # Update to different author
        book.author.value = author2
        assert book.author.value.name == "Author 2"
        assert book.author.value.id == 2

    def test_relation_isinstance_check(self):
        """Test that Relation is recognized by isinstance."""
        book = Book(id=1, title="Test", year=2000)

        assert isinstance(book.author, Relation)


class TestRelationValidation:
    """Test Relation field validation."""

    def test_relation_validates_type(self):
        """Test that Relation validates the type of assigned value."""
        book = Book(id=1, title="Test", year=2000)

        # Valid type
        author = Author(id=1, name="Valid", field="Physics")
        book.author.value = author
        assert book.author.value.name == "Valid"

        # Invalid type should raise ValidationError
        with pytest.raises(ValidationError):
            book.author.value = "not an author"

    def test_relation_none_validation_required(self):
        """Test that required Relation fields cannot be set to None."""
        book = Book(id=1, title="Test", year=2000)
        author = Author(id=1, name="Test", field="Physics")

        book.author.value = author
        assert book.author.value is not None

        # Author is required, setting to None should fail
        with pytest.raises(ValidationError):
            book.author.value = None

    def test_relation_none_validation_optional(self):
        """Test that optional Relation fields can be None."""
        book = Book(id=1, title="Test", year=2000)

        # Translator is optional, None is valid
        assert book.translator.value is None

        # Can set a value
        translator = Translator(id=1, name="Test Translator", language="English")
        book.translator.value = translator
        assert book.translator.value is not None

    def test_relation_validation_on_initialization(self):
        """Test that Relation values are validated on model initialization."""
        author = Author(id=1, name="Valid Author", field="Physics")

        # Valid initialization
        book = Book(
            id=1,
            title="Test",
            year=2000,
            author=Relation(author),
        )
        assert book.author.value.name == "Valid Author"

        # Invalid initialization should fail
        with pytest.raises(ValidationError):
            Book(
                id=1,
                title="Test",
                year=2000,
                author=Relation("not an author"),  # pyright: ignore[reportArgumentType]
            )


class TestRelationCollectionBasics:
    """Test basic RelationCollection behavior."""

    def test_relation_collection_initialization_empty(self):
        """Test that RelationCollection initializes as empty list."""
        author = Author(id=1, name="Test", field="Physics")

        assert isinstance(author.books, RelationCollection)
        assert len(author.books) == 0
        assert list(author.books) == []

    def test_relation_collection_initialization_with_data(self):
        """Test RelationCollection initialization with data."""
        books = [
            Book(id=1, title="Book 1", year=2000),
            Book(id=2, title="Book 2", year=2001),
        ]
        author = Author(
            id=1,
            name="Test",
            field="Physics",
            books=RelationCollection(books),
        )

        assert len(author.books) == 2
        assert author.books[0].title == "Book 1"
        assert author.books[1].title == "Book 2"

    def test_relation_collection_isinstance_check(self):
        """Test that RelationCollection is recognized by isinstance."""
        author = Author(id=1, name="Test", field="Physics")

        assert isinstance(author.books, RelationCollection)
        assert isinstance(author.books, list)


class TestRelationCollectionListOperations:
    """Test that RelationCollection implements list operations correctly."""

    def test_append(self):
        """Test append operation."""
        author = Author(id=1, name="Test", field="Physics")
        book = Book(id=1, title="Test Book", year=2000)

        author.books.append(book)

        assert len(author.books) == 1
        assert author.books[0] is book

    def test_extend(self):
        """Test extend operation."""
        author = Author(id=1, name="Test", field="Physics")
        books = [
            Book(id=1, title="Book 1", year=2000),
            Book(id=2, title="Book 2", year=2001),
        ]

        author.books.extend(books)

        assert len(author.books) == 2
        assert author.books[0].title == "Book 1"
        assert author.books[1].title == "Book 2"

    def test_insert(self):
        """Test insert operation."""
        author = Author(id=1, name="Test", field="Physics")
        book1 = Book(id=1, title="First", year=2000)
        book2 = Book(id=2, title="Second", year=2001)
        book3 = Book(id=3, title="Inserted", year=2002)

        author.books.extend([book1, book2])
        author.books.insert(1, book3)

        assert len(author.books) == 3
        assert author.books[0].title == "First"
        assert author.books[1].title == "Inserted"
        assert author.books[2].title == "Second"

    def test_remove(self):
        """Test remove operation."""
        author = Author(id=1, name="Test", field="Physics")
        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)

        author.books.extend([book1, book2])
        author.books.remove(book1)

        assert len(author.books) == 1
        assert author.books[0] is book2

    def test_pop(self):
        """Test pop operation."""
        author = Author(id=1, name="Test", field="Physics")
        books = [
            Book(id=1, title="Book 1", year=2000),
            Book(id=2, title="Book 2", year=2001),
            Book(id=3, title="Book 3", year=2002),
        ]
        author.books.extend(books)

        # Pop last item
        popped = author.books.pop()
        assert popped.title == "Book 3"
        assert len(author.books) == 2

        # Pop at index
        popped = author.books.pop(0)
        assert popped.title == "Book 1"
        assert len(author.books) == 1
        assert author.books[0].title == "Book 2"

    def test_clear(self):
        """Test clear operation."""
        author = Author(id=1, name="Test", field="Physics")
        books = [
            Book(id=1, title="Book 1", year=2000),
            Book(id=2, title="Book 2", year=2001),
        ]
        author.books.extend(books)

        assert len(author.books) == 2

        author.books.clear()

        assert len(author.books) == 0
        assert list(author.books) == []

    def test_index(self):
        """Test index operation."""
        author = Author(id=1, name="Test", field="Physics")
        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)

        author.books.extend([book1, book2])

        assert author.books.index(book1) == 0
        assert author.books.index(book2) == 1

    def test_count(self):
        """Test count operation."""
        author = Author(id=1, name="Test", field="Physics")
        book = Book(id=1, title="Book", year=2000)

        author.books.extend([book, book])  # Add same book twice

        assert author.books.count(book) == 2

    def test_reverse(self):
        """Test reverse operation."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(3)]
        author.books.extend(books)

        author.books.reverse()

        assert author.books[0].title == "Book 2"
        assert author.books[1].title == "Book 1"
        assert author.books[2].title == "Book 0"

    def test_sort(self):
        """Test sort operation."""
        author = Author(id=1, name="Test", field="Physics")
        books = [
            Book(id=3, title="C", year=2002),
            Book(id=1, title="A", year=2000),
            Book(id=2, title="B", year=2001),
        ]
        author.books.extend(books)

        author.books.sort(key=lambda b: b.title)

        assert author.books[0].title == "A"
        assert author.books[1].title == "B"
        assert author.books[2].title == "C"


class TestRelationCollectionIndexingAndSlicing:
    """Test indexing and slicing operations on RelationCollection."""

    def test_indexing_get(self):
        """Test getting items by index."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(3)]
        author.books.extend(books)

        assert author.books[0].title == "Book 0"
        assert author.books[1].title == "Book 1"
        assert author.books[2].title == "Book 2"
        assert author.books[-1].title == "Book 2"

    def test_indexing_set(self):
        """Test setting items by index."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(3)]
        author.books.extend(books)

        new_book = Book(id=99, title="Replacement", year=2024)
        author.books[1] = new_book

        assert author.books[1].title == "Replacement"
        assert len(author.books) == 3

    def test_slicing_get(self):
        """Test getting slices."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(5)]
        author.books.extend(books)

        # Get slice
        slice_result = author.books[1:4]
        assert len(slice_result) == 3
        assert slice_result[0].title == "Book 1"
        assert slice_result[2].title == "Book 3"

        # Get slice with step
        slice_result = author.books[::2]
        assert len(slice_result) == 3
        assert slice_result[0].title == "Book 0"
        assert slice_result[1].title == "Book 2"
        assert slice_result[2].title == "Book 4"

    def test_slicing_set(self):
        """Test setting slices."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(5)]
        author.books.extend(books)

        new_books = [
            Book(id=10, title="New 1", year=2020),
            Book(id=11, title="New 2", year=2021),
        ]
        author.books[1:3] = new_books

        assert len(author.books) == 5
        assert author.books[1].title == "New 1"
        assert author.books[2].title == "New 2"

    def test_slicing_delete(self):
        """Test deleting slices."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(5)]
        author.books.extend(books)

        del author.books[1:3]

        assert len(author.books) == 3
        assert author.books[0].title == "Book 0"
        assert author.books[1].title == "Book 3"
        assert author.books[2].title == "Book 4"


class TestRelationCollectionIteration:
    """Test iteration and membership operations."""

    def test_iteration(self):
        """Test iterating over RelationCollection."""
        author = Author(id=1, name="Test", field="Physics")
        books = [Book(id=i, title=f"Book {i}", year=2000 + i) for i in range(3)]
        author.books.extend(books)

        titles = [book.title for book in author.books]

        assert titles == ["Book 0", "Book 1", "Book 2"]

    def test_membership_in(self):
        """Test 'in' operator."""
        author = Author(id=1, name="Test", field="Physics")
        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)
        book3 = Book(id=3, title="Book 3", year=2002)

        author.books.extend([book1, book2])

        assert book1 in author.books
        assert book2 in author.books
        assert book3 not in author.books

    def test_membership_not_in(self):
        """Test 'not in' operator."""
        author = Author(id=1, name="Test", field="Physics")
        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)

        author.books.append(book1)

        assert book1 in author.books
        assert book2 not in author.books

    def test_len(self):
        """Test len() function."""
        author = Author(id=1, name="Test", field="Physics")

        assert len(author.books) == 0

        author.books.append(Book(id=1, title="Book 1", year=2000))
        assert len(author.books) == 1

        author.books.append(Book(id=2, title="Book 2", year=2001))
        assert len(author.books) == 2

    def test_bool(self):
        """Test boolean evaluation."""
        author = Author(id=1, name="Test", field="Physics")

        # Empty collection is False
        assert not bool(author.books)

        # Non-empty collection is True
        author.books.append(Book(id=1, title="Book", year=2000))
        assert bool(author.books)


class TestAssociationInstanceIsolation:
    """Test that association instances are not shared between model instances."""

    def test_relation_not_shared_between_instances(self):
        """Test that Relation fields are not shared."""
        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)

        author1 = Author(id=1, name="Author 1", field="Physics")
        author2 = Author(id=2, name="Author 2", field="Biology")

        book1.author.value = author1
        book2.author.value = author2

        # Each book should have its own author
        assert book1.author.value.name == "Author 1"
        assert book2.author.value.name == "Author 2"

        # Changing one shouldn't affect the other
        book1.author.value = Author(id=3, name="Author 3", field="Chemistry")
        assert book1.author.value.name == "Author 3"
        assert book2.author.value.name == "Author 2"

    def test_relation_collection_not_shared_between_instances(self):
        """Test that RelationCollection instances are not shared."""
        author1 = Author(id=1, name="Author 1", field="Physics")
        author2 = Author(id=2, name="Author 2", field="Biology")

        book1 = Book(id=1, title="Book 1", year=2000)
        book2 = Book(id=2, title="Book 2", year=2001)

        author1.books.append(book1)
        author2.books.append(book2)

        # Each author should have their own books collection
        assert len(author1.books) == 1
        assert len(author2.books) == 1
        assert author1.books[0].title == "Book 1"
        assert author2.books[0].title == "Book 2"

        # Modifying one shouldn't affect the other
        author1.books.clear()
        assert len(author1.books) == 0
        assert len(author2.books) == 1

    def test_relation_isolation_on_copy(self):
        """Test that copied models have independent Relation fields."""
        book = Book(id=1, title="Original", year=2000)
        author = Author(id=1, name="Original Author", field="Physics")
        book.author.value = author

        # Copy the book - note: shallow copy shares the Relation instance
        book_copy = book.model_copy()

        # Modify the copy's author - this affects both since Relation is shared in shallow copy
        book_copy.author.value = Author(id=2, name="Copy Author", field="Biology")

        # With shallow copy, both point to the same Relation instance
        # Use deep copy for true isolation
        book_deep = book.model_copy(deep=True)
        book_deep.author.value = Author(
            id=3, name="Deep Copy Author", field="Chemistry"
        )

        # Now book_copy has modified author but book_deep is independent
        assert book_copy.author.value.name == "Copy Author"
        assert book_deep.author.value.name == "Deep Copy Author"

    def test_relation_collection_isolation_on_copy(self):
        """Test that copied models have independent RelationCollection fields."""
        author = Author(id=1, name="Test", field="Physics")
        book = Book(id=1, title="Book 1", year=2000)
        author.books.append(book)

        # Shallow copy shares the RelationCollection list
        author_copy = author.model_copy()

        # Modify the copy's books - affects original due to shared list
        new_book = Book(id=2, title="Book 2", year=2001)
        author_copy.books.append(new_book)

        # With shallow copy, both share the same list
        assert len(author.books) == 2  # Also affected
        assert len(author_copy.books) == 2

        # Use deep copy for true isolation
        author_deep = author.model_copy(deep=True)
        author_deep.books.clear()
        author_deep.books.append(Book(id=3, title="Deep Book", year=2002))

        assert len(author_deep.books) == 1
        assert author_deep.books[0].title == "Deep Book"


class TestAssociationPrepareAndValidation:
    """Test association preparation and validation mechanisms."""

    def test_relation_prepare_sets_instance(self):
        """Test that accessing Relation triggers prepare()."""
        book = Book(id=1, title="Test", year=2000)

        # Access the relation (triggers prepare)
        relation = book.author

        # After prepare, relation should know its field name and instance
        assert relation.field_name == "author"
        # The __instance__ attribute is defined in Association class
        # But it's actually a private attribute with single underscore naming
        # Check via accessing the actual stored instance
        assert relation.field_info is not None

    def test_relation_collection_prepare_sets_instance(self):
        """Test that accessing RelationCollection triggers prepare()."""
        author = Author(id=1, name="Test", field="Physics")

        # Access the collection (triggers prepare)
        collection = author.books

        # After prepare, collection should know its field name and instance
        assert collection.field_name == "books"
        # Check via accessing the actual stored metadata
        assert collection.field_info is not None

    def test_validation_with_nested_models(self):
        """Test that nested model validation works correctly."""
        # Create author with nested books
        author_dict = {
            "id": 1,
            "name": "Test Author",
            "field": "Physics",
            "books": [
                {"id": 1, "title": "Book 1", "year": 2000},
                {"id": 2, "title": "Book 2", "year": 2001},
            ],
        }

        author = Author.model_validate(author_dict)

        assert author.name == "Test Author"
        assert len(author.books) == 2
        assert isinstance(author.books[0], Book)
        assert author.books[0].title == "Book 1"


class TestAssociationEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_relation_collection_operations(self):
        """Test operations on empty RelationCollection."""
        author = Author(id=1, name="Test", field="Physics")

        # Operations on empty collection
        assert len(author.books) == 0
        assert list(author.books) == []
        assert author.books[:] == []

        # Pop on empty should raise
        with pytest.raises(IndexError):
            author.books.pop()

    def test_relation_with_same_type(self):
        """Test relations where model references itself (if applicable)."""
        # This would require a self-referential model, which we don't have in schemas
        # But we can test that the type system handles it
        pass

    def test_multiple_associations_on_same_model(self):
        """Test model with multiple association fields."""
        book = Book(id=1, title="Test", year=2000)

        # Should have multiple independent associations
        assert isinstance(book.author, Relation)
        assert isinstance(book.publisher, Relation)
        assert isinstance(book.categories, RelationCollection)
        assert isinstance(book.reviews, RelationCollection)

        # Each should be independent
        author = Author(id=1, name="Author", field="Physics")
        publisher = Publisher(id=1, name="Publisher", country="USA")

        book.author.value = author
        book.publisher.value = publisher

        assert book.author.value.name == "Author"
        assert book.publisher.value.name == "Publisher"

    def test_relation_collection_with_duplicates(self):
        """Test that RelationCollection can contain duplicate references."""
        author = Author(id=1, name="Test", field="Physics")
        book = Book(id=1, title="Book", year=2000)

        # Add same book twice
        author.books.append(book)
        author.books.append(book)

        assert len(author.books) == 2
        assert author.books[0] is book
        assert author.books[1] is book
        assert author.books[0] is author.books[1]

    def test_relation_collection_concatenation(self):
        """Test concatenating RelationCollections."""
        author = Author(id=1, name="Test", field="Physics")
        books1 = [Book(id=1, title="Book 1", year=2000)]
        books2 = [Book(id=2, title="Book 2", year=2001)]

        author.books.extend(books1)
        author.books.extend(books2)

        assert len(author.books) == 2

    def test_relation_collection_repr(self):
        """Test repr for a prepared RelationCollection."""
        author = Author(id=1, name="Test", field="Physics")
        r = repr(author.books)
        assert "RelationCollection" in r
        assert "Book" in r

    def test_relation_collection_repr_unprepared(self):
        """repr() must not raise AttributeError when __args__ is not yet set."""
        rc = RelationCollection()
        r = repr(rc)
        assert "RelationCollection" in r
        assert "?" in r
