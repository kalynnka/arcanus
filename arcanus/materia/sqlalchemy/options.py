# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal, Self, TypeVar, cast, overload

from sqlalchemy import orm
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.orm.strategy_options import _AbstractLoad
from sqlalchemy.orm.util import AliasedClass

from arcanus.base import Transmuter
from arcanus.expression import Column
from arcanus.materia.base import active_materia

NativeLoadAttribute = Literal["*"] | QueryableAttribute[Any]
LoadAttribute = NativeLoadAttribute | Column[Any]
T1 = TypeVar("T1", bound=Transmuter)
T2 = TypeVar("T2", bound=Transmuter)
T3 = TypeVar("T3", bound=Transmuter)

if TYPE_CHECKING:

    class LoadOption(_AbstractLoad):
        @overload
        def contains_eager(self, attr: Column[Any], **kwargs: Any) -> Self: ...

        @overload
        def contains_eager(self, attr: NativeLoadAttribute, **kwargs: Any) -> Self: ...

        def contains_eager(self, attr: LoadAttribute, **kwargs: Any) -> Self: ...

        @overload
        def defaultload(self, attr: Column[Any]) -> Self: ...

        @overload
        def defaultload(self, attr: NativeLoadAttribute) -> Self: ...

        def defaultload(self, attr: LoadAttribute) -> Self: ...

        @overload
        def defer(self, key: Column[Any], raiseload: bool = False) -> Self: ...

        @overload
        def defer(self, key: NativeLoadAttribute, raiseload: bool = False) -> Self: ...

        def defer(self, key: LoadAttribute, raiseload: bool = False) -> Self: ...

        @overload
        def joinedload(self, attr: Column[Any], **kwargs: Any) -> Self: ...

        @overload
        def joinedload(self, attr: NativeLoadAttribute, **kwargs: Any) -> Self: ...

        def joinedload(self, attr: LoadAttribute, **kwargs: Any) -> Self: ...

        @overload
        def lazyload(self, attr: Column[Any]) -> Self: ...

        @overload
        def lazyload(self, attr: NativeLoadAttribute) -> Self: ...

        def lazyload(self, attr: LoadAttribute) -> Self: ...

        @overload
        def load_only(self, *attrs: Column[Any], raiseload: bool = False) -> Self: ...

        @overload
        def load_only(
            self, *attrs: NativeLoadAttribute, raiseload: bool = False
        ) -> Self: ...

        @overload
        def load_only(self, *attrs: LoadAttribute, raiseload: bool = False) -> Self: ...

        def load_only(self, *attrs: LoadAttribute, raiseload: bool = False) -> Self: ...

        def noload(self, attr: LoadAttribute) -> Self: ...

        @overload
        def raiseload(self, attr: Column[Any], **kwargs: Any) -> Self: ...

        @overload
        def raiseload(self, attr: NativeLoadAttribute, **kwargs: Any) -> Self: ...

        def raiseload(self, attr: LoadAttribute, **kwargs: Any) -> Self: ...

        @overload
        def selectinload(
            self, attr: Column[Any], recursion_depth: int | None = None
        ) -> Self: ...

        @overload
        def selectinload(
            self,
            attr: NativeLoadAttribute,
            recursion_depth: int | None = None,
        ) -> Self: ...

        def selectinload(
            self, attr: LoadAttribute, recursion_depth: int | None = None
        ) -> Self: ...

        @overload
        def subqueryload(self, attr: Column[Any]) -> Self: ...

        @overload
        def subqueryload(self, attr: NativeLoadAttribute) -> Self: ...

        def subqueryload(self, attr: LoadAttribute) -> Self: ...

        @overload
        def undefer(self, key: Column[Any]) -> Self: ...

        @overload
        def undefer(self, key: NativeLoadAttribute) -> Self: ...

        def undefer(self, key: LoadAttribute) -> Self: ...

else:
    LoadOption = _AbstractLoad


@overload
def attributes(
    values: tuple[Column[Any], ...],
) -> tuple[QueryableAttribute[Any], ...]: ...


@overload
def attributes(
    values: tuple[NativeLoadAttribute, ...],
) -> tuple[NativeLoadAttribute, ...]: ...


