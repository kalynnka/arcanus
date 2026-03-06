from __future__ import annotations

import operator
from collections.abc import AsyncIterator, Callable
from functools import cached_property
from typing import (
    Any,
    Iterator,
    Literal,
    Optional,
    Self,
    Sequence,
    TypeVar,
    overload,
)

from pydantic import TypeAdapter
from sqlalchemy import (
    FrozenResult,
    IteratorResult,
    Result,
    Row,
    ScalarResult,
)
from sqlalchemy.engine.result import (
    _NO_ROW,
    _R,
    FilterResult,
    ResultMetaData,
    _KeyIndexType,
    _UniqueFilterType,
    _WithKeys,
)
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.sql.base import _generative
from sqlalchemy.util.concurrency import greenlet_spawn

from arcanus.utils import get_cached_adapter

_T = TypeVar("_T", bound=Any)
_TP = TypeVar("_TP", bound=tuple[Any, ...])


class AdaptedCommon(FilterResult[_R]):
    __slots__ = ()

    _real_result: Result[Any]
    _metadata: ResultMetaData

    # SQLAlchemy's C extension accesses _yield_per during _manyrow_getter
    # property creation. FilterResult does not inherit this from Result, so
    # we provide the same default here to prevent AttributeError on Python
    # versions that use the C extension (e.g. Python 3.13).
    _yield_per: Optional[int] = None

    def close(self) -> None:
        self._real_result.close()

    @property
    def closed(self) -> bool:
        return self._real_result.closed


