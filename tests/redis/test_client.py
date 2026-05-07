"""Tests for the sync Redis :class:`Client`."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from arcanus.association import Association, Relation
from arcanus.base import BaseTransmuter
from arcanus.materia.redis import RedisMateria
from tests.redis.conftest import (
    Author,
    Book,
    BookCategory,
    FakeClient,
    NoIdentity,
    Unblessed,
    User,
    redis_materia,
)


class TestKeyFormat:
    def test_default_prefix_is_class_name(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="Asimov"))
        assert client.get("Author:1") is not None

    def test_custom_prefix(self, client: FakeClient, materia_active):
        uid = uuid4()
        client.tset(User(id=uid, name="alice"))
        assert client.get(f"users:{uid}") is not None

    def test_int_ident(self, client: FakeClient, materia_active):
        client.tset(Author(id=42, name="x"))
        assert client.tget(Author, 42) is not None

    def test_str_ident_lookup(self, client: FakeClient, materia_active):
        # str(int) and int produce the same key suffix
        client.tset(Author(id=42, name="x"))
        assert client.tget(Author, "42") is not None

    def test_uuid_ident(self, client: FakeClient, materia_active):
        uid = uuid4()
        client.tset(User(id=uid, name="alice"))
        got = client.tget(User, uid)
        assert got is not None and got.name == "alice"

    def test_composite_tuple_ident(self, client: FakeClient, materia_active):
        client.tset(BookCategory(book_id=10, category_id=20))
        assert client.get("BookCategory:10:20") is not None
        got = client.tget(BookCategory, (10, 20))
        assert got is not None and got.book_id == 10 and got.category_id == 20


class TestCRUD:
    def test_set_get_roundtrip(self, client: FakeClient, materia_active):
        a = Author(id=1, name="Asimov")
        client.tset(a)
        loaded = client.tget(Author, 1)
        assert loaded is not None
        assert isinstance(loaded, Author)
        assert loaded.id == 1
        assert loaded.name == "Asimov"

    def test_get_missing_returns_none(self, client: FakeClient, materia_active):
        assert client.tget(Author, 999) is None

    def test_delete_existing(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="x"))
        assert client.tdelete(Author, 1) == 1
        assert client.tget(Author, 1) is None

    def test_delete_missing(self, client: FakeClient, materia_active):
        assert client.tdelete(Author, 999) == 0

    def test_delete_variadic(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="a"))
        client.tset(Author(id=2, name="b"))
        client.tset(Author(id=3, name="c"))
        assert client.tdelete(Author, 1, 2, 3) == 3
        assert client.tget(Author, 1) is None
        assert client.tget(Author, 2) is None
        assert client.tget(Author, 3) is None

    def test_delete_empty_returns_zero(self, client: FakeClient, materia_active):
        assert client.tdelete(Author) == 0

    def test_mget_all_hits(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="a"))
        client.tset(Author(id=2, name="b"))
        results = client.tmget(Author, 1, 2)
        assert len(results) == 2
        assert results[0] is not None and results[0].name == "a"
        assert results[1] is not None and results[1].name == "b"

    def test_mget_mixed_hits_and_misses(
        self, client: FakeClient, materia_active
    ):
        client.tset(Author(id=1, name="a"))
        client.tset(Author(id=3, name="c"))
        results = client.tmget(Author, 1, 2, 3)
        assert results[0] is not None and results[0].name == "a"
        assert results[1] is None
        assert results[2] is not None and results[2].name == "c"

    def test_mget_all_misses(self, client: FakeClient, materia_active):
        assert client.tmget(Author, 100, 200, 300) == [None, None, None]

    def test_mget_empty_returns_empty(self, client: FakeClient, materia_active):
        assert client.tmget(Author) == []

    def test_mget_preserves_order(self, client: FakeClient, materia_active):
        for i in range(5):
            client.tset(Author(id=i, name=f"a{i}"))
        results = client.tmget(Author, 4, 0, 2, 1, 3)
        assert [r.name for r in results if r is not None] == ["a4", "a0", "a2", "a1", "a3"]


class TestNativeRedisPassthrough:
    """The native get/set/delete/mget must keep working unchanged."""

    def test_native_set_get(self, client: FakeClient):
        client.set("raw-key", "raw-value")
        assert client.get("raw-key") == b"raw-value"

    def test_native_delete(self, client: FakeClient):
        client.set("k1", "v1")
        client.set("k2", "v2")
        assert client.delete("k1", "k2") == 2

    def test_native_mget(self, client: FakeClient):
        client.set("k1", "v1")
        client.set("k2", "v2")
        assert client.mget(["k1", "missing", "k2"]) == [b"v1", None, b"v2"]


class TestSerialization:
    def test_nested_relation_roundtrip(self, client: FakeClient, materia_active):
        # Loaded association: explicit value triggers serialization
        author = Author(id=1, name="Asimov")
        book = Book(id=42, title="Foundation", author=Relation(author))
        client.tset(book)

        loaded = client.tget(Book, 42)
        assert loaded is not None
        assert loaded.title == "Foundation"
        assert loaded.author.value is not None
        assert loaded.author.value.name == "Asimov"

    def test_unloaded_associations_excluded_from_dump(
        self, client: FakeClient, materia_active
    ):
        # Author with no .books set → unloaded → not in JSON → tget rehydrates
        # and accessing .books triggers load_association which is a noop
        client.tset(Author(id=1, name="a"))
        loaded = client.tget(Author, 1)
        assert loaded is not None
        assert loaded.name == "a"
        # books is unloaded; the noop materia returns None which validates to []
        assert list(loaded.books) == []


class TestErrors:
    def test_missing_materia_raises(self, client: FakeClient):
        # NOT using the materia_active fixture
        with pytest.raises(RuntimeError, match="RedisMateria"):
            client.tget(Author, 1)

    def test_unblessed_transmuter_raises_key_error(
        self, client: FakeClient, materia_active
    ):
        with pytest.raises(KeyError):
            client.tset(Unblessed(id=1, name="x"))

    def test_no_identity_fields_raises_value_error(
        self, client: FakeClient, materia_active
    ):
        with pytest.raises(ValueError, match="no Identity fields"):
            client.tset(NoIdentity(name="x"))


class TestTTL:
    def test_set_with_ex_seconds(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="x"), ex=60)
        ttl = cast(int, client.ttl("Author:1"))
        assert 0 < ttl <= 60

    def test_set_without_ex_has_no_ttl(self, client: FakeClient, materia_active):
        client.tset(Author(id=1, name="x"))
        # -1 = key exists with no expiry
        assert cast(int, client.ttl("Author:1")) == -1


class TestRedisMateria:
    def test_load_association_is_noop(self):
        m = RedisMateria()
        # association arg is unused by the noop, just need a placeholder
        assert m.load_association(cast(Association, None)) is None

    def test_bless_returns_decorated_class(self):
        m = RedisMateria()

        @m.bless()
        class T(BaseTransmuter):
            pass

        assert m.key_prefixes[T] == "T"

    def test_bless_with_custom_prefix(self):
        m = RedisMateria()

        @m.bless(key_prefix="custom")
        class T(BaseTransmuter):
            pass

        assert m.key_prefixes[T] == "custom"

    def test_bless_positional_prefix(self):
        m = RedisMateria()

        @m.bless("positional")
        class T(BaseTransmuter):
            pass

        assert m.key_prefixes[T] == "positional"


class TestMateriaContext:
    def test_aload_association_is_noop(self):
        import asyncio

        m = RedisMateria()
        # placeholder association; noop ignores it
        assert asyncio.run(m.aload_association(cast(Association, None))) is None

    def test_nested_materia_context(self, client: FakeClient):
        # Verify nested `with redis_materia:` works (shallow copy each time)
        with redis_materia:
            client.tset(Author(id=1, name="outer"))
            with redis_materia():  # nested
                client.tset(Author(id=2, name="inner"))
            # Both writes hit the same fake server
            outer = client.tget(Author, 1)
            inner = client.tget(Author, 2)
            assert outer is not None and outer.name == "outer"
            assert inner is not None and inner.name == "inner"