@overload
def attributes(
    values: tuple[LoadAttribute, ...],
) -> tuple[NativeLoadAttribute, ...]: ...


def attributes(values: tuple[LoadAttribute, ...]) -> tuple[NativeLoadAttribute, ...]:
    return tuple(
        cast(QueryableAttribute[Any], value()) if isinstance(value, Column) else value
        for value in values
    )


@overload
def contains_eager(*keys: Column[Any], **kwargs: Any) -> LoadOption: ...


@overload
def contains_eager(*keys: NativeLoadAttribute, **kwargs: Any) -> LoadOption: ...


@overload
def contains_eager(*keys: LoadAttribute, **kwargs: Any) -> LoadOption: ...


def contains_eager(*keys: LoadAttribute, **kwargs: Any) -> LoadOption:
    return cast(LoadOption, orm.contains_eager(*attributes(keys), **kwargs))


@overload
def defaultload(*keys: Column[Any]) -> LoadOption: ...


@overload
def defaultload(*keys: NativeLoadAttribute) -> LoadOption: ...


@overload
def defaultload(*keys: LoadAttribute) -> LoadOption: ...


def defaultload(*keys: LoadAttribute) -> LoadOption:
    return cast(LoadOption, orm.defaultload(*attributes(keys)))


@overload
def defer(
    key: Column[Any], *addl_attrs: Column[Any], raiseload: bool = False
) -> LoadOption: ...


@overload
def defer(
    key: NativeLoadAttribute,
    *addl_attrs: NativeLoadAttribute,
    raiseload: bool = False,
) -> LoadOption: ...


@overload
def defer(
    key: LoadAttribute, *addl_attrs: LoadAttribute, raiseload: bool = False
) -> LoadOption: ...


def defer(
    key: LoadAttribute, *addl_attrs: LoadAttribute, raiseload: bool = False
) -> LoadOption:
    return cast(
        LoadOption,
        orm.defer(*attributes((key, *addl_attrs)), raiseload=raiseload),
    )


@overload
def joinedload(*keys: Column[Any], **kwargs: Any) -> LoadOption: ...


@overload
def joinedload(*keys: NativeLoadAttribute, **kwargs: Any) -> LoadOption: ...


@overload
def joinedload(*keys: LoadAttribute, **kwargs: Any) -> LoadOption: ...


def joinedload(*keys: LoadAttribute, **kwargs: Any) -> LoadOption:
    return cast(LoadOption, orm.joinedload(*attributes(keys), **kwargs))


@overload
def lazyload(*keys: Column[Any]) -> LoadOption: ...


@overload
def lazyload(*keys: NativeLoadAttribute) -> LoadOption: ...


@overload
def lazyload(*keys: LoadAttribute) -> LoadOption: ...


def lazyload(*keys: LoadAttribute) -> LoadOption:
    return cast(LoadOption, orm.lazyload(*attributes(keys)))


@overload
def load_only(*attrs: Column[Any], raiseload: bool = False) -> LoadOption: ...


@overload
def load_only(*attrs: NativeLoadAttribute, raiseload: bool = False) -> LoadOption: ...


@overload
def load_only(*attrs: LoadAttribute, raiseload: bool = False) -> LoadOption: ...


def load_only(*attrs: LoadAttribute, raiseload: bool = False) -> LoadOption:
    return cast(LoadOption, orm.load_only(*attributes(attrs), raiseload=raiseload))


@overload
def noload(*keys: Column[Any]) -> LoadOption: ...


@overload
def noload(*keys: NativeLoadAttribute) -> LoadOption: ...


@overload
def noload(*keys: LoadAttribute) -> LoadOption: ...


def noload(*keys: LoadAttribute) -> LoadOption:
    return cast(LoadOption, orm.noload(*attributes(keys)))


@overload
def raiseload(*keys: Column[Any], **kwargs: Any) -> LoadOption: ...


@overload
def raiseload(*keys: NativeLoadAttribute, **kwargs: Any) -> LoadOption: ...


@overload
def raiseload(*keys: LoadAttribute, **kwargs: Any) -> LoadOption: ...


def raiseload(*keys: LoadAttribute, **kwargs: Any) -> LoadOption:
    return cast(LoadOption, orm.raiseload(*attributes(keys), **kwargs))


