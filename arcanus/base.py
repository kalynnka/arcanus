from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Generator
from contextvars import ContextVar
from copy import copy as shallow_copy
from copy import deepcopy
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Optional,
    Protocol,
    Self,
    TypeVar,
    cast,
    dataclass_transform,
    get_origin,
    get_type_hints,
    overload,
    runtime_checkable,
)
from weakref import WeakKeyDictionary, ref

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    create_model,
    model_validator,
)
from pydantic._internal._generics import PydanticGenericMetadata
from pydantic._internal._model_construction import ModelMetaclass, NoInitField
from pydantic.fields import Field, FieldInfo, PrivateAttr
from pydantic_core import SchemaValidator

from arcanus.association import Association
from arcanus.expression import Column
from arcanus.materia.base import (
    BaseMateria,
    BidirectonDict,
    NoOpMateria,
    active_materia,
)
from arcanus.utils import get_cached_adapter

# Cache NoOpMateria singleton for fast identity check
_noop_materia = NoOpMateria()


T = TypeVar("T", bound="BaseTransmuter")
M = TypeVar("M", bound="TransmuterMetaclass")


ValidationContextT = WeakKeyDictionary[Any, "Transmuter"]
ValidateContextGeneratorT = contextlib._GeneratorContextManager[
    ValidationContextT, None, None
]


# The shared default is deliberate: the process-wide fallback registry used
# outside any validation_context(); contexts get fresh dicts via .set().
validated: ContextVar[ValidationContextT] = ContextVar(
    "validated",
    default=WeakKeyDictionary(),  # noqa: B039
)


@contextlib.contextmanager
def validation_context(
    context: WeakKeyDictionary | None = None,
) -> Generator[ValidationContextT, None, None]:
    validated_ = context if context is not None else WeakKeyDictionary()
    token = validated.set(validated_)
    try:
        yield validated_
    finally:
        validated.reset(token)


@runtime_checkable
class TransmuterProxied(Protocol):
    transmuter_proxy: Transmuter | None


class TransmuterType(Protocol):
    __name__: str
    __module__: str
    __qualname__: str
    __pydantic_fields__: dict[str, FieldInfo]

    @property
    def model_associations(self) -> dict[str, FieldInfo]: ...

    def __getitem__(self, name: str) -> Column[Any]: ...

    def __hash__(self) -> int: ...


def transmuter_type(model: object) -> TransmuterType:
    if isinstance(model, TransmuterMetaclass):
        return cast(TransmuterType, model)
    raise TypeError("Criteria generics expect an arcanus transmuter type")


class TransmuterProxiedMixin:
    """Mixin for materia provided objects proxied by a transmuter."""

    _transmuter_proxy: ref[Transmuter] | None = None

    @property
    def transmuter_proxy(self) -> Transmuter | None:
        return self._transmuter_proxy() if self._transmuter_proxy else None

    @transmuter_proxy.setter
    def transmuter_proxy(self, value: Transmuter) -> None:
        self._transmuter_proxy = ref(value)


class TransmuterTypingMetaclass(type):
    # Dataclass transmuters need class subscription typing before Pydantic finalizes them.
    @overload
    def __getitem__(self, name: str) -> Column[Any]: ...

    @overload
    def __getitem__(self, name: object) -> Any: ...

    def __getitem__(self, name: object) -> Any:
        return cast(Any, self).__class_getitem__(name)


@dataclasses.dataclass(frozen=True)
class Identity:
    """Marker for a record's identity field(s), following SQLAlchemy's PK concept.

    Usable bare (``Identity``) or instantiated (``Identity()``) — the bare class
    takes the defaults below.

    ``server_side`` (default ``True``) declares the identity server-assigned (an
    autoincrement / IDENTITY column), so it is dropped from ``.Create``. Pass
    ``Identity(server_side=False)`` for a *natural*/composite key the client must
    supply, keeping it in ``.Create``. Mark identities ``frozen=True`` to keep
    them immutable and out of ``.Update``::

        id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
        book_id: Annotated[int, Identity(server_side=False)] = Field(frozen=True)
    """

    server_side: bool = True


def identity_marker(info: FieldInfo) -> Identity | None:
    """The ``Identity`` marker on a field as an instance, or ``None``.

    A bare ``Identity`` class used as metadata is normalized to ``Identity()`` so
    callers always work with an instance.
    """
    for metadata in info.metadata:
        if isinstance(metadata, Identity):
            return metadata
        if isinstance(metadata, type) and issubclass(metadata, Identity):
            return metadata()
    return None


