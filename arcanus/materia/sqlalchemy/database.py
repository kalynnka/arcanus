from __future__ import annotations

import operator
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Sequence
from functools import reduce
from types import TracebackType, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
    Self,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)
from weakref import WeakKeyDictionary

from pydantic import Discriminator, Tag
from sqlalchemy import event, exc, inspect, tuple_, util
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.engine.interfaces import _CoreAnyExecuteParams, _CoreSingleExecuteParams
from sqlalchemy.engine.result import Result, ScalarResult
from sqlalchemy.ext.asyncio import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession as SqlalchemyAsyncSession
from sqlalchemy.orm import (
    InstanceState,
    Mapper,
    Query,
    attributes,
    object_mapper,
)
from sqlalchemy.orm import Session as SqlalchemySession
from sqlalchemy.orm._typing import (
    OrmExecuteOptionsParameter,
    _IdentityKeyType,
)
from sqlalchemy.orm.base import _O, _state_mapper
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.orm.session import (
    JoinTransactionMode,
    _BindArguments,
    _EntityBindKey,
    _PKIdentityArgument,
    _SessionBind,
    _SessionBindKey,
)
from sqlalchemy.orm.util import Bundle
from sqlalchemy.sql import Executable, Select, functions, select
from sqlalchemy.sql._typing import (
    _ColumnExpressionArgument,
    _ColumnExpressionOrStrLabelArgument,
    _InfoType,
)
from sqlalchemy.sql.base import ExecutableOption, _NoArg
from sqlalchemy.sql.dml import Delete, Insert, Update, UpdateBase
from sqlalchemy.sql.selectable import ForUpdateArg, ForUpdateParameter, TypedReturnsRows

from arcanus.base import (
    BaseTransmuter,
    Transmuter,
    TransmuterProxied,
    ValidateContextGeneratorT,
    ValidationContextT,
    validation_context,
)
from arcanus.criteria import CriteriaValue, with_identity_tiebreak
from arcanus.expression import Column, Expression, Order
from arcanus.materia.base import active_materia
from arcanus.materia.sqlalchemy.result import (
    _T,
    AdaptedResult,
    AsyncAdaptedResult,
)

T = TypeVar("T", bound=Transmuter)


class PolymorphicInspection(Protocol):
    with_polymorphic_mappers: Sequence[Mapper[Any]]


def polymorphic_discriminator(discriminator_key: str) -> Callable[..., str | None]:
    def get_discriminator(value: Any) -> str | None:
        if isinstance(value, dict):
            discriminator = value.get(discriminator_key)
        else:
            discriminator = getattr(value, discriminator_key, None)
        return str(discriminator) if discriminator is not None else None

    return get_discriminator


def union_type(types: Sequence[Any]) -> Any:
    if not types:
        return object
    return reduce(operator.or_, types)


def contains_transmuter_type(entity: Any) -> bool:
    if isinstance(entity, type):
        return issubclass(entity, Transmuter)
    origin = get_origin(entity)
    if origin is Annotated:
        return contains_transmuter_type(get_args(entity)[0])
    if origin in (Union, UnionType):
        return any(contains_transmuter_type(arg) for arg in get_args(entity))
    return False


def discriminated_union_type(
    variants: Sequence[tuple[type[Transmuter], Any]], discriminator_key: str
) -> Any:
    tagged_variants = [
        Annotated[transmuter, Tag(str(identity))] for transmuter, identity in variants
    ]
    return Annotated[
        union_type(tagged_variants),
        Discriminator(polymorphic_discriminator(discriminator_key)),
    ]


def polymorphic_result_type(
    provider: type[Any], selected_mappers: Iterable[Mapper[Any]] | None = None
) -> Any:
    mapper = cast(Mapper[Any], inspect(provider))
    formulars = active_materia.get().formulars
    transmuter = formulars.reverse.get(provider)
    if transmuter is None:
        return object

    descendant_variants: list[tuple[type[Transmuter], Any]] = []
    base_variant: tuple[type[Transmuter], Any] | None = None
    mappers = selected_mappers or mapper.self_and_descendants
    for descendant in mappers:
        descendant_transmuter = formulars.reverse.get(descendant.class_)
        if descendant_transmuter is None or descendant.polymorphic_identity is None:
            continue
        variant = (descendant_transmuter, descendant.polymorphic_identity)
        if descendant.class_ is provider:
            base_variant = variant
        else:
            descendant_variants.append(variant)

    if not descendant_variants:
        return transmuter

    variants = descendant_variants
    if base_variant is not None and not mapper.polymorphic_abstract:
        variants = [*descendant_variants, base_variant]

    polymorphic_on = mapper.polymorphic_on
    discriminator_key = getattr(polymorphic_on, "key", None)
    if discriminator_key:
        return discriminated_union_type(variants, discriminator_key)
    return union_type([variant[0] for variant in variants])