@overload
def selectinload(
    *keys: Column[Any], recursion_depth: int | None = None
) -> LoadOption: ...


@overload
def selectinload(
    *keys: NativeLoadAttribute, recursion_depth: int | None = None
) -> LoadOption: ...


@overload
def selectinload(
    *keys: LoadAttribute, recursion_depth: int | None = None
) -> LoadOption: ...


def selectinload(
    *keys: LoadAttribute, recursion_depth: int | None = None
) -> LoadOption:
    return cast(
        LoadOption,
        orm.selectinload(*attributes(keys), recursion_depth=recursion_depth),
    )


@overload
def selectin_polymorphic(
    base_cls: type[Transmuter], classes: Iterable[type[Transmuter]]
) -> LoadOption: ...


@overload
def selectin_polymorphic(
    base_cls: type[Any], classes: Iterable[type[Any]]
) -> LoadOption: ...


def selectin_polymorphic(
    base_cls: type[Any], classes: Iterable[type[Any]]
) -> LoadOption:
    base_provider = provider_type(base_cls)
    class_providers = tuple(provider_type(cls) for cls in classes)
    return cast(
        LoadOption,
        orm.selectin_polymorphic(base_provider, class_providers),
    )


def provider_type(cls: type[Any]) -> type[Any]:
    if isinstance(cls, type) and issubclass(cls, Transmuter):
        return cast(type[Any], active_materia.get().formulars.get(cls) or cls)
    return cls


@overload
def with_polymorphic(
    base_cls: type[Any],
    classes: tuple[type[T1]],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[T1]: ...


@overload
def with_polymorphic(
    base_cls: type[Any],
    classes: tuple[type[T1], type[T2]],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[T1 | T2]: ...


@overload
def with_polymorphic(
    base_cls: type[Any],
    classes: tuple[type[T1], type[T2], type[T3]],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[T1 | T2 | T3]: ...


@overload
def with_polymorphic(
    base_cls: type[Any],
    classes: Literal["*"],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[Any]: ...


@overload
def with_polymorphic(
    base_cls: type[Any],
    classes: Iterable[type[Any]],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[Any]: ...


def with_polymorphic(
    base_cls: type[Any],
    classes: Iterable[type[Any]] | Literal["*"],
    selectable: Any = False,
    flat: bool = False,
    polymorphic_on: Any = None,
    aliased: bool = False,
    innerjoin: bool = False,
    adapt_on_names: bool = False,
    name: str | None = None,
    _use_mapper_path: bool = False,
) -> AliasedClass[Any]:
    base_provider = provider_type(base_cls)
    if classes == "*":
        class_providers: Iterable[type[Any]] | Literal["*"] = "*"
    else:
        class_providers = tuple(provider_type(cls) for cls in classes)
    native_polymorphic_on = (
        polymorphic_on() if isinstance(polymorphic_on, Column) else polymorphic_on
    )
    return cast(
        AliasedClass[Any],
        orm.with_polymorphic(
            base_provider,
            class_providers,
            selectable=selectable,
            flat=flat,
            polymorphic_on=native_polymorphic_on,
            aliased=aliased,
            innerjoin=innerjoin,
            adapt_on_names=adapt_on_names,
            name=name,
            _use_mapper_path=_use_mapper_path,
        ),
    )


@overload
def subqueryload(*keys: Column[Any]) -> LoadOption: ...


@overload
def subqueryload(*keys: NativeLoadAttribute) -> LoadOption: ...


@overload
def subqueryload(*keys: LoadAttribute) -> LoadOption: ...


def subqueryload(*keys: LoadAttribute) -> LoadOption:
    return cast(LoadOption, orm.subqueryload(*attributes(keys)))


@overload
def undefer(key: Column[Any], *addl_attrs: Column[Any]) -> LoadOption: ...


@overload
def undefer(
    key: NativeLoadAttribute, *addl_attrs: NativeLoadAttribute
) -> LoadOption: ...


@overload
def undefer(key: LoadAttribute, *addl_attrs: LoadAttribute) -> LoadOption: ...


def undefer(key: LoadAttribute, *addl_attrs: LoadAttribute) -> LoadOption:
    return cast(LoadOption, orm.undefer(*attributes((key, *addl_attrs))))
