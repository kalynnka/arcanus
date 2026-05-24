from __future__ import annotations

import base64
import sys
from datetime import datetime
from functools import cached_property
from types import UnionType, prepare_class
from typing import (
    Any,
    ClassVar,
    Generic,
    Iterator,
    Literal,
    Self,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    model_validator,
)
from pydantic._internal import _forward_ref, _generics, _typing_extra, _utils
from pydantic._internal._generics import _get_caller_frame_info
from pydantic.errors import PydanticUndefinedAnnotation, PydanticUserError
from pydantic_core import PydanticCustomError

from arcanus.association import is_association
from arcanus.expression import Column, Expression, Order

P = TypeVar("P")
T = TypeVar("T")
S = TypeVar("S", bound=str)
N = TypeVar("N", bound=float | int | UUID | datetime)
CriteriaValue = str | UUID | int | float | bool | datetime

CRITERIA_CURSOR_VERSION = 1


class BaseCriteria(BaseModel, Generic[T]):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_alias=True,
        validate_by_name=True,
        extra="forbid",
    )

    eq: T | None = None
    ne: T | None = None
    in_: tuple[T, ...] | None = Field(default=None, alias="in")
    not_in: tuple[T, ...] | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        ("eq", "eq"),
        ("ne", "ne"),
        ("in_", "in_"),
        ("not_in", "not_in"),
    )


class TextCriteria(BaseCriteria[S]):
    contains: S | None = None
    not_contains: S | None = None
    starts_with: S | None = None
    ends_with: S | None = None
    like: S | None = None
    ilike: S | None = None
    not_like: S | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *BaseCriteria.criteria_operators,
        ("contains", "contains"),
        ("not_contains", "not_contains"),
        ("starts_with", "starts_with"),
        ("ends_with", "ends_with"),
        ("like", "like"),
        ("ilike", "ilike"),
        ("not_like", "not_like"),
    )


class NumericCriteria(BaseCriteria[N]):
    lt: N | None = None
    le: N | None = None
    gt: N | None = None
    ge: N | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *BaseCriteria.criteria_operators,
        ("lt", "lt"),
        ("le", "le"),
        ("gt", "gt"),
        ("ge", "ge"),
    )


