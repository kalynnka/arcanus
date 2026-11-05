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

    def bless(self, materia: str | None = None, *, key_prefix: str | None = None):
        """Register *transmuter_cls* with an optional Redis key prefix.

        Pass the prefix positionally, as ``key_prefix``, or as ``materia`` for
        compatibility with BaseMateria. It defaults to the transmuter's class
        name. Redis keys are formatted as ``{prefix}:{identity}``.
        """

        if materia is not None and key_prefix is not None:
            raise TypeError("Specify either materia or key_prefix, not both.")
        prefix = key_prefix if key_prefix is not None else materia

        def decorator(transmuter_cls: type[T]) -> type[T]:
            self.key_prefixes[transmuter_cls] = (
                prefix if prefix is not None else transmuter_cls.__name__
            )
            return transmuter_cls

        return decorator

    def load_association(self, association: Association) -> None:
        return

    async def aload_association(self, association: Association) -> None:
        return
