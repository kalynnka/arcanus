"""Custom ``@dataclass`` decorator for creating transmuter dataclasses.

This module provides :func:`dataclass`, a drop-in replacement for
``@pydantic.dataclasses.dataclass`` that additionally mixes in
:class:`~arcanus.base.Transmuter` and uses
:class:`~arcanus.base.TransmuterMetaclass`.

Three input forms are supported:

1. A plain class → converted to a pydantic dataclass, then to a transmuter.
2. A stdlib ``@dataclasses.dataclass`` → converted to a pydantic dataclass,
   then to a transmuter.
3. A ``@pydantic.dataclasses.dataclass`` → converted to a transmuter directly.

Circular forward references between dataclass transmuters are handled
automatically via a deferred-rebuild mechanism: if ``rebuild_dataclass``
fails because a referenced type does not exist yet, the rebuild is
queued and retried each time a new transmuter dataclass is created.

.. todo::

   If Python gains intersection types (``type[T & TransmuterProtocol]``),
   the ``@dataclass`` return type could express both the original class
   and the transmuter interface, eliminating the need for users to
   explicitly inherit from ``Transmuter`` for full static type
   visibility.  No PEP exists for this yet; track discussions at
   https://github.com/python/typing/issues/213
"""

from __future__ import annotations

import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    TypeVar,
    dataclass_transform,
    overload,
)

from pydantic import PydanticUndefinedAnnotation
from pydantic._internal._decorators import DecoratorInfos
from pydantic.config import ConfigDict
from pydantic.dataclasses import dataclass as pdc_dataclass
from pydantic.dataclasses import is_pydantic_dataclass, rebuild_dataclass
from pydantic.fields import Field, PrivateAttr

from arcanus.base import Transmuter, TransmuterMetaclass

if TYPE_CHECKING:
    from pydantic._internal._dataclasses import PydanticDataclass

__all__ = ("dataclass", "make_transmuter_dataclass")

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Deferred forward-reference rebuild helpers
# ---------------------------------------------------------------------------

# Transmuter dataclasses whose ``rebuild_dataclass`` was deferred because
# one or more forward-referenced types were not yet available.
_deferred_transmuter_dataclasses: list[TransmuterMetaclass] = []


def _rebuild_transmuter_dataclass(cls: TransmuterMetaclass) -> bool:
    """Try to ``rebuild_dataclass`` a transmuter and finalize it.

    Returns ``True`` if the rebuild succeeded, ``False`` if it was
    deferred because forward refs could not be resolved yet.
    """
    module = sys.modules.get(cls.__module__)
    types_ns = vars(module) if module else None
    try:
        rebuild_dataclass(cls, force=True, _types_namespace=types_ns)  # type: ignore[arg-type]
    except PydanticUndefinedAnnotation:
        return False
    cls._finalize_transmuter()
    return True


def _retry_deferred_transmuters() -> None:
    """Retry ``rebuild_dataclass`` for all previously deferred transmuters.

    Called after each new transmuter dataclass is created so that
    circular forward references are resolved once all classes exist.
    """
    still_deferred: list[TransmuterMetaclass] = []
    for dc_cls in _deferred_transmuter_dataclasses:
        if getattr(dc_cls, "__transmuter_complete__", False):
            continue
        if not _rebuild_transmuter_dataclass(dc_cls):
            still_deferred.append(dc_cls)
    _deferred_transmuter_dataclasses[:] = still_deferred


# ---------------------------------------------------------------------------
# make_transmuter_dataclass – low-level helper
# ---------------------------------------------------------------------------


