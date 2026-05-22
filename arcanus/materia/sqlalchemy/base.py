from __future__ import annotations

import operator as operators
from collections.abc import Hashable
from functools import lru_cache
from typing import Any, cast

from pydantic import ValidationInfo
from sqlalchemy import and_, inspect, or_
from sqlalchemy.exc import InvalidRequestError, MissingGreenlet
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.inspection import Inspectable
from sqlalchemy.orm import InstanceState, Mapper
from sqlalchemy.sql.elements import SQLCoreOperations
from sqlalchemy.util import greenlet_spawn

from arcanus.association import Association, DefferedAssociation, RelationGroupMap
from arcanus.base import Transmuter
from arcanus.criteria import CriteriaValue
from arcanus.expression import Column, ExpressionCompiler, Order, unwrap
from arcanus.materia.base import BaseMateria, T


class LoadedData: ...


@lru_cache(maxsize=None)
def extract_association_proxies(orm_class: Hashable) -> dict[str, str]:
    """Return ``{proxy_attr_name: target_relationship_name}`` for *orm_class*.

    The result is cached per ORM class because mapper metadata is immutable.
    """
    proxies: dict[str, str] = {}
    mapper = inspect(cast(Inspectable[Mapper[Any]], orm_class))
    for key, descriptor in mapper.all_orm_descriptors.items():
        if isinstance(descriptor, AssociationProxy):
            proxies[key] = descriptor.target_collection
    return proxies


class SqlalchemyExpressionCompiler(
    ExpressionCompiler[SQLCoreOperations[bool], SQLCoreOperations[CriteriaValue]]
):
    def apply(
        self, column: Column[Any], operator: str, value: object
    ) -> SQLCoreOperations[bool]:
        native = cast(SQLCoreOperations[CriteriaValue], column.native)
        operation = None if operator == "contains" else getattr(operators, operator, None)
        if operation is not None:
            return cast(SQLCoreOperations[bool], operation(native, unwrap(value)))

        if operator == "not_contains":
            return operators.invert(native.contains(unwrap(value)))

        method_name = operator.replace("_with", "with")
        native_method = getattr(native, method_name, None)
        if native_method is None:
            raise ValueError(f"Unsupported expression operator: {operator}")
        return cast(SQLCoreOperations[bool], native_method(unwrap(value)))

    def and_(
        self, expressions: tuple[SQLCoreOperations[bool], ...]
    ) -> SQLCoreOperations[bool]:
        return cast(SQLCoreOperations[bool], and_(*expressions))

    def or_(
        self, expressions: tuple[SQLCoreOperations[bool], ...]
    ) -> SQLCoreOperations[bool]:
        return cast(SQLCoreOperations[bool], or_(*expressions))

    def not_(self, expression: SQLCoreOperations[bool]) -> SQLCoreOperations[bool]:
        return cast(SQLCoreOperations[bool], operators.invert(expression))

    def order(self, order: Order[Any]) -> SQLCoreOperations[CriteriaValue]:
        native = cast(SQLCoreOperations[CriteriaValue], order.column.native)
        return native.desc() if order.descending else native.asc()


