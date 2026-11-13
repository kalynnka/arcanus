from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar, assert_type

import pytest
from pydantic import ValidationError
from sqlalchemy import IteratorResult, Result, inspect, select, update
from sqlalchemy.engine.result import SimpleResultMetaData
from sqlalchemy.ext.asyncio import AsyncResult
from sqlalchemy.orm import Session as NativeSession

from arcanus.association import (
    GroupedRelationship,
    MappedRelationship,
    RelationCollection,
    RelationGroupMap,
    RelationMap,
    RelationSet,
    Relationships,
)
from arcanus.base import (
    BaseTransmuter,
    TransmuterProxied,
    TransmuterProxiedMixin,
    validated,
)
from arcanus.materia.redis import RedisMateria
from arcanus.materia.sqlalchemy import AsyncSession, Session
from arcanus.materia.sqlalchemy.result import AdaptedResult, AsyncAdaptedResult
from tests import models, transmuters

K = TypeVar("K")
V = TypeVar("V")


class KeysOnly(Generic[K, V]):
    data: dict[K, V]

    def __init__(self, data: dict[K, V]) -> None:
        self.data = data

    def keys(self) -> list[K]:
        return list(self.data)

    def __getitem__(self, key: K) -> V:
        return self.data[key]


class Item(BaseTransmuter):
    name: str


class Collections(BaseTransmuter):
    sequence: RelationCollection[Item] = Relationships()
    items: RelationSet[Item] = Relationships(unique=True)
    mapping: RelationMap[str, Item] = MappedRelationship()
    groups: RelationGroupMap[str, Item] = GroupedRelationship()


def test_collection_extend_validates_dictionary_inputs() -> None:
    collections = Collections()
    payloads: list[dict[str, str]] = [{"name": "from dict"}]
    item = Item(name="existing")
    collections.sequence.extend(payloads)
    collections.sequence.extend([item, {"name": "mixed"}])
    assert [value.name for value in collections.sequence] == [
        "from dict",
        "existing",
        "mixed",
    ]
    assert_type(collections.sequence[0], Item)
    assert collections.sequence[1] is item
    with pytest.raises(ValidationError):
        collections.sequence.extend([{"name": 1}])
    assert len(collections.sequence) == 3


def test_heterogeneous_set_operations() -> None:
    collections = Collections()
    item = Item(name="item")
    collections.items.add(item)
    assert assert_type(collections.items.union([1]), set[Item | int]) == {item, 1}
    assert assert_type(collections.items | frozenset({1}), set[Item | int]) == {item, 1}
    assert collections.items <= frozenset({item})
    collections.items.discard("absent")
    collections.items.difference_update([1])
    assert collections.items == {item}


@pytest.mark.parametrize("equal_foreign_value", [False, True])
def test_set_discard_synchronizes_provider(equal_foreign_value: bool) -> None:
    class NamedItem(Item):
        def __hash__(self) -> int:
            return hash(self.name)

        def __eq__(self, other) -> bool:
            return self.name == other if isinstance(other, str) else self is other

    @dataclass
    class SetProvider(TransmuterProxiedMixin):
        items: set[models.Author]

    item = NamedItem(name="item")
    other = NamedItem(name="other")
    item_provider = models.Author(name="item", field="Physics")
    other_provider = models.Author(name="other", field="Physics")
    assert isinstance(item_provider, TransmuterProxied)
    assert isinstance(other_provider, TransmuterProxied)
    item.__transmuter_provided__ = item_provider
    other.__transmuter_provided__ = other_provider
    collections = Collections()
    collections.items.update([item, other])
    provider = SetProvider({item_provider, other_provider})
    assert isinstance(provider, TransmuterProxied)
    collections.__transmuter_provided__ = provider

    target = item.name if equal_foreign_value else item
    collections.items.discard(target)
    assert collections.items == {other}
    assert provider.items == {other_provider}

    collections.items.discard(target)
    assert collections.items == {other}
    assert provider.items == {other_provider}


def test_mapping_protocol_and_default_types() -> None:
    collections = Collections()
    item = Item(name="item")
    values = KeysOnly({"item": item})
    collections.mapping.update(values)
    collections.mapping |= values
    assert assert_type(collections.mapping.get("item", item), Item) is item
    assert assert_type(collections.mapping.get("missing", 1), Item | int) == 1
    assert assert_type(collections.mapping.get("missing"), Item | None) is None
    assert assert_type(
        collections.mapping | {1: "value"}, dict[str | int, Item | str]
    ) == {
        "item": item,
        1: "value",
    }
    collections.groups.update(KeysOnly({"item": [item]}))
    collections.groups |= KeysOnly({"other": [item]})
    assert assert_type(collections.groups.get("item", []), list[Item]) == [item]
    assert assert_type(collections.groups.get("missing", 1), list[Item] | int) == 1
    assert collections.groups.setdefault("empty", None) == []
    assert collections.mapping.setdefault("empty", None) is None


def test_redis_bless_keyword_compatibility() -> None:
    materia = RedisMateria()
    assert materia.bless(materia="base")(transmuter_cls=Item) is Item
    assert materia.key_prefixes[Item] == "base"
    materia.bless(key_prefix="redis")(Item)
    assert materia.key_prefixes[Item] == "redis"
    materia.bless("positional")(Item)
    assert materia.key_prefixes[Item] == "positional"
    with pytest.raises(TypeError, match="either materia or key_prefix"):
        materia.bless("base", key_prefix="redis")


def test_native_relationship_loading() -> None:
    provider = models.Author(name="Native", field="Physics")
    with Session() as session:
        session.enable_relationship_loading(provider)
        assert inspect(provider).session is session


def test_transmuter_relationship_loading_registers_validation_context() -> None:
    with transmuters.sqlalchemy_materia:
        author = transmuters.Author(name="Transmuter", field="Physics")
        provider = author.__transmuter_provided__
        assert isinstance(provider, models.Author)
        with Session() as session:
            assert provider not in validated.get()
            session.enable_relationship_loading(author)
            assert inspect(provider).session is session
            assert validated.get()[provider] is author
            assert transmuters.Author.model_validate(provider) is author


def test_mapping_result_wraps_native_result() -> None:
    source = IteratorResult(SimpleResultMetaData(["value"]), iter([(1,), (2,)]))
    result = AdaptedResult(source, entities=(int,), force_revalidate=True)
    mapping = result.mappings()
    assert mapping.fetchall() == [
        {"value": 1},
        {"value": 2},
    ]
    mapping.close()
    assert source.closed and result.closed and mapping.closed


@pytest.mark.asyncio
async def test_async_result_close() -> None:
    source = IteratorResult(SimpleResultMetaData(["value"]), iter([(1,)]))
    result = AsyncAdaptedResult(source, entities=(int,))
    await result.close()
    assert source.closed and result.closed


def test_async_session_validates_sync_session_type() -> None:
    session = AsyncSession()
    assert isinstance(session.transmuter_session, Session)
    session.sync_session.close()
    session.sync_session = NativeSession()
    with pytest.raises(TypeError, match="Arcanus sync Session"):
        _ = session.transmuter_session
    session.sync_session.close()


if TYPE_CHECKING:

    async def check_statement_types(
        session: Session, async_session: AsyncSession
    ) -> None:
        statement = select(models.Author.id, models.Author.name)
        assert_type(session.execute(statement), Result[tuple[int, str]])
        assert_type(await async_session.stream(statement), AsyncResult[tuple[int, str]])
        assert_type(session.merge(models.Author()), models.Author)
        assert_type(
            session.execute(update(models.Author).returning(models.Author.id)),
            Result[tuple[int]],
        )
