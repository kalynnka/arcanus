from __future__ import annotations

from functools import cached_property, partial, wraps
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Concatenate,
    ForwardRef,
    Generic,
    Iterable,
    Literal,
    Optional,
    ParamSpec,
    Self,
    SupportsIndex,
    Type,
    TypeVar,
    Union,
    final,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel, Field, GetCoreSchemaHandler, TypeAdapter
from pydantic_core import core_schema

from arcanus.materia.base import active_materia
from arcanus.utils import get_cached_adapter

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

    from arcanus.base import BaseTransmuter

A = TypeVar("A")
T = TypeVar("T", bound="BaseTransmuter")
Optional_T = TypeVar("Optional_T", bound="BaseTransmuter | Optional[BaseTransmuter]")

P = ParamSpec("P")
R = TypeVar("R")


@final
class DefferedAssociation:
    """A type used as a sentinel for already loaded association values, for deffering the blessing"""

    def __copy__(self) -> Self: ...
    def __deepcopy__(self, memo: Any) -> Self: ...


def is_association(t: type) -> bool:
    origin = get_origin(t)
    arg = origin or t

    # Union of scalar types, e.g. Union[int, str] or Optional[str], which is Union[str, NoneType]
    if origin is Union or origin is UnionType:
        arg = get_args(t)[0]

    # Literal types, e.g. Literal["value1", "value2"]
    if origin is Literal:
        arg = type(get_args(t)[0])

    return issubclass(arg, Association)


