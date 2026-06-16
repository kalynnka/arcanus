from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.transmuters import Account, Author, Book, BookCategory

"""Test transmuter-specific features with NoOpMateria.

This module tests:
- Create/Update model generation and usage
- shell() and absorb() methods
- Validation context
- Additional properties and custom behavior
- Model inheritance and metaclass features
"""


class TestCreateModel:
    """Test the dynamically generated Create model."""

    def test_create_model_excludes_identity_fields(self):
        """Test that Create model excludes Identity fields."""
        # Create model should not have 'id' field
        partial = Book.Create(title="New Book", year=2024)

        assert hasattr(partial, "title")
        assert hasattr(partial, "year")
        assert not hasattr(partial, "id")  # Identity field excluded

    def test_create_model_excludes_associations(self):
        """Test that Create model excludes association fields."""
        partial = Book.Create(title="New Book", year=2024)

        # Association fields should not be in Create model
        assert not hasattr(partial, "author")
        assert not hasattr(partial, "publisher")
        assert not hasattr(partial, "categories")

    def test_create_model_with_valid_data(self):
        """Test creating valid Create model instances."""
        partial = Book.Create(
            title="Test Book",
            year=2024,
            author_id=1,
            publisher_id=2,
        )

        data = partial.model_dump(exclude_none=True)
        assert data["title"] == "Test Book"
        assert data["year"] == 2024
        assert data["author_id"] == 1
        assert data["publisher_id"] == 2

    def test_create_model_requires_non_optional_fields(self):
        """Test that Create model still validates required fields."""
        with pytest.raises(ValidationError) as exc_info:
            Book.Create(year=2024)  # Missing required 'title'

        errors = exc_info.value.errors()
        assert any("title" in str(error["loc"]) for error in errors)

    def test_create_model_name_and_module(self):
        """Test that Create model has proper naming."""
        assert Book.Create.__name__ == "BookCreate"
        assert Author.Create.__name__ == "AuthorCreate"

    def test_create_model_keeps_natural_keys(self):
        """Identity(server_side=False) keys stay in Create; server-side identities don't."""
        # BookCategory's composite PK is declared server_side=False => client supplies it.
        fields = BookCategory.Create.model_fields
        assert "book_id" in fields
        assert "category_id" in fields
        assert fields["book_id"].is_required()
        assert fields["category_id"].is_required()

        # Author.id is a server-assigned identity => excluded regardless of shape.
        assert "id" not in Author.Create.model_fields


class TestUpdateModel:
    """Test the dynamically generated Update model."""

    def test_update_model_makes_all_fields_optional(self):
        """Test that Update model makes all non-frozen fields optional."""
        partial = Book.Update(title="Updated Title")

        data = partial.model_dump(exclude_none=True)
        assert "title" in data
        assert data["title"] == "Updated Title"

        # Other fields should have None as default
        assert "year" not in data
        assert "author_id" not in data

    def test_update_model_excludes_associations(self):
        """Test that Update model excludes association fields."""
        partial = Book.Update(title="Updated")

        assert not hasattr(partial, "author")
        assert not hasattr(partial, "publisher")
        assert not hasattr(partial, "categories")

    def test_update_model_with_multiple_fields(self):
        """Test Update model with multiple fields."""
        partial = Book.Update(
            title="New Title",
            year=2025,
        )

        data = partial.model_dump(exclude_none=True)
        assert data["title"] == "New Title"
        assert data["year"] == 2025
        assert "author_id" not in data

    def test_update_model_with_empty_update(self):
        """Test creating Update model with no fields."""
        partial = Book.Update()

        # All fields should be None when not provided
        data = partial.model_dump(exclude_none=True)
        assert "title" not in data
        assert "year" not in data

    def test_update_model_name_and_module(self):
        """Test that Update model has proper naming."""
        assert Book.Update.__name__ == "BookUpdate"
        assert Author.Update.__name__ == "AuthorUpdate"


class TestShellMethod:
    """Test the shell() class method for creating instances from partial models."""

    def test_shell_from_create_model(self):
        """Test creating full model from Create model."""
        partial = Book.Create(title="Partial Book", year=2024)
        book = Book.shell(partial)

        assert isinstance(book, Book)
        assert book.title == "Partial Book"
        assert book.year == 2024
        assert book.id is None  # Identity field gets default value

    def test_shell_ignores_extra_fields_in_partial(self):
        """Test that shell() ignores fields that shouldn't exist in target."""
        # Create model with extra 'id' field (should be ignored)
        partial = Book.Create(
            id=999,  # This should be ignored
            title="Test Book",
            year=2024,
        )
        book = Book.shell(partial)

        # ID should be None (default), not 999
        assert book.id is None
        assert book.title == "Test Book"
        assert book.year == 2024

    def test_shell_from_dict(self):
        """Test creating model from dictionary using shell()."""
        data = {"title": "Dict Book", "year": 2023}
        book = Book.shell(Book.Create(**data))

        assert book.title == "Dict Book"
        assert book.year == 2023

    def test_shell_preserves_valid_fields(self):
        """Test that shell() preserves all valid fields from partial."""
        partial = Author.Create(name="Test Author", field="Physics")
        author = Author.shell(partial)

        assert author.name == "Test Author"
        assert author.field == "Physics"
        assert author.id is None


