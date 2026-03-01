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
    Mapping,
    Optional,
    ParamSpec,
    Self,
    SupportsIndex,
    Type,
    TypeVar,
    Union,
    cast,
    final,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from pydantic import Field, GetCoreSchemaHandler, TypeAdapter
from pydantic_core import core_schema

from arcanus.materia.base import active_materia
from arcanus.utils import get_cached_adapter

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

    from arcanus.base import Transmuter

A = TypeVar("A")
K = TypeVar("K")
T = TypeVar("T", bound="Transmuter")
Optional_T = TypeVar("Optional_T", bound="Transmuter | Optional[Transmuter]")

P = ParamSpec("P")
R = TypeVar("R")


@final
class DefferedAssociation:
    """A type used as a sentinel for already loaded association values, for deffering the blessing"""

    def __copy__(self) -> Self: ...


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
    __instance__: Transmuter | None
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
            # if not info.field_name:
            #     raise ValueError(
            #         f"The association type {source_type} must be used as a model field."
            #     )

            # materia = active_materia.get()
            # value = materia.association_before_validator(cls, value, info)

            if value is DefferedAssociation:
                instance = cls()
            elif type(value) is cls:
                instance = value
                instance.__payloads__ = handler(instance.__payloads__)
            else:
                instance = cls(handler(value))

            instance.__generic__ = generic_type
            instance.field_name = info.field_name  # pyright: ignore[reportAttributeAccessIssue]
            # instance = materia.association_after_validator(instance, info)

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
            if self.__instance__ and (alias := self.field_info.alias)
            else self.field_name
        )

    def __init__(self, payloads: A | None = None):
        self.__instance__ = None
        self.__loaded__ = False
        self.__payloads__ = payloads

    def __await__(self):
        raise NotImplementedError("This association is not awaitable.")

    def _load(self) -> Self:
        raise NotImplementedError(
            "This association does not support synchronous loading."
        )

    def _aload(self) -> Self:
        raise NotImplementedError(
            "This association does not support asynchronous loading."
        )

    def prepare(self, instance: Transmuter, field_name: str):
        if self.__instance__ is not None:
            return

        self.field_name = field_name
        self.field_info = type(instance).__pydantic_fields__[field_name]

        self.__instance__ = instance

        annotation = self.field_info.annotation
        if isinstance(annotation, ForwardRef):
            resolved_hints = get_type_hints(type(instance))
            actual_type = resolved_hints[field_name]
            self.__generic__ = get_args(actual_type)[0]
        else:
            self.__generic__ = get_args(annotation)[0]

    def bless(self, value: Any) -> Any:
        """Bless the value into the generic type."""
        return self.__validator__.validate_python(value)


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
            fields_set = getattr(
                association.__instance__, "__pydantic_fields_set__", None
            )
            if (
                association.__instance__
                and fields_set is not None
                and association.field_name in fields_set
            ):
                return serializer(association.value)
            return serializer(association.__payloads__)

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

    def prepare(self, instance: Transmuter, field_name: str):
        super().prepare(instance, field_name)
        if self.__payloads__ is not None:
            self._load()
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

    def __await__(self):
        return self._aload().__await__()

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
            fields_set = getattr(
                association.__instance__, "__pydantic_fields_set__", None
            )
            if (
                association.__instance__
                and fields_set is not None
                and association.field_name in fields_set
            ):
                return serializer(association.copy())
            return serializer(list.copy(association))

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
        is_iterable = isinstance(value, Iterable) and not isinstance(
            value, get_origin(self.__generic__) or self.__generic__
        )

        if is_iterable:
            return self.__list_validator__.validate_python(value)
        else:
            return self.__validator__.validate_python(value)

    def prepare(self, instance: Transmuter, field_name: str):
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

        return self

    def __await__(self):
        return self._aload().__await__()

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
    def __setitem__(self, key: SupportsIndex | slice, value: T | Iterable[T]):
        if isinstance(value, Iterable):
            items = self.bless(value)
            slc = cast(slice, key)
            if self.__provided__ is not None:
                self.__provided__[slc] = [
                    item.__transmuter_provided__ for item in items
                ]
            super().__setitem__(slc, items)
        else:
            item = self.bless(value)
            idx = cast(SupportsIndex, key)
            if self.__provided__ is not None:
                self.__provided__[idx] = item.__transmuter_provided__
            super().__setitem__(idx, item)

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