class Association(Generic[A]):
    __generic__: Type[A]
    __instance__: BaseTransmuter | None
    __loaded__: bool
    __payloads__: A | None

    field_name: str

    @classmethod
    def __get_pydantic_generic_schema__(
        cls,
        generic_type: Type[A],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        raise NotImplementedError()

    @classmethod
    def __get_pydantic_serialize_schema__(
        cls,
        generic_type: Type[A],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.SerSchema | None:
        # TODO: Implement automatic circular reference detection in serialization.
        # Currently, circular references must be manually excluded using the exclude
        # parameter. Pydantic does not provide built-in cycle detection.
        # See: https://docs.pydantic.dev/latest/concepts/serialization/
        raise NotImplementedError()

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Type[Association[A]], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        args = get_args(source_type)

        if not args:
            raise TypeError(f"Generic type must be provided to the {source_type}.")

        generic_type = args[0]

        def validate(
            value: Any,
            handler: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> Association[A]:
            if not info.field_name:
                raise ValueError(
                    f"The association type {source_type} must be used as a model field."
                )

            materia = active_materia.get()
            value = materia.association_before_validator(cls, value, info)
            if value is DefferedAssociation:
                instance = cls()
            elif isinstance(value, cls):
                instance = value
                instance.__payloads__ = handler(instance.__payloads__)
            else:
                instance = cls(handler(value))
            instance.__generic__ = generic_type
            instance.field_name = info.field_name
            instance = materia.association_after_validator(instance, info)

            return instance

        return core_schema.with_default_schema(
            core_schema.with_info_wrap_validator_function(
                validate,
                cls.__get_pydantic_generic_schema__(generic_type, handler),
            ),
            default_factory=cls,
            serialization=cls.__get_pydantic_serialize_schema__(generic_type, handler),
        )

    @property
    def __instance_provider__(self) -> Optional[Any]:
        """Owner instance' provider, owner of this association's provider."""
        if self.__instance__ is not None:
            return self.__instance__.__transmuter_provided__
        return None

    @property
    def __provided__(self) -> Any | None:
        raise NotImplementedError()

    @cached_property
    def __validator__(self) -> TypeAdapter[A]:
        return get_cached_adapter(self.__generic__)

    @cached_property
    def used_name(self) -> str:
        return (
            alias
            if self.__instance__
            and (alias := type(self.__instance__).model_fields[self.field_name].alias)
            else self.field_name
        )

    def __init__(self, payloads: A | None = None):
        self.__instance__ = None
        self.__loaded__ = False
        self.__payloads__ = payloads

    def __await__(self):
        return self._aload().__await__()

    def __construct__(self, value: Any) -> Any:
        if issubclass(self.__generic__, BaseModel):
            if hasattr(self.__generic__, "__transmuter_materia__"):
                return self.__generic__.model_construct(data=value)
            return self.__generic__.model_construct(
                **value if isinstance(value, dict) else value.__dict__
            )
        return value

    def _load(self):
        raise NotImplementedError()

    def _aload(self):
        raise NotImplementedError()

    def prepare(self, instance: BaseTransmuter, field_name: str):
        if self.__instance__ is not None:
            return

        self.field_name = field_name
        self.field_info = type(instance).model_fields[field_name]

        self.__instance__ = instance

        annotation = self.field_info.annotation
        if isinstance(annotation, ForwardRef):
            actual_type = annotation.__forward_value__
            if actual_type is None:
                actual_type = annotation._evaluate(globals(), locals(), set())
            self.__generic__ = get_args(actual_type)[0]
        else:
            self.__generic__ = get_args(annotation)[0]

    def bless(self, value: Any) -> Any:
        """Bless the value into the generic type."""
        if active_materia.get().validate:
            return self.__validator__.validate_python(value)
        return self.__construct__(value)


class Relation(Association[Optional_T]):
    # new item and loaded item are shared the __payloads__ here
    __payloads__: Optional_T

    @classmethod
    def __get_pydantic_generic_schema__(
        cls, generic_type: type[Optional_T], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        # TODO: strict the validation for lazy-load non-optional single relationship
        # to fobid the folowing example
        # class A(BaseTransmuter):
        #     b: Relation[B] = Relation()
        # a = A(b=None)  # should raise validation error
        return core_schema.union_schema(
            choices=[
                handler.generate_schema(generic_type),
                core_schema.none_schema(),
            ]
        )

        # return handler.generate_schema(generic_type)

    @classmethod
    def __get_pydantic_serialize_schema__(
        cls, generic_type: type[Optional_T], handler: GetCoreSchemaHandler
    ) -> core_schema.SerSchema | None:
        def serialize(association: Relation[Optional_T], serializer) -> Any:
            return serializer(association.value)

        return core_schema.wrap_serializer_function_ser_schema(
            serialize,
            schema=handler.generate_schema(generic_type),
            when_used="always",
        )

    @property
    def __provided__(self) -> Any:
        if not self.__instance_provider__:
            return None

        # TODO: provider not exist, or the provided value is None both return None
        return getattr(self.__instance_provider__, self.used_name)

    @__provided__.setter
    def __provided__(self, object: Any):
        if not self.__instance_provider__:
            return  # No provider, skip syncing
        setattr(self.__instance_provider__, self.used_name, object)

    def prepare(self, instance: BaseTransmuter, field_name: str):
        super().prepare(instance, field_name)
        if (
            self.__instance_provider__
            and not self.__loaded__
            and self.__payloads__ is not None
        ):
            self.__provided__ = self.__payloads__.__transmuter_provided__

    @staticmethod
    def ensure_loaded(
        func: Callable[Concatenate[Relation[Optional_T], P], R],
    ) -> Callable[Concatenate[Relation[Optional_T], P], R]:
        @wraps(func)
        def wrapper(self: Relation[Optional_T], *args: P.args, **kwargs: P.kwargs) -> R:
            self._load()
            return func(self, *args, **kwargs)

        return wrapper

    def _load(self) -> Optional_T:
        # maybe during deepcopy from field default, or the relationship is already loaded
        if not self.__instance__ or self.__loaded__:
            return self.__payloads__

        active_materia.get().load_association(self)

        # A: No provided, None
        # B: provided value is None
        if not self.__provided__:
            return self.__payloads__

        if self.__payloads__ is not None and self.__payloads__.__transmuter_provided__:
            # Already loaded by ORM (e.g., selectinload), no need to set back
            self.__provided__ = self.__payloads__.__transmuter_provided__
        else:
            self.__payloads__ = self.bless(self.__provided__)

        self.__loaded__ = True

        return self.__payloads__

    async def _aload(self) -> Optional_T:
        # maybe during deepcopy from field default, or the relationship is already loaded
        if not self.__instance__ or self.__loaded__:
            return self.__payloads__

        await active_materia.get().aload_association(self)

        # A: No provided, None
        # B: provided value is None
        if not self.__provided__:
            return self.__payloads__

        if self.__payloads__ is not None and self.__payloads__.__transmuter_provided__:
            # Already loaded by ORM (e.g., selectinload), no need to set back
            self.__provided__ = self.__payloads__.__transmuter_provided__
        else:
            self.__payloads__ = self.bless(self.__provided__)

        self.__loaded__ = True

        return self.__payloads__

    @property
    @ensure_loaded
    def value(self) -> Optional_T:
        return self.__payloads__

    @value.setter
    @ensure_loaded
    def value(self, object: Optional_T):
        object = self.bless(object)
        if object is not None:
            self.__provided__ = object.__transmuter_provided__
        else:
            self.__provided__ = None
        self.__payloads__ = object


# built-in types must be put at front to avoid pydantic convert it to built-in types
class RelationCollection(list[T], Association[T]):
    # new items are held in __payloads__, loaded items are kept in the list itself
    __payloads__: list[T]

    @classmethod
    def __get_pydantic_generic_schema__(
        cls,
        generic_type: Type[T],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.list_schema(handler.generate_schema(generic_type))

    @classmethod
    def __get_pydantic_serialize_schema__(
        cls, generic_type: Type[T], handler: GetCoreSchemaHandler
    ) -> core_schema.SerSchema | None:
        def serialize(association: RelationCollection[T], serializer) -> Any:
            return serializer(association.copy())

        return core_schema.wrap_serializer_function_ser_schema(
            serialize,
            schema=core_schema.list_schema(handler.generate_schema(generic_type)),
            when_used="always",
        )

    def __init__(self, payloads: Iterable[T] | None = None):
        super().__init__()
        self.__instance__ = None
        self.__loaded__ = False
        self.__payloads__ = list(payloads) if payloads else []

    @property
    def __provided__(self) -> list[Any] | None:
        # The return type should be a duck typed list-like object provided by the current materia provider.
        # For example, with SQLAlchemyMateria, it would be a InstrumentedList[list[...]] which is actually a sqlalchemy descriptor.
        if not self.__instance_provider__:
            return None
        return getattr(self.__instance_provider__, self.used_name)

    @cached_property
    def __list_validator__(self) -> TypeAdapter[list[T]]:
        return get_cached_adapter(list[self.__generic__])

    @overload
    def bless(self, value: T) -> T: ...
    @overload
    def bless(self, value: Iterable[Any]) -> list[T]: ...
    @overload
    def bless(self, value: Any) -> T: ...
    def bless(self, value: Any | Iterable[Any]) -> T | Iterable[T]:
        """Bless the value into the generic type."""
        validate = active_materia.get().validate
        is_iterable = isinstance(value, Iterable) and not isinstance(
            value, get_origin(self.__generic__) or self.__generic__
        )

        if validate:
            if is_iterable:
                return self.__list_validator__.validate_python(value)
            else:
                return self.__validator__.validate_python(value)
        else:
            if is_iterable:
                return [self.__construct__(item) for item in value]
            else:
                return self.__construct__(value)

    def prepare(self, instance: BaseTransmuter, field_name: str):
        super().prepare(instance, field_name)
        if self.__payloads__:
            # manualy enforce loading first to remove duplicates in payloads
            # objects already assigned to the relationship may be add to payloads during revalidation
            self._load()
            self.extend(self.__payloads__)
            self.__payloads__.clear()

    @staticmethod
    def ensure_loaded(
        func: Callable[Concatenate[RelationCollection[T], P], R],
    ) -> Callable[Concatenate[RelationCollection[T], P], R]:
        @wraps(func)
        def wrapper(
            self: RelationCollection[T], *args: P.args, **kwargs: P.kwargs
        ) -> R:
            self._load()
            return func(self, *args, **kwargs)

        return wrapper

    def _load(self):
        # maybe during deepcopy from field default
        if not self.__instance__:
            return self

        # or the relationship is already loaded
        if self.__loaded__:
            return self

        active_materia.get().load_association(self)

        # A: No provided, None
        # B: provided value is empty, []
        if not (self.__provided__):
            return self

        # TODO: Better way to avoid duplication relationship append ?
        self.__payloads__ = [
            payload
            for payload in self.__payloads__
            if payload.__transmuter_provided__ not in set(self.__provided__)
        ]

        if not len(self.__provided__) == super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().extend(self.bless(self.__provided__))
        self.__loaded__ = True

        return self

    async def _aload(self):
        # maybe during deepcopy from field default
        if not self.__instance__:
            return self

        # or the relationship is already loaded
        if self.__loaded__:
            return self

        # A: No provided, None
        # B: provided value is empty, []
        if not (provided := await active_materia.get().aload_association(self)):
            return self

        # TODO: Better way to avoid duplication relationship append ?
        self.__payloads__ = [
            payload
            for payload in self.__payloads__
            if payload.__transmuter_provided__ not in set(provided)
        ]

        if not len(provided) == super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().extend(self.bless(provided))
        self.__loaded__ = True

    @overload
    def __getitem__(self, index: SupportsIndex) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> list[T]: ...
    @ensure_loaded
    def __getitem__(self, index: SupportsIndex | slice) -> T | list[T]:
        return super().__getitem__(index)

    @ensure_loaded
    def __iter__(self):
        return super().__iter__()

    @ensure_loaded
    def __len__(self):
        return super().__len__()

    @ensure_loaded
    def __contains__(self, key: T) -> bool:
        return super().__contains__(key)

    @ensure_loaded
    def __bool__(self):
        return super().__len__() > 0

    @overload
    def __setitem__(self, key: SupportsIndex, value: T) -> None: ...
    @overload
    def __setitem__(self, key: slice, value: Iterable[T]) -> None: ...
    @ensure_loaded
    def __setitem__(self, key: slice, value: T | Iterable[T]):
        if isinstance(value, Iterable):
            items = self.bless(value)
            if self.__provided__ is not None:
                self.__provided__[key] = [
                    item.__transmuter_provided__ for item in items
                ]
            super().__setitem__(key, items)
        else:
            item = self.bless(value)
            if self.__provided__ is not None:
                self.__provided__[key] = item.__transmuter_provided__
            super().__setitem__(key, item)

    @ensure_loaded
    def __delitem__(self, key: slice):
        if self.__provided__ is not None:
            self.__provided__.__delitem__(key)
        super().__delitem__(key)

    @ensure_loaded
    def __add__(self, other: Iterable[T]):
        return self.copy() + self.bless(other)

    @ensure_loaded
    def __iadd__(self, other: Iterable[T]):
        self.extend(other)
        return self

    def __mul__(self, other):
        raise NotImplementedError(
            "Left multiplication on relationship is not supported."
        )

    def __rmul__(self, other):
        raise NotImplementedError(
            "Right multiplication on relationship is not supported."
        )

    def __imul__(self, other):
        raise NotImplementedError(
            "Self multiplication on relationship is not supported."
        )

    @ensure_loaded
    def __eq__(self, other: list[T]):
        return super().__eq__(other)

    @ensure_loaded
    def __ne__(self, other: list[T]):
        return super().__ne__(other)

    @ensure_loaded
    def __lt__(self, other: list[T]):
        return super().__lt__(other)

    @ensure_loaded
    def __le__(self, other: list[T]):
        return super().__le__(other)

    @ensure_loaded
    def __gt__(self, other: list[T]):
        return super().__gt__(other)

    @ensure_loaded
    def __ge__(self, other: list[T]):
        return super().__ge__(other)

    # @ensure_loaded
    def __repr__(self):
        # return super().__repr__()
        return f"RelationCollection[{self.__generic__.__name__}], instance={id(self.__instance__)}, size={super().__len__()}"

    @ensure_loaded
    def __str__(self):
        return super().__str__()

    @ensure_loaded
    def __reversed__(self):
        return super().__reversed__()

    @ensure_loaded
    def append(self, object: T):
        object = self.bless(object)
        if self.__provided__ is not None:
            self.__provided__.append(
                object.__transmuter_provided__
                if hasattr(object, "__transmuter_provided__")
                else object
            )
        super().append(object)

    @ensure_loaded
    def extend(self, iterable: Iterable[T]):
        iterable = self.bless(iterable)
        if self.__provided__ is not None:
            self.__provided__.extend(
                (
                    item.__transmuter_provided__
                    if hasattr(item, "__transmuter_provided__")
                    else item
                    for item in iterable
                )
            )
        super().extend(iterable)

    @ensure_loaded
    def clear(self):
        if self.__provided__ is not None:
            self.__provided__.clear()
        super().clear()

    @ensure_loaded
    def copy(self):
        return super().copy()

    @ensure_loaded
    def count(self, value: T) -> int:
        return super().count(value)

    @ensure_loaded
    def index(self, value, start=0, stop=None):
        if stop is None:
            return super().index(value, start)
        return super().index(value, start, stop)

    @ensure_loaded
    def insert(self, index: SupportsIndex, object: T):
        object = self.bless(object)
        if self.__provided__ is not None:
            self.__provided__.insert(index, object.__transmuter_provided__)
        super().insert(index, object)

    @ensure_loaded
    def pop(self, index: SupportsIndex = -1):
        item = super().pop(index)
        if self.__provided__ is not None:
            self.__provided__.remove(item.__transmuter_provided__)
        return item

    @ensure_loaded
    def remove(self, value: T):
        item: T = self.bless(value)
        if self.__provided__ is not None:
            self.__provided__.remove(item.__transmuter_provided__)
        super().remove(value)

    @ensure_loaded
    def reverse(self):
        super().reverse()

    @ensure_loaded
    def sort(
        self,
        *,
        key: Callable[[T], SupportsRichComparison],
        reverse: bool = False,
    ):
        super().sort(key=key, reverse=reverse)


Relationship = partial(Field, default_factory=Relation, frozen=True)
Relationships = partial(Field, default_factory=RelationCollection, frozen=True)