class Criteria(BaseModel, Generic[P]):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_alias=True,
        validate_by_name=True,
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    generic_model: ClassVar[type[Any]]

    and_: tuple[Criteria[P], ...] | None = Field(default=None, alias="and")
    or_: tuple[Criteria[P], ...] | None = Field(default=None, alias="or")
    not_: Criteria[P] | None = Field(default=None, alias="not")

    criteria_type_mapping: ClassVar[dict[type[Any], type[BaseCriteria[Any]]]] = {
        str: TextCriteria[str],
        UUID: NumericCriteria[UUID],
        int: NumericCriteria[int],
        float: NumericCriteria[float],
        bool: BaseCriteria[bool],
        datetime: NumericCriteria[datetime],
    }

    # Build model-specific criteria fields while preserving Pydantic's generic cache.
    def __class_getitem__(
        cls, typevar_values: type[Any] | tuple[type[Any], ...]
    ) -> type[BaseModel] | _forward_ref.PydanticRecursiveRef:
        cached = _generics.get_cached_generic_type_early(cls, typevar_values)
        if cached is not None:
            return cached

        if cls is BaseModel:
            raise TypeError(
                "Type parameters should be placed on typing.Generic, not BaseModel"
            )
        if not hasattr(cls, "__parameters__"):
            raise TypeError(
                f"{cls} cannot be parametrized because it does not inherit from "
                "typing.Generic"
            )
        if (
            not cls.__pydantic_generic_metadata__["parameters"]
            and Generic not in cls.__bases__
        ):
            raise TypeError(f"{cls} is not a generic class")

        if not isinstance(typevar_values, tuple):
            typevar_values = (typevar_values,)

        typevars_map = _generics.map_generic_model_arguments(cls, typevar_values)
        typevar_values = tuple(value for value in typevars_map.values())

        if (
            _utils.all_identical(typevars_map.keys(), typevars_map.values())
            and typevars_map
        ):
            submodel = cls
            _generics.set_cached_generic_type(cls, typevar_values, submodel)
        else:
            parent_args = cls.__pydantic_generic_metadata__["args"]
            if not parent_args:
                args = typevar_values
            else:
                args = tuple(
                    _generics.replace_types(arg, typevars_map) for arg in parent_args
                )

            origin = cls.__pydantic_generic_metadata__["origin"] or cls
            model_name = origin.model_parametrized_name(args)
            params = tuple(
                dict.fromkeys(_generics.iter_contained_typevars(typevars_map.values()))
            )

            with _generics.generic_recursion_self_type(origin, args) as maybe_self_type:
                cached = _generics.get_cached_generic_type_late(
                    cls, typevar_values, origin, args
                )
                if cached is not None:
                    return cached
                if maybe_self_type is not None:
                    return maybe_self_type

                try:
                    parent_ns = (
                        _typing_extra.parent_frame_namespace(parent_depth=2) or {}
                    )
                    origin.model_rebuild(_types_namespace=parent_ns)
                except PydanticUndefinedAnnotation:
                    pass

                generic_model = args[0]
                annotations: dict[str, Any] = {}
                fields: dict[str, Any] = {}
                field_definitions = cls.__get_generic_model_field_definitions__(
                    generic_model
                )
                for name, field_definition in field_definitions.items():
                    if isinstance(field_definition, tuple):
                        if len(field_definition) != 2:
                            raise PydanticUserError(
                                f"Field definition for {name!r} should a single "
                                "element representing the type or a two-tuple, the "
                                "first element being the type and the second element "
                                "the assigned value.",
                                code="create-model-field-definitions",
                            )
                        annotations[name] = field_definition[0]
                        fields[name] = field_definition[1]
                    else:
                        annotations[name] = field_definition

                namespace: dict[str, Any] = {
                    "__annotations__": annotations,
                    "__module__": origin.__module__,
                }
                bases = (origin,)
                meta, ns, kwds = prepare_class(model_name, bases)
                namespace.update(ns)
                namespace.update(fields)
                submodel = meta(
                    model_name,
                    bases,
                    namespace,
                    __pydantic_generic_metadata__={
                        "origin": origin,
                        "args": args,
                        "parameters": params,
                    },
                    __pydantic_reset_parent_namespace__=False,
                    **kwds,
                )
                cast(Any, submodel).generic_model = generic_model

                _model_module, called_globally = _get_caller_frame_info(depth=2)
                if called_globally:
                    object_by_reference = None
                    reference_name = model_name
                    reference_module_globals = sys.modules[submodel.__module__].__dict__
                    while object_by_reference is not submodel:
                        object_by_reference = reference_module_globals.setdefault(
                            reference_name, submodel
                        )
                        reference_name += "_"

                _generics.set_cached_generic_type(
                    cls, typevar_values, submodel, origin, args
                )

        return submodel

    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: type[Any]
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for name, info in getattr(generic_model, "__pydantic_fields__", {}).items():
            if name in getattr(generic_model, "model_associations", {}):
                continue
            # Normalize scalar field annotations before mapping them to criteria types.
            annotation = info.annotation
            origin = get_origin(annotation)
            if origin is Literal:
                annotation = type(get_args(annotation)[0])
            elif origin is UnionType or str(origin) == "typing.Union":
                annotation = next(
                    (arg for arg in get_args(annotation) if arg is not type(None)),
                    object,
                )
            else:
                try:
                    if is_association(cast(type[Any], annotation)):
                        annotation = object
                except TypeError:
                    annotation = object
            if isinstance(annotation, type) and annotation in cls.criteria_type_mapping:
                fields[name] = (
                    cls.criteria_type_mapping[annotation] | None,
                    Field(default=None),
                )
        return fields

    @cached_property
    def expression(self) -> Expression[bool] | None:
        expressions: list[Expression[bool]] = []
        generic_model = type(self).generic_model
        reserved = {"and_", "or_", "not_", "bookmark", "limit", "offset", "order_by"}

        for name, value in self:
            if value is None or name in reserved:
                continue
            if isinstance(value, BaseCriteria):
                column = cast(
                    Column[CriteriaValue],
                    generic_model[name],  # pyright: ignore[reportIndexIssue]
                )
                column_expressions = [
                    column.operate(operator, operator_value)
                    for attribute, operator in value.criteria_operators
                    if (operator_value := getattr(value, attribute)) is not None
                ]
                if not column_expressions:
                    continue
                expressions.append(
                    column_expressions[0]
                    if len(column_expressions) == 1
                    else Expression(kind="and", expressions=tuple(column_expressions))
                )

        if self.and_:
            for criteria in self.and_:
                expression = criteria.expression
                if expression is not None:
                    expressions.append(expression)

        if self.or_:
            or_expressions: list[Expression[bool]] = []
            for criteria in self.or_:
                expression = criteria.expression
                if expression is not None:
                    or_expressions.append(expression)
            if or_expressions:
                expressions.append(
                    or_expressions[0]
                    if len(or_expressions) == 1
                    else Expression(kind="or", expressions=tuple(or_expressions))
                )

        if self.not_:
            expression = self.not_.expression
            if expression is not None:
                expressions.append(~expression)

        if not expressions:
            return None
        return (
            expressions[0]
            if len(expressions) == 1
            else Expression(kind="and", expressions=tuple(expressions))
        )


