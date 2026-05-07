"""Tests for the async Redis :class:`AsyncClient` (mirrors test_client.py)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from arcanus.association import Relation
from tests.redis.conftest import (
    Author,
    Book,
    BookCategory,
    FakeAsyncClient,
    NoIdentity,
    Unblessed,
    User,
)


class TestKeyFormat:
    async def test_default_prefix_is_class_name(
        self, async_client: FakeAsyncClient, materia_active
    ):
        await async_client.tset(Author(id=1, name="Asimov"))
        assert await async_client.get("Author:1") is not None

    async def test_custom_prefix(self, async_client: FakeAsyncClient, materia_active):
        uid = uuid4()
        await async_client.tset(User(id=uid, name="alice"))
        assert await async_client.get(f"users:{uid}") is not None

    async def test_uuid_ident(self, async_client: FakeAsyncClient, materia_active):
        uid = uuid4()
        await async_client.tset(User(id=uid, name="alice"))
        got = await async_client.tget(User, uid)
        assert got is not None and got.name == "alice"

    async def test_composite_tuple_ident(
        self, async_client: FakeAsyncClient, materia_active
    ):
        await async_client.tset(BookCategory(book_id=10, category_id=20))
        got = await async_client.tget(BookCategory, (10, 20))
        assert got is not None and got.book_id == 10


class TestCRUD:
    async def test_set_get_roundtrip(
        self, async_client: FakeAsyncClient, materia_active
    ):
        await async_client.tset(Author(id=1, name="Asimov"))
        loaded = await async_client.tget(Author, 1)
        assert loaded is not None and loaded.name == "Asimov"
        assert isinstance(loaded, Author)

    async def test_get_missing_returns_none(
        self, async_client: FakeAsyncClient, materia_active
    ):
        assert await async_client.tget(Author, 999) is None

    async def test_delete_existing(self, async_client: FakeAsyncClient, materia_active):
        await async_client.tset(Author(id=1, name="x"))
        assert await async_client.tdelete(Author, 1) == 1
        assert await async_client.tget(Author, 1) is None

    async def test_delete_variadic(self, async_client: FakeAsyncClient, materia_active):
        for i in (1, 2, 3):
            await async_client.tset(Author(id=i, name=f"a{i}"))
        assert await async_client.tdelete(Author, 1, 2, 3) == 3

    async def test_delete_empty_returns_zero(
        self, async_client: FakeAsyncClient, materia_active
    ):
        assert await async_client.tdelete(Author) == 0

    async def test_mget_mixed_hits_and_misses(
        self, async_client: FakeAsyncClient, materia_active
    ):
        await async_client.tset(Author(id=1, name="a"))
        await async_client.tset(Author(id=3, name="c"))
        results = await async_client.tmget(Author, 1, 2, 3)
        assert results[0] is not None and results[0].name == "a"
        assert results[1] is None
        assert results[2] is not None and results[2].name == "c"

    async def test_mget_empty_returns_empty(
        self, async_client: FakeAsyncClient, materia_active
    ):
        assert await async_client.tmget(Author) == []


class TestNativeRedisPassthrough:
    async def test_native_set_get(self, async_client: FakeAsyncClient):
        await async_client.set("raw-key", "raw-value")
        assert await async_client.get("raw-key") == b"raw-value"

    async def test_native_delete(self, async_client: FakeAsyncClient):
        await async_client.set("k1", "v1")
        await async_client.set("k2", "v2")
        assert await async_client.delete("k1", "k2") == 2


class TestSerialization:
    async def test_nested_relation_roundtrip(
        self, async_client: FakeAsyncClient, materia_active
    ):
        author = Author(id=1, name="Asimov")
        book = Book(id=42, title="Foundation", author=Relation(author))
        await async_client.tset(book)

        loaded = await async_client.tget(Book, 42)
        assert loaded is not None
        assert loaded.author.value is not None
        assert loaded.author.value.name == "Asimov"


class TestErrors:
    async def test_missing_materia_raises(self, async_client: FakeAsyncClient):
        with pytest.raises(RuntimeError, match="RedisMateria"):
            await async_client.tget(Author, 1)

    async def test_unblessed_transmuter_raises_key_error(
        self, async_client: FakeAsyncClient, materia_active
    ):
        with pytest.raises(KeyError):
            await async_client.tset(Unblessed(id=1, name="x"))

    async def test_no_identity_fields_raises_value_error(
        self, async_client: FakeAsyncClient, materia_active
    ):
        with pytest.raises(ValueError, match="no Identity fields"):
            await async_client.tset(NoIdentity(name="x"))


class TestTTL:
    async def test_set_with_ex_seconds(
        self, async_client: FakeAsyncClient, materia_active
    ):
        await async_client.tset(Author(id=1, name="x"), ex=60)
        ttl = await async_client.ttl("Author:1")
        assert 0 < ttl <= 60
