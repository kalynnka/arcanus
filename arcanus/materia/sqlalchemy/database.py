from __future__ import annotations

from typing import (
    Any,
    Iterable,
    Literal,
    Optional,
    Self,
    Sequence,
    TypeVar,
    Union,
    overload,
)
from weakref import WeakKeyDictionary

from sqlalchemy import exc, inspect, tuple_, util
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.engine.interfaces import _CoreAnyExecuteParams, _CoreSingleExecuteParams
from sqlalchemy.engine.result import Result, ScalarResult
from sqlalchemy.ext.asyncio import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession as SqlalchemyAsyncSession
from sqlalchemy.orm import (
    InstanceState,
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
    TransmuterProxied,
    ValidateContextGeneratorT,
    ValidationContextT,
    validation_context,
)
from arcanus.materia.base import active_materia
from arcanus.materia.sqlalchemy.result import (
    _T,
    AdaptedResult,
    AsyncAdaptedResult,
)

T = TypeVar("T", bound=BaseTransmuter)


def resolve_statement_entities(statement: Executable) -> list[type[Any]]:
    entities: list[type[Any]] = []
    if isinstance(statement, Select):
        for desc in statement.column_descriptions:
            if ((expr := desc.get("expr")) is not None) and (
                (type := desc.get("type")) is not None
            ):
                # Bundle types (For example, used by selectinload for pk grouping) return tuple[*]
                if type is Bundle:
                    entities.append(tuple[*(e.type.python_type for e in expr.exprs)])
                else:
                    transmuter = BaseTransmuter.transmuter_formulars.reverse.get(type)
                    if transmuter:
                        entities.append(transmuter)
                    else:
                        try:
                            entities.append(type.python_type)
                        except NotImplementedError:
                            # NullType and other types without python_type
                            entities.append(object)
    elif isinstance(statement, (Insert, Update, Delete)):
        if statement._returning:
            for item in statement._returning:
                if transmuter := BaseTransmuter.transmuter_formulars.reverse.get(
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
        bind: Optional[_SessionBind] = None,
        *,
        autoflush: bool = True,
        future: Literal[True] = True,
        expire_on_commit: bool = True,
        autobegin: bool = True,
        twophase: bool = False,
        binds: Optional[dict[_SessionBindKey, _SessionBind]] = None,
        enable_baked_queries: bool = True,
        info: Optional[_InfoType] = None,
        query_cls: Optional[type[Query[Any]]] = None,
        autocommit: Literal[False] = False,
        join_transaction_mode: JoinTransactionMode = "conditional_savepoint",
        close_resets_only: Union[bool, _NoArg] = _NoArg.NO_ARG,
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

    def __exit__(self, exc_type, exc_value, traceback) -> Optional[bool]:
        if self._validation_context_manager is not None:
            self._validation_context_manager.__exit__(exc_type, exc_value, traceback)
        return super().__exit__(exc_type, exc_value, traceback)

    def __iter__(self) -> Iterable[BaseTransmuter]:
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
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> Result[_T]: ...

    @overload
    def execute(
        self,
        statement: UpdateBase,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> CursorResult[Any]: ...
    @overload
    def execute(
        self,
        statement: Executable,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> Result[Any]: ...
    def execute(
        self,
        statement: Executable,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
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
        if entities and any(
            isinstance(e, type) and issubclass(e, BaseTransmuter) for e in entities
        ):
            return AdaptedResult(
                real_result=result,
                entities=tuple(entities),
            )  # pyright: ignore[reportReturnType]

        return result

    @overload
    def scalar(
        self,
        statement: TypedReturnsRows[tuple[_T]],
        params: Optional[_CoreSingleExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        **kw: Any,
    ) -> Optional[_T]: ...
    @overload
    def scalar(
        self,
        statement: Executable,
        params: Optional[_CoreSingleExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        **kw: Any,
    ) -> Any: ...
    def scalar(
        self,
        statement: Executable,
        params: Optional[_CoreSingleExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
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
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        **kw: Any,
    ) -> ScalarResult[_T]: ...
    @overload
    def scalars(
        self,
        statement: Executable,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
        **kw: Any,
    ) -> ScalarResult[Any]: ...
    def scalars(
        self,
        statement: Executable,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
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
        if isinstance(instance, BaseTransmuter):
            if instance.__transmuter_provided__ in self._validation_context:
                del self._validation_context[instance.__transmuter_provided__]
            super().expunge(instance.__transmuter_provided__)
        else:
            super().expunge(instance)

    def expunge_all(self) -> None:
        self._validation_context.clear()
        return super().expunge_all()

    def add(self, instance: object, _warn: bool = True) -> None:
        if isinstance(instance, BaseTransmuter):
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
        if isinstance(instance, BaseTransmuter):
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
        if isinstance(instance, BaseTransmuter):
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
                if active_materia.get().validate:
                    instance = type(instance).model_validate(merged)
                else:
                    instance = type(instance).model_construct(data=merged)
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
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
    ) -> Optional[T]: ...
    @overload
    def get(
        self,
        entity: _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
    ) -> Optional[_O]: ...
    def get(
        self,
        entity: type[T] | _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Sequence[ORMOption] | None = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
    ) -> Optional[T] | Optional[_O]:
        if isinstance(entity, type) and issubclass(entity, BaseTransmuter):
            instance = super().get(
                # sqlalchemy materia requires transumter to have a provider blessed
                entity.__transmuter_provider__,  # pyright: ignore[reportArgumentType]
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
            if active_materia.get().validate:
                return entity.model_validate(instance)
            else:
                return entity.model_construct(data=instance)
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
            if isinstance(instance, BaseTransmuter):
                return instance.__transmuter_provided__  # pyright: ignore[reportReturnType]
            return instance

    @overload
    def get_one(
        self,
        entity: type[T],
        ident: _PKIdentityArgument,
        *,
        options: Optional[Sequence[ORMOption]] = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
    ) -> T: ...
    @overload
    def get_one(
        self,
        entity: _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Optional[Sequence[ORMOption]] = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
    ) -> _O: ...
    def get_one(
        self,
        entity: type[T] | _EntityBindKey[_O],
        ident: _PKIdentityArgument,
        *,
        options: Optional[Sequence[ORMOption]] = None,
        populate_existing: bool = False,
        with_for_update: ForUpdateParameter = None,
        identity_token: Optional[Any] = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[_BindArguments] = None,
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

        mapper = inspect(entity.__transmuter_provider__)
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
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
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
        # cursor: UUID | None = None, # TODO: re-enable cursor pagination when identity solution is clarified
        order_bys: Iterable[_ColumnExpressionOrStrLabelArgument[Any]] | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
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

        return self.execute(statement).scalars().all()

    def partitions(
        self,
        entity: type[_T],
        limit: int | None = 100,
        offset: int | None = None,
        # cursor: UUID | None = None, # TODO: re-enable cursor pagination when identity solution is clarified
        size: int | None = 10,
        order_bys: Iterable[_ColumnExpressionOrStrLabelArgument[Any]] | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        **filters,
    ):
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


class AsyncSession(SqlalchemyAsyncSession):
    sync_session_class = Session
    sync_session: Session

    async def __aenter__(self) -> Self:
        self._validation_context_manager = validation_context(self._validation_context)
        self._validation_context_manager.__enter__()
        await super().__aenter__()
        return self

    async def __aexit__(self, type_: Any, value: Any, traceback: Any) -> None:
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
    ) -> Optional[_T]:
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
    ) -> Optional[_T]:
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
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
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
        order_bys: Iterable[_ColumnExpressionOrStrLabelArgument[Any]] | None = None,
        options: Iterable[ExecutableOption] | None = None,
        expressions: Iterable[_ColumnExpressionArgument[bool]] | None = None,
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
