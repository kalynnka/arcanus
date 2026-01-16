from __future__ import annotations

import contextlib
from contextvars import ContextVar
from copy import copy as shallow_copy
from copy import deepcopy
from typing import (
    TYPE_CHECKING,
    Any,
    Generator,
    Optional,
    Protocol,
    Self,
    TypeVar,
    dataclass_transform,
    get_origin,
    get_type_hints,
    runtime_checkable,
)
from weakref import WeakKeyDictionary, ref

from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    ValidationInfo,
    create_model,
    model_validator,
)
from pydantic._internal._generics import PydanticGenericMetadata
from pydantic._internal._model_construction import ModelMetaclass, NoInitField
from pydantic.fields import Field, FieldInfo, PrivateAttr

from arcanus.association import Association
from arcanus.materia.base import (
    BaseMateria,
    BidirectonDict,
    NoOpMateria,
    active_materia,
)

# Cache NoOpMateria singleton for fast identity check
_noop_materia = NoOpMateria()

T = TypeVar("T", bound="BaseTransmuter")
M = TypeVar("M", bound="TransmuterMetaclass")


ValidationContextT = WeakKeyDictionary[Any, "BaseTransmuter"]
ValidateContextGeneratorT = contextlib._GeneratorContextManager[
    ValidationContextT, None, None
]


validated: ContextVar[ValidationContextT] = ContextVar(
    "validated", default=WeakKeyDictionary()
)


@contextlib.contextmanager
def validation_context(
    context: Optional[WeakKeyDictionary] = None,
) -> Generator[ValidationContextT, None, None]:
    validated_ = context if context is not None else WeakKeyDictionary()
    token = validated.set(validated_)
    try:
        yield validated_
    finally:
        validated.reset(token)


@runtime_checkable
class TransmuterProxied(Protocol):
    transmuter_proxy: BaseTransmuter | None


class TransmuterProxiedMixin:
    """Protocol for materia provided objects proxied by Transmuter."""

    _transmuter_proxy: ref[BaseTransmuter] | None = None

    @property
    def transmuter_proxy(self) -> BaseTransmuter | None:
        return self._transmuter_proxy() if self._transmuter_proxy else None

    @transmuter_proxy.setter
    def transmuter_proxy(self, value: BaseTransmuter) -> None:
        self._transmuter_proxy = ref(value)


class Identity:
    """Marker class for identity fields that could not be set in creation and immutable."""


