from __future__ import annotations

import operator as operators
from dataclasses import dataclass
from functools import reduce
from typing import (
    Any,
    Generic,
    Iterable,
    Literal,
    Protocol,
    Self,
    TypeVar,
    cast,
    overload,
)

from pydantic.fields import FieldInfo

T = TypeVar("T")
NativeExpressionT = TypeVar("NativeExpressionT")
NativeOrderT = TypeVar("NativeOrderT", covariant=True)


class ExpressionCompiler(Protocol[NativeExpressionT, NativeOrderT]):
    def apply(
        self, column: Column[Any], operator: str, value: object
    ) -> NativeExpressionT: ...

    def and_(self, expressions: tuple[NativeExpressionT, ...]) -> NativeExpressionT: ...

    def or_(self, expressions: tuple[NativeExpressionT, ...]) -> NativeExpressionT: ...

    def not_(self, expression: NativeExpressionT) -> NativeExpressionT: ...

    def any_(
        self, column: Column[Any], value: Expression[bool] | None
    ) -> NativeExpressionT: ...

    def has(
        self, column: Column[Any], value: Expression[bool] | None
    ) -> NativeExpressionT: ...

    def order(self, order: Order[Any]) -> NativeOrderT: ...


class NativeExpressionCompiler(ExpressionCompiler[Any, Any]):
    def apply(self, column: Column[Any], operator: str, value: object) -> Any:
        native = column.native
        operation = getattr(operators, operator, None)
        if operation is not None:
            return operation(native, unwrap(value))

        if operator == "not_contains":
            return operators.invert(native.contains(unwrap(value)))

        method_name = operator.replace("_with", "with")
        native_method = getattr(native, method_name, None)
        if native_method is None:
            raise ValueError(f"Unsupported expression operator: {operator}")
        return native_method(unwrap(value))

    def and_(self, expressions: tuple[Any, ...]) -> Any:
        return reduce(operators.and_, expressions)

    def or_(self, expressions: tuple[Any, ...]) -> Any:
        return reduce(operators.or_, expressions)

    def not_(self, expression: Any) -> Any:
        return operators.invert(expression)

    def any_(self, column: Column[Any], value: Expression[bool] | None) -> Any:
        native = column.native
        expression = unwrap(value)
        any_method = getattr(native, "any", None)
        if any_method is None:
            raise ValueError("Any expression requires a collection relationship column")
        return any_method(expression) if expression is not None else any_method()

    def has(self, column: Column[Any], value: Expression[bool] | None) -> Any:
        native = column.native
        expression = unwrap(value)
        has_method = getattr(native, "has", None)
        if has_method is None:
            raise ValueError("Has expression requires a scalar relationship column")
        return has_method(expression) if expression is not None else has_method()

    def order(self, order: Order[Any]) -> Any:
        native = order.column.native
        return native.desc() if order.descending else native.asc()


def and_(expressions: Iterable[Expression[bool]]) -> Expression[bool]:
    return Expression(kind="and", expressions=tuple(expressions))


def or_(expressions: Iterable[Expression[bool]]) -> Expression[bool]:
    return Expression(kind="or", expressions=tuple(expressions))


def not_(expression: Expression[bool]) -> Expression[bool]:
    return Expression(kind="not", expressions=(expression,))


def any_(column: Column[Any], value: Expression[bool] | None = None) -> Expression[bool]:
    return Expression(kind="any", column=column, value=value)


def has(column: Column[Any], value: Expression[bool] | None = None) -> Expression[bool]:
    return Expression(kind="has", column=column, value=value)


# TODO: Add a true expression-level exists(subquery) once Arcanus has a typed
# subquery abstraction; relationship criteria should stay on any_/has.
def unwrap(value: object) -> object:
    if isinstance(value, (Column, Expression, Order)):
        return value()
    if isinstance(value, tuple):
        return tuple(unwrap(item) for item in value)
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


def dump(value: object) -> object:
    if isinstance(value, (Column, Expression, Order)):
        return value.dump()
    if isinstance(value, tuple):
        return [dump(item) for item in value]
    if isinstance(value, list):
        return [dump(item) for item in value]
    return value


@dataclass(frozen=True, eq=False)
class Column(Generic[T]):
    owner: type[Any]
    field_name: str
    used_name: str
    info: FieldInfo
    annotation: object
    native: Any

    @property
    def is_association(self) -> bool:
        return self.field_name in getattr(self.owner, "model_associations", {})

    def __getattr__(self, name: str) -> Any:
        if name == "__clause_element__":
            raise AttributeError(name)
        return getattr(self.native, name)

    def __str__(self) -> str:
        return str(self.native)

    def __hash__(self) -> int:
        return hash(self.native)

    def __call__(self, compiler: object | None = None) -> Any:
        return self.native

    def __clause_element__(self) -> Any:
        # SQLAlchemy inspects this hook structurally when columns enter SQL clauses.
        return self.native

    def dump(self) -> str:
        return self.used_name

    def operate(self, operator: str, value: object) -> Expression[bool]:
        return Expression(
            kind="comparison",
            column=self,
            operator=operator,
            value=value,
        )

    def any(self, value: Expression[bool] | None = None) -> Expression[bool]:
        return any_(self, value)

    def has(self, value: Expression[bool] | None = None) -> Expression[bool]:
        return has(self, value)

    def __lt__(self, value: object) -> Expression[bool]:
        return self.operate("lt", value)

    def __le__(self, value: object) -> Expression[bool]:
        return self.operate("le", value)

    def __eq__(self, value: object) -> Expression[bool]:  # type: ignore[override]
        return self.operate("eq", value)

    def __ne__(self, value: object) -> Expression[bool]:  # type: ignore[override]
        return self.operate("ne", value)

    def __gt__(self, value: object) -> Expression[bool]:
        return self.operate("gt", value)

    def __ge__(self, value: object) -> Expression[bool]:
        return self.operate("ge", value)

    def like(self, value: str) -> Expression[bool]:
        return self.operate("like", value)

    def ilike(self, value: str) -> Expression[bool]:
        return self.operate("ilike", value)

    def not_like(self, value: str) -> Expression[bool]:
        return self.operate("not_like", value)

    def in_(self, value: object) -> Expression[bool]:
        return self.operate("in_", value)

    def not_in(self, value: object) -> Expression[bool]:
        return self.operate("not_in", value)

    def contains(self, value: object) -> Expression[bool]:
        return self.operate("contains", value)

    def not_contains(self, value: object) -> Expression[bool]:
        return self.operate("not_contains", value)

    def starts_with(self, value: str) -> Expression[bool]:
        return self.operate("starts_with", value)

    def ends_with(self, value: str) -> Expression[bool]:
        return self.operate("ends_with", value)

    def startswith(self, value: str) -> Expression[bool]:
        return self.starts_with(value)

    def endswith(self, value: str) -> Expression[bool]:
        return self.ends_with(value)

    def asc(self) -> Order[T]:
        return Order(column=self, descending=False)

    def desc(self) -> Order[T]:
        return Order(column=self, descending=True)


