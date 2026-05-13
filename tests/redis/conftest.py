"""Fixtures and shared transmuters for Redis materia tests."""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

import fakeredis
import fakeredis.aioredis
import pytest
from pydantic import ConfigDict, Field

from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
from arcanus.base import BaseTransmuter, Identity
from arcanus.materia.redis import AsyncRedis, Redis, RedisMateria

redis_materia = RedisMateria()


@redis_materia.bless()
class Author(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection["Book"] = Relationships()


@redis_materia.bless()
class Book(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    author: Relation[Optional[Author]] = Relationship()


@redis_materia.bless(key_prefix="users")
class User(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)
    id: Annotated[UUID, Identity] = Field(frozen=True)
    name: str


@redis_materia.bless()
class BookCategory(BaseTransmuter):
    """Composite identity (book_id, category_id)."""

    model_config = ConfigDict(from_attributes=True)
    book_id: Annotated[int, Identity] = Field(frozen=True)
    category_id: Annotated[int, Identity] = Field(frozen=True)


class Unblessed(BaseTransmuter):
    """Has Identity but isn't blessed — used to test the unblessed-key error."""

    model_config = ConfigDict(from_attributes=True)
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str


@redis_materia.bless()
class NoIdentity(BaseTransmuter):
    """Blessed but has no Identity fields — used to test the missing-identity error."""

    model_config = ConfigDict(from_attributes=True)
    name: str


class FakeClient(Redis, fakeredis.FakeRedis):
    """Sync Redis backed by an in-memory fakeredis server."""


class FakeAsyncClient(AsyncRedis, fakeredis.aioredis.FakeRedis):
    """AsyncRedis backed by an in-memory fakeredis server."""


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
async def async_client() -> FakeAsyncClient:
    return FakeAsyncClient()


@pytest.fixture
def materia_active():
    """Enter the RedisMateria context for the duration of the test."""
    with redis_materia:
        yield redis_materia