@dataclass_transform(
    kw_only_default=True,
    field_specifiers=(Field, PrivateAttr, NoInitField),
)
class TransmuterMetaclass(ModelMetaclass):
    __transmuter_complete__: bool
    __transmuter_associations__: dict[str, FieldInfo]
    __transmuter_identities__: dict[str, FieldInfo]
    __transmuter_create_model__: Optional[type[BaseModel]]
    __transmuter_update_model__: Optional[type[BaseModel]]

    if TYPE_CHECKING:
        __pydantic_fields__: dict[str, FieldInfo]
        __hash__: Any  # Override to indicate instances are hashable

        model_config: ConfigDict
        model_fields: dict[str, FieldInfo]

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__transmuter_associations__ = {}
        self.__transmuter_associations_completed__ = False
        self.__transmuter_identities__ = {}
        self.__transmuter_create_model__ = None
        self.__transmuter_update_model__ = None

        self._ensure_associations_resolved()

        for name, info in self.__pydantic_fields__.items():
            for metadata in info.metadata:
                if isinstance(metadata, type) and issubclass(metadata, Identity):
                    self.__transmuter_identities__[name] = info
                    break
                elif isinstance(metadata, Identity):
                    self.__transmuter_identities__[name] = info
                    break

        self.__transmuter_complete__ = True

        NoOpMateria().bless()(self)

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
                raise e

            else:
                fields: dict[str, FieldInfo] = object.__getattribute__(
                    self, "__pydantic_fields__"
                )
                transmuter_name = object.__getattribute__(self, "__name__")
                if info := fields.get(name):
                    if provider := object.__getattribute__(
                        self, "__transmuter_provider__"
                    ):
                        try:
                            return object.__getattribute__(provider, info.alias or name)
                        except AttributeError as inner:
                            raise AttributeError(
                                f"Attribute '{name}' (alias: '{info.alias or name}') is not defined in the materia provider for {transmuter_name}. "
                                f"The provider {provider.__name__} does not have this attribute. "
                                f"Ensure the provider class includes this attribute definition."
                            ) from inner
                    else:
                        materia = object.__getattribute__(
                            self, "__transmuter_materia__"
                        )
                        raise AttributeError(
                            f"Transmuter {transmuter_name} has not been blessed by the active materia ({materia.__class__.__name__}). "
                            f"Cannot access attribute '{name}' without a provider. "
                            f"Use materia.bless() to register this transmuter with a provider."
                        ) from e
                raise AttributeError(
                    f"Attribute '{name}' is not defined in transmuter {transmuter_name}. "
                    f"Available fields: {', '.join(fields.keys())}"
                ) from e

    # TODO: Have no idea to give proper type hint to proxied provider column here
    def __getitem__(self, name: str) -> Any:
        if info := self.__pydantic_fields__.get(name):
            if provider := self.__transmuter_provider__:
                try:
                    return getattr(provider, info.alias or name)
                except AttributeError as inner:
                    raise KeyError(
                        f"Column '{name}' (alias: '{info.alias or name}') is not defined in the materia provider for {self.__name__}. "
                        f"The provider {provider.__name__} does not have this attribute. "
                        f"Ensure the provider class includes this column definition."
                    ) from inner
            else:
                materia = self.__transmuter_materia__
                raise KeyError(
                    f"Transmuter {self.__name__} has not been blessed by the active materia ({materia.__class__.__name__}). "
                    f"Cannot access column '{name}' without a provider. "
                    f"Use materia.bless() to register this transmuter with a provider."
                )
        raise KeyError(
            f"Field '{name}' is not defined in transmuter {self.__name__}. "
            f"Available fields: {', '.join(self.__pydantic_fields__.keys())}"
        )

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
    ) -> BidirectonDict[TransmuterMetaclass, type[TransmuterProxied]]:
        return self.__transmuter_materia__.formulars

    @property
    def Create(self) -> type[BaseModel]:
        if self.__transmuter_create_model__:
            return self.__transmuter_create_model__

        config = self.model_config.copy()

        field_definitions = {}
        # TODO: include nested associations
        for field_name in set(
            self.__pydantic_fields__.keys()
            - self.model_identities.keys()
            - set(self.model_associations.keys())
        ):
            info = shallow_copy(self.__pydantic_fields__[field_name])
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
                field_definitions[field_name] = (Optional[info.annotation], info)

        self.__transmuter_update_model__ = create_model(
            f"{self.__name__}Update",
            __config__=config,
            __module__=self.__module__,
            **field_definitions,
        )
        return self.__transmuter_update_model__


