from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Self,
    TypeVar,
    cast,
)
from uuid import UUID

import redis
import redis.asyncio

from arcanus.base import Transmuter, TransmuterMetaclass
from arcanus.materia.base import active_materia
from arcanus.materia.redis.base import RedisMateria
from arcanus.utils import get_cached_adapter

if TYPE_CHECKING:
    from redis.typing import AbsExpiryT, ExpiryT

T = TypeVar("T", bound=Transmuter)

ScalarIdentT = str | int | UUID
IdentT = ScalarIdentT | tuple[ScalarIdentT, ...]


def _make_key(entity: type[Transmuter], ident: IdentT) -> str:
    materia = active_materia.get()
    if not isinstance(materia, RedisMateria):
        # Guards ambient context, not an argument type: RuntimeError is right.
        raise RuntimeError(  # noqa: TRY004
            "No active RedisMateria found. Activate one with 'with redis_materia:' "
            "before calling transmuter-aware client helpers."
        )
    suffix = ":".join(str(x) for x in ident) if isinstance(ident, tuple) else str(ident)
    return f"{materia.key_prefixes[entity]}:{suffix}"


def _instance_key(instance: Transmuter) -> str:
    meta = cast(TransmuterMetaclass, type(instance))
    identities = meta.__transmuter_identities__
    if not identities:
        raise ValueError(
            f"Transmuter {type(instance).__name__} has no Identity fields; "
            "cannot derive a Redis key automatically."
        )
    ident = tuple(getattr(instance, field) for field in identities)
    return _make_key(type(instance), ident)


class Redis(redis.Redis):
    """Subclass of :class:`redis.Redis` that adds transmuter-aware helpers.

    The native ``get``/``set``/``delete``/``mget`` methods are untouched and
    continue to behave exactly like the parent class. The ``t*`` helpers below
    operate on :class:`Transmuter` instances and store/retrieve them as JSON.

    The active :class:`RedisMateria` is read from the context var, so the caller
    is responsible for activating it (``with redis_materia:``) before invoking
    any ``t*`` helper.
    """

    if TYPE_CHECKING:

        @classmethod
        def from_url(cls, url: str, **kwargs: Any) -> Self: ...

    def tget(self, entity: type[T], ident: IdentT) -> T | None:
        key = _make_key(entity, ident)
        data = cast(bytes | None, self.get(key))
        if data is None:
            return None
        return get_cached_adapter(entity).validate_json(data)

    def tset(
        self,
        instance: Transmuter,
        ex: ExpiryT | None = None,
        px: ExpiryT | None = None,
        nx: bool = False,
        xx: bool = False,
        keepttl: bool = False,
        exat: AbsExpiryT | None = None,
        pxat: AbsExpiryT | None = None,
    ) -> bool | None:
        key = _instance_key(instance)
        payload = get_cached_adapter(type(instance)).dump_json(instance)
        return cast(
            bool | None,
            self.set(
                key,
                payload,
                ex=ex,
                px=px,
                nx=nx,
                xx=xx,
                keepttl=keepttl,
                exat=exat,
                pxat=pxat,
            ),
        )

    def tdelete(self, entity: type[Transmuter], *idents: IdentT) -> int:
        if not idents:
            return 0
        keys = [_make_key(entity, i) for i in idents]
        return cast(int, self.delete(*keys))

    def tmget(self, entity: type[T], *idents: IdentT) -> list[T | None]:
        if not idents:
            return []
        keys = [_make_key(entity, i) for i in idents]
        raw = cast(list[bytes | None], self.mget(keys))
        adapter = get_cached_adapter(entity)
        return [adapter.validate_json(v) if v is not None else None for v in raw]


class AsyncRedis(redis.asyncio.Redis):
    """Async counterpart of :class:`Redis`. See :class:`Redis` for details."""

    if TYPE_CHECKING:

        @classmethod
        def from_url(
            cls,
            url: str,
            single_connection_client: bool = False,
            auto_close_connection_pool: bool | None = None,
            **kwargs: Any,
        ) -> Self: ...

    async def tget(self, entity: type[T], ident: IdentT) -> T | None:
        key = _make_key(entity, ident)
        data: bytes | None = await self.get(key)
        if data is None:
            return None
        return get_cached_adapter(entity).validate_json(data)

    async def tset(
        self,
        instance: Transmuter,
        ex: ExpiryT | None = None,
        px: ExpiryT | None = None,
        nx: bool = False,
        xx: bool = False,
        keepttl: bool = False,
        exat: AbsExpiryT | None = None,
        pxat: AbsExpiryT | None = None,
    ) -> bool | None:
        key = _instance_key(instance)
        payload = get_cached_adapter(type(instance)).dump_json(instance)
        result: bool | None = await self.set(
            key,
            payload,
            ex=ex,
            px=px,
            nx=nx,
            xx=xx,
            keepttl=keepttl,
            exat=exat,
            pxat=pxat,
        )
        return result

    async def tdelete(self, entity: type[Transmuter], *idents: IdentT) -> int:
        if not idents:
            return 0
        keys = [_make_key(entity, i) for i in idents]
        result: int = await self.delete(*keys)
        return result

    async def tmget(self, entity: type[T], *idents: IdentT) -> list[T | None]:
        if not idents:
            return []
        keys = [_make_key(entity, i) for i in idents]
        raw = await self.mget(keys)
        adapter = get_cached_adapter(entity)
        return [adapter.validate_json(v) if v is not None else None for v in raw]