PROVIDED_FIELD_MARK = "__transmuter_provided_field__"

F = TypeVar("F")


def provided(target: F) -> F:
    """Mark a computed field as backed by a same-named provider attribute.

    Only marked computed fields join the expression layer — ``Schema[name]``
    resolution, criteria query params, ordering, and cursor bookmarks — by
    compiling through the provider's attribute (e.g. a SQLAlchemy
    ``hybrid_property``). Unmarked computed fields stay serialization-only.

    Stacks anywhere around pydantic's ``computed_field``/``property`` pair::

        @computed_field
        @provided
        @property
        def title(self) -> str | None: ...

    The mark lives on the getter function, so ``@title.setter`` rebinds
    (which reuse the getter) keep it.
    """
    wrapped = getattr(target, "wrapped", target)  # pydantic descriptor proxy
    getter = (
        getattr(wrapped, "fget", None)  # property
        or getattr(wrapped, "func", None)  # functools.cached_property
        or wrapped
    )
    setattr(getter, PROVIDED_FIELD_MARK, True)
    return target


def provided_computed_fields(owner: type[Any] | Any) -> dict[str, Any]:
    """Computed fields of *owner* marked with :func:`provided`, by name."""
    computed_fields: dict[str, Any] = getattr(owner, "__pydantic_computed_fields__", {})
    provided_fields: dict[str, Any] = {}
    for name, computed in computed_fields.items():
        prop = computed.wrapped_property
        getter = getattr(prop, "fget", None) or getattr(prop, "func", None) or prop
        if getattr(getter, PROVIDED_FIELD_MARK, False):
            provided_fields[name] = computed
    return provided_fields


