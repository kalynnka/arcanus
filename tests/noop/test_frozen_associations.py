from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import ConfigDict, Field, ValidationError
from typing_extensions import TypedDict

from arcanus.association import (
    GroupedRelationship,
    MappedRelationship,
    Relation,
    RelationCollection,
    RelationGroupMap,
    RelationMap,
    RelationSet,
    Relationship,
    Relationships,
    TypedRelationMap,
    TypedRelationship,
)
from arcanus.base import BaseTransmuter, Identity
from tests.transmuters import Author, Book


class FrozenTag(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None)
    name: str


class FrozenMedia(TypedDict, total=False):
    primary: FrozenTag
    secondary: FrozenTag


class FrozenContainer(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None)
    name: str

    scalar: Relation[FrozenTag] = Relationship(frozen=True)
    items: RelationCollection[FrozenTag] = Relationships(frozen=True)
    unique_items: RelationSet[FrozenTag] = Relationships(unique=True, frozen=True)
    mapped: RelationMap[str, FrozenTag] = MappedRelationship(frozen=True)
    grouped: RelationGroupMap[str, FrozenTag] = GroupedRelationship(frozen=True)
    typed: TypedRelationMap[FrozenMedia] = TypedRelationship(frozen=True)


class ProvidedRelationSet(RelationSet[FrozenTag]):
    def __init__(self, payloads: set[FrozenTag], provided: set[object]) -> None:
        super().__init__(payloads)
        self.provided = provided

    @property
    def __provided__(self) -> set[object]:
        return self.provided

    def _load(self) -> ProvidedRelationSet:
        return self


class ProvidedRelationMap(RelationMap[str, FrozenTag]):
    def __init__(
        self, payloads: dict[str, FrozenTag], provided: dict[str, object]
    ) -> None:
        super().__init__(payloads)
        self.provided = provided

    @property
    def __provided__(self) -> dict[str, object]:
        return self.provided

    def _load(self) -> ProvidedRelationMap:
        return self


class ProvidedTypedRelationMap(TypedRelationMap[FrozenMedia]):
    def __init__(
        self, payloads: dict[str, FrozenTag], provided: dict[str, object]
    ) -> None:
        super().__init__(payloads)
        self.provided = provided

    @property
    def __provided__(self) -> dict[str, object]:
        return self.provided

    def _load(self) -> ProvidedTypedRelationMap:
        return self


def test_relationship_field_replacement_is_rejected_with_default_mutability() -> None:
    author = Author(id=1, name="Author", field="Physics")
    book = Book(id=1, title="Book", year=2024)

    with pytest.raises(ValidationError, match="frozen"):
        author.books = RelationCollection([book])

    with pytest.raises(ValidationError, match="frozen"):
        book.author = Relation(author)


def test_missing_relationship_field_replacement_is_rejected() -> None:
    author = Author(id=1, name="Author", field="Physics")
    object.__getattribute__(author, "__dict__").pop("books")

    with pytest.raises(ValidationError, match="frozen"):
        author.books = RelationCollection()


def test_default_relationship_helpers_keep_association_contents_mutable() -> None:
    author = Author(id=1, name="Author", field="Physics")
    book = Book(id=1, title="Book", year=2024)

    author.books.append(book)
    assert author.books == [book]

    extra = Book(id=2, title="Extra", year=2025)
    author.books += [extra]
    assert author.books == [book, extra]

    book.author.value = author
    assert book.author.value is author


def test_provider_payload_prepare_merges_without_public_mutators() -> None:
    existing = FrozenTag(id=1, name="existing")
    extra = FrozenTag(id=2, name="extra")
    container = FrozenContainer(id=1, name="container")

    provided_set: set[object] = set()
    relation_set = ProvidedRelationSet({existing, extra}, provided_set)
    set.add(relation_set, existing)
    relation_set.prepare(container, "unique_items")
    assert relation_set == {existing, extra}
    assert provided_set == {None}

    provided_map: dict[str, object] = {}
    relation_map = ProvidedRelationMap({"main": existing}, provided_map)
    relation_map.prepare(container, "mapped")
    assert relation_map == {"main": existing}
    assert provided_map == {"main": None}

    provided_typed: dict[str, object] = {}
    typed_map = ProvidedTypedRelationMap({"primary": existing}, provided_typed)
    typed_map.prepare(container, "typed")
    assert typed_map == {"primary": existing}
    assert provided_typed == {"primary": None}


def test_frozen_associations_accept_initial_values_and_serialize() -> None:
    tag = FrozenTag(id=1, name="initial")
    container = FrozenContainer(
        id=1,
        name="container",
        scalar=Relation(tag),
        items=RelationCollection([tag]),
        unique_items=RelationSet({tag}),
        mapped=RelationMap({"main": tag}),
        grouped=RelationGroupMap({"group": [tag]}),
        typed=TypedRelationMap({"primary": tag}),
    )

    dumped = container.model_dump()

    assert dumped["scalar"]["name"] == "initial"
    assert dumped["items"][0]["name"] == "initial"
    assert dumped["unique_items"][0]["name"] == "initial"
    assert dumped["mapped"]["main"]["name"] == "initial"
    assert dumped["grouped"]["group"][0]["name"] == "initial"
    assert dumped["typed"]["primary"]["name"] == "initial"


def test_frozen_association_mutators_are_rejected() -> None:
    tag = FrozenTag(id=1, name="initial")
    extra = FrozenTag(id=2, name="extra")
    container = FrozenContainer(
        id=1,
        name="container",
        scalar=Relation(tag),
        items=RelationCollection([tag]),
        unique_items=RelationSet({tag}),
        mapped=RelationMap({"main": tag}),
        grouped=RelationGroupMap({"group": [tag]}),
        typed=TypedRelationMap({"primary": tag}),
    )

    with pytest.raises(ValidationError, match="frozen"):
        container.scalar.value = extra
    assert container.scalar.value is tag

    with pytest.raises(ValidationError, match="frozen"):
        container.items.append(extra)
    assert container.items == [tag]

    with pytest.raises(ValidationError, match="frozen"):
        container.unique_items.add(extra)
    assert container.unique_items == {tag}

    with pytest.raises(ValidationError, match="frozen"):
        container.mapped.update({"extra": extra})
    assert container.mapped == {"main": tag}

    with pytest.raises(ValidationError, match="frozen"):
        container.grouped.append("group", extra)
    assert container.grouped == {"group": [tag]}

    with pytest.raises(ValidationError, match="frozen"):
        container.typed.update({"secondary": extra})
    assert container.typed == {"primary": tag}
