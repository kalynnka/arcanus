from __future__ import annotations

from typing import Any

from pydantic import ValidationInfo
from sqlalchemy import inspect
from sqlalchemy.exc import InvalidRequestError, MissingGreenlet
from sqlalchemy.orm import InstanceState
from sqlalchemy.util import greenlet_spawn

from arcanus.association import Association, DefferedAssociation
from arcanus.base import BaseTransmuter
from arcanus.materia.base import TM, BaseMateria


class LoadedData: ...


class SqlalchemyMateria(BaseMateria):
    def bless(self, materia: type[Any]):
        def decorator(transmuter_cls: TM) -> TM:
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
            @classmethod
            def __clause_element__(cls: type[BaseTransmuter]):
                return inspect(cls.__transmuter_provider__)

            transmuter_cls.__clause_element__ = __clause_element__

            return transmuter_cls

        return decorator

    def transmuter_before_validator(
        self, transmuter_type: type[BaseTransmuter], materia: Any, info: ValidationInfo
    ):
        if not self.validate:
            return materia

        # don't use a dict to hold loaded data here
        # to avoid pydantic's handler call this formulate function again and go to the else block
        # use an object instead to keep the behavior same with pydantic's original model_validate
        # with from_attributes=True which will skip the instance __init__.
        loaded = LoadedData()

        inspector: InstanceState = inspect(materia)

        # Get all loaded attributes from sqlalchemy orm instance
        # relationships/associations are excluded here to:
        # 1. prevent firing loading procedures to respect lazy loading
        # 2. avoid circular validation
        # related objects will be load and validated when they are visited
        data = {}
        for field_name, field_info in transmuter_type.model_fields.items():
            used_name = field_info.alias or field_name
            if used_name in inspector.dict:
                if field_name in transmuter_type.model_associations:
                    data[used_name] = DefferedAssociation
                else:
                    data[used_name] = inspector.dict[used_name]

            # if field_name in transmuter_type.model_associations:
            #     if loaded_value is not LoaderCallableStatus.NO_VALUE:
            #         data[used_name] = field_info.get_default(call_default_factory=True)
            # else:
            #     if loaded_value is LoaderCallableStatus.NO_VALUE:
            #         data[used_name] = field_info.get_default(call_default_factory=True)
            #     else:
            #         data[used_name] = loaded_value

            # if loaded_value is LoaderCallableStatus.NO_VALUE:
            #     data[used_name] = field_info.get_default(call_default_factory=True)
            # else:
            #     data[used_name] = loaded_value

        loaded.__dict__ = data

        return loaded

    def transmuter_before_construct(
        self, transmuter_type: type[BaseTransmuter], materia: Any
    ):
        # inspector: InstanceState = inspect(materia)

        # Get all loaded attributes from sqlalchemy orm instance
        # relationships/associations are excluded here to:
        # 1. prevent firing loading procedures to respect lazy loading
        # 2. avoid circular validation
        # related objects will be load and validated when they are visited
        data = {}
        for field_name, field_info in transmuter_type.model_fields.items():
            if field_name in transmuter_type.model_associations:
                continue
            used_name = field_info.alias or field_name

            # TODO: support defferred columns?
            # if used_name in inspector.attrs:
            #     data[used_name] = inspector.attrs[used_name].loaded_value
            data[used_name] = getattr(materia, used_name)

        return data

    def load_association(self, association: Association):
        if not association.__instance__:
            raise RuntimeError(
                f"The relation '{association.field_name}' is not yet prepared with an owner instance."
            )
        try:
            return getattr(
                association.__instance__.__transmuter_provided__, association.used_name
            )
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
