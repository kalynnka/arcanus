from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from copy import copy as shallow_copy
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Optional,
    Self,
    TypeVar,
)

from pydantic import ValidationInfo
from pydantic_core import core_schema

if TYPE_CHECKING:
    from arcanus.association import Association
    from arcanus.base import (
        Transmuter,
        TransmuterProxied,
    )

M = TypeVar("M", bound=Any)
A = TypeVar("A", bound="Association")
T = TypeVar("T", bound="Transmuter")

K = TypeVar("K")
V = TypeVar("V")


class BidirectonDict(dict, Generic[K, V]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reverse: BidirectonDict[V, K] | None = None

    @property
    def reverse(self) -> BidirectonDict[V, K]:
        if self._reverse is None:
            self._reverse = BidirectonDict({v: k for k, v in self.items()})
            self._reverse._reverse = self
        return self._reverse

    def __setitem__(self, key: K, value: V) -> None:
        super().__setitem__(key, value)
        if self._reverse is not None:
            dict.__setitem__(self._reverse, value, key)

    def __delitem__(self, key: K) -> None:
        value = self[key]
        super().__delitem__(key)
        if self._reverse is not None:
            dict.__delitem__(self._reverse, value)


class BaseMateria:
    formulars: BidirectonDict[type[Transmuter], type[TransmuterProxied]]
    token: Optional[Token[BaseMateria]]

    def __init__(self) -> None:
        self.formulars = BidirectonDict()
        self.token = None

    @contextmanager
    def __call__(self):
        """Create a shallow copy of the materia and activate it as a context manager.

        The copy shares the validation context (formulars) with the original instance.

        Yields:
            A shallow copy set as the active materia.

        Example:
            materia = SqlalchemyMateria()
            with materia():
                instance = MyModel.model_validate(orm_obj)
        """
        copied = shallow_copy(self)

        copied.token = active_materia.set(copied)
        try:
            yield copied
        finally:
            active_materia.reset(copied.token)

    def __enter__(self) -> Self:
        if self.token is not None:
            raise RuntimeError(
                "This materia is already active. Use materia() to create "
                "a nested context: `with materia(): ...`"
            )
        self.token = active_materia.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.token:
            active_materia.reset(self.token)
            self.token = None

    def __getitem__(
        self, transmuter: type[Transmuter]
    ) -> type[TransmuterProxied] | None:
        return self.formulars.get(transmuter)

    def __contains__(self, transmuter: type[Transmuter]) -> bool:
        return transmuter in self.formulars

    def bless(self, materia: Any):
        def decorator(transmuter_cls: type[T]) -> type[T]:
            # Check if materia implements TransmuterProxied by verifying required attributes
            if not hasattr(materia, "transmuter_proxy"):
                raise TypeError(
                    f"{self.__class__.__name__} require materia must implement TransmuterProxied."
                )

            self.formulars[transmuter_cls] = materia
            return transmuter_cls

        return decorator

    @staticmethod
    def transmuter_before_validator(
        transmuter_type: type[T], materia: M, info: ValidationInfo
    ) -> M:
        return materia

    @staticmethod
    def transmuter_after_validator(transmuter: T, info: ValidationInfo) -> T:
        return transmuter

    @staticmethod
    def transmuter_before_construct(transmuter_type: type[T], materia: object) -> dict:
        return materia.__dict__

    @staticmethod
    def transmuter_after_construct(transmuter: T) -> T:
        return transmuter

    @staticmethod
    def association_before_validator(
        association_type: type[A],
        value: Any,
        info: core_schema.ValidationInfo,
    ) -> Any:
        return value

    @staticmethod
    def association_after_validator(
        association: A, info: core_schema.ValidationInfo
    ) -> A:
        return association

    def load_association(self, association: Association) -> Any:
        raise NotImplementedError()

    async def aload_association(self, association: Association) -> Any:
        raise NotImplementedError()


class NoOpMateria(BaseMateria):
    _instance: ClassVar[Optional[NoOpMateria]] = None
    _initialized: ClassVar[bool] = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not NoOpMateria._initialized:
            super().__init__()
            NoOpMateria._initialized = True

    def load_association(self, association: Association):
        return

    async def aload_association(self, association: Association) -> Any:
        return

    def bless(self):
        def decorator(transmuter_cls: type[T]) -> type[T]:
            return transmuter_cls

        return decorator


active_materia: ContextVar[BaseMateria] = ContextVar(
    "active_materia", default=NoOpMateria()
)