class Transmuter(metaclass=TransmuterTypingMetaclass):
    """
    A mixin base providing common transmuter instance methods.
    All the subclasses should use TransmuterMetaclass as their metaclass.

    Shared by both :class:`BaseTransmuter` (BaseModel path) and dataclass
    transmuters.  Uses cooperative ``super()`` so it integrates cleanly with
    any class hierarchy.

    Inherit from this class (or the ``Transmuter`` alias exported from
    ``arcanus``) in your ``@dataclass`` to gain full type visibility for
    transmuter methods (``revalidate()``, ``Create``, etc.)::

        @dataclass
        class Foo(Transmuter):
            name: str
    """

    if TYPE_CHECKING:
        __pydantic_fields__: ClassVar[dict[str, FieldInfo]]
        __pydantic_validator__: ClassVar[SchemaValidator]
        __transmuter_is_dataclass__: ClassVar[bool]
        __transmuter_complete__: ClassVar[bool]
        __transmuter_provider__: ClassVar[type[TransmuterProxied] | None]
        __transmuter_provided__: TransmuterProxied | None
        __transmuter_revalidating__: bool
        model_associations: ClassVar[dict[str, FieldInfo]]
        model_identities: ClassVar[dict[str, FieldInfo]]
        Create: ClassVar[type[BaseModel]]
        Update: ClassVar[type[BaseModel]]

        @classmethod
        def model_validate(
            cls: type[Self],
            obj: Any,
            *,
            strict: bool | None = None,
            extra: Any | None = None,
            from_attributes: bool | None = None,
            context: Any | None = None,
            by_alias: bool | None = None,
            by_name: bool | None = None,
        ) -> Self: ...

    @overload
    @classmethod
    def __class_getitem__(cls, name: str) -> Column[Any]: ...

    @overload
    @classmethod
    def __class_getitem__(cls, name: object) -> Any: ...

    @classmethod
    def __class_getitem__(cls, name: object) -> Any:
        if (
            isinstance(name, str)
            and isinstance(cls, TransmuterMetaclass)
            and (
                name in cls.__pydantic_fields__ or name in provided_computed_fields(cls)
            )
        ):
            return cls._column(name)
        if isinstance(name, str) and name in getattr(
            cls, "__pydantic_computed_fields__", {}
        ):
            raise KeyError(
                f"Computed field '{name}' of {cls.__name__} is not marked with "
                "@provided; only provided computed fields resolve to provider "
                "expressions."
            )
        return BaseModel.__class_getitem__.__func__(cls, name)

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        # Identity equality, to match the identity __hash__ above. Transmuters are
        # mutable, provider-backed proxies; pydantic's default structural equality
        # both violates the hash/eq contract (id hash vs value eq) and is costly on
        # hot paths — e.g. list.remove / `in` over a relationship collection scans
        # with a full field-by-field compare. Defined alongside __hash__ so Python
        # does not reset __hash__ to None.
        return self is other

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if isinstance(value, Association):
            value.prepare(self, name)
        return value

    def __getattr__(self, name: str) -> Any:
        # Try the normal __getattr__ chain (handles BaseModel specifics)
        try:
            return super().__getattr__(name)  # pyright: ignore[reportAttributeAccessIssue]
        except AttributeError:
            pass
        # Proxy to the underlying materia provider
        try:
            provided = object.__getattribute__(self, "__transmuter_provided__")
            if provided is not None:
                return getattr(provided, name)
        except AttributeError:
            pass
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        cls = type(self)
        model_associations = getattr(cls, "model_associations", {})
        if name in model_associations:
            try:
                current_value = object.__getattribute__(self, name)
            except AttributeError:
                missing = object()
                current_value = missing
            if current_value is value:
                return
            raise ValidationError.from_exception_data(
                cls.__name__,
                [{"type": "frozen_field", "loc": (name,), "input": value}],
            )

        super().__setattr__(name, value)
        try:
            provided: Any = object.__getattribute__(self, "__transmuter_provided__")
        except AttributeError:
            return
        if (
            provided is not None
            and name in cls.__pydantic_fields__
            and name not in model_associations
        ):
            setattr(provided, name, object.__getattribute__(self, name))

    if not TYPE_CHECKING:

        @classmethod
        def model_validate(
            cls,
            obj: Any,
            *,
            strict: bool | None = None,
            from_attributes: bool | None = None,
            context: dict[str, Any] | None = None,
        ) -> Any:
            """Validate *obj* and return a transmuter instance.

            For BaseModel transmuters, ``BaseTransmuter.model_validate`` takes
            precedence in MRO. This branch handles dataclass transmuters using
            ``TypeAdapter``.
            """
            return get_cached_adapter(cls).validate_python(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
            )

    @model_validator(mode="wrap")
    @classmethod
    def model_formulate(
        cls,
        data: Any,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> Self:
        if isinstance(data, cls):
            return handler(data)

        # Get materia once to avoid repeated ContextVar lookups
        materia = active_materia.get()

        # Handle NoOpMateria case - fast path using identity check
        if materia is _noop_materia:
            instance = handler(data)
            object.__setattr__(instance, "__transmuter_provided__", None)
            object.__setattr__(instance, "__transmuter_revalidating__", False)
            return instance

        provider = materia[cls]  # type: ignore[assignment]
        if provider is not None and isinstance(data, provider):
            context = validated.get()
            cached = context.get(data)
            instance = cached or data.transmuter_proxy  # pyright: ignore[reportAssignmentType]

            # Polymorphic narrowing (provider path): the cached/proxy
            # instance may be a parent or sibling schema when cls expects a
            # more specific child type.  Force re-validation so the correct
            # concrete schema is produced.
            needs_narrowing = instance is not None and not isinstance(instance, cls)
            if needs_narrowing:
                instance = None  # pyright: ignore[reportAssignmentType]

            if instance is None or instance.__transmuter_revalidating__:
                loaded = materia.transmuter_before_validator(cls, data, info)
                # Pydantic dataclasses only accept dicts or the exact dataclass
                # type — not arbitrary objects like LoadedData.  Convert to dict
                # so the inner handler can process it.
                if cls.__transmuter_is_dataclass__ and not isinstance(
                    loaded, (dict, cls)
                ):
                    loaded = loaded.__dict__
                instance = handler(loaded)
                object.__setattr__(instance, "__transmuter_provided__", data)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
                data.transmuter_proxy = instance
                instance = materia.transmuter_after_validator(instance, info)

            if not cached or needs_narrowing:
                context[data] = instance

        # Polymorphic narrowing (Transmuter path): data is an already-
        # validated parent schema (e.g. File) but cls expects a child schema
        # (e.g. Markdown).  Re-validate as the concrete child while
        # preserving the ORM provider link.
        elif isinstance(data, Transmuter) and issubclass(cls, type(data)):
            instance = handler(data)
            provided: TransmuterProxied | None = object.__getattribute__(
                data, "__transmuter_provided__"
            )
            object.__setattr__(instance, "__transmuter_provided__", provided)
            object.__setattr__(instance, "__transmuter_revalidating__", False)
            if provided is not None:
                provided.transmuter_proxy = instance
                context = validated.get()
                context[provided] = instance
            del data
            return instance

        else:
            # Normal validation
            instance: Self = handler(data)
            if provider is not None:
                skipped_fields = set(cls.model_associations.keys()) | set(
                    getattr(cls, "__pydantic_computed_fields__", {}).keys()
                )
                provider_values: dict[str, Any] = {}
                for name, field_info in cls.__pydantic_fields__.items():
                    if name in skipped_fields:
                        continue
                    try:
                        provider_values[field_info.alias or name] = getattr(
                            instance, name
                        )
                    except AttributeError:
                        continue
                provided = provider(**provider_values)
                provided.transmuter_proxy = instance
                object.__setattr__(instance, "__transmuter_provided__", provided)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
            else:
                object.__setattr__(instance, "__transmuter_provided__", None)
                object.__setattr__(instance, "__transmuter_revalidating__", False)

        # Prepare associations for fields that were explicitly set.
        # Pydantic dataclasses don't track __pydantic_fields_set__; fall back to all fields.
        fields_set = getattr(instance, "__pydantic_fields_set__", None)
        if fields_set is None:
            fields_set = set(cls.__pydantic_fields__.keys())
        for name in cls.model_associations.keys() & fields_set:
            association: Association = object.__getattribute__(instance, name)
            association.prepare(instance, name)

        return instance

    def revalidate(self) -> Self:
        """Re-validate the instance against the underlying provider instance."""
        if self.__transmuter_revalidating__:
            return self
        self.__transmuter_revalidating__ = True
        if self.__transmuter_provided__:
            type(self).__pydantic_validator__.validate_python(
                self.__transmuter_provided__,
                self_instance=self,
                by_alias=True,
            )
        self.__transmuter_revalidating__ = False
        return self

    @classmethod
    def shell(cls, create_partial: BaseModel) -> Self:
        """Create a new instance using the Create partial model. No good way to do proper typing for the input data"""
        partial = cls.Create.model_validate(create_partial)
        return cls(**partial.model_dump())

    def absorb(self, update_partial: BaseModel) -> Self:
        """Update the instance using the Update partial model."""
        partial = (
            type(self)
            .Update.model_validate(update_partial)
            .model_dump(exclude_unset=True)
        )
        for key, value in partial.items():
            setattr(self, key, value)
        return self


@dataclass_transform(
    eq_default=False,
    kw_only_default=True,
    field_specifiers=(Field, PrivateAttr, NoInitField),
)
class TransmuterMetaclass(TransmuterTypingMetaclass, ModelMetaclass):
    __transmuter_complete__: bool
    __transmuter_associations__: dict[str, FieldInfo]
    __transmuter_associations_completed__: bool
    __transmuter_identities__: dict[str, FieldInfo]
    __transmuter_create_model__: type[BaseModel] | None
    __transmuter_update_model__: type[BaseModel] | None
    __transmuter_is_dataclass__: bool

    if TYPE_CHECKING:
        __pydantic_fields__: dict[str, FieldInfo]

        model_config: ConfigDict

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        __pydantic_generic_metadata__: PydanticGenericMetadata | None = None,
        __pydantic_reset_parent_namespace__: bool = True,
        _create_model_module: str | None = None,
        **kwargs: Any,
    ) -> type:
        # Dataclass path: no BaseModel base, use plain type.__new__
        if not any(isinstance(b, ModelMetaclass) for b in bases):
            return type.__new__(mcs, cls_name, bases, namespace)

        # BaseModel path: delegate to ModelMetaclass
        for instance_slot in ("__transmuter_provided__", "__transmuter_revalidating__"):
            namespace.pop(instance_slot, None)
        return super().__new__(
            mcs,
            cls_name,
            bases,
            namespace,
            __pydantic_generic_metadata__,
            __pydantic_reset_parent_namespace__,
            _create_model_module,
            **kwargs,
        )

    def __init__(self: TransmuterMetaclass, *args: Any, **kwargs: Any) -> None:
        self.__transmuter_complete__ = False
        self.__transmuter_associations__ = {}
        self.__transmuter_associations_completed__ = False
        self.__transmuter_identities__ = {}
        self.__transmuter_create_model__ = None
        self.__transmuter_update_model__ = None
        self.__transmuter_is_dataclass__ = False

        # Dataclass path: skip ModelMetaclass.__init__, defer finalization
        if not issubclass(self, BaseModel):
            type.__init__(self, *args)
            self.__transmuter_is_dataclass__ = True
            return

        # BaseModel path
        super().__init__(*args, **kwargs)
        self._finalize_transmuter()

    def __hash__(self) -> int:
        return id(self)

    def _finalize_transmuter(self) -> None:
        """Complete transmuter class setup after pydantic fields are available.

        For BaseModel transmuters, this is called immediately in __init__.
        For dataclass transmuters, this is called by the @dataclass decorator
        after pydantic has processed the class.
        """
        self._ensure_associations_resolved()

        for name, info in self.__pydantic_fields__.items():
            if identity_marker(info) is not None:
                self.__transmuter_identities__[name] = info

        self.__transmuter_complete__ = True

    def _ensure_associations_resolved(self) -> None:
        if self.__transmuter_associations_completed__:
            return

        # Use get_type_hints to resolve all ForwardRefs at once
        try:
            resolved_hints = get_type_hints(self)
            self.__transmuter_associations_completed__ = True
        except (NameError, AttributeError):
            # Can't resolve all hints yet, fall back to manual checking
            resolved_hints = {}

        for name, info in self.__pydantic_fields__.items():
            if name in self.__transmuter_associations__:
                continue  # Already processed

            # Use the resolved type hint if available
            annotation = resolved_hints.get(name, info.annotation)

            # Check if it's an Association
            origin = get_origin(annotation)
            if origin:
                if isinstance(origin, type) and issubclass(origin, Association):
                    self.__transmuter_associations__[name] = info
            elif isinstance(annotation, type) and issubclass(annotation, Association):
                self.__transmuter_associations__[name] = info

    def __getattr__(self, name: str) -> Any:
        try:
            return object.__getattribute__(self, name)
        except AttributeError as e:
            if not object.__getattribute__(self, "__transmuter_complete__"):
                raise

            fields = object.__getattribute__(self, "__pydantic_fields__")

            transmuter_name = object.__getattribute__(self, "__name__")
            if fields.get(name):
                try:
                    return self._column(name)
                except KeyError as inner:
                    raise AttributeError(str(inner)) from e
            raise AttributeError(
                f"Attribute '{name}' is not defined in transmuter {transmuter_name}. "
                f"Available fields: {', '.join(fields.keys())}"
            ) from e

    def _column(self, name: str) -> Column[Any]:
        info = self.__pydantic_fields__.get(name)
        if info is None and (computed := provided_computed_fields(self).get(name)):
            # @provided computed fields carry no FieldInfo; synthesize one so
            # the Column keeps the same metadata shape as regular fields. The
            # provider is expected to expose a same-named expression-capable
            # attribute (e.g. a SQLAlchemy hybrid_property) for
            # filtering/ordering.
            info = FieldInfo(annotation=computed.return_type, alias=computed.alias)
        if info:
            used_name = info.alias or name
            provider = self.__transmuter_provider__
            if provider is not None:
                try:
                    native = getattr(provider, used_name)
                except AttributeError as inner:
                    raise KeyError(
                        f"Column '{name}' (alias: '{used_name}') is not defined in the materia provider for {self.__name__}. "
                        f"The provider {provider.__name__} does not have this attribute. "
                        f"Ensure the provider class includes this column definition."
                    ) from inner
            else:
                # No provider is bound (e.g. NoOpMateria). The Column/Expression
                # layer is backend-neutral, so the column can still be built and
                # serialized — operators, `.dump()`, criteria.expressions. It just
                # has no native attribute to compile against; that step needs a
                # blessed provider.
                native = None
            return self.__transmuter_materia__.column_type(
                owner=self,
                field_name=name,
                used_name=used_name,
                info=info,
                annotation=info.annotation,
                native=native,
            )
        raise KeyError(
            f"Field '{name}' is not defined in transmuter {self.__name__}. "
            f"Available fields: {', '.join(self.__pydantic_fields__.keys())}"
        )

    @overload
    def __getitem__(self, name: str) -> Column[Any]: ...

    @overload
    def __getitem__(self, name: object) -> Any: ...

    def __getitem__(self, name: object) -> Column[Any] | Any:
        if isinstance(name, str) and (
            name in self.__pydantic_fields__ or name in provided_computed_fields(self)
        ):
            return self._column(name)
        return self.__class_getitem__(name)

    @property
    def __transmuter_materia__(self) -> BaseMateria:
        return active_materia.get()

    @property
    def __transmuter_provider__(self) -> type[TransmuterProxied] | None:
        return self.__transmuter_materia__[self]

    @property
    def model_associations(self) -> dict[str, FieldInfo]:
        if not self.__transmuter_associations_completed__:
            self._ensure_associations_resolved()
        return self.__transmuter_associations__

    @property
    def model_identities(self) -> dict[str, FieldInfo]:
        return self.__transmuter_identities__

    @property
    def transmuter_formulars(
        self,
    ) -> BidirectonDict[type[Transmuter], type[TransmuterProxied]]:
        return self.__transmuter_materia__.formulars

    @property
    def Create(self) -> type[BaseModel]:
        if self.__transmuter_create_model__:
            return self.__transmuter_create_model__

        if self.__transmuter_is_dataclass__:
            cfg = getattr(self, "__pydantic_config__", None)
            config = ConfigDict(**cfg) if cfg else ConfigDict()
        else:
            config = self.model_config.copy()

        field_definitions = {}
        # TODO: include nested associations
        # Drop server-assigned identities; natural/composite keys declared
        # Identity(server_side=False) stay so the client supplies them.
        server_side_ids = {
            name
            for name, info in self.model_identities.items()
            if (marker := identity_marker(info)) is not None and marker.server_side
        }
        for field_name in (
            self.__pydantic_fields__.keys()
            - server_side_ids
            - set(self.model_associations.keys())
        ):
            info = shallow_copy(self.__pydantic_fields__[field_name])
            # `exclude` only masks the read/response side; the create body still
            # accepts the value and must carry it through shell()'s model_dump().
            info.exclude = None
            field_definitions[field_name] = (info.annotation, info)

        self.__transmuter_create_model__ = create_model(
            f"{self.__name__}Create",
            __config__=config,
            __module__=self.__module__,
            **field_definitions,
        )

        return self.__transmuter_create_model__

    @property
    def Update(self) -> type[BaseModel]:
        if self.__transmuter_update_model__:
            return self.__transmuter_update_model__

        if self.__transmuter_is_dataclass__:
            cfg = getattr(self, "__pydantic_config__", None)
            config = ConfigDict(**cfg) if cfg else ConfigDict()
        else:
            config = self.model_config.copy()

        field_definitions = {}
        # TODO: include nested associations
        for field_name in set(
            self.__pydantic_fields__.keys() - set(self.model_associations.keys())
        ):
            info = self.__pydantic_fields__[field_name]
            if not info.frozen:
                info = shallow_copy(info)
                info.default = None
                info.default_factory = None
                # See .Create: masking is read-side only; keep the value writable
                # so absorb()'s model_dump(exclude_unset=True) carries it through.
                info.exclude = None
                # Runtime type construction: `info.annotation | None` breaks on
                # forward-ref/str annotations, which Optional[...] handles.
                field_definitions[field_name] = (Optional[info.annotation], info)  # noqa: UP045

        self.__transmuter_update_model__ = create_model(
            f"{self.__name__}Update",
            __config__=config,
            __module__=self.__module__,
            **field_definitions,
        )
        return self.__transmuter_update_model__