# built-in types must be put at front to avoid pydantic convert it to built-in types
class RelationSet(set[T], Association[T]):
    # new items are held in __payloads__, loaded items are kept in the set itself
    __payloads__: set[T]

    @classmethod
    def __get_pydantic_generic_schema__(
        cls,
        generic_type: Type[T],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.set_schema(handler.generate_schema(generic_type))

    @classmethod
    def __get_pydantic_serialize_schema__(
        cls, generic_type: Type[T], handler: GetCoreSchemaHandler
    ) -> core_schema.SerSchema | None:
        def serialize(association: RelationSet[T], serializer) -> Any:
            fields_set = getattr(
                association.__instance__, "__pydantic_fields_set__", None
            )
            if (
                association.__instance__
                and fields_set is not None
                and association.field_name in fields_set
            ):
                return serializer(list(association.copy()))
            return serializer(list(set.copy(association)))

        return core_schema.wrap_serializer_function_ser_schema(
            serialize,
            schema=core_schema.list_schema(handler.generate_schema(generic_type)),
            when_used="always",
        )

    def __init__(self, payloads: Iterable[T] | None = None):
        super().__init__()
        self.__instance__ = None
        self.__loaded__ = False
        self.__payloads__ = set(payloads) if payloads else set()

    @property
    def __provided__(self) -> Any | None:
        # The return type should be a duck typed set-like object provided by the current materia provider.
        # For example, with SQLAlchemyMateria and collection_class=set, it would be an InstrumentedSet.
        if not self.__instance_provider__:
            return None
        return getattr(self.__instance_provider__, self.used_name)

    @cached_property
    def __set_validator__(self) -> TypeAdapter[set[T]]:
        return get_cached_adapter(set[self.__generic__])

    @overload
    def bless(self, value: T) -> T: ...
    @overload
    def bless(self, value: Iterable[Any]) -> set[T]: ...
    @overload
    def bless(self, value: Any) -> T: ...
    def bless(self, value: Any | Iterable[Any]) -> T | set[T]:
        """Bless the value into the generic type."""
        is_iterable = isinstance(value, Iterable) and not isinstance(
            value, get_origin(self.__generic__) or self.__generic__
        )

        if is_iterable:
            return self.__set_validator__.validate_python(value)
        else:
            return self.__validator__.validate_python(value)

    def prepare(self, instance: Transmuter, field_name: str):
        super().prepare(instance, field_name)
        if self.__payloads__:
            # manually enforce loading first to remove duplicates in payloads
            # objects already assigned to the relationship may be added to payloads during revalidation
            self._load()
            self.update(self.__payloads__)
            self.__payloads__.clear()

    @staticmethod
    def ensure_loaded(
        func: Callable[Concatenate[RelationSet[T], P], R],
    ) -> Callable[Concatenate[RelationSet[T], P], R]:
        @wraps(func)
        def wrapper(self: RelationSet[T], *args: P.args, **kwargs: P.kwargs) -> R:
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
        # B: provided value is empty
        if not self.__provided__:
            return self

        # Remove payloads that are already present in __provided__
        provided_set = set(self.__provided__)
        self.__payloads__ = {
            payload
            for payload in self.__payloads__
            if payload.__transmuter_provided__ not in provided_set
        }

        if len(self.__provided__) != super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().update(self.bless(self.__provided__))
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
        # B: provided value is empty
        if not (provided := await active_materia.get().aload_association(self)):
            return self

        # Remove payloads that are already present in provided
        provided_set = set(provided)
        self.__payloads__ = {
            payload
            for payload in self.__payloads__
            if payload.__transmuter_provided__ not in provided_set
        }

        if len(provided) != super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().update(self.bless(provided))
        self.__loaded__ = True

        return self

    def __await__(self):
        return self._aload().__await__()

    @ensure_loaded
    def __iter__(self):
        return super().__iter__()

    @ensure_loaded
    def __len__(self):
        return super().__len__()

    @ensure_loaded
    def __contains__(self, item: object) -> bool:
        return super().__contains__(item)

    @ensure_loaded
    def __bool__(self):
        return super().__len__() > 0

    def __repr__(self):
        return f"RelationSet[{self.__generic__.__name__}], instance={id(self.__instance__)}, size={super().__len__()}"

    @ensure_loaded
    def __str__(self):
        return super().__str__()

    @ensure_loaded
    def add(self, item: T) -> None:
        """Add an element. No effect if already present (identity-based)."""
        item = self.bless(item)
        if item in self:
            return
        if self.__provided__ is not None:
            provided = (
                item.__transmuter_provided__
                if hasattr(item, "__transmuter_provided__")
                else item
            )
            self.__provided__.add(provided)
        super().add(item)

    @ensure_loaded
    def discard(self, item: T) -> None:
        """Remove an element if present."""
        if item not in self:
            return
        if self.__provided__ is not None and hasattr(item, "__transmuter_provided__"):
            self.__provided__.discard(item.__transmuter_provided__)
        super().discard(item)

    @ensure_loaded
    def remove(self, item: T) -> None:
        """Remove an element. Raises KeyError if not present."""
        if self.__provided__ is not None and hasattr(item, "__transmuter_provided__"):
            self.__provided__.discard(item.__transmuter_provided__)
        super().remove(item)

    @ensure_loaded
    def pop(self) -> T:
        """Remove and return an arbitrary element. Raises KeyError if empty."""
        item = super().pop()
        if self.__provided__ is not None and hasattr(item, "__transmuter_provided__"):
            self.__provided__.discard(item.__transmuter_provided__)
        return item

    @ensure_loaded
    def update(self, *others: Iterable[T]) -> None:
        """Add all elements from iterables."""
        for other in others:
            items = self.bless(other)
            for item in items:
                self.add(item)

    @ensure_loaded
    def clear(self) -> None:
        """Remove all elements."""
        if self.__provided__ is not None:
            self.__provided__.clear()
        super().clear()

    @ensure_loaded
    def intersection_update(self, *others: Iterable[T]) -> None:
        """Keep only elements found in all others."""
        keep = set.intersection(self, *others)
        removed = set.difference(self, keep)
        for item in removed:
            self.discard(item)

    @ensure_loaded
    def difference_update(self, *others: Iterable[T]) -> None:
        """Remove all elements found in others."""
        to_remove = set.intersection(self, *others)
        for item in to_remove:
            self.discard(item)

    @ensure_loaded
    def symmetric_difference_update(self, other: Iterable[T]) -> None:
        """Update to symmetric difference with other."""
        other_set = set(other)
        to_remove = set.intersection(self, other_set)
        to_add = other_set - set.copy(self)
        for item in to_remove:
            self.discard(item)
        for item in to_add:
            self.add(item)

    @ensure_loaded
    def copy(self) -> set[T]:
        return super().copy()

    @ensure_loaded
    def union(self, *others: Iterable[T]) -> set[T]:
        return super().union(*others)

    @ensure_loaded
    def intersection(self, *others: Iterable[T]) -> set[T]:
        return super().intersection(*others)

    @ensure_loaded
    def difference(self, *others: Iterable[T]) -> set[T]:
        return super().difference(*others)

    @ensure_loaded
    def symmetric_difference(self, other: Iterable[T]) -> set[T]:
        return super().symmetric_difference(other)

    @ensure_loaded
    def issubset(self, other: Iterable[T]) -> bool:
        return super().issubset(other)

    @ensure_loaded
    def issuperset(self, other: Iterable[T]) -> bool:
        return super().issuperset(other)

    @ensure_loaded
    def isdisjoint(self, other: Iterable[T]) -> bool:
        return super().isdisjoint(other)

    @ensure_loaded
    def __eq__(self, other: object) -> bool:
        if isinstance(other, RelationSet):
            return set.__eq__(self, other)
        if isinstance(other, (set, frozenset)):
            return set.__eq__(self, other)
        return False

    @ensure_loaded
    def __ne__(self, other: object) -> bool:
        if isinstance(other, RelationSet):
            return set.__ne__(self, other)
        if isinstance(other, (set, frozenset)):
            return set.__ne__(self, other)
        return False

    @ensure_loaded
    def __le__(self, other: set[T]) -> bool:
        return super().__le__(other)

    @ensure_loaded
    def __lt__(self, other: set[T]) -> bool:
        return super().__lt__(other)

    @ensure_loaded
    def __ge__(self, other: set[T]) -> bool:
        return super().__ge__(other)

    @ensure_loaded
    def __gt__(self, other: set[T]) -> bool:
        return super().__gt__(other)

    @ensure_loaded
    def __or__(self, other: set[T]) -> set[T]:
        return super().__or__(other)

    @ensure_loaded
    def __and__(self, other: set[T]) -> set[T]:
        return super().__and__(other)

    @ensure_loaded
    def __sub__(self, other: set[T]) -> set[T]:
        return super().__sub__(other)

    @ensure_loaded
    def __xor__(self, other: set[T]) -> set[T]:
        return super().__xor__(other)

    @ensure_loaded
    def __ior__(self, other: Iterable[T]) -> Self:
        self.update(other)
        return self

    @ensure_loaded
    def __iand__(self, other: Iterable[T]) -> Self:
        self.intersection_update(other)
        return self

    @ensure_loaded
    def __isub__(self, other: Iterable[T]) -> Self:
        self.difference_update(other)
        return self

    @ensure_loaded
    def __ixor__(self, other: Iterable[T]) -> Self:
        self.symmetric_difference_update(other)
        return self


# built-in types must be put at front to avoid pydantic convert it to built-in types
class RelationMap(dict[K, T], Association[T]):
    # new items are held in __payloads__, loaded items are kept in the dict itself
    __payloads__: dict[K, T]
    __key_type__: Type[K]

    @classmethod
    def __get_pydantic_generic_schema__(
        cls,
        key_type: Type[K],
        value_type: Type[T],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.dict_schema(
            keys_schema=handler.generate_schema(key_type),
            values_schema=handler.generate_schema(value_type),
        )

    @classmethod
    def __get_pydantic_serialize_schema__(
        cls,
        key_type: Type[K],
        value_type: Type[T],
        handler: GetCoreSchemaHandler,
    ) -> core_schema.SerSchema | None:
        def serialize(association: RelationMap[K, T], serializer) -> Any:
            fields_set = getattr(
                association.__instance__, "__pydantic_fields_set__", None
            )
            if (
                association.__instance__
                and fields_set is not None
                and association.field_name in fields_set
            ):
                return serializer(dict(association.copy()))
            return serializer(dict(dict.copy(association)))

        return core_schema.wrap_serializer_function_ser_schema(
            serialize,
            schema=core_schema.dict_schema(
                keys_schema=handler.generate_schema(key_type),
                values_schema=handler.generate_schema(value_type),
            ),
            when_used="always",
        )

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Type[RelationMap[K, T]], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        args = get_args(source_type)

        if not args or len(args) < 2:
            raise TypeError(
                f"Two generic types (key, value) must be provided to {source_type}."
            )

        key_type = args[0]
        value_type = args[1]

        def validate(
            value: Any,
            handler: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> RelationMap[K, T]:
            if value is DefferedAssociation:
                instance = cls()
            elif type(value) is cls:
                instance = value
                instance.__payloads__ = handler(instance.__payloads__)
            else:
                instance = cls(handler(value))

            instance.__generic__ = value_type
            instance.__key_type__ = key_type
            instance.field_name = info.field_name  # pyright: ignore[reportAttributeAccessIssue]

            return instance

        return core_schema.with_default_schema(
            core_schema.with_info_wrap_validator_function(
                validate,
                cls.__get_pydantic_generic_schema__(key_type, value_type, handler),
            ),
            default_factory=cls,
            serialization=cls.__get_pydantic_serialize_schema__(
                key_type, value_type, handler
            ),
        )

    def __init__(self, payloads: Mapping[K, T] | None = None):
        super().__init__()
        self.__instance__ = None
        self.__loaded__ = False
        self.__payloads__ = dict(payloads) if payloads else {}

    @property
    def __provided__(self) -> Any | None:
        # The return type should be a duck typed dict-like object provided by the current materia provider.
        # For example, with SQLAlchemyMateria and collection_class=attribute_keyed_dict,
        # it would be a KeyFuncDict.
        if not self.__instance_provider__:
            return None
        return getattr(self.__instance_provider__, self.used_name)

    @cached_property
    def __dict_validator__(self) -> TypeAdapter[dict[K, T]]:
        return get_cached_adapter(dict[self.__key_type__, self.__generic__])

    @overload
    def bless(self, value: T) -> T: ...
    @overload
    def bless(self, value: Mapping[K, Any]) -> dict[K, T]: ...
    @overload
    def bless(self, value: Any) -> T: ...
    def bless(self, value: Any | Mapping[K, Any]) -> T | dict[K, T]:
        """Bless the value into the generic type."""
        if isinstance(value, Mapping) and not isinstance(
            value, get_origin(self.__generic__) or self.__generic__
        ):
            return self.__dict_validator__.validate_python(value)
        else:
            return self.__validator__.validate_python(value)

    def prepare(self, instance: Transmuter, field_name: str):
        if self.__instance__ is not None:
            return

        self.field_name = field_name
        self.field_info = type(instance).__pydantic_fields__[field_name]

        self.__instance__ = instance

        annotation = self.field_info.annotation
        if isinstance(annotation, ForwardRef):
            resolved_hints = get_type_hints(type(instance))
            actual_type = resolved_hints[field_name]
            args = get_args(actual_type)
        else:
            args = get_args(annotation)

        self.__key_type__ = args[0]
        self.__generic__ = args[1]

        if self.__payloads__:
            # manually enforce loading first to remove duplicates in payloads
            # objects already assigned to the relationship may be added to payloads during revalidation
            self._load()
            self.update(self.__payloads__)
            self.__payloads__.clear()

    @staticmethod
    def ensure_loaded(
        func: Callable[Concatenate[RelationMap[K, T], P], R],
    ) -> Callable[Concatenate[RelationMap[K, T], P], R]:
        @wraps(func)
        def wrapper(self: RelationMap[K, T], *args: P.args, **kwargs: P.kwargs) -> R:
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
        # B: provided value is empty, {}
        if not self.__provided__:
            return self

        # Remove payloads whose provider is already in __provided__
        provided_values = set(self.__provided__.values())
        self.__payloads__ = {
            k: v
            for k, v in self.__payloads__.items()
            if v.__transmuter_provided__ not in provided_values
        }

        if len(self.__provided__) != super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().update(self.bless(self.__provided__))
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
        # B: provided value is empty, {}
        if not (provided := await active_materia.get().aload_association(self)):
            return self

        # Remove payloads whose provider is already in provided
        provided_values = set(provided.values())
        self.__payloads__ = {
            k: v
            for k, v in self.__payloads__.items()
            if v.__transmuter_provided__ not in provided_values
        }

        if len(provided) != super().__len__():
            # If the length of __provided__ is not equal to the length of self,
            # it means some items were not blessed into transmuter objects.
            super().clear()
            super().update(self.bless(provided))
        self.__loaded__ = True

        return self

    def __await__(self):
        return self._aload().__await__()

    @ensure_loaded
    def __getitem__(self, key: K) -> T:
        return super().__getitem__(key)

    @ensure_loaded
    def __iter__(self):
        return super().__iter__()

    @ensure_loaded
    def __len__(self):
        return super().__len__()

    @ensure_loaded
    def __contains__(self, key: object) -> bool:
        return super().__contains__(key)

    @ensure_loaded
    def __bool__(self):
        return super().__len__() > 0

    @ensure_loaded
    def __setitem__(self, key: K, value: T) -> None:
        value = self.bless(value)
        if self.__provided__ is not None:
            self.__provided__[key] = (
                value.__transmuter_provided__
                if hasattr(value, "__transmuter_provided__")
                else value
            )
        super().__setitem__(key, value)

    @ensure_loaded
    def __delitem__(self, key: K) -> None:
        if self.__provided__ is not None:
            try:
                del self.__provided__[key]
            except (KeyError, TypeError):
                # The provided dict may use different keys (e.g. ORM objects as values)
                # Try to remove by finding the matching value
                item = super().__getitem__(key)
                if hasattr(item, "__transmuter_provided__"):
                    for pk, pv in list(self.__provided__.items()):
                        if pv is item.__transmuter_provided__:
                            del self.__provided__[pk]
                            break
        super().__delitem__(key)

    def __repr__(self):
        return f"RelationMap[{self.__key_type__.__name__}, {self.__generic__.__name__}], instance={id(self.__instance__)}, size={super().__len__()}"

    @ensure_loaded
    def __str__(self):
        return super().__str__()

    @ensure_loaded
    def __eq__(self, other: object) -> bool:
        if isinstance(other, RelationMap):
            return dict.__eq__(self, other)
        if isinstance(other, dict):
            return dict.__eq__(self, other)
        return False

    @ensure_loaded
    def __ne__(self, other: object) -> bool:
        if isinstance(other, RelationMap):
            return dict.__ne__(self, other)
        if isinstance(other, dict):
            return dict.__ne__(self, other)
        return True

    @ensure_loaded
    def __or__(self, other: Mapping[K, T]) -> dict[K, T]:
        return dict.__or__(dict.copy(self), dict(other))

    @ensure_loaded
    def __ior__(self, other: Mapping[K, T]) -> Self:
        self.update(other)
        return self

    @ensure_loaded
    def __reversed__(self):
        return super().__reversed__()

    @ensure_loaded
    def get(self, key: K, default: T | None = None) -> T | None:
        return super().get(key, default)

    @ensure_loaded
    def keys(self):
        return super().keys()

    @ensure_loaded
    def values(self):
        return super().values()

    @ensure_loaded
    def items(self):
        return super().items()

    @ensure_loaded
    def pop(self, key: K, *args: Any) -> T:
        """Remove specified key and return the corresponding value."""
        item = super().pop(key, *args)
        if self.__provided__ is not None and hasattr(item, "__transmuter_provided__"):
            # Remove from provided by value identity
            for pk, pv in list(self.__provided__.items()):
                if pv is item.__transmuter_provided__:
                    del self.__provided__[pk]
                    break
        return item

    @ensure_loaded
    def popitem(self) -> tuple[K, T]:
        """Remove and return an arbitrary (key, value) pair. Raises KeyError if empty."""
        key, item = super().popitem()
        if self.__provided__ is not None and hasattr(item, "__transmuter_provided__"):
            for pk, pv in list(self.__provided__.items()):
                if pv is item.__transmuter_provided__:
                    del self.__provided__[pk]
                    break
        return key, item

    @ensure_loaded
    def update(self, *args: Mapping[K, T] | Iterable[tuple[K, T]], **kwargs: T) -> None:
        """Update the dict with key-value pairs."""
        if args:
            other = args[0]
            if isinstance(other, Mapping):
                blessed = self.bless(other)
                for key, value in blessed.items():
                    self[key] = value
            else:
                for key, value in other:
                    self[key] = self.bless(value)
        for key, value in kwargs.items():
            self[key] = self.bless(value)

    @ensure_loaded
    def setdefault(self, key: K, default: T | None = None) -> T:
        """If key is not in the dict, insert key with the default value."""
        if key not in self:
            if default is not None:
                self[key] = default
        return super().__getitem__(key)

    @ensure_loaded
    def clear(self) -> None:
        """Remove all items."""
        if self.__provided__ is not None:
            self.__provided__.clear()
        super().clear()

    @ensure_loaded
    def copy(self) -> dict[K, T]:
        return super().copy()


Relationship = partial(Field, default_factory=Relation, frozen=True)

RelationMaps = partial(Field, default_factory=RelationMap, frozen=True)


@overload
def Relationships(*, unique: Literal[True], **kwargs: Any) -> Any: ...
@overload
def Relationships(*, unique: Literal[False] = ..., **kwargs: Any) -> Any: ...
@overload
def Relationships(**kwargs: Any) -> Any: ...
def Relationships(*, unique: bool = False, **kwargs: Any) -> Any:
    """Create a relationship field for a collection of related transmuters.

    Args:
        unique: If True, use a RelationSet (set semantics, no duplicates).
                If False (default), use a RelationCollection (list semantics).
        **kwargs: Additional keyword arguments passed to pydantic's Field().

    Returns:
        A pydantic Field configured with the appropriate default_factory.
    """
    factory = RelationSet if unique else RelationCollection
    return Field(default_factory=factory, frozen=True, **kwargs)