class AdaptedResult(_WithKeys, AdaptedCommon[Row[_TP]]):
    entities: tuple[type[Any], ...]

    _real_result: Result[_TP]
    _row_logging_fn: Optional[Callable[[Row[Any]], Row[Any]]] = None

    def __init__(
        self,
        real_result: Result[_TP],
        entities: tuple[type[Any], ...] = (),
    ):
        self._real_result = real_result

        self._metadata = real_result._metadata
        self._unique_filter_state = real_result._unique_filter_state
        self._source_supports_scalars = real_result._source_supports_scalars
        self._post_creational_filter = None

        self.entities = entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(real_result, "_yield_per", None)) is not None:
            self._yield_per = yp

        # BaseCursorResult pre-generates the "_row_getter".  Use that
        # if available rather than building a second one
        if "_row_getter" in real_result.__dict__:
            self._set_memoized_attribute(
                "_row_getter", real_result.__dict__["_row_getter"]
            )

    @cached_property
    def adapter(self) -> TypeAdapter:
        """Get the adapter for tuple results."""
        return get_cached_adapter(tuple[*self.entities])

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self.entities[0])
            if self.entities
            else TypeAdapter(object)
        )

    def _adapt(self, row: Any) -> Any:
        """Adapt a row using TypeAdapter validation."""
        return self.adapter.validate_python(row)

    def _adapt_scalar(self, item: Any) -> Any:
        """Adapt a scalar result using TypeAdapter validation."""
        return self.scalar_adapter.validate_python(item)

    @property
    def t(self) -> Self:
        return self

    @property
    def tuples(self) -> Self:
        return self

    @_generative
    def unique(self, strategy: Optional[_UniqueFilterType] = None) -> Self:
        """Apply unique filtering to the objects returned by this
        :class:`_asyncio.AsyncResult`.

        Refer to :meth:`_engine.Result.unique` in the synchronous
        SQLAlchemy API for a complete behavioral description.

        """
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions: _KeyIndexType) -> Self:
        r"""Establish the columns that should be returned in each row.

        Refer to :meth:`_engine.Result.columns` in the synchronous
        SQLAlchemy API for a complete behavioral description.

        """
        return self._column_slices(col_expressions)

    def __iter__(self) -> Iterator[Row[_TP]]:
        for row in self._iter_impl():
            yield self._adapt(row)

    def __next__(self) -> Row[_TP]:
        return self._adapt(self._next_impl())

    def partitions(self, size: int | None = None) -> Iterator[Sequence[Row[_TP]]]:
        while True:
            partition = self._manyrow_getter(self, size)
            if partition:
                yield [self._adapt(row) for row in partition]
            else:
                break

    def fetchall(self) -> Sequence[Row[_TP]]:
        return [self._adapt(row) for row in self._allrows()]

    def fetchone(self) -> Optional[Row[_TP]]:
        row = self._onerow_getter(self)
        if row is _NO_ROW:
            return None
        else:
            return self._adapt(row)

    def fetchmany(self, size: int | None = None) -> Sequence[Row[_TP]]:
        return [self._adapt(row) for row in self._manyrow_getter(size)]

    def all(self) -> Sequence[Row[_TP]]:
        return [self._adapt(row) for row in self._allrows()]

    def first(self) -> Optional[Row[_TP]]:
        return (
            self._adapt(row)
            if (
                row := self._only_one_row(
                    raise_for_second_row=False,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )

    def one(self) -> Row[_TP]:
        return self._adapt(
            self._only_one_row(
                raise_for_second_row=True,
                raise_for_none=True,
                scalar=False,
            )
        )

    def one_or_none(self) -> Optional[Row[_TP]]:
        return (
            self._adapt(row)
            if (
                row := self._only_one_row(
                    raise_for_second_row=True,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )

    @overload
    def scalar(self: AdaptedResult[tuple[_T]]) -> Optional[_T]: ...

    @overload
    def scalar(self) -> Any: ...
    def scalar(self) -> Any:
        return self._adapt_scalar(
            self._only_one_row(
                raise_for_second_row=False,
                raise_for_none=False,
                scalar=True,
            )
        )

    @overload
    def scalar_one(self: AdaptedResult[tuple[_T]]) -> _T: ...

    @overload
    def scalar_one(self) -> Any: ...
    def scalar_one(self) -> Any:
        return self._adapt_scalar(
            self._only_one_row(
                raise_for_second_row=True,
                raise_for_none=True,
                scalar=True,
            )
        )

    @overload
    def scalar_one_or_none(self: AdaptedResult[tuple[_T]]) -> Optional[_T]: ...

    @overload
    def scalar_one_or_none(self) -> Optional[Any]: ...

    def scalar_one_or_none(self) -> Optional[Any]:
        return (
            self._adapt_scalar(row)
            if (
                row := self._only_one_row(
                    raise_for_second_row=True,
                    raise_for_none=False,
                    scalar=True,
                )
            )
            else None
        )

    @overload
    def scalars(self: AdaptedResult[tuple[_T]]) -> AdaptedScalarResult[_T]: ...

    @overload
    def scalars(
        self: Result[tuple[_T]], index: Literal[0]
    ) -> AdaptedScalarResult[_T]: ...

    @overload
    def scalars(self, index: _KeyIndexType = 0) -> AdaptedScalarResult[Any]: ...
    def scalars(self, index: _KeyIndexType = 0) -> AdaptedScalarResult[Any]:
        return AdaptedScalarResult(
            self,
            index=index,
            entities=self.entities,
        )

    def freeze(self) -> AdaptedFrozenResult[_TP]:
        return AdaptedFrozenResult(
            self,
            entities=self.entities,
        )

    def mappings(self) -> AdaptedMappingResult:
        return AdaptedMappingResult(self)


class AdaptedScalarResult(ScalarResult[_R]):
    _entities: tuple[type[Any], ...]

    __slots__ = ()

    _generate_rows = False
    _real_result: AdaptedResult[Any]

    def __init__(
        self,
        real_result: AdaptedResult[Any],
        index: _KeyIndexType,
        entities: tuple[type[Any], ...] = (),
    ):
        self._unique_filter_state = real_result._unique_filter_state
        self._real_result = real_result

        if real_result._source_supports_scalars:
            self._metadata = real_result._metadata
            self._post_creational_filter = None
        else:
            self._metadata = real_result._metadata._reduce([index])
            self._post_creational_filter = operator.itemgetter(0)

        self._entities = entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(real_result, "_yield_per", None)) is not None:
            self._yield_per = yp

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self._entities[0])
            if self._entities
            else TypeAdapter(object)
        )

    def _adapt_scalar(self, item: Any) -> Any:
        """Adapt a scalar result using TypeAdapter validation."""
        return self.scalar_adapter.validate_python(item)

    def unique(
        self,
        strategy: Optional[_UniqueFilterType] = None,
    ) -> Self:
        self._unique_filter_state = (set(), strategy)
        return self

    def __iter__(self) -> Iterator[_R]:
        for row in self._iter_impl():
            yield self._adapt_scalar(row)

    def __next__(self) -> _R:
        return self._adapt_scalar(self._next_impl())

    def partitions(self, size: int | None = None) -> Iterator[Sequence[_R]]:
        while True:
            partition = self._manyrow_getter(self, size)
            if partition:
                yield [self._adapt_scalar(scalar) for scalar in partition]
            else:
                break

    def fetchall(self) -> Sequence[_R]:
        return [self._adapt_scalar(scalar) for scalar in self._allrows()]

    def fetchmany(self, size: int | None = None) -> Sequence[_R]:
        return [self._adapt_scalar(scalar) for scalar in self._manyrow_getter(size)]

    def all(self) -> Sequence[_R]:
        return [self._adapt_scalar(scalar) for scalar in self._allrows()]

    def first(self) -> _R | None:
        return (
            self._adapt_scalar(row)
            if (
                row := self._only_one_row(
                    raise_for_second_row=False,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )

    def one(self) -> _R:
        return self._adapt_scalar(
            self._only_one_row(
                raise_for_second_row=True,
                raise_for_none=True,
                scalar=False,
            )
        )

    def one_or_none(self) -> _R | None:
        return (
            self._adapt_scalar(row)
            if (
                row := self._only_one_row(
                    raise_for_second_row=True,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )


class AdaptedFrozenResult(FrozenResult[_TP]):
    data: Sequence[Any]
    _entities: tuple[type[Any], ...]

    def __init__(
        self,
        result: AdaptedResult[_TP],
        entities: tuple[type[Any], ...] = (),
    ):
        self.metadata = result._metadata._for_freeze()
        self._source_supports_scalars = result._source_supports_scalars
        self._attributes = result._attributes
        self._entities = entities

        if self._source_supports_scalars:
            self.data = self._adapt_scalar(result._real_result._raw_row_iterator())
        else:
            self.data = result.fetchall()

    @cached_property
    def adapter(self) -> TypeAdapter:
        """Get the adapter for tuple results."""
        return get_cached_adapter(tuple[*self._entities])

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self._entities[0])
            if self._entities
            else TypeAdapter(object)
        )

    def _adapt_scalar(self, item: Any) -> Any:
        """Adapt a scalar result using TypeAdapter validation."""
        return self.scalar_adapter.validate_python(item)

    def rewrite_rows(self) -> Sequence[Sequence[Any]]:
        if self._source_supports_scalars:
            return [[elem] for elem in self.data]
        else:
            return [list(row) for row in self.data]

    def with_new_rows(self, tuple_data: Sequence[Row[_TP]]) -> AdaptedFrozenResult[_TP]:
        afr = AdaptedFrozenResult.__new__(AdaptedFrozenResult)
        afr.metadata = self.metadata
        afr._attributes = self._attributes
        afr._source_supports_scalars = self._source_supports_scalars
        afr._entities = self._entities

        if self._source_supports_scalars:
            afr.data = [d[0] for d in tuple_data]
        else:
            afr.data = tuple_data
        return afr

    def __call__(self) -> Result[_TP]:
        result = IteratorResult(
            self.metadata,
            iter(self.data),
        )
        result._attributes = self._attributes  # type: ignore
        result._source_supports_scalars = self._source_supports_scalars
        return result


class AdaptedMappingResult(_WithKeys, AdaptedCommon[RowMapping]):
    __slots__ = ()

    _generate_rows = True
    _post_creational_filter = operator.attrgetter("_mapping")

    _real_result: AdaptedResult[Any]
    _entities: tuple[type[Any], ...]

    def __init__(self, result: AdaptedResult[Any]):
        self._real_result = result
        self._metadata = result._metadata
        self._unique_filter_state = result._unique_filter_state
        if result._source_supports_scalars:
            self._metadata = self._metadata._reduce([0])

        self._entities = result.entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(result, "_yield_per", None)) is not None:
            self._yield_per = yp

    @cached_property
    def adapter(self) -> TypeAdapter:
        """Get the adapter for tuple results."""
        return get_cached_adapter(tuple[*self._entities])

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self._entities[0])
            if self._entities
            else TypeAdapter(object)
        )

    def _adapt(self, row: Any) -> Any:
        """Adapt a row using TypeAdapter validation."""
        return self.adapter.validate_python(row)

    @_generative
    def unique(self, strategy: Optional[_UniqueFilterType] = None) -> Self:
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions: _KeyIndexType) -> Self:
        return self._column_slices(col_expressions)

    def partitions(self, size: int | None = None) -> Iterator[Sequence[dict[str, Any]]]:
        while True:
            partition = self._manyrow_getter(self, size)
            if partition:
                yield list(
                    dict(zip(row.keys(), self._adapt(row.values())))
                    for row in partition
                )
            else:
                break

    def fetchone(self) -> Optional[dict[str, Any]]:
        row = self._onerow_getter(self)
        if row is _NO_ROW:
            return None
        else:
            return dict(zip(row.keys(), self._adapt(row.values())))

    def fetchmany(self, size: int | None = None) -> Sequence[dict[str, Any]]:
        return list(
            dict(zip(row.keys(), self._adapt(row.values())))
            for row in self._manyrow_getter(size)
        )

    def fetchall(self) -> Sequence[dict[str, Any]]:
        """A synonym for the :meth:`AdaptedMappingResult.all` method."""
        return list(
            dict(zip(row.keys(), self._adapt(row.values()))) for row in self._allrows()
        )

    def first(self) -> dict[str, Any] | None:
        return (
            dict(zip(row.keys(), self._adapt(row.values())))
            if (
                row := self._only_one_row(
                    raise_for_second_row=False,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )

    def all(self) -> Sequence[dict[str, Any]]:
        return list(
            dict(zip(row.keys(), self._adapt(row.values()))) for row in self._allrows()
        )

    def one(self) -> dict[str, Any]:
        row = self._only_one_row(
            raise_for_second_row=True,
            raise_for_none=True,
            scalar=False,
        )
        return dict(zip(row.keys(), self._adapt(row.values())))

    def one_or_none(self) -> dict[str, Any] | None:
        return (
            dict(zip(row.keys(), self._adapt(row.values())))
            if (
                row := self._only_one_row(
                    raise_for_second_row=True,
                    raise_for_none=False,
                    scalar=False,
                )
            )
            else None
        )


class AsyncAdaptedCommon(FilterResult[_R]):
    """Base class for async adapted results with common functionality."""

    __slots__ = ()

    _real_result: Result[Any]
    _metadata: ResultMetaData

    # SQLAlchemy's C extension accesses _yield_per during _manyrow_getter
    # property creation. FilterResult does not inherit this from Result, so
    # we provide the same default here to prevent AttributeError on Python
    # versions that use the C extension (e.g. Python 3.13).
    _yield_per: Optional[int] = None

    async def close(self) -> None:
        """Close this result."""
        await greenlet_spawn(self._real_result.close)

    @property
    def closed(self) -> bool:
        return self._real_result.closed


class AsyncAdaptedResult(_WithKeys, AsyncAdaptedCommon[Row[_TP]]):
    """An asyncio wrapper around an AdaptedResult that provides async iteration
    and adapted row conversion for transmuter types.
    """

    __slots__ = ()

    entities: tuple[type[Any], ...]
    _real_result: Result[_TP]

    def __init__(
        self,
        real_result: Result[_TP],
        entities: tuple[type[Any], ...] = (),
    ):
        self._real_result = real_result

        self._metadata = real_result._metadata
        self._unique_filter_state = real_result._unique_filter_state
        self._source_supports_scalars = real_result._source_supports_scalars
        self._post_creational_filter = None

        self.entities = entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(real_result, "_yield_per", None)) is not None:
            self._yield_per = yp

        # BaseCursorResult pre-generates the "_row_getter".  Use that
        # if available rather than building a second one
        if "_row_getter" in real_result.__dict__:
            self._set_memoized_attribute(
                "_row_getter", real_result.__dict__["_row_getter"]
            )

    @cached_property
    def adapter(self) -> TypeAdapter:
        """Get the adapter for tuple results."""
        return get_cached_adapter(tuple[*self.entities])

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self.entities[0])
            if self.entities
            else TypeAdapter(object)
        )

    def _adapt(self, row: Any) -> Any:
        """Adapt a row using TypeAdapter validation."""
        return self.adapter.validate_python(row)

    def _adapt_scalar(self, item: Any) -> Any:
        """Adapt a scalar result using TypeAdapter validation."""
        return self.scalar_adapter.validate_python(item)

    @property
    def t(self) -> Self:
        return self

    def tuples(self) -> Self:
        return self

    @_generative
    def unique(self, strategy: Optional[_UniqueFilterType] = None) -> Self:
        """Apply unique filtering to the objects returned by this
        :class:`AsyncAdaptedResult`.
        """
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions: _KeyIndexType) -> Self:
        r"""Establish the columns that should be returned in each row."""
        return self._column_slices(col_expressions)

    async def partitions(
        self, size: int | None = None
    ) -> AsyncIterator[Sequence[Row[_TP]]]:
        """Iterate through sub-lists of rows of the size given."""
        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield [self._adapt(row) for row in partition]
            else:
                break

    async def fetchall(self) -> Sequence[Row[_TP]]:
        """A synonym for the :meth:`AsyncAdaptedResult.all` method."""
        rows = await greenlet_spawn(self._allrows)
        return [self._adapt(row) for row in rows]

    async def fetchone(self) -> Optional[Row[_TP]]:
        """Fetch one row."""
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            return None
        else:
            return self._adapt(row)

    async def fetchmany(self, size: int | None = None) -> Sequence[Row[_TP]]:
        """Fetch many rows."""
        rows = await greenlet_spawn(self._manyrow_getter, self, size)
        return [self._adapt(row) for row in rows]

    async def all(self) -> Sequence[Row[_TP]]:
        """Return all rows in a list."""
        rows = await greenlet_spawn(self._allrows)
        return [self._adapt(row) for row in rows]

    def __aiter__(self) -> AsyncAdaptedResult[_TP]:
        return self

    async def __anext__(self) -> Row[_TP]:
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return self._adapt(row)

    async def first(self) -> Optional[Row[_TP]]:
        """Fetch the first row or ``None`` if no row is present."""
        row = await greenlet_spawn(self._only_one_row, False, False, False)
        return self._adapt(row) if row else None

    async def one_or_none(self) -> Optional[Row[_TP]]:
        """Return at most one result or raise an exception."""
        row = await greenlet_spawn(self._only_one_row, True, False, False)
        return self._adapt(row) if row else None

    async def one(self) -> Row[_TP]:
        """Return exactly one row or raise an exception."""
        row = await greenlet_spawn(self._only_one_row, True, True, False)
        return self._adapt(row)

    @overload
    async def scalar_one(self: AsyncAdaptedResult[tuple[_T]]) -> _T: ...

    @overload
    async def scalar_one(self) -> Any: ...

    async def scalar_one(self) -> Any:
        """Return exactly one scalar result or raise an exception."""
        scalar = await greenlet_spawn(self._only_one_row, True, True, True)
        return self._adapt_scalar(scalar)

    @overload
    async def scalar_one_or_none(
        self: AsyncAdaptedResult[tuple[_T]],
    ) -> Optional[_T]: ...

    @overload
    async def scalar_one_or_none(self) -> Optional[Any]: ...

    async def scalar_one_or_none(self) -> Optional[Any]:
        """Return exactly one scalar result or ``None``."""
        scalar = await greenlet_spawn(self._only_one_row, True, False, True)
        return self._adapt_scalar(scalar) if scalar else None

    @overload
    async def scalar(self: AsyncAdaptedResult[tuple[_T]]) -> Optional[_T]: ...

    @overload
    async def scalar(self) -> Any: ...

    async def scalar(self) -> Any:
        """Fetch the first column of the first row, and close the result set."""
        scalar = await greenlet_spawn(self._only_one_row, False, False, True)
        return self._adapt_scalar(scalar) if scalar else None

    async def freeze(self) -> AdaptedFrozenResult[_TP]:
        """Return a callable object that will produce copies of this result."""
        return await greenlet_spawn(
            AdaptedFrozenResult, self._real_result, self.entities
        )

    @overload
    def scalars(
        self: AsyncAdaptedResult[tuple[_T]], index: Literal[0]
    ) -> AsyncAdaptedScalarResult[_T]: ...

    @overload
    def scalars(
        self: AsyncAdaptedResult[tuple[_T]],
    ) -> AsyncAdaptedScalarResult[_T]: ...

    @overload
    def scalars(self, index: _KeyIndexType = 0) -> AsyncAdaptedScalarResult[Any]: ...

    def scalars(self, index: _KeyIndexType = 0) -> AsyncAdaptedScalarResult[Any]:
        """Return an :class:`AsyncAdaptedScalarResult` filtering object."""
        return AsyncAdaptedScalarResult(self._real_result, index, self.entities)

    def mappings(self) -> AsyncAdaptedMappingResult:
        """Apply a mappings filter to returned rows."""
        return AsyncAdaptedMappingResult(self._real_result, self.entities)