def polymorphic_mappers(expr: Any) -> tuple[Mapper[Any], ...] | None:
    inspected = inspect(expr, raiseerr=False)
    if inspected is None:
        return None
    polymorphic = cast(PolymorphicInspection, inspected)
    mappers = polymorphic.with_polymorphic_mappers
    return tuple(mappers) if mappers else None


def resolve_statement_entities(statement: Executable) -> list[Any]:
    entities: list[Any] = []
    if isinstance(statement, Select):
        for desc in statement.column_descriptions:
            if ((expr := desc.get("expr")) is not None) and (
                (type := desc.get("type")) is not None
            ):
                # Bundle types (For example, used by selectinload for pk grouping) return tuple[*]
                if type is Bundle:
                    entities.append(tuple[*(e.type.python_type for e in expr.exprs)])
                else:
                    transmuter = active_materia.get().formulars.reverse.get(type)
                    if transmuter:
                        entity = polymorphic_result_type(
                            type,
                            polymorphic_mappers(expr),
                        )
                        entities.append(entity)
                    else:
                        try:
                            entities.append(type.python_type)
                        except NotImplementedError:
                            # NullType and other types without python_type
                            entities.append(object)
    elif isinstance(statement, (Insert, Update, Delete)) and statement._returning:
        for item in statement._returning:
            if transmuter := active_materia.get().formulars.reverse.get(
                item.entity_namespace
            ):
                entities.append(transmuter)
            else:
                try:
                    entities.append(item.type.python_type)  # type: ignore[attr-defined]
                except NotImplementedError:
                    # NullType and other types without python_type
                    entities.append(object)
    return entities