@dataclass(frozen=True, eq=False)
class Expression(Generic[T]):
    kind: Literal["comparison", "any", "has", "and", "or", "not"]
    column: Column[Any] | None = None
    operator: str | None = None
    value: object | None = None
    expressions: tuple[Expression[bool], ...] = ()

    def __and__(self, other: Expression[bool]) -> Expression[bool]:
        return and_((cast(Expression[bool], self), other))

    def __or__(self, other: Expression[bool]) -> Expression[bool]:
        return or_((cast(Expression[bool], self), other))

    def __invert__(self) -> Expression[bool]:
        return not_(cast(Expression[bool], self))

    def __clause_element__(self) -> Any:
        # SQLAlchemy inspects this hook structurally when expressions enter SQL clauses.
        return self()

    @overload
    def __call__(self) -> Any: ...

    @overload
    def __call__(
        self, compiler: ExpressionCompiler[NativeExpressionT, NativeOrderT]
    ) -> NativeExpressionT: ...

    def __call__(
        self,
        compiler: ExpressionCompiler[NativeExpressionT, NativeOrderT] | None = None,
    ) -> NativeExpressionT | Any:
        if compiler is None:
            # Local import avoids a startup cycle while materia creates its compiler.
            from arcanus.materia.base import active_materia

            compiler = active_materia.get().expression_compiler
        if self.kind == "comparison":
            if self.column is None or self.operator is None:
                raise ValueError("Comparison expression requires a column and operator")
            return compiler.apply(self.column, self.operator, self.value)
        if self.kind == "any":
            if self.column is None:
                raise ValueError("Any expression requires a column")
            return compiler.any_(
                self.column, cast(Expression[bool] | None, self.value)
            )
        if self.kind == "has":
            if self.column is None:
                raise ValueError("Has expression requires a column")
            return compiler.has(
                self.column, cast(Expression[bool] | None, self.value)
            )

        if self.kind == "and":
            return compiler.and_(
                tuple(expression(compiler) for expression in self.expressions)
            )
        if self.kind == "or":
            return compiler.or_(
                tuple(expression(compiler) for expression in self.expressions)
            )
        if self.kind == "not":
            if len(self.expressions) != 1:
                raise ValueError("Not expression requires exactly one expression")
            return compiler.not_(self.expressions[0](compiler))
        raise ValueError(f"Unsupported expression kind: {self.kind}")

    def dump(self) -> dict[str, object]:
        if self.kind == "comparison":
            if self.column is None or self.operator is None:
                raise ValueError("Comparison expression requires a column and operator")
            key = "in" if self.operator == "in_" else self.operator
            return {self.column.used_name: {key: dump(self.value)}}
        if self.kind in {"any", "has"}:
            if self.column is None:
                raise ValueError(f"{self.kind.title()} expression requires a column")
            return {self.column.used_name: dump(self.value)}
        if self.kind in {"and", "or"}:
            return {self.kind: [expression.dump() for expression in self.expressions]}
        if self.kind == "not":
            if len(self.expressions) != 1:
                raise ValueError("Not expression requires exactly one expression")
            return {"not": self.expressions[0].dump()}
        raise ValueError(f"Unsupported expression kind: {self.kind}")


@dataclass(frozen=True, eq=False)
class Order(Generic[T]):
    column: Column[T]
    descending: bool = False

    def __clause_element__(self) -> Any:
        # SQLAlchemy inspects this hook structurally when orders enter SQL clauses.
        return self()

    @overload
    def __call__(self) -> Any: ...

    @overload
    def __call__(
        self, compiler: ExpressionCompiler[NativeExpressionT, NativeOrderT]
    ) -> NativeOrderT: ...

    def __call__(
        self,
        compiler: ExpressionCompiler[NativeExpressionT, NativeOrderT] | None = None,
    ) -> NativeOrderT | Any:
        if compiler is None:
            # Local import avoids a startup cycle while materia creates its compiler.
            from arcanus.materia.base import active_materia

            compiler = active_materia.get().expression_compiler
        return compiler.order(self)

    def dump(self) -> str:
        column = cast(Column[T], self.column)
        return f"-{column.used_name}" if self.descending else f"+{column.used_name}"

    def reverse(self) -> Self:
        return type(self)(column=self.column, descending=not self.descending)
