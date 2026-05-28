from __future__ import annotations

import base64
import sys
from datetime import datetime
from functools import cached_property
from types import UnionType, prepare_class
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Iterable,
    Iterator,
    Literal,
    Self,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    create_model,
    model_validator,
)
from pydantic._internal import _forward_ref, _generics, _typing_extra, _utils
from pydantic._internal._generics import _get_caller_frame_info
from pydantic.errors import PydanticUndefinedAnnotation, PydanticUserError
from pydantic_core import PydanticCustomError

from arcanus.association import is_association
from arcanus.base import TransmuterType, transmuter_type
from arcanus.expression import Column, Expression, Order, and_, or_

P = TypeVar("P")
R = TypeVar("R")
T = TypeVar("T")
S = TypeVar("S", bound=str)
N = TypeVar("N", bound=float | int | UUID | datetime | bool)
CriteriaValue = str | UUID | int | float | bool | datetime
CriteriaValueType = (
    type[str] | type[UUID] | type[int] | type[float] | type[bool] | type[datetime]
)
CriteriaExampleValue = str | int | float | bool
CriteriaExample = dict[str, CriteriaExampleValue | list[CriteriaExampleValue]]

CRITERIA_CURSOR_VERSION = 1


class _ClassProperty(Generic[R]):
    def __init__(self, fget: Callable[[Any], R]) -> None:
        self.fget = fget

    def __get__(self, instance: object, owner: type[Any] | None = None) -> R:
        return self.fget(owner or type(instance))


class BaseCriteria(BaseModel, Generic[T]):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_alias=True,
        validate_by_name=True,
        extra="forbid",
    )

    eq: T | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (("eq", "eq"),)


class ExactCriteria(BaseCriteria[T]):
    ne: T | None = None
    in_: tuple[T, ...] | None = Field(default=None, alias="in")
    not_in: tuple[T, ...] | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *BaseCriteria.criteria_operators,
        ("ne", "ne"),
        ("in_", "in_"),
        ("not_in", "not_in"),
    )


class TextCriteria(ExactCriteria[S]):
    lt: S | None = None
    le: S | None = None
    gt: S | None = None
    ge: S | None = None
    contains: S | None = None
    not_contains: S | None = None
    starts_with: S | None = None
    ends_with: S | None = None
    like: S | None = None
    ilike: S | None = None
    not_like: S | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *ExactCriteria.criteria_operators,
        ("lt", "lt"),
        ("le", "le"),
        ("gt", "gt"),
        ("ge", "ge"),
        ("contains", "contains"),
        ("not_contains", "not_contains"),
        ("starts_with", "starts_with"),
        ("ends_with", "ends_with"),
        ("like", "like"),
        ("ilike", "ilike"),
        ("not_like", "not_like"),
    )


class NumericCriteria(ExactCriteria[N]):
    lt: N | None = None
    le: N | None = None
    gt: N | None = None
    ge: N | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *ExactCriteria.criteria_operators,
        ("lt", "lt"),
        ("le", "le"),
        ("gt", "gt"),
        ("ge", "ge"),
    )


class BookmarkValueCriteria(BaseCriteria[T]):
    lt: T | None = None
    gt: T | None = None

    criteria_operators: ClassVar[tuple[tuple[str, str], ...]] = (
        *BaseCriteria.criteria_operators,
        ("lt", "lt"),
        ("gt", "gt"),
    )


