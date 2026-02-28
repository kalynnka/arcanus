"""Dataclass transmuter definitions for testing.

Models are created using ``@arcanus.dataclass`` which handles both
pydantic dataclass creation and transmuter protocol injection.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import ConfigDict, Field

from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
from arcanus.base import Identity, Transmuter
from arcanus.dataclass import dataclass


@dataclass
class SimpleTag(Transmuter):
    """A simple tag with no associations."""

    label: str


tag = SimpleTag(label="example")


@dataclass
class SimpleUser(Transmuter):
    """A user with default fields."""

    name: str
    age: int = 25


@dataclass(config=ConfigDict(validate_assignment=True))
class ValidatedUser(Transmuter):
    """A user with validate_assignment enabled."""

    name: str
    age: int = 25


@dataclass
class IdentifiedUser(Transmuter):
    """A user with identity fields."""

    name: str
    email: str = ""
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)


@dataclass
class PydanticItem(Transmuter):
    """A plain pydantic dataclass."""

    name: str
    score: float = 0.0


@dataclass
class DCAuthor(Transmuter):
    """An author with a collection of books."""

    name: str
    field: Literal["Physics", "Biology", "Chemistry", "Literature", "History"] = (
        "Physics"
    )
    books: RelationCollection[DCBook] = Relationships()


@dataclass
class DCPublisher(Transmuter):
    """A publisher with books."""

    name: str
    country: str = "US"
    books: RelationCollection[DCBook] = Relationships()


@dataclass
class DCBook(Transmuter):
    """A book with multiple associations."""

    title: str
    year: int = 2024
    author: Relation[DCAuthor] = Relationship()
    publisher: Relation[DCPublisher] = Relationship()
    tags: RelationCollection[SimpleTag] = Relationships()