class PagedCriteria(Criteria[P], Generic[P]):
    limit: int | None = Field(default=100, ge=1)
    offset: int | None = Field(default=None, ge=0)
    order_by: tuple[str, ...] | None = None
    bookmark: Criteria[P] | None = None

    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: type[Any]
    ) -> dict[str, Any]:
        fields = super().__get_generic_model_field_definitions__(generic_model)
        order_by_allowed = tuple(
            order for name in fields for order in (f"+{name}", f"-{name}")
        )
        if order_by_allowed:
            order_by_item = cast(Any, Literal).__getitem__(order_by_allowed)
            order_by_type = tuple.__class_getitem__((order_by_item, ...)) | None
            fields["order_by"] = (
                order_by_type,
                Field(default=None),
            )
        return fields

    @cached_property
    def expression(self) -> Expression[bool] | None:
        expressions: list[Expression[bool]] = []
        expression = super().expression
        if expression is not None:
            expressions.append(expression)
        if self.bookmark:
            bookmark_expression = self.bookmark.expression
            if bookmark_expression is not None:
                expressions.append(bookmark_expression)
        if not expressions:
            return None
        return (
            expressions[0]
            if len(expressions) == 1
            else Expression(kind="and", expressions=tuple(expressions))
        )

    @cached_property
    def orders(self) -> tuple[Order[CriteriaValue], ...]:
        # Parse compact '+field'/'-field' values into compiler order expressions.
        order_bys: list[Order[CriteriaValue]] = []
        generic_model = type(self).generic_model
        for order in self.order_by or ():
            if not order or order[0] not in "+-":
                raise ValueError("order_by entries must start with '+' or '-'")
            column = cast(
                Column[CriteriaValue],
                generic_model[order[1:]],  # pyright: ignore[reportIndexIssue]
            )
            order_bys.append(column.desc() if order[0] == "-" else column.asc())
        return tuple(order_bys)


class CursorPayload(BaseModel, Generic[P]):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        extra="forbid",
    )

    version: Literal[1] = 1
    entity: str
    criteria: PagedCriteria[P]

    @model_validator(mode="after")
    def validate_entity(self) -> Self:
        arguments = (
            getattr(type(self), "__pydantic_generic_metadata__", {}).get("args") or ()
        )
        generic_model = arguments[0] if arguments else None
        if isinstance(generic_model, type):
            expected_entity = generic_model.__name__
            if self.entity != expected_entity:
                raise PydanticCustomError(
                    "invalid_cursor", "Cursor entity does not match requested entity"
                )
        return self