class ModelGeneric(BaseModel, Generic[P]):
    generic_model: ClassVar[TransmuterType]

    # Build model-specific fields while preserving Pydantic's generic cache.
    def __class_getitem__(
        cls, typevar_values: object | tuple[object, ...]
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
            model_args = cast(tuple[type[Any], ...], args)

            origin = cls.__pydantic_generic_metadata__["origin"] or cls
            model_name = origin.model_parametrized_name(model_args)
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

                generic_model = (
                    transmuter_type(args[0]) if isinstance(args[0], type) else None
                )
                annotations: dict[str, Any] = {}
                fields: dict[str, Any] = {}
                field_definitions = (
                    cls.__get_generic_model_field_definitions__(generic_model)
                    if generic_model is not None
                    else {}
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
                if generic_model is not None:
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
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        return {}


class ScalarCriteria(ModelGeneric[P]):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_alias=True,
        validate_by_name=True,
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    criteria_type_mapping: ClassVar[
        dict[CriteriaValueType, type[BaseCriteria[Any]]]
    ] = {
        str: TextCriteria[str],
        UUID: NumericCriteria[UUID],
        int: NumericCriteria[int],
        float: NumericCriteria[float],
        bool: NumericCriteria[bool],
        datetime: NumericCriteria[datetime],
    }

    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        scalar_fields: dict[str, Any] = {}

        for name, info in generic_model.__pydantic_fields__.items():
            if name in generic_model.model_associations:
                continue
            # Normalize scalar field annotations before mapping them to criteria types.
            annotation = info.annotation
            origin = get_origin(annotation)
            if origin is UnionType or str(origin) == "typing.Union":
                annotation = next(
                    (arg for arg in get_args(annotation) if arg is not type(None)),
                    object,
                )
                origin = get_origin(annotation)
            if origin is Literal:
                literal_values = get_args(annotation)
                if not literal_values:
                    continue
                criteria_type = cast(
                    type[BaseCriteria[Any]], cast(Any, ExactCriteria)[annotation]
                )
                scalar_fields[name] = (
                    criteria_type | None,
                    Field(default=None),
                )
                continue
            else:
                try:
                    if is_association(cast(type[Any], annotation)):
                        annotation = object
                except TypeError:
                    annotation = object
            if isinstance(annotation, type) and annotation in cls.criteria_type_mapping:
                criteria_value_type = cast(CriteriaValueType, annotation)
                criteria_type = cast(
                    type[BaseCriteria[Any]],
                    cls.criteria_type_mapping[criteria_value_type],
                )
                scalar_fields[name] = (
                    criteria_type | None,
                    Field(default=None),
                )

        return scalar_fields

    @classmethod
    def __get_generic_model_examples__(
        cls, generic_model: TransmuterType
    ) -> dict[str, CriteriaExample]:
        scalar_examples: dict[str, CriteriaExample] = {}

        def example_value(annotation: CriteriaValueType) -> CriteriaExampleValue:
            if annotation is str:
                return "string"
            if annotation is UUID:
                return "3fa85f64-5717-4562-b3fc-2c963f66afa6"
            if annotation is bool:
                return True
            if annotation is datetime:
                return "2026-05-25T16:59:31.252Z"
            if annotation is int:
                return 1
            if annotation is float:
                return 1.0
            return "string"

        def criteria_example(
            criteria_type: type[BaseCriteria[Any]], value: CriteriaExampleValue
        ) -> CriteriaExample:
            return {
                (criteria_type.model_fields[attribute].alias or attribute): [value]
                if attribute in {"in_", "not_in"}
                else value
                for attribute, _ in criteria_type.criteria_operators
            }

        for name, info in generic_model.__pydantic_fields__.items():
            if name in generic_model.model_associations:
                continue
            annotation = info.annotation
            origin = get_origin(annotation)
            if origin is UnionType or str(origin) == "typing.Union":
                annotation = next(
                    (arg for arg in get_args(annotation) if arg is not type(None)),
                    object,
                )
                origin = get_origin(annotation)
            if origin is Literal:
                literal_values = get_args(annotation)
                if not literal_values:
                    continue
                criteria_type = cast(
                    type[BaseCriteria[Any]], cast(Any, ExactCriteria)[annotation]
                )
                example = literal_values[0]
                scalar_examples[name] = criteria_example(
                    criteria_type,
                    example
                    if isinstance(example, (str, int, float, bool))
                    else "string",
                )
                continue
            else:
                try:
                    if is_association(cast(type[Any], annotation)):
                        annotation = object
                except TypeError:
                    annotation = object
            if isinstance(annotation, type) and annotation in cls.criteria_type_mapping:
                criteria_value_type = cast(CriteriaValueType, annotation)
                criteria_type = cast(
                    type[BaseCriteria[Any]],
                    cls.criteria_type_mapping[criteria_value_type],
                )
                scalar_examples[name] = criteria_example(
                    criteria_type, example_value(criteria_value_type)
                )
        return scalar_examples

    @cached_property
    def expressions(self) -> tuple[Expression[bool], ...]:
        expressions: list[Expression[bool]] = []
        generic_model = type(self).generic_model
        reserved = {"limit", "offset", "order_by", "cursor"}

        for name, value in self:
            if value is None or name in reserved:
                continue
            if isinstance(value, BaseCriteria):
                column = cast(
                    Column[CriteriaValue],
                    generic_model[name],
                )
                column_expressions = [
                    column.operate(operator, operator_value)
                    for attribute, operator in value.criteria_operators
                    if (operator_value := getattr(value, attribute)) is not None
                ]
                expressions.extend(column_expressions)

        return tuple(expressions)


class Criteria(ScalarCriteria[P]):
    and_: tuple[Criteria[P], ...] | None = Field(default=None, alias="and")
    or_: tuple[Criteria[P], ...] | None = Field(default=None, alias="or")
    not_: Criteria[P] | None = Field(default=None, alias="not")

    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        scalar_fields = super().__get_generic_model_field_definitions__(generic_model)
        scalar_examples = cls.__get_generic_model_examples__(generic_model)
        first_example = next(iter(scalar_examples.items()), None)
        second_example = next(
            (
                item
                for item in scalar_examples.items()
                if first_example is None or item[0] != first_example[0]
            ),
            first_example,
        )
        and_example = (
            [
                {first_example[0]: first_example[1]},
                {second_example[0]: second_example[1]},
            ]
            if first_example is not None and second_example is not None
            else []
        )
        single_example = (
            {first_example[0]: first_example[1]} if first_example is not None else {}
        )
        and_examples = cast(Any, [and_example])
        single_examples = cast(Any, [single_example])

        criteria_model = cast(type[Criteria[P]], cast(Any, Criteria)[generic_model])
        fields: dict[str, Any] = {}
        fields["and_"] = (
            tuple.__class_getitem__((criteria_model, ...)) | None,
            Field(
                default=None,
                alias="and",
                json_schema_extra={"examples": and_examples},
            ),
        )
        fields["or_"] = (
            tuple.__class_getitem__((criteria_model, ...)) | None,
            Field(
                default=None,
                alias="or",
                json_schema_extra={"examples": and_examples},
            ),
        )
        fields["not_"] = (
            criteria_model | None,
            Field(
                default=None,
                alias="not",
                json_schema_extra={"examples": single_examples},
            ),
        )
        fields.update(scalar_fields)
        return fields

    @cached_property
    def expressions(self) -> tuple[Expression[bool], ...]:
        expressions = list(super().expressions)

        if self.and_:
            for criteria in self.and_:
                expressions.extend(criteria.expressions)

        if self.or_:
            or_expressions: list[Expression[bool]] = []
            for criteria in self.or_:
                branch_expressions = criteria.expressions
                if len(branch_expressions) == 1:
                    or_expressions.append(branch_expressions[0])
                elif branch_expressions:
                    or_expressions.append(and_(branch_expressions))
            if or_expressions:
                expressions.append(or_(or_expressions))

        if self.not_:
            for expression in self.not_.expressions:
                expressions.append(~expression)

        return tuple(expressions)


class NestedCriteriaBranch(Criteria[P]):
    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        fields = super().__get_generic_model_field_definitions__(generic_model)
        try:
            annotations = get_type_hints(generic_model)
        except (NameError, TypeError):
            annotations = {}
        for name, info in generic_model.model_associations.items():
            annotation = annotations.get(name, info.annotation)
            try:
                if not is_association(
                    cast(type[Any], get_origin(annotation) or annotation)
                ):
                    continue
            except TypeError:
                continue
            related_model = next(
                (
                    argument
                    for argument in reversed(get_args(annotation))
                    if isinstance(argument, type)
                    and hasattr(argument, "__pydantic_fields__")
                ),
                None,
            )
            if related_model is None:
                continue
            criteria_model = cast(
                type[Criteria[P]],
                cast(Any, Criteria)[related_model],
            )
            fields[name] = (criteria_model | None, Field(default=None))
        return fields

    @cached_property
    def expressions(self) -> tuple[Expression[bool], ...]:
        expressions = list(super().expressions)

        generic_model = type(self).generic_model
        try:
            annotations = get_type_hints(generic_model)
        except (NameError, TypeError):
            annotations = {}
        for name in generic_model.model_associations:
            criteria = getattr(self, name, None)
            if not isinstance(criteria, Criteria):
                continue
            for expression in criteria.expressions:
                column = cast(Column[CriteriaValue], generic_model[name])
                annotation = annotations.get(
                    name, generic_model.model_associations[name].annotation
                )
                origin = get_origin(annotation) or annotation
                is_collection = isinstance(origin, type) and any(
                    base in {list, set, dict} for base in origin.__mro__
                )
                expressions.append(
                    column.any(expression) if is_collection else column.has(expression)
                )

        return tuple(expressions)


class NestedCriteria(NestedCriteriaBranch[P]):
    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        fields = super().__get_generic_model_field_definitions__(generic_model)
        branch_model = cast(
            type[NestedCriteriaBranch[P]],
            cast(Any, NestedCriteriaBranch)[generic_model],
        )
        fields["and_"] = (
            tuple.__class_getitem__((branch_model, ...)) | None,
            Field(default=None, alias="and"),
        )
        fields["or_"] = (
            tuple.__class_getitem__((branch_model, ...)) | None,
            Field(default=None, alias="or"),
        )
        fields["not_"] = (
            branch_model | None,
            Field(default=None, alias="not"),
        )
        return fields


class Ordering(RootModel[tuple[str, ...]], Generic[P]):
    model_config = ConfigDict(frozen=True)

    generic_model: ClassVar[TransmuterType]
    generic_cache: ClassVar[
        dict[tuple[type[BaseModel], TransmuterType], type[BaseModel]]
    ] = {}

    def __class_getitem__(
        cls, generic_model: object | tuple[object, ...]
    ) -> type[BaseModel] | _forward_ref.PydanticRecursiveRef:
        if isinstance(generic_model, tuple):
            if len(generic_model) != 1:
                raise TypeError(f"{cls.__name__} expects exactly one generic model")
            generic_model = generic_model[0]

        if not isinstance(generic_model, type):
            return cast(
                type[BaseModel] | _forward_ref.PydanticRecursiveRef,
                super().__class_getitem__(cast(Any, generic_model)),
            )
        generic_model_type = transmuter_type(generic_model)

        cache_key = (cls, generic_model_type)
        if cache_key in cls.generic_cache:
            return cls.generic_cache[cache_key]

        criteria_model = cast(
            type[Criteria[P]], cast(Any, Criteria)[generic_model_type]
        )
        order_by_allowed = tuple(
            order
            for name in criteria_model.__pydantic_fields__
            if name not in {"and_", "or_", "not_"}
            for order in (f"+{name}", f"-{name}")
        )
        root_type: Any = tuple[str, ...]
        if order_by_allowed:
            order_by_item = cast(Any, Literal).__getitem__(order_by_allowed)
            root_type = tuple.__class_getitem__((order_by_item, ...))

        model = cast(
            type[BaseModel],
            create_model(
                f"{cls.__name__}[{generic_model_type.__name__}]",
                __base__=cls,
                __module__=cls.__module__,
                root=(root_type, Field(default=())),
            ),
        )
        cast(Any, model).generic_model = generic_model_type
        cls.generic_cache[cache_key] = model
        return model

    @classmethod
    def from_orders(cls, order_bys: tuple[Order[CriteriaValue], ...]) -> Self:
        return cls.model_validate(tuple(order_by.dump() for order_by in order_bys))

    @cached_property
    def orders(self) -> tuple[Order[CriteriaValue], ...]:
        order_bys: list[Order[CriteriaValue]] = []
        generic_model = type(self).generic_model
        for order in self.root:
            column = cast(
                Column[CriteriaValue],
                generic_model[order[1:]],
            )
            order_bys.append(column.desc() if order[0] == "-" else column.asc())
        return tuple(order_bys)

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def __bool__(self) -> bool:
        return bool(self.root)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Ordering):
            return self.root == other.root
        return self.root == other


class BookmarkCriteria(ScalarCriteria[P]):
    criteria_type_mapping: ClassVar[
        dict[CriteriaValueType, type[BaseCriteria[Any]]]
    ] = {
        str: BookmarkValueCriteria[str],
        UUID: BookmarkValueCriteria[UUID],
        int: BookmarkValueCriteria[int],
        float: BookmarkValueCriteria[float],
        bool: BookmarkValueCriteria[bool],
        datetime: BookmarkValueCriteria[datetime],
    }

    @classmethod
    def __get_generic_model_field_definitions__(
        cls, generic_model: TransmuterType
    ) -> dict[str, Any]:
        fields = super().__get_generic_model_field_definitions__(generic_model)
        bookmark_model = cast(
            type[BookmarkCriteria[P]], cast(Any, BookmarkCriteria)[generic_model]
        )
        fields["and_"] = (
            tuple.__class_getitem__((bookmark_model, ...)) | None,
            Field(default=None, alias="and"),
        )
        fields["or_"] = (
            tuple.__class_getitem__((bookmark_model, ...)) | None,
            Field(default=None, alias="or"),
        )
        return fields

    @cached_property
    def expression(self) -> Expression[bool] | None:
        expressions = list(super().expressions)

        if and_criteria := getattr(self, "and_", None):
            for criteria in and_criteria:
                expression = criteria.expression
                if expression is not None:
                    expressions.append(expression)

        if or_criteria := getattr(self, "or_", None):
            or_expressions: list[Expression[bool]] = []
            for criteria in or_criteria:
                expression = criteria.expression
                if expression is not None:
                    or_expressions.append(expression)
            if or_expressions:
                expressions.append(or_(or_expressions))

        if not expressions:
            return None
        return expressions[0] if len(expressions) == 1 else and_(expressions)


def bookmark_criteria_fields(bookmark: BookmarkCriteria[Any]) -> set[str]:
    fields: set[str] = set()
    for name, value in bookmark:
        if value is None:
            continue
        if name in {"and_", "or_"}:
            for branch in value:
                fields.update(bookmark_criteria_fields(branch))
            continue
        if name == "not_":
            raise PydanticCustomError(
                "invalid_cursor",
                "Invalid cursor bookmark: Cursor bookmark cannot contain not",
            )
        if not isinstance(value, BaseCriteria):
            raise PydanticCustomError(
                "invalid_cursor",
                "Invalid cursor bookmark: Cursor bookmark can only contain scalar criteria",
            )
        fields.add(name)
    return fields


class CursorPayload(BaseModel, Generic[P]):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        extra="forbid",
    )

    version: Literal[1] = CRITERIA_CURSOR_VERSION
    entity: str
    criteria: Criteria[P] | None = None
    limit: int | None = Field(default=100, ge=1)
    order_by: Ordering[P]
    bookmark: BookmarkCriteria[P]

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
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
        if not self.order_by:
            raise PydanticCustomError("invalid_cursor", "Cursor requires order_by")
        order_names = tuple(order[1:] for order in self.order_by)
        order_name_set = set(order_names)
        bookmark_names = bookmark_criteria_fields(self.bookmark)
        if not bookmark_names <= order_name_set:
            raise PydanticCustomError(
                "invalid_cursor",
                "Cursor bookmark fields must be present in order_by",
            )
        return self


