from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from arcanus.materia.base import BaseMateria

if TYPE_CHECKING:
    from arcanus.association import Association
    from arcanus.base import Transmuter

T = TypeVar("T", bound="Transmuter")


class RedisMateria(BaseMateria):
    key_prefixes: dict[type[Transmuter], str]

    def __init__(self) -> None:
        super().__init__()
        self.key_prefixes = {}

    def bless(self, key_prefix: str | None = None):
        """Register *transmuter_cls* with an optional Redis key prefix.

        If ``key_prefix`` is omitted, the transmuter's class name is used.
        Redis keys are formatted as ``{prefix}:{identity}``.
        """

        def decorator(transmuter_cls: type[T]) -> type[T]:
            prefix = key_prefix if key_prefix is not None else transmuter_cls.__name__
            self.key_prefixes[transmuter_cls] = prefix
            return transmuter_cls

        return decorator

    def load_association(self, association: Association) -> None:
        return

    async def aload_association(self, association: Association) -> None:
        return
