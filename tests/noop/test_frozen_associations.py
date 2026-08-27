from __future__ import annotations

from typing import Annotated

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

    id: Annotated[int | None, Identity] = Field(default=None)
    name: str


class FrozenMedia(TypedDict, total=False):
    primary: FrozenTag
    secondary: FrozenTag


class FrozenContainer(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[int | None, Identity] = Field(default=None)
    name: str

    scalar: Relation[FrozenTag] = Relationship(frozen=True)
    items: RelationCollection[FrozenTag] = Relationships(frozen=True)
    unique_items: RelationSet[FrozenTag] = Relationships(unique=True, frozen=True)
    mapped: RelationMap[str, FrozenTag] = MappedRelationship(frozen=True)
    grouped: RelationGroupMap[str, FrozenTag] = GroupedRelationship(frozen=True)
    typed: TypedRelationMap[FrozenMedia] = TypedRelationship(frozen=True)


def test_relationship_field_replacement_is_rejected_with_default_mutability() -> None:
    author = Author(id=1, name="Author", field="Physics")
    book = Book(id=1, title="Book", year=2024)

    with pytest.raises(ValidationError, match="frozen"):
        author.books = RelationCollection([book])

    with pytest.raises(ValidationError, match="frozen"):
        book.author = Relation(author)


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