class AsyncAdaptedScalarResult(AsyncAdaptedCommon[_R]):
    """An async wrapper that returns adapted scalar values rather than Row values."""

    __slots__ = ()

    _generate_rows = False
    _entities: tuple[type[Any], ...]

    def __init__(
        self,
        real_result: Result[Any],
        index: _KeyIndexType,
        entities: tuple[type[Any], ...] = (),
    ):
        self._real_result = real_result

        if real_result._source_supports_scalars:
            self._metadata = real_result._metadata
            self._post_creational_filter = None
        else:
            self._metadata = real_result._metadata._reduce([index])
            self._post_creational_filter = operator.itemgetter(0)

        self._unique_filter_state = real_result._unique_filter_state
        self._entities = entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(real_result, "_yield_per", None)) is not None:
            self._yield_per = yp

    @cached_property
    def scalar_adapter(self) -> TypeAdapter:
        """Get the adapter for scalar results."""
        return (
            get_cached_adapter(self._entities[0])
            if self._entities
            else TypeAdapter(object)
        )

    def _adapt_scalar(self, item: Any) -> Any:
        """Adapt a scalar result using TypeAdapter validation."""
        return self.scalar_adapter.validate_python(item)

    def unique(
        self,
        strategy: Optional[_UniqueFilterType] = None,
    ) -> Self:
        """Apply unique filtering to the objects returned by this result."""
        self._unique_filter_state = (set(), strategy)
        return self

    async def partitions(self, size: int | None = None) -> AsyncIterator[Sequence[_R]]:
        """Iterate through sub-lists of elements of the size given."""
        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield [self._adapt_scalar(scalar) for scalar in partition]
            else:
                break

    async def fetchall(self) -> Sequence[_R]:
        """A synonym for the :meth:`AsyncAdaptedScalarResult.all` method."""
        scalars = await greenlet_spawn(self._allrows)
        return [self._adapt_scalar(scalar) for scalar in scalars]

    async def fetchmany(self, size: int | None = None) -> Sequence[_R]:
        """Fetch many objects."""
        scalars = await greenlet_spawn(self._manyrow_getter, self, size)
        return [self._adapt_scalar(scalar) for scalar in scalars]

    async def all(self) -> Sequence[_R]:
        """Return all scalar values in a list."""
        scalars = await greenlet_spawn(self._allrows)
        return [self._adapt_scalar(scalar) for scalar in scalars]

    def __aiter__(self) -> AsyncAdaptedScalarResult[_R]:
        return self

    async def __anext__(self) -> _R:
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return self._adapt_scalar(row)

    async def first(self) -> Optional[_R]:
        """Fetch the first object or ``None`` if no object is present."""
        scalar = await greenlet_spawn(self._only_one_row, False, False, False)
        return self._adapt_scalar(scalar) if scalar else None

    async def one_or_none(self) -> Optional[_R]:
        """Return at most one object or raise an exception."""
        scalar = await greenlet_spawn(self._only_one_row, True, False, False)
        return self._adapt_scalar(scalar) if scalar else None

    async def one(self) -> _R:
        """Return exactly one object or raise an exception."""
        scalar = await greenlet_spawn(self._only_one_row, True, True, False)
        return self._adapt_scalar(scalar)