class TestAbsorbMethod:
    """Test the absorb() method for updating instances."""

    def test_absorb_updates_provided_fields(self):
        """Test that absorb() updates only the provided fields."""
        book = Book(id=1, title="Original Title", year=2020)
        partial = Book.Update(title="Updated Title")

        updated_book = book.absorb(partial)

        assert updated_book is book  # Should be same instance
        assert book.title == "Updated Title"
        assert book.year == 2020  # Unchanged
        assert book.id == 1  # Unchanged

    def test_absorb_ignores_none_values(self):
        """Test that absorb() behavior with None values in Update model."""
        book = Book(id=2, title="Original", year=2020, author_id=5)
        partial = Book.Update(title="Updated", author_id=None)

        book.absorb(partial)

        # Title should be updated
        assert book.title == "Updated"
        # absorb() updates with all provided values, including explicit None
        # If you want to skip None values, filter them before calling absorb
        assert book.author_id is None  # Updated to None as explicitly set

        # Test filtering None values before absorb
        book2 = Book(id=3, title="Original2", year=2021, author_id=10)
        partial2 = Book.Update(title="Updated2", author_id=None)
        # Filter out None values
        update_data = {k: v for k, v in partial2.model_dump().items() if v is not None}
        book2.absorb(Book.Update(**update_data))

        assert book2.title == "Updated2"
        assert book2.author_id == 10  # Not updated since None was filtered

    def test_absorb_with_multiple_updates(self):
        """Test absorbing multiple fields at once."""
        author = Author(id=1, name="Original Name", field="Physics")
        partial = Author.Update(name="New Name", field="Biology")

        author.absorb(partial)

        assert author.name == "New Name"
        assert author.field == "Biology"
        assert author.id == 1  # Unchanged

    def test_absorb_ignores_identity_fields(self):
        """Test that absorb() ignores identity fields even if provided."""
        book = Book(id=1, title="Test", year=2020)

        # Update model shouldn't have 'id', but if someone passes it in dict
        partial = Book.Update(id=999, title="Updated")

        book.absorb(partial)

        assert book.id == 1  # ID unchanged
        assert book.title == "Updated"

    def test_absorb_returns_self(self):
        """Test that absorb() returns the same instance."""
        author = Author(id=1, name="Test", field="Physics")
        partial = Author.Update(name="Updated")

        result = author.absorb(partial)

        assert result is author


class TestModelMetadata:
    """Test metadata and introspection of transmuter models."""

    def test_model_associations_property(self):
        """Test that model_associations returns association fields."""
        associations = Book.model_associations

        # Association fields
        assert "author" in associations
        assert "publisher" in associations
        assert "categories" in associations

        # Non-association fields should not be present
        assert "title" not in associations
        assert "year" not in associations

    def test_model_identities_property(self):
        """Test that model_identities returns identity fields."""
        identities = Book.model_identities

        assert "id" in identities

        # Non-identity fields should not be present
        assert "title" not in identities
        assert "year" not in identities

    def test_model_fields_property(self):
        """Test that model_fields contains all fields."""
        fields = Book.model_fields

        # Should contain all fields
        assert "id" in fields
        assert "title" in fields
        assert "year" in fields
        assert "author" in fields
        assert "publisher" in fields

    def test_model_config(self):
        """Test model configuration."""
        assert Book.model_config.get("from_attributes") is True
        assert Author.model_config.get("from_attributes") is True


class TestWriteOnceFields:
    """frozen=True gives write-once semantics: in Create, not in Update."""

    def test_write_once_in_create_not_update(self):
        assert "api_token" in Account.Create.model_fields
        assert "api_token" not in Account.Update.model_fields

    def test_write_once_round_trips_through_shell(self):
        account = Account.shell(
            Account.Create(username="neo", password="trinity", api_token="tok-123")
        )
        assert account.api_token == "tok-123"
        assert account.id is None  # generated identity stays default


class TestMaskedFields:
    """exclude=True masks a field from the response while keeping it writable."""

    def test_masked_field_present_in_partials(self):
        assert "password" in Account.Create.model_fields
        assert "password" in Account.Update.model_fields

    def test_masked_field_written_via_shell(self):
        account = Account.shell(
            Account.Create(username="neo", password="trinity", api_token="tok")
        )
        assert account.password == "trinity"

    def test_masked_field_written_via_absorb(self):
        account = Account.shell(
            Account.Create(username="neo", password="old", api_token="tok")
        )
        account.absorb(Account.Update(password="new"))
        assert account.password == "new"

    def test_masked_field_hidden_from_model_dump(self):
        account = Account.shell(
            Account.Create(username="neo", password="secret", api_token="tok")
        )
        dumped = account.model_dump()
        assert "password" not in dumped  # hidden from the API response
        assert dumped["username"] == "neo"
        assert account.password == "secret"  # still functional in the backend