class BaseTransmuter(BaseModel, metaclass=TransmuterMetaclass):
    __slots__ = ("__transmuter_provided__", "__transmuter_revalidating__")

    __transmuter_provided__: Optional[TransmuterProxied] = NoInitField(init=False)
    __transmuter_revalidating__: bool = NoInitField(init=False)

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if isinstance(value, Association):
            value.prepare(self, name)
        return value

    def __getattr__(self, name: str) -> Any:
        # only called when attribute not found in normal places
        try:
            return super().__getattr__(name)  # pyright: ignore[reportAttributeAccessIssue]
        except AttributeError as e:
            try:
                provided = object.__getattribute__(self, "__transmuter_provided__")
                return getattr(provided, name)
            except AttributeError as inner:
                raise e from inner

    def __setattr__(self, name: str, value: Any):
        super().__setattr__(name, value)
        if (
            self.__transmuter_provided__
            and name in type(self).model_fields
            and name not in type(self).model_associations
        ):
            setattr(self.__transmuter_provided__, name, getattr(self, name))

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

    @model_validator(mode="wrap")
    @classmethod
    def model_formulate(
        cls, data: Any, handler: ModelWrapValidatorHandler[Self], info: ValidationInfo
    ) -> BaseTransmuter:
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

        provider = materia[cls]
        # Handle provider with matching data type
        if provider is not None and isinstance(data, provider):
            context = validated.get()
            cached = context.get(data)

            instance = cached or data.transmuter_proxy
            if instance is None or instance.__transmuter_revalidating__:
                loaded = materia.transmuter_before_validator(cls, data, info)
                instance = handler(loaded)
                object.__setattr__(instance, "__transmuter_provided__", data)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
                data.transmuter_proxy = instance
                instance = materia.transmuter_after_validator(instance, info)

            if not cached:
                context[data] = instance

        else:
            # Normal validation
            instance = handler(data)
            if provider is not None:
                model_fields = cls.model_fields
                included = instance.model_dump(
                    exclude=set(cls.model_associations.keys()),
                    by_alias=True,
                )
                excluded = {
                    model_fields[name].alias or name: getattr(instance, name)
                    for name in cls.model_fields.keys() - cls.model_associations.keys()
                    if model_fields[name].exclude
                }
                provided = provider(**included, **excluded)
                provided.transmuter_proxy = instance
                object.__setattr__(instance, "__transmuter_provided__", provided)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
            else:
                object.__setattr__(instance, "__transmuter_provided__", None)
                object.__setattr__(instance, "__transmuter_revalidating__", False)

        for name in cls.model_associations.keys() & instance.model_fields_set:
            association = object.__getattribute__(instance, name)
            if isinstance(association, Association):
                association.prepare(instance, name)

        return instance

    @classmethod
    def model_construct(
        cls,
        _fields_set: Optional[set[str]] = None,
        *,
        data: Optional[object] = None,
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
            if instance is None or instance.__transmuter_revalidating__:
                inputs = materia.transmuter_before_construct(cls, data)
                inputs.update(values)
                instance = super().model_construct(_fields_set=_fields_set, **inputs)
                object.__setattr__(instance, "__transmuter_provided__", data)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
                data.transmuter_proxy = instance
                instance = materia.transmuter_after_construct(instance)

            if not cached:
                context[data] = instance

        else:
            # Normal construction
            inputs = data if isinstance(data, dict) else data.__dict__ if data else {}
            inputs.update(values)
            instance = super().model_construct(_fields_set=_fields_set, **inputs)

            if provider is not None:
                model_fields = cls.model_fields
                included = instance.model_dump(
                    exclude=set(cls.model_associations.keys()),
                    by_alias=True,
                )
                excluded = {
                    model_fields[name].alias or name: getattr(instance, name)
                    for name in cls.model_fields.keys() - cls.model_associations.keys()
                    if model_fields[name].exclude
                }
                provided = provider(**included, **excluded)
                provided.transmuter_proxy = instance
                object.__setattr__(instance, "__transmuter_provided__", provided)
                object.__setattr__(instance, "__transmuter_revalidating__", False)
            else:
                object.__setattr__(instance, "__transmuter_provided__", None)
                object.__setattr__(instance, "__transmuter_revalidating__", False)

        for name in cls.model_associations.keys() & instance.model_fields_set:
            association = object.__getattribute__(instance, name)
            if isinstance(association, Association):
                association.prepare(instance, name)

        return instance  # pyright: ignore[reportReturnType]

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

    def revalidate(self) -> Self:
        """Re-validate the instance against the underlying provider instance."""
        # if True, it means that the revalidation is already in progress and triggered by an upper validation round,
        # so we skip the revalidation here to avoid infinite recursion.
        if self.__transmuter_revalidating__:
            return self

        self.__transmuter_revalidating__ = True
        if self.__transmuter_provided__:
            self.__pydantic_validator__.validate_python(
                self.__transmuter_provided__,
                self_instance=self,
                by_alias=True,
            )
        # double ensure the revalidation flag is reset to False
        self.__transmuter_revalidating__ = False

        return self