class AsyncAdaptedMappingResult(_WithKeys, AsyncAdaptedCommon[RowMapping]):
    """An async wrapper that returns adapted dictionary values."""

    __slots__ = ()

    _generate_rows = True
    _post_creational_filter = operator.attrgetter("_mapping")
    _entities: tuple[type[Any], ...]

    def __init__(
        self,
        result: Result[Any],
        entities: tuple[type[Any], ...] = (),
    ):
        self._real_result = result
        self._metadata = result._metadata
        self._unique_filter_state = result._unique_filter_state
        if result._source_supports_scalars:
            self._metadata = self._metadata._reduce([0])

        self._entities = entities

        # Propagate _yield_per so that the SQLAlchemy C extension's
        # _manyrow_getter can access it on this object instead of failing
        # with AttributeError (FilterResult does not define _yield_per).
        if (yp := getattr(result, "_yield_per", None)) is not None:
            self._yield_per = yp

    @cached_property
    def adapter(self) -> TypeAdapter:
        """Get the adapter for tuple results."""
        return get_cached_adapter(tuple[*self._entities])

    def _adapt(self, row: Any) -> Any:
        """Adapt a row using TypeAdapter validation."""
        return self.adapter.validate_python(row)

    @_generative
    def unique(self, strategy: Optional[_UniqueFilterType] = None) -> Self:
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions: _KeyIndexType) -> Self:
        return self._column_slices(col_expressions)

    async def partitions(
        self, size: int | None = None
    ) -> AsyncIterator[Sequence[dict[str, Any]]]:
        """Iterate through sub-lists of elements of the size given."""
        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield list(
                    dict(zip(row.keys(), self._adapt(row.values())))
                    for row in partition
                )
            else:
                break

    async def fetchone(self) -> Optional[dict[str, Any]]:
        """Fetch one object."""
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            return None
        else:
            return dict(zip(row.keys(), self._adapt(row.values())))

    async def fetchmany(self, size: int | None = None) -> Sequence[dict[str, Any]]:
        """Fetch many rows."""
        rows = await greenlet_spawn(self._manyrow_getter, self, size)
        return list(dict(zip(row.keys(), self._adapt(row.values()))) for row in rows)

    async def fetchall(self) -> Sequence[dict[str, Any]]:
        """A synonym for the :meth:`AsyncAdaptedMappingResult.all` method."""
        rows = await greenlet_spawn(self._allrows)
        return list(dict(zip(row.keys(), self._adapt(row.values()))) for row in rows)

    async def all(self) -> Sequence[dict[str, Any]]:
        """Return all rows in a list."""
        rows = await greenlet_spawn(self._allrows)
        return list(dict(zip(row.keys(), self._adapt(row.values()))) for row in rows)

    def __aiter__(self) -> AsyncAdaptedMappingResult:
        return self

    async def __anext__(self) -> dict[str, Any]:
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return dict(zip(row.keys(), self._adapt(row.values())))

    async def first(self) -> Optional[dict[str, Any]]:
        """Fetch the first object or ``None`` if no object is present."""
        row = await greenlet_spawn(self._only_one_row, False, False, False)
        if row:
            return dict(zip(row.keys(), self._adapt(row.values())))
        return None

    async def one_or_none(self) -> Optional[dict[str, Any]]:
        """Return at most one object or raise an exception."""
        row = await greenlet_spawn(self._only_one_row, True, False, False)
        if row:
            return dict(zip(row.keys(), self._adapt(row.values())))
        return None

    async def one(self) -> dict[str, Any]:
        """Return exactly one object or raise an exception."""
        row = await greenlet_spawn(self._only_one_row, True, True, False)
        return dict(zip(row.keys(), self._adapt(row.values())))