class Session(SqlalchemySession):
    _validation_context: ValidationContextT
    _validation_context_manager: ValidateContextGeneratorT | None

    def __init__(
        self,
        bind: _SessionBind | None = None,
        *,
        autoflush: bool = True,
        future: Literal[True] = True,
        expire_on_commit: bool = True,
        autobegin: bool = True,
        twophase: bool = False,
        binds: dict[_SessionBindKey, _SessionBind] | None = None,
        enable_baked_queries: bool = True,
        info: _InfoType | None = None,
        query_cls: type[Query[Any]] | None = None,
        autocommit: Literal[False] = False,
        join_transaction_mode: JoinTransactionMode = "conditional_savepoint",
        close_resets_only: bool | _NoArg = _NoArg.NO_ARG,
    ) -> None:
        super().__init__(
            bind,
            autoflush=autoflush,
            future=future,
            expire_on_commit=expire_on_commit,
            autobegin=autobegin,
            twophase=twophase,
            binds=binds,
            enable_baked_queries=enable_baked_queries,
            info=info,
            query_cls=query_cls,
            autocommit=autocommit,
            join_transaction_mode=join_transaction_mode,
            close_resets_only=close_resets_only,
        )
        self._validation_context = WeakKeyDictionary()
        self._validation_context_manager = None

    def __enter__(self):
        self._validation_context_manager = validation_context(self._validation_context)
        self._validation_context_manager.__enter__()
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        if self._validation_context_manager is not None:
            self._validation_context_manager.__exit__(exc_type, exc_value, traceback)
        return super().__exit__(exc_type, exc_value, traceback)

    def __iter__(self) -> Iterator[object]:
        if not self._validation_context:
            raise RuntimeError(
                "Active validation context is requried, please use a context manager 'with Session() as session' to create a session context."
            )
        for instance in super().__iter__():
            if instance in self._validation_context:
                yield self._validation_context[instance]
            if isinstance(instance, TransmuterProxied) and (
                transmuter := instance.transmuter_proxy
            ):
                yield transmuter
            yield instance  # type: ignore[reportUnreachable]

    @overload
    def execute(
        self,
        statement: TypedReturnsRows[_T],
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        _parent_execute_state: Any | None = None,
        _add_event: Any | None = None,
    ) -> Result[_T]: ...

    @overload
    def execute(
        self,
        statement: UpdateBase,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        _parent_execute_state: Any | None = None,
        _add_event: Any | None = None,
    ) -> CursorResult[Any]: ...
    @overload
    def execute(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        _parent_execute_state: Any | None = None,
        _add_event: Any | None = None,
    ) -> Result[Any]: ...
    def execute(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        _parent_execute_state: Any | None = None,
        _add_event: Any | None = None,
    ) -> Result[Any]:
        result = super().execute(
            statement,
            params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            _parent_execute_state=_parent_execute_state,
            _add_event=_add_event,
        )

        if execution_options.get("sa_top_level_orm_context", False):
            return result

        if execution_options.get("_sa_orm_load_options", {}):
            return result

        entities = resolve_statement_entities(statement)
        if entities and any(contains_transmuter_type(entity) for entity in entities):
            return AdaptedResult(
                real_result=result,
                entities=tuple(entities),
                # An UPDATE ... RETURNING refreshes the ORM row but hands back the
                # cached (stale) transmuter — force a re-sync from the fresh row.
                force_revalidate=isinstance(statement, Update)
                and bool(statement._returning),
            )  # pyright: ignore[reportReturnType]

        return result

    @overload
    def scalar(
        self,
        statement: TypedReturnsRows[tuple[_T]],
        params: _CoreSingleExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> _T | None: ...
    @overload
    def scalar(
        self,
        statement: Executable,
        params: _CoreSingleExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> Any: ...
    def scalar(
        self,
        statement: Executable,
        params: _CoreSingleExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> Any:
        return self.execute(
            statement=statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            **kw,
        ).scalar()

    @overload
    def scalars(
        self,
        statement: TypedReturnsRows[tuple[_T]],
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> ScalarResult[_T]: ...
    @overload
    def scalars(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> ScalarResult[Any]: ...
    def scalars(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> ScalarResult[Any]:
        return self.execute(
            statement=statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            **kw,
        ).scalars()

    def expunge(self, instance: object) -> None:
        if isinstance(instance, Transmuter):
            if instance.__transmuter_provided__ in self._validation_context:
                del self._validation_context[instance.__transmuter_provided__]
            super().expunge(instance.__transmuter_provided__)
        else:
            super().expunge(instance)

    def expunge_all(self) -> None:
        self._validation_context.clear()
        return super().expunge_all()

    def add(self, instance: object, _warn: bool = True) -> None:
        if isinstance(instance, Transmuter):
            self._validation_context[instance.__transmuter_provided__] = instance
            super().add(instance.__transmuter_provided__, _warn=_warn)
        else:
            super().add(instance, _warn=_warn)

    def _save_or_update_state(
        self,
        state: InstanceState,
    ) -> None:
        state._orphaned_outside_of_session = False
        self._save_or_update_impl(state)

        mapper = _state_mapper(state)
        for o, m, st_, dct_ in mapper.cascade_iterator(
            "save-update", state, halt_on=self._contains_state
        ):
            if isinstance(o, TransmuterProxied) and (transmuter := o.transmuter_proxy):
                self._validation_context[o] = transmuter
            self._save_or_update_impl(st_)

    def refresh(
        self,
        instance: object,
        attribute_names: Iterable[str] | None = None,
        with_for_update: ForUpdateArg | None | bool | dict[str, Any] = None,
    ) -> None:
        if isinstance(instance, Transmuter):
            if instance.__transmuter_provided__ not in self._validation_context:
                self._validation_context[instance.__transmuter_provided__] = instance
            super().refresh(instance, attribute_names, with_for_update)
            instance.revalidate()
        else:
            super().refresh(instance, attribute_names, with_for_update)

    def rollback(self) -> None:
        super().rollback()
        self._validation_context.clear()

    def merge(
        self,
        instance: T,
        *,
        load: bool = True,
        options: Sequence[ORMOption] | None = None,
    ) -> T:
        if isinstance(instance, Transmuter):
            if self._warn_on_events:
                self._flush_warning("Session.merge()")

            _recursive: dict[InstanceState[Any], object] = {}
            _resolve_conflict_map: dict[_IdentityKeyType[Any], object] = {}

            if load:
                # flush current contents if we expect to load data
                self._autoflush()

            object_mapper(instance)  # verify mapped
            autoflush = self.autoflush
            try:
                self.autoflush = False
                merged = self._merge(
                    attributes.instance_state(instance),
                    attributes.instance_dict(instance.__transmuter_provided__),
                    load=load,
                    options=options,
                    _recursive=_recursive,
                    _resolve_conflict_map=_resolve_conflict_map,
                )
                instance = type(instance).model_validate(merged)
                instance.revalidate()
                return instance
            finally:
                self.autoflush = autoflush
        else:
            return super().merge(
                instance,
                load=load,
                options=options,
            )

    def enable_relationship_loading(self, obj: BaseTransmuter) -> None:
        super().enable_relationship_loading(obj.__transmuter_provided__)
        self._validation_context[obj.__transmuter_provided__] = obj

    @overload
    def get(
        self,
        entity: type[T],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> T | None: ...
    @overload
    def get(
        self,
        entity: _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> _O | None: ...
    def get(
        self,
        entity: type[T] | _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> T | None | _O:
        if isinstance(entity, type) and issubclass(entity, Transmuter):
            instance = super().get(
                # sqlalchemy materia requires transumter to have a provider blessed
                active_materia.get()[entity],  # pyright: ignore[reportArgumentType]
                ident,
                options=options,
                populate_existing=populate_existing,
                with_for_update=with_for_update,
                identity_token=identity_token,
                execution_options=execution_options,
                bind_arguments=bind_arguments,
            )
            if not instance:
                return None
            return entity.model_validate(instance)
        else:
            instance = super().get(
                entity,
                ident,
                options=options,
                populate_existing=populate_existing,
                with_for_update=with_for_update,
                identity_token=identity_token,
                execution_options=execution_options,
                bind_arguments=bind_arguments,
            )
            if isinstance(instance, Transmuter):
                return instance.__transmuter_provided__  # pyright: ignore[reportReturnType]
            return instance

    @overload
    def get_one(
        self,
        entity: type[T],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> T: ...
    @overload
    def get_one(
        self,
        entity: _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> _O: ...
    def get_one(
        self,
        entity: type[T] | _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Any | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
    ) -> T | _O:
        instance = self.get(
            entity,
            ident,
            options=options,
            populate_existing=populate_existing,
            with_for_update=with_for_update,
            identity_token=identity_token,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
        )

        if instance is None:
            raise exc.NoResultFound("No row was found when one was required")

        return instance

    def one(
        self,
        entity: type[_T],
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
        statement = select(entity)

        if expressions:
            statement = statement.where(*expressions)
        if filters:
            statement = statement.filter_by(**filters)
        if options:
            statement = statement.options(*options)
        if execution_options:
            statement = statement.execution_options(**execution_options)

        return self.execute(statement).scalar_one()

    def one_or_none(
        self,
        entity: type[_T],
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
        statement = select(entity)

        if expressions:
            statement = statement.where(*expressions)
        if filters:
            statement = statement.filter_by(**filters)
        if options:
            statement = statement.options(*options)
        if execution_options:
            statement = statement.execution_options(**execution_options)

        return self.execute(statement).scalar_one_or_none()

    def first(
        self,
        entity: type[_T],
        order_bys: Iterable[_ColumnExpressionOrStrLabelArgument[Any]] | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
        statement = select(entity)

        if order_bys:
            statement = statement.order_by(*order_bys)
        if expressions:
            statement = statement.where(*expressions)
        if filters:
            statement = statement.filter_by(**filters)
        if options:
            statement = statement.options(*options)
        if execution_options:
            statement = statement.execution_options(**execution_options)

        return self.execute(statement).scalars().first()

    def bulk(
        self,
        entity: type[_T],
        idents: Sequence[_PKIdentityArgument],
        *,
        options: Sequence[ORMOption] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
    ) -> list[_T | None]:
        """Bulk version of Session.get. Each element in idents should be
        exactly the same format as Session.get's ident parameter.

        Returns a list of entities in the same order as idents, with None
        for any ident that was not found.
        """
        if not idents:
            return []

        mapper = inspect(active_materia.get()[entity])
        pk_columns = mapper.primary_key  # pyright: ignore[reportOptionalMemberAccess]

        if len(pk_columns) == 1:
            # Build the WHERE clause based on single or composite PK
            pk_col = pk_columns[0]
            statement = select(entity).where(pk_col.in_(idents))
        else:
            # Composite PK: use tuple comparison
            # Each ident should be a tuple matching the PK columns
            statement = select(entity).where(tuple_(*pk_columns).in_(idents))

        if options:
            statement = statement.options(*options)
        if execution_options:
            statement = statement.execution_options(**execution_options)

        entities = self.execute(statement).scalars().all()

        # Build mapping from PK value(s) to entity
        if len(pk_columns) == 1:
            pk_attr = pk_columns[0].key
            mapping = {getattr(e, pk_attr): e for e in entities}
            return [mapping.get(ident) for ident in idents]
        else:
            # Composite PK: map tuple of PK values to entity
            pk_attrs = [col.key for col in pk_columns]
            mapping = {
                tuple(getattr(e, attr) for attr in pk_attrs): e for e in entities
            }
            return [
                mapping.get(tuple(ident) if not isinstance(ident, tuple) else ident)
                for ident in idents
            ]

    def count(
        self,
        entity: type[_T],
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
        statement = select(functions.count()).select_from(entity)

        if expressions:
            statement = statement.where(*expressions)
        if filters:
            statement = statement.filter_by(**filters)
        if execution_options:
            statement = statement.execution_options(**execution_options)

        return self.execute(statement).scalar_one()

    def list(
        self,
        entity: type[_T],
        limit: int | None = 100,
        offset: int | None = None,
        order_bys: Iterable[
            _ColumnExpressionOrStrLabelArgument[Any]
            | Column[CriteriaValue]
            | Order[CriteriaValue]
        ]
        | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> Sequence[_T]:
        statement = select(entity)

        if limit:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        if order_bys:
            statement = statement.order_by(
                *with_identity_tiebreak(entity, tuple(order_bys))
            )
        if options:
            statement = statement.options(*options)
        if expressions:
            statement = statement.where(*expressions)
        if execution_options:
            statement = statement.execution_options(**execution_options)
        if filters:
            statement = statement.filter_by(**filters)

        return self.execute(statement).scalars().all()

    def partitions(
        self,
        entity: type[_T],
        limit: int | None = 100,
        offset: int | None = None,
        size: int | None = 10,
        order_bys: Iterable[
            _ColumnExpressionOrStrLabelArgument[Any]
            | Column[CriteriaValue]
            | Order[CriteriaValue]
        ]
        | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> Iterable[Sequence[_T]]:
        statement = select(entity).execution_options(yield_per=size)

        if limit:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        if order_bys:
            statement = statement.order_by(*order_bys)
        if options:
            statement = statement.options(*options)
        if expressions:
            statement = statement.where(*expressions)
        if execution_options:
            statement = statement.execution_options(**execution_options)
        if filters:
            statement = statement.filter_by(**filters)

        yield from self.execute(statement).scalars().partitions(size)


@event.listens_for(Session, "after_flush")
def _revalidate_after_flush(session: Session, flush_context: object) -> None:
    """Re-validate freshly inserted transmuters so server-assigned values (e.g.
    an autoincrement ``id``) sync back from their ORM rows.

    Only ``session.new`` is revalidated: an INSERT is where the server assigns
    values the transmuter doesn't have yet. UPDATEs of user-set columns are
    already mirrored onto the transmuter by write-through ``__setattr__``, so
    re-validating them would be pure overhead. (A server-side ``onupdate`` is the
    rare exception — pull it back with ``session.refresh()`` when you need it.)

    Runs for both sync and async sessions (``AsyncSession`` drives this same sync
    ``Session``); ``session.new`` still holds the just-inserted rows here, with
    primary keys already populated.
    """
    for instance in session.new:
        if isinstance(instance, TransmuterProxied) and (
            proxy := instance.transmuter_proxy
        ):
            proxy.revalidate()


class AsyncSession(SqlalchemyAsyncSession):
    sync_session_class = Session
    sync_session: Session

    async def __aenter__(self) -> Self:
        self._validation_context_manager = validation_context(self._validation_context)
        self._validation_context_manager.__enter__()
        await super().__aenter__()
        return self

    async def __aexit__(
        self,
        type_: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._validation_context_manager is not None:
            self._validation_context_manager.__exit__(type_, value, traceback)
            self._validation_context_manager = None
        await super().__aexit__(type_, value, traceback)

    @property
    def _validation_context(self) -> ValidationContextT:
        return self.sync_session._validation_context

    @property
    def _validation_context_manager(self) -> ValidateContextGeneratorT | None:
        return self.sync_session._validation_context_manager

    @_validation_context_manager.setter
    def _validation_context_manager(self, value: ValidateContextGeneratorT | None):
        self.sync_session._validation_context_manager = value

    @overload
    async def stream(
        self,
        statement: TypedReturnsRows[tuple[_T]],
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> AsyncResult[tuple[_T]]: ...

    @overload
    async def stream(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> AsyncResult[Any]: ...

    async def stream(
        self,
        statement: Executable,
        params: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: _BindArguments | None = None,
        **kw: Any,
    ) -> AsyncResult[Any]:
        """Execute a statement and return a streaming
        :class:`AsyncAdaptedResult` object that adapts rows to transmuter types.
        """
        _STREAM_OPTIONS = util.immutabledict({"stream_results": True})

        if execution_options:
            execution_options = util.immutabledict(execution_options).union(
                _STREAM_OPTIONS
            )
        else:
            execution_options = _STREAM_OPTIONS

        result = await util.greenlet_spawn(
            self.sync_session.execute,
            statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            **kw,
        )

        if isinstance(result, AdaptedResult):
            return AsyncAdaptedResult(
                result,
                entities=result.entities,
                force_revalidate=result._force_revalidate,
            )  # pyright: ignore[reportReturnType]

        return AsyncResult(result)

    async def one(
        self,
        entity: type[_T],
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> _T:
        return await util.greenlet_spawn(
            self.sync_session.one,
            entity,
            options,
            expressions,
            execution_options,
            **filters,
        )

    async def one_or_none(
        self,
        entity: type[_T],
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> _T | None:
        r = await util.greenlet_spawn(
            self.sync_session.one_or_none,
            entity,
            options,
            expressions,
            execution_options,
            **filters,
        )
        return r

    async def first(
        self,
        entity: type[_T],
        order_bys: Iterable[_ColumnExpressionOrStrLabelArgument[Any]] | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> _T | None:
        return await util.greenlet_spawn(
            self.sync_session.first,
            entity,
            order_bys,
            options,
            expressions,
            execution_options,
            **filters,
        )

    async def bulk(
        self,
        entity: type[_T],
        idents: Sequence[_PKIdentityArgument],
        *,
        options: Sequence[ORMOption] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
    ) -> list[_T | None]:
        return await util.greenlet_spawn(
            self.sync_session.bulk,
            entity,
            idents,
            options=options,
            execution_options=execution_options,
        )

    async def count(
        self,
        entity: type[_T],
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> int:
        return await util.greenlet_spawn(
            self.sync_session.count,
            entity,
            expressions,
            execution_options,
            **filters,
        )

    async def list(
        self,
        entity: type[_T],
        limit: int | None = 100,
        offset: int | None = None,
        order_bys: Iterable[
            _ColumnExpressionOrStrLabelArgument[Any]
            | Column[CriteriaValue]
            | Order[CriteriaValue]
        ]
        | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> Sequence[_T]:
        return await util.greenlet_spawn(
            self.sync_session.list,
            entity,
            limit,
            offset,
            order_bys,
            options,
            expressions,
            execution_options,
            **filters,
        )

    async def partitions(
        self,
        entity: type[_T],
        limit: int | None = 100,
        offset: int | None = None,
        size: int | None = 10,
        order_bys: Iterable[
            _ColumnExpressionOrStrLabelArgument[Any]
            | Column[CriteriaValue]
            | Order[CriteriaValue]
        ]
        | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool] | Expression[bool]]
        | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ) -> AsyncIterator[Sequence[_T]]:
        statement = select(entity)

        if limit:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        if order_bys:
            statement = statement.order_by(*order_bys)
        if options:
            statement = statement.options(*options)
        if expressions:
            statement = statement.where(*expressions)
        if execution_options:
            statement = statement.execution_options(**execution_options)
        if filters:
            statement = statement.filter_by(**filters)

        async for partition in (
            (
                await self.stream(
                    statement,
                    execution_options={"yield_per": size},
                )
            )
            .scalars()
            .partitions(size)
        ):
            yield partition
