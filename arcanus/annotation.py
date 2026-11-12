"""Public field annotations for transmuter models and dataclasses."""

from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from pydantic import AliasChoices, AliasPath
from pydantic.fields import FieldInfo

if TYPE_CHECKING:
    from arcanus.base import Transmuter

__all__ = ("AttributeInput", "Identity", "Transient", "TransientMap")

InputT = TypeVar("InputT")
SourceT = TypeVar("SourceT")
Paths = dict[str | int, "str | Paths"]


@dataclass(frozen=True)
class Identity:
    """Marker for a record's identity field(s), following SQLAlchemy's PK concept.

    Usable bare (``Identity``) or instantiated (``Identity()``) — the bare class
    takes the defaults below.

    ``server_side`` (default ``True``) declares the identity server-assigned (an
    autoincrement / IDENTITY column), so it is dropped from ``.Create``. Pass
    ``Identity(server_side=False)`` for a *natural*/composite key the client must
    supply, keeping it in ``.Create``. Mark identities ``frozen=True`` to keep
    them immutable and out of ``.Update``::

        id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
        book_id: Annotated[int, Identity(server_side=False)] = Field(frozen=True)
    """

    server_side: bool = True


class Transient:
    """Keep a field in the Pydantic contract without mapping it to a provider.

    Use as ``Annotated[T, Transient]`` or ``Annotated[T, Transient()]``.
    Provider loads use the field's default; revalidation uses existing runtime values.
    """


class TransientMap:
    """Map input paths to transient fields once when a transmuter is finalized."""

    __slots__ = ("__paths__", "__required_roots__")

    def __init__(self, fields: dict[str, FieldInfo]) -> None:
        self.__paths__: Paths = {}
        self.__required_roots__: set[str | int] = set()
        for name, info in fields.items():
            alias = info.validation_alias or info.alias or name
            aliases = alias.choices if isinstance(alias, AliasChoices) else [alias]
            if info.alias and info.alias not in aliases:
                aliases = [*aliases, info.alias]
            if name not in aliases:
                aliases = [*aliases, name]
            for index, alias in enumerate(aliases):
                keys = alias.path if isinstance(alias, AliasPath) else [alias]
                branch = self.__paths__
                for key in keys[:-1]:
                    child = branch.setdefault(key, {})
                    assert isinstance(child, dict)
                    branch = child
                branch[keys[-1]] = name
                if index == 0:
                    self.__required_roots__.add(keys[0])

    @overload
    def prepare(
        self,
        source: dict[str, SourceT],
        instance: "Transmuter | None",
    ) -> dict[str, SourceT]: ...

    @overload
    def prepare(
        self,
        source: SourceT,
        instance: "Transmuter | None",
    ) -> "SourceT | AttributeInput[SourceT]": ...

    def prepare(
        self,
        source: SourceT,
        instance: "Transmuter | None",
    ) -> "SourceT | AttributeInput[SourceT]":
        view = AttributeInput(source, self.__paths__, instance)
        if not isinstance(source, dict):
            return view
        values: SourceT = copy(source)
        for root in self.__paths__:
            if root in values or (
                instance is not None and root in self.__required_roots__
            ):
                try:
                    values[root] = view[root]
                except KeyError:
                    values.pop(root, None)
        return values


class AttributeInput(Generic[InputT]):
    """Adapt provider lookups; internal slots must not shadow field names."""

    __slots__ = ("__instance__", "__paths__", "__source__")

    def __init__(
        self, source: InputT, paths: Paths, instance: "Transmuter | None"
    ) -> None:
        self.__source__: InputT = source
        self.__paths__: Paths = paths
        self.__instance__: Transmuter | None = instance

    def __getitem__(self, key: str | int):
        path = self.__paths__.get(key)
        if isinstance(path, str):
            if self.__instance__ is None:
                raise KeyError(key)
            return getattr(self.__instance__, path)
        try:
            if isinstance(self.__source__, Mapping):
                value = self.__source__[key]
            elif isinstance(self.__source__, (list, tuple)):
                if not isinstance(key, int):
                    raise KeyError(key)
                value = self.__source__[key]
            elif isinstance(key, str):
                value = getattr(self.__source__, key)
            else:
                raise KeyError(key)
        except (AttributeError, KeyError, IndexError):
            if path is None:
                raise KeyError(key) from None
            value = None
        return AttributeInput(value, path, self.__instance__) if path else value

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None