class BaseTransmuter(Transmuter, BaseModel, metaclass=TransmuterMetaclass):
    __slots__ = ("__transmuter_provided__", "__transmuter_revalidating__")

    __transmuter_provided__: TransmuterProxied | None = NoInitField(init=False)
    __transmuter_revalidating__: bool = NoInitField(init=False)

    @overload
    @classmethod
    def __class_getitem__(cls, name: str) -> Column[Any]: ...

    @overload
    @classmethod
    def __class_getitem__(cls, name: object) -> Any: ...

    @classmethod
    def __class_getitem__(cls, name: object) -> Any:
        return Transmuter.__class_getitem__.__func__(cls, name)

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        copied = super().__deepcopy__(memo)
        object.__setattr__(
            copied,
            "__transmuter_provided__",
            shallow_copy(self.__transmuter_provided__),
        )
        object.__setattr__(
            copied,
            "__transmuter_revalidating__",
            deepcopy(self.__transmuter_revalidating__),
        )
        return copied

    @classmethod
    def model_construct(
        cls,
        _fields_set: set[str] | None = None,
        *,
        data: object | None = None,
        **values: Any,
    ) -> Self:
        if isinstance(data, cls):
            return data

        # Get materia once to avoid repeated ContextVar lookups
        materia = active_materia.get()

        # Handle NoOpMateria case
        if materia is _noop_materia:
            inputs = data if isinstance(data, dict) else data.__dict__ if data else {}
            inputs.update(values)

            instance = super().model_construct(_fields_set=_fields_set, **inputs)
            object.__setattr__(instance, "__transmuter_provided__", None)
            object.__setattr__(instance, "__transmuter_revalidating__", False)
            return instance

        # Handle provider with matching data type
        provider = materia[cls]
        if provider is not None and isinstance(data, provider):
            context = validated.get()
            cached = context.get(data)

            instance = cached or data.transmuter_proxy

            # Polymorphic narrowing (provider path): the cached/proxy
            # instance may be a parent or sibling schema when cls expects a
            # more specific child type.  Force re-construction.
            needs_narrowing = instance is not None and not isinstance(instance, cls)
            if needs_narrowing:
                instance = None  # pyright: ignore[reportAssignmentType]

            if instance is None or instance.__transmuter_revalidating__:
                inputs = materia.transmuter_before_construct(cls, data)
                inputs.update(values)
                instance = super().model_construct(_fields_set=_fields_set, **inputs)
                object.__setattr__(instance, "__transmuter_provided__", data)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
                data.transmuter_proxy = instance
                instance = materia.transmuter_after_construct(instance)

            if not cached or needs_narrowing:
                context[data] = instance

        # Polymorphic narrowing (Transmuter path): data is an already-
        # constructed parent schema but cls expects a child schema.
        # Re-construct as the concrete child while preserving the ORM link.
        elif isinstance(data, Transmuter) and issubclass(cls, type(data)):
            provided: TransmuterProxied | None = object.__getattribute__(
                data, "__transmuter_provided__"
            )
            if provided is not None:
                inputs = materia.transmuter_before_construct(cls, provided)
            else:
                inputs = data.__dict__.copy()
            inputs.update(values)
            instance = super().model_construct(_fields_set=_fields_set, **inputs)
            object.__setattr__(instance, "__transmuter_provided__", provided)
            object.__setattr__(instance, "__transmuter_revalidating__", False)
            if provided is not None:
                provided.transmuter_proxy = instance
                instance = materia.transmuter_after_construct(instance)
                context = validated.get()
                context[provided] = instance
            for name in (
                cls.model_associations.keys() & instance.__pydantic_fields_set__
            ):
                association: Association = object.__getattribute__(instance, name)
                association.prepare(instance, name)
            return instance  # type: ignore[return-value]

        else:
            # Normal construction
            inputs = dict(
                data if isinstance(data, dict) else data.__dict__ if data else {}
            )
            inputs.update(values)
            instance = super().model_construct(_fields_set=_fields_set, **inputs)

            if provider is not None:
                skipped_fields = set(cls.model_associations.keys()) | set(
                    getattr(cls, "__pydantic_computed_fields__", {}).keys()
                )
                provider_values: dict[str, Any] = {}
                for name, field_info in cls.__pydantic_fields__.items():
                    if name in skipped_fields:
                        continue
                    try:
                        provider_values[field_info.alias or name] = getattr(
                            instance, name
                        )
                    except AttributeError:
                        continue
                provided = provider(**provider_values)
                provided.transmuter_proxy = instance
                object.__setattr__(instance, "__transmuter_provided__", provided)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
            else:
                object.__setattr__(instance, "__transmuter_provided__", None)
                object.__setattr__(instance, "__transmuter_revalidating__", False)

        for name in cls.model_associations.keys() & instance.__pydantic_fields_set__:
            association: Association = object.__getattribute__(instance, name)
            association.prepare(instance, name)

        return instance  # type: ignore[return-value]
