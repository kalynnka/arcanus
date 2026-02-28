"""Tests for dataclass transmuters with NoOpMateria.

Covers:
- Basic creation (direct and via TypeAdapter)
- Field defaults and validation
- Identity fields
- Association fields (Relation, RelationCollection)
- validate_assignment support
- Revalidation
- validation_context
- model_dump / serialization
- Create / Update partial models
- __setattr__ sync behavior
- Same-type passthrough
- Metaclass introspection
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from arcanus.association import Relation, RelationCollection
from arcanus.base import (
    Transmuter,
    TransmuterMetaclass,
    validation_context,
)
from tests.transmuters import (
    DCAuthor,
    DCBook,
    IdentifiedUser,
    PydanticItem,
    SimpleTag,
    SimpleUser,
    ValidatedUser,
)


class TestBasicCreation:
    """Test basic dataclass transmuter creation."""

    def test_direct_creation(self):
        user = SimpleUser(name="Alice", age=30)
        assert user.name == "Alice"
        assert user.age == 30

    def test_direct_creation_with_defaults(self):
        user = SimpleUser(name="Bob")
        assert user.name == "Bob"
        assert user.age == 25  # default

    def test_type_adapter_from_dict(self):
        ta = TypeAdapter(SimpleUser)
        user = ta.validate_python({"name": "Carol", "age": 40})
        assert user.name == "Carol"
        assert user.age == 40

    def test_type_adapter_partial_dict(self):
        ta = TypeAdapter(SimpleUser)
        user = ta.validate_python({"name": "Dan"})
        assert user.name == "Dan"
        assert user.age == 25

    def test_type_adapter_same_type_passthrough(self):
        ta = TypeAdapter(SimpleUser)
        user = SimpleUser(name="Eve")
        result = ta.validate_python(user)
        assert result is user

    def test_validation_error_on_invalid_data(self):
        ta = TypeAdapter(SimpleUser)
        with pytest.raises(ValidationError):
            ta.validate_python({"name": 123})  # name should be str

    def test_validation_error_on_missing_required(self):
        ta = TypeAdapter(SimpleUser)
        with pytest.raises(ValidationError):
            ta.validate_python({})


class TestTransmuterAttributes:
    """Test transmuter instance attributes (__transmuter_provided__, etc.)."""

    def test_provided_is_none_in_noop(self):
        user = SimpleUser(name="Alice")
        assert user.__transmuter_provided__ is None

    def test_revalidating_is_false(self):
        user = SimpleUser(name="Alice")
        assert user.__transmuter_revalidating__ is False


class TestMetaclassIntrospection:
    """Test TransmuterMetaclass properties on dataclass transmuters."""

    def test_is_dataclass(self):
        assert SimpleUser.__transmuter_is_dataclass__ is True

    def test_transmuter_complete(self):
        assert SimpleUser.__transmuter_complete__ is True

    def test_pydantic_fields(self):
        assert set(SimpleUser.__pydantic_fields__.keys()) == {"name", "age"}

    def test_model_associations_empty(self):
        assert SimpleUser.model_associations == {}

    def test_model_identities_empty(self):
        assert SimpleUser.model_identities == {}

    def test_model_associations_with_relations(self):
        assert "author" in DCBook.model_associations
        assert "publisher" in DCBook.model_associations
        assert "tags" in DCBook.model_associations

    def test_model_identities_with_identity(self):
        assert "id" in IdentifiedUser.model_identities

    def test_create_model(self):
        Create = SimpleUser.Create
        assert "name" in Create.model_fields
        assert "age" in Create.model_fields

    def test_create_model_excludes_identities(self):
        Create = IdentifiedUser.Create
        assert "id" not in Create.model_fields
        assert "name" in Create.model_fields
        assert "email" in Create.model_fields

    def test_update_model(self):
        Update = SimpleUser.Update
        assert "name" in Update.model_fields
        assert "age" in Update.model_fields


class TestIdentityFields:
    """Test identity field tracking."""

    def test_identity_detection(self):
        assert "id" in IdentifiedUser.model_identities

    def test_identity_field_create(self):
        user = IdentifiedUser(name="Alice", email="alice@example.com")
        assert user.name == "Alice"
        assert user.id is None  # default

    def test_identity_field_set(self):
        user = IdentifiedUser(name="Alice", id=42)
        assert user.id == 42


class TestValidateAssignment:
    """Test validate_assignment support."""

    def test_setattr_updates_value(self):
        user = ValidatedUser(name="Alice", age=30)
        user.name = "Bob"
        assert user.name == "Bob"

    def test_setattr_validates(self):
        user = ValidatedUser(name="Alice", age=30)
        with pytest.raises(ValidationError):
            user.age = "not a number"  # type: ignore


class TestRevalidation:
    """Test revalidate behavior."""

    def test_revalidate_returns_self(self):
        user = SimpleUser(name="Alice")
        result = user.revalidate()
        assert result is user

    def test_revalidate_no_error_without_provider(self):
        """With NoOp, revalidate should be a no-op."""
        user = SimpleUser(name="Alice")
        user.revalidate()  # should not raise


class TestValidationContext:
    """Test validation_context integration."""

    def test_validation_context_works(self):
        ta = TypeAdapter(SimpleUser)
        with validation_context():
            user = ta.validate_python({"name": "Alice"})
            assert user.name == "Alice"


class TestSerialization:
    """Test TypeAdapter dump_python for dataclass transmuters."""

    def test_dump_simple(self):
        user = SimpleUser(name="Alice", age=30)
        ta = TypeAdapter(SimpleUser)
        dumped = ta.dump_python(user)
        assert dumped == {"name": "Alice", "age": 30}

    def test_dump_with_associations(self):
        ta_book = TypeAdapter(DCBook)
        book = ta_book.validate_python(
            {
                "title": "Test Book",
                "year": 2024,
                "author": {"name": "Alice", "field": "Physics"},
                "tags": [{"label": "sci"}, {"label": "tech"}],
            }
        )

        dumped = ta_book.dump_python(book)
        assert dumped["title"] == "Test Book"
        assert dumped["year"] == 2024
        assert dumped["author"]["name"] == "Alice"
        assert len(dumped["tags"]) == 2


class TestRelationBasics:
    """Test Relation fields on dataclass transmuters."""

    def test_relation_initialization_empty(self):
        book = DCBook(title="Test")
        assert isinstance(book.author, Relation)
        assert book.author.value is None

    def test_relation_initialization_with_value_via_validation(self):
        ta = TypeAdapter(DCBook)
        book = ta.validate_python(
            {
                "title": "Test",
                "author": {"name": "Alice", "field": "Physics"},
            }
        )
        assert isinstance(book.author, Relation)
        assert book.author.value is not None
        assert book.author.value.name == "Alice"

    def test_relation_set_value(self):
        book = DCBook(title="Test")
        author = DCAuthor(name="Bob", field="Biology")
        book.author.value = author
        assert book.author.value.name == "Bob"

    def test_relation_isinstance(self):
        book = DCBook(title="Test")
        assert isinstance(book.author, Relation)


class TestRelationCollectionBasics:
    """Test RelationCollection fields on dataclass transmuters."""

    def test_collection_initialization_empty(self):
        book = DCBook(title="Test")
        assert isinstance(book.tags, RelationCollection)
        assert len(book.tags) == 0

    def test_collection_initialization_with_values_via_validation(self):
        ta = TypeAdapter(DCBook)
        book = ta.validate_python(
            {
                "title": "Test",
                "tags": [{"label": "sci"}, {"label": "tech"}],
            }
        )
        assert isinstance(book.tags, RelationCollection)
        assert len(book.tags) == 2
        assert book.tags[0].label == "sci"

    def test_collection_append(self):
        book = DCBook(title="Test")
        tag = SimpleTag(label="new")
        book.tags.append(tag)
        assert len(book.tags) == 1
        assert book.tags[0].label == "new"

    def test_collection_iteration(self):
        ta = TypeAdapter(DCBook)
        book = ta.validate_python(
            {
                "title": "Test",
                "tags": [{"label": "a"}, {"label": "b"}, {"label": "c"}],
            }
        )
        labels = [t.label for t in book.tags]
        assert labels == ["a", "b", "c"]


class TestInstanceIsolation:
    """Test that transmuter instances are properly isolated."""

    def test_separate_instances_independent(self):
        u1 = SimpleUser(name="Alice")
        u2 = SimpleUser(name="Bob")
        assert u1.name != u2.name

    def test_association_isolation(self):
        """Each instance should have its own association."""
        b1 = DCBook(title="Book 1")
        b2 = DCBook(title="Book 2")

        tag = SimpleTag(label="shared")
        b1.tags.append(tag)

        assert len(b1.tags) == 1
        assert len(b2.tags) == 0


class TestTransmuterInstanceMixin:
    """Verify Transmuter is in the hierarchy and provides methods."""

    def test_plain_dc_has_mixin(self):
        assert issubclass(SimpleUser, Transmuter)

    def test_mixin_provides_revalidate(self):
        u = SimpleUser(name="Alice")
        assert hasattr(u, "revalidate")
        assert u.revalidate() is u


class TestPydanticDataclassBlessing:
    """Test pydantic @dataclass blessed via NoOpMateria().bless()."""

    def test_create_from_pydantic(self):
        item = PydanticItem(name="test")
        assert item.name == "test"
        assert item.score == 0.0

    def test_is_transmuter_metaclass(self):
        assert isinstance(PydanticItem, TransmuterMetaclass)

    def test_type_adapter_works(self):
        adapter = TypeAdapter(PydanticItem)
        item = adapter.validate_python({"name": "test", "score": 9.5})
        assert isinstance(item, PydanticItem)
        assert item.score == 9.5

    def test_has_mixin(self):
        assert issubclass(PydanticItem, Transmuter)

    def test_revalidate(self):
        item = PydanticItem(name="test")
        assert item.revalidate() is item

    def test_transmuter_attributes(self):
        assert hasattr(PydanticItem, "__pydantic_fields__")
        assert hasattr(PydanticItem, "model_associations")
        assert "name" in PydanticItem.__pydantic_fields__
        assert "score" in PydanticItem.__pydantic_fields__