class Cursor(RootModel[str], Generic[P]):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    _payload: CursorPayload[P] = PrivateAttr()

    def __str__(self) -> str:
        return self.model_dump()

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        generics = type(self).__pydantic_generic_metadata__["args"]
        generic_model = generics[0] if generics else None
        if generic_model is None:
            raise PydanticCustomError(
                "invalid_cursor", "Cursor entity does not match requested entity"
            )

        # Mypy cannot express runtime Pydantic generic indexing here.
        payload_model = cast(
            type[CursorPayload[P]],
            cast(Any, CursorPayload)[generic_model],
        )
        try:
            # Decode and validate user tokens before accepting the root string.
            token = str(self)
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode()).decode()
            payload = payload_model.model_validate_json(decoded)
        except Exception as error:
            raise PydanticCustomError(
                "invalid_cursor",
                "Invalid cursor token: {error}",
                {"error": str(error)},
            ) from None

        self._payload = payload
        return self

    @classmethod
    def from_criteria(
        cls,
        *,
        criteria: PagedCriteria[P],
    ) -> Self:
        generics = cls.__pydantic_generic_metadata__["args"]
        generic_model = generics[0] if generics else None
        if not isinstance(generic_model, type):
            raise PydanticCustomError(
                "invalid_cursor", "Cursor generic model is not specified"
            )

        # Mypy cannot express runtime Pydantic generic indexing here.
        payload_model = cast(
            type[CursorPayload[Any]],
            cast(Any, CursorPayload)[generic_model],
        )
        payload = payload_model.model_validate(
            {
                "entity": generic_model.__name__,
                "criteria": criteria,
            }
        )

        # Serialize the typed payload as a URL-safe cursor token.
        payload_json = payload.model_dump_json(by_alias=True, exclude_none=True)
        token = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
        cursor = cls.model_construct(root=token)
        cursor._payload = payload
        return cursor

    @classmethod
    def from_expression(
        cls,
        *,
        expression: Expression[bool] | None = None,
        bookmark: Expression[bool] | None = None,
        order_bys: tuple[Order[CriteriaValue], ...] = (),
        limit: int | None = 100,
        offset: int | None = None,
    ) -> Self:
        generics = cls.__pydantic_generic_metadata__["args"]
        generic_model = generics[0] if generics else None
        if not isinstance(generic_model, type):
            raise PydanticCustomError(
                "invalid_cursor", "Cursor generic model is not specified"
            )

        data: dict[str, object] = {"limit": limit}
        if expression is not None:
            data.update(expression.dump())
        if bookmark is not None:
            data["bookmark"] = bookmark.dump()
        if order_bys:
            data["order_by"] = [order_by.dump() for order_by in order_bys]
        if offset is not None:
            data["offset"] = offset

        # Mypy cannot express runtime Pydantic generic indexing here.
        criteria_model = cast(
            type[PagedCriteria[P]],
            cast(Any, PagedCriteria)[generic_model],
        )
        return cls.from_criteria(criteria=criteria_model.model_validate(data))

    @property
    def payload(self) -> CursorPayload[P]:
        return self._payload

    @property
    def version(self) -> int:
        return self.payload.version

    @property
    def entity(self) -> str:
        return self.payload.entity

    @property
    def criteria(self) -> PagedCriteria[P]:
        return self.payload.criteria

    @property
    def paged_criteria(self) -> PagedCriteria[P]:
        return self.criteria


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    items: tuple[T, ...]
    next_cursor: str | None
    has_more: bool

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[T, ...]: ...

    def __getitem__(self, index: int | slice) -> T | tuple[T, ...]:
        return self.items[index]

    def __iter__(self) -> Iterator[T]:  # type: ignore[override]
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __contains__(self, item: object) -> bool:
        return item in self.items

    def __reversed__(self) -> Iterator[T]:
        return reversed(self.items)