def make_transmuter_dataclass(cls: type[PydanticDataclass]) -> type:
    """Create a transmuter subclass from a pydantic dataclass.

    The input *cls* must be a valid ``@pydantic.dataclasses.dataclass``.
    A new subclass is created with :class:`Transmuter` mixed in
    and :class:`TransmuterMetaclass` as its metaclass.  The pydantic
    schema is then rebuilt so that ``model_formulate`` from the protocol
    is picked up.

    If some forward-referenced annotations cannot be resolved yet (e.g.
    circular references between dataclass transmuters), the rebuild is
    deferred and automatically retried when subsequent transmuters are
    created.
    """
    if not is_pydantic_dataclass(cls):
        raise TypeError(
            f"{cls.__qualname__} is not a pydantic dataclass. "
            f"Apply @pydantic.dataclasses.dataclass first."
        )

    # Already a completed transmuter — return as-is
    if isinstance(cls, TransmuterMetaclass) and getattr(
        cls, "__transmuter_complete__", False
    ):
        return cls

    # Create a subclass that mixes in the transmuter mixin.
    # TransmuterMetaclass.__new__ takes the dataclass path (type.__new__)
    # because no base is a ModelMetaclass instance.
    # If cls already inherits from Transmuter (e.g. the user
    # declared it in source code for type-checking), skip the mixin
    # to avoid an MRO conflict.
    if issubclass(cls, Transmuter):
        bases: tuple[type, ...] = (cls,)
    else:
        bases = (Transmuter, cls)

    new_cls = TransmuterMetaclass(cls.__name__, bases, {})
    new_cls.__module__ = cls.__module__
    new_cls.__qualname__ = cls.__qualname__

    # Re-scan decorators so model_formulate from Transmuter
    # is included, then rebuild the pydantic schema in-place.
    new_cls.__pydantic_decorators__ = DecoratorInfos.build(new_cls)  # type: ignore[attr-defined]

    # Early-bind the name in module globals so that forward references
    # from other (deferred) transmuters can resolve this class.
    module = sys.modules.get(cls.__module__)
    if module is not None:
        setattr(module, cls.__name__, new_cls)

    if not _rebuild_transmuter_dataclass(new_cls):
        _deferred_transmuter_dataclasses.append(new_cls)

    # Retry any previously deferred transmuters now that a new name
    # may have become available in the module namespace.
    _retry_deferred_transmuters()

    return new_cls


# ---------------------------------------------------------------------------
# @dataclass – public decorator
# ---------------------------------------------------------------------------


@dataclass_transform(field_specifiers=(Field, PrivateAttr))
@overload
def dataclass(
    _cls: type[_T],
    *,
    init: Literal[False] = False,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool | None = None,
    config: ConfigDict | type[object] | None = None,
    kw_only: bool = ...,
    slots: bool = ...,
) -> type[_T]: ...


@dataclass_transform(field_specifiers=(Field, PrivateAttr))
@overload
def dataclass(
    _cls: None = None,
    *,
    init: Literal[False] = False,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool | None = None,
    config: ConfigDict | type[object] | None = None,
    kw_only: bool = ...,
    slots: bool = ...,
) -> Callable[[type[_T]], type[_T]]: ...


def dataclass(
    _cls: type[_T] | None = None,
    *,
    init: Literal[False] = False,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool | None = None,
    config: ConfigDict | type[object] | None = None,
    kw_only: bool = False,
    slots: bool = False,
) -> Callable[[type[_T]], type[_T]] | type[_T]:
    """Create a transmuter dataclass.

    Works like ``@pydantic.dataclasses.dataclass`` but additionally mixes
    in :class:`~arcanus.base.Transmuter`.  Accepts plain classes,
    stdlib dataclasses, and pydantic dataclasses as input.

    Can be used as a bare decorator (``@dataclass``) or with keyword
    arguments (``@dataclass(config=...)``)::

        @dataclass
        class Foo:
            name: str

        @dataclass(config=ConfigDict(validate_assignment=True))
        class Bar:
            value: int = 0
    """

    def process(cls: type[_T]) -> type[_T]:
        inner_cls: Any = cls
        # Step 1: ensure it's a pydantic dataclass
        if not is_pydantic_dataclass(inner_cls):
            inner_cls = pdc_dataclass(
                inner_cls,
                init=init,
                repr=repr,
                eq=eq,
                order=order,
                unsafe_hash=unsafe_hash,
                frozen=frozen,
                config=config,
                kw_only=kw_only,
                slots=slots,
            )
        # Step 2: convert to transmuter
        return make_transmuter_dataclass(inner_cls)  # type: ignore[return-value]

    if _cls is not None:
        return process(_cls)
    return process
