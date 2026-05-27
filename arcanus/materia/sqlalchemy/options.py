# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Literal, Self, overload, cast

from sqlalchemy import orm
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.orm.strategy_options import _AbstractLoad

from arcanus.base import Transmuter
from arcanus.expression import Column

NativeLoadAttribute = Literal["*"] | QueryableAttribute[Any]
LoadAttribute = NativeLoadAttribute | Column[Any]

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
    base_provider = cast(
        type[Any], getattr(base_cls, "__transmuter_provider__", None) or base_cls
    )
    class_providers = tuple(
        cast(type[Any], getattr(cls, "__transmuter_provider__", None) or cls)
        for cls in classes
    )
    return cast(
        LoadOption,
        orm.selectin_polymorphic(base_provider, class_providers),
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