class SqlalchemyMateria(BaseMateria):
    def __init__(self) -> None:
        super().__init__()
        self.expression_compiler = SqlalchemyExpressionCompiler()

    def bless(self, materia: type[Any]):
        def decorator(transmuter_cls: type[T]) -> type[T]:
            if transmuter_cls in self.formulars:
                raise RuntimeError(
                    f"Transmuter {transmuter_cls.__name__} is already blessed with {self} in {self.__class__.__name__}"
                )
            # Check if materia implements TransmuterProxied by verifying required attributes
            if not hasattr(materia, "transmuter_proxy"):
                raise TypeError(
                    f"{self.__class__.__name__} require materia must implement TransmuterProxied."
                )

            self.formulars[transmuter_cls] = materia

            # Inject __clause_element__ methods to make transmuter_cls compatible with SQLAlchemy SQL constructions
            def __clause_element__(cls: type[Transmuter]):
                return inspect(cls.__transmuter_provider__)

            setattr(
                transmuter_cls,
                "__clause_element__",
                classmethod(__clause_element__),
            )

            return transmuter_cls

        return decorator

    @staticmethod
    def transmuter_before_validator(
        transmuter_type: type[T], materia: object, info: ValidationInfo
    ) -> Any:
        inspector = inspect(cast(Inspectable[InstanceState[Any]], materia))

        # Get all loaded attributes from sqlalchemy orm instance
        # relationships/associations are excluded here to:
        # 1. prevent firing loading procedures to respect lazy loading
        # 2. avoid circular validation
        # related objects will be load and validated when they are visited
        data = {}
        association_proxies = extract_association_proxies(cast(Hashable, type(materia)))
        loaded_data = inspector.dict
        for field_name, field_info in transmuter_type.__pydantic_fields__.items():
            used_name = field_info.alias or field_name
            if used_name in loaded_data:
                if field_name in transmuter_type.model_associations:
                    data[used_name] = DefferedAssociation
                else:
                    data[used_name] = loaded_data[used_name]
            else:
                proxied = association_proxies.get(used_name)
                if proxied and proxied in loaded_data:
                    if field_name in transmuter_type.model_associations:
                        data[used_name] = DefferedAssociation
                    else:
                        data[used_name] = getattr(materia, used_name)

        # don't use a dict to hold loaded data here
        # to avoid pydantic's handler call this formulate function again and go to the else block
        # use an object instead to keep the behavior same with pydantic's original model_validate
        # with from_attributes=True which will skip the instance __init__.
        loaded = LoadedData()
        loaded.__dict__ = data

        return loaded

    @staticmethod
    def transmuter_before_construct(transmuter_type: type[T], materia: object) -> dict:
        # inspector: InstanceState = inspect(materia)

        # Get all loaded attributes from sqlalchemy orm instance
        # relationships/associations are excluded here to:
        # 1. prevent firing loading procedures to respect lazy loading
        # 2. avoid circular validation
        # related objects will be load and validated when they are visited
        data = {}
        association_proxies = extract_association_proxies(cast(Hashable, type(materia)))
        inspector = inspect(cast(Inspectable[InstanceState[Any]], materia))
        loaded_data = inspector.dict
        for field_name, field_info in transmuter_type.__pydantic_fields__.items():
            if field_name in transmuter_type.model_associations:
                continue
            used_name = field_info.alias or field_name

            if used_name in loaded_data:
                # TODO: support deferred columns?
                data[used_name] = getattr(materia, used_name)
            else:
                proxied = association_proxies.get(used_name)
                if proxied and proxied in loaded_data:
                    data[used_name] = getattr(materia, used_name)

        return data

    def load_association(self, association: Association):
        if not association.__instance__:
            raise RuntimeError(
                f"The relation '{association.field_name}' is not yet prepared with an owner instance."
            )
        try:
            orm_instance = association.__instance__.__transmuter_provided__
            used_name = association.used_name

            # When a RelationGroupMap field maps to an association_proxy
            # (e.g. proxy over a attribute_keyed_list_dict relationship),
            # SQLAlchemy's _AssociationDict cannot iterate dict-of-lists
            # values correctly.  Bypass the proxy and resolve manually:
            # return a plain dict[K, list[target_ORM]] that the association
            # can consume directly.
            if isinstance(association, RelationGroupMap):
                orm_class = type(orm_instance)
                proxies = extract_association_proxies(cast(Hashable, orm_class))
                if used_name in proxies:
                    target_rel = proxies[used_name]
                    association.__backing_attr__ = target_rel

                    mapper = inspect(cast(Inspectable[Mapper[Any]], orm_class))
                    proxy_descriptor: AssociationProxy
                    proxy_descriptor = mapper.all_orm_descriptors[used_name]  # type: ignore
                    value_attr = proxy_descriptor.value_attr

                    underlying = getattr(orm_instance, target_rel)
                    return {
                        key: [getattr(item, value_attr) for item in items]
                        for key, items in underlying.items()
                    }

            return getattr(orm_instance, used_name)
        except MissingGreenlet as missing_greenlet_error:
            association.__loaded__ = False
            raise MissingGreenlet(
                f"""Failed to load relation '{association.field_name}' of {association.__instance__.__class__.__name__} for a greenlet is expected. Are you trying to get the relation in a sync context ? Await the {association.__instance__.__class__.__name__}.{association.field_name} instance to trigger the sqlalchemy async IO first."""
            ) from missing_greenlet_error
        except InvalidRequestError as invalid_request_error:
            association.__loaded__ = False
            raise InvalidRequestError(
                f"""Failed to load relation '{association.field_name}' of {association.__instance__.__class__.__name__} for the relation's loading strategy is set to 'raise' in sqlalchemy. Specify the relationship with selectinload in statement options or change the loading strategy to 'select' or 'selectin' instead."""
            ) from invalid_request_error

    def aload_association(self, association: Association) -> Any:
        return greenlet_spawn(self.load_association, association)