class NestedCursorPayload(CursorPayload[P]):
    criteria: NestedCriteria[P] | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class Cursor(RootModel[str], Generic[P]):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        ignored_types=(_ClassProperty,),
    )

    payload_type: ClassVar[type[BaseModel]] = CursorPayload
    criteria_type: ClassVar[type[BaseModel]] = Criteria

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
            cast(Any, type(self).payload_type)[generic_model],
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

    @_ClassProperty
    def generic_model(cls) -> type[P]:
        generics = cls.__pydantic_generic_metadata__["args"]
        generic_model = generics[0] if generics else None
        if not isinstance(generic_model, type):
            raise PydanticCustomError(
                "invalid_cursor", "Cursor generic model is not specified"
            )
        return generic_model

    @classmethod
    def from_expressions(
        cls,
        *,
        expressions: Iterable[Expression[bool]] | None = None,
        bookmark: Expression[bool] | None = None,
        limit: int | None = None,
        order_bys: tuple[Order[CriteriaValue], ...],
    ) -> Self:
        generic_model = cls.generic_model

        # Mypy cannot express runtime Pydantic generic indexing here.
        criteria_model = cast(
            type[Criteria[P]], cast(Any, cls.criteria_type)[generic_model]
        )
        payload_model = cast(
            type[CursorPayload[P]], cast(Any, cls.payload_type)[generic_model]
        )
        order_by_model = cast(type[Ordering[P]], cast(Any, Ordering)[generic_model])
        criteria_expressions = tuple(expressions or ())
        criteria_expression = (
            None
            if not criteria_expressions
            else criteria_expressions[0]
            if len(criteria_expressions) == 1
            else and_(criteria_expressions)
        )
        criteria = (
            criteria_model.model_validate(criteria_expression.dump())
            if criteria_expression is not None
            else None
        )
        order_by = order_by_model.from_orders(order_bys)
        bookmark_model = cast(
            type[BookmarkCriteria[P]], cast(Any, BookmarkCriteria)[generic_model]
        )
        bookmark_criteria = bookmark_model.model_validate(
            bookmark.dump() if bookmark is not None else {}
        )

        payload = payload_model(
            entity=generic_model.__name__,
            criteria=criteria,
            limit=limit,
            order_by=order_by,
            bookmark=bookmark_criteria,
        )

        payload_json = payload.model_dump_json(by_alias=True, exclude_none=True)
        token = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
        cursor = cls.model_construct(root=token)
        cursor._payload = payload
        return cursor

    @classmethod
    def bookmark_from_item(
        cls,
        item: P,
        order_bys: tuple[Order[CriteriaValue], ...],
    ) -> Expression[bool]:
        if not order_bys:
            raise PydanticCustomError(
                "invalid_cursor", "Cursor bookmark requires order_by"
            )
        clauses: list[Expression[bool]] = []
        equalities: list[Expression[bool]] = []
        for order_by in order_bys:
            column = order_by.column
            value = getattr(item, column.field_name)
            comparison = column < value if order_by.descending else column > value
            clauses.append(
                comparison if not equalities else and_((*equalities, comparison))
            )
            equalities.append(column == value)
        return clauses[0] if len(clauses) == 1 else or_(clauses)

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
    def criteria(self) -> Criteria[P] | None:
        return self.payload.criteria

    @property
    def limit(self) -> int | None:
        return self.payload.limit

    @property
    def order_by(self) -> Ordering[P]:
        return self.payload.order_by

    @property
    def bookmark(self) -> BookmarkCriteria[P]:
        return self.payload.bookmark


class NestedCursor(Cursor[P]):
    payload_type: ClassVar[type[BaseModel]] = NestedCursorPayload
    criteria_type: ClassVar[type[BaseModel]] = NestedCriteria

    @property
    def payload(self) -> NestedCursorPayload[P]:
        return cast(NestedCursorPayload[P], self._payload)

    @property
    def criteria(self) -> NestedCriteria[P] | None:
        return self.payload.criteria


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    items: tuple[T, ...]
    total: int = 0
    next_cursor: str
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
