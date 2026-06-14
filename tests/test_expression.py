from __future__ import annotations

import pytest

from arcanus import Column, Expression, Order
from arcanus.expression import NativeExpressionCompiler, and_, dump, not_, or_, unwrap
from arcanus.materia.base import BaseMateria
from tests.transmuters import Author, Book, sqlalchemy_materia


def test_column_creation_from_transmuter_field():
    with sqlalchemy_materia:
        column = Author["name"]

    assert isinstance(column, Column)
    assert column.owner is Author
    assert column.field_name == "name"
    assert column.used_name == "name"
    assert column.annotation is str


def test_relationship_field_returns_column_wrapper():
    with sqlalchemy_materia:
        column = Book["detail"]

    assert isinstance(column, Column)
    assert column.owner is Book
    assert column.field_name == "detail"
    assert column.used_name == "detail"
    assert column.is_association is True


def test_expression_operators_and_dump_are_immutable():
    with sqlalchemy_materia:
        column = Author["name"]
        like_expression = column.like("A%")
        equality_expression = column == "Alice"
        combined = like_expression & equality_expression

    assert isinstance(like_expression, Expression)
    assert like_expression.dump() == {"name": {"like": "A%"}}
    assert equality_expression.dump() == {"name": {"eq": "Alice"}}
    assert combined.dump() == {
        "and": [
            {"name": {"like": "A%"}},
            {"name": {"eq": "Alice"}},
        ]
    }


def test_expression_logical_operators_and_text_helpers():
    with sqlalchemy_materia:
        expression = (
            Author["name"].starts_with("A") | Author["field"].in_(("Physics",))
        ) & ~(Author["name"].not_like("%z"))

    assert expression.dump() == {
        "and": [
            {
                "or": [
                    {"name": {"starts_with": "A"}},
                    {"field": {"in": ["Physics"]}},
                ]
            },
            {"not": {"name": {"not_like": "%z"}}},
        ]
    }


def test_expression_static_helpers_dump_logical_groups():
    with sqlalchemy_materia:
        expression = and_(
            (
                Author["name"] == "Ada",
                or_(
                    (
                        Author["field"] == "Physics",
                        not_(Author["id"] < 10),
                    )
                ),
            )
        )

    assert expression.dump() == {
        "and": [
            {"name": {"eq": "Ada"}},
            {
                "or": [
                    {"field": {"eq": "Physics"}},
                    {"not": {"id": {"lt": 10}}},
                ]
            },
        ]
    }


def test_expression_any_and_has_dump_shape():
    with sqlalchemy_materia:
        any_expression = Author["books"].any(Book["title"] == "Notes")
        has_expression = Book["author"].has(Author["name"] == "Ada")

    assert any_expression.dump() == {"books": {"title": {"eq": "Notes"}}}
    assert has_expression.dump() == {"author": {"name": {"eq": "Ada"}}}


def test_expression_nested_boolean_dump_shape():
    with sqlalchemy_materia:
        expression = ~(
            (Author["name"] == "Ada")
            | (Author["field"] == "Physics")
            | (Author["id"].not_in((1, 2, 3)))
        )

    assert expression.dump() == {
        "not": {
            "or": [
                {
                    "or": [
                        {"name": {"eq": "Ada"}},
                        {"field": {"eq": "Physics"}},
                    ]
                },
                {"id": {"not_in": [1, 2, 3]}},
            ]
        }
    }


def test_expression_comparison_inclusion_and_text_operator_dumps():
    with sqlalchemy_materia:
        expressions = [
            Author["id"] >= 1,
            Author["id"] < 10,
            Author["field"].not_in(("Biology", "Chemistry")),
            Author["name"].contains("Ada"),
            Author["name"].ends_with("Lovelace"),
        ]

    assert [expression.dump() for expression in expressions] == [
        {"id": {"ge": 1}},
        {"id": {"lt": 10}},
        {"field": {"not_in": ["Biology", "Chemistry"]}},
        {"name": {"contains": "Ada"}},
        {"name": {"ends_with": "Lovelace"}},
    ]


def test_expression_all_scalar_operator_dumps():
    with sqlalchemy_materia:
        expressions = [
            Author["id"] == 1,
            Author["id"] != 2,
            Author["id"] <= 3,
            Author["id"] > 4,
            Author["name"].is_(None),
            Author["name"].is_not(None),
            Author["name"].ilike("%ada%"),
            Author["name"].not_ilike("%bot%"),
            Author["name"].not_contains("bot"),
            Author["name"].icontains("ada"),
            Author["name"].istartswith("ada"),
            Author["name"].iendswith("lovelace"),
            Author["id"].between(1, 10),
            Author["name"].match("ada"),
            Author["name"].regexp_match("^A"),
        ]

    assert [expression.dump() for expression in expressions] == [
        {"id": {"eq": 1}},
        {"id": {"ne": 2}},
        {"id": {"le": 3}},
        {"id": {"gt": 4}},
        {"name": {"is_": None}},
        {"name": {"is_not": None}},
        {"name": {"ilike": "%ada%"}},
        {"name": {"not_ilike": "%bot%"}},
        {"name": {"not_contains": "bot"}},
        {"name": {"icontains": "ada"}},
        {"name": {"istartswith": "ada"}},
        {"name": {"iendswith": "lovelace"}},
        {"id": {"between": [1, 10]}},
        {"name": {"match": "ada"}},
        {"name": {"regexp_match": "^A"}},
    ]


def test_expression_reuses_column_without_mutating_previous_expressions():
    with sqlalchemy_materia:
        column = Author["name"]
        first = column.starts_with("A")
        second = column.ends_with("Z")

    assert first.dump() == {"name": {"starts_with": "A"}}
    assert second.dump() == {"name": {"ends_with": "Z"}}


def test_expression_compiler_rejects_unsupported_operator():
    with sqlalchemy_materia:
        expression = Author["name"].operate("definitely_not_supported", "Ada")

        with pytest.raises(ValueError, match="Unsupported expression operator"):
            expression()


def test_expression_compiler_supports_extended_sqlalchemy_operators():
    with sqlalchemy_materia:
        expressions = [
            Author["name"].is_not(None),
            Author["id"].between(1, 10),
            Author["name"].not_ilike("%bot%"),
            Author["name"].icontains("ada"),
            Author["name"].istartswith("ada"),
            Author["name"].iendswith("lovelace"),
            Author["name"].match("ada"),
            Author["name"].regexp_match("^A"),
        ]
        compiled = [expression() for expression in expressions]

    assert len(compiled) == len(expressions)


def test_expression_compiler_rejects_malformed_expression():
    expression = Expression(kind="comparison")

    with pytest.raises(ValueError, match="requires a column and operator"):
        expression()


def test_expression_compiler_rejects_malformed_not_expression():
    expression = Expression(kind="not")

    with pytest.raises(ValueError, match="requires exactly one expression"):
        expression()


def test_order_objects_from_columns():
    with sqlalchemy_materia:
        ascending = Author["name"].asc()
        descending = Author["id"].desc()

    assert isinstance(ascending, Order)
    assert ascending.dump() == "+name"
    assert descending.dump() == "-id"


class NativeRecorder:
    __hash__ = object.__hash__

    def __eq__(self, value: object) -> object:
        return ("eq", value)

    def __ne__(self, value: object) -> object:
        return ("ne", value)

    def __lt__(self, value: object) -> object:
        return ("lt", value)

    def __and__(self, value: object) -> object:
        return ("and", value)

    def __or__(self, value: object) -> object:
        return ("or", value)

    def __invert__(self) -> object:
        return ("not",)

    def is_(self, value: object) -> object:
        return ("is", value)

    def is_not(self, value: object) -> object:
        return ("is_not", value)

    def between(self, left: object, right: object) -> object:
        return ("between", left, right)

    def contains(self, value: object) -> object:
        return NativeRecorder()

    def startswith(self, value: object) -> object:
        return ("startswith", value)

    def asc(self) -> object:
        return ("asc",)

    def desc(self) -> object:
        return ("desc",)

    def delegated(self) -> object:
        return ("delegated",)

    def any(self, value: object = None) -> object:
        return ("any", value)

    def has(self, value: object = None) -> object:
        return ("has", value)


def native_column() -> Column[str]:
    return Column(
        owner=Author,
        field_name="name",
        used_name="name",
        info=Author.__pydantic_fields__["name"],
        annotation=str,
        native=NativeRecorder(),
    )


def test_native_expression_compiler_operator_branches():
    compiler = NativeExpressionCompiler()
    column = native_column()

    assert compiler.apply(column, "is_", None) == ("is", None)
    assert compiler.apply(column, "is_not", None) == ("is_not", None)
    assert compiler.apply(column, "is_null", True) == ("is", None)
    assert compiler.apply(column, "is_null", False) == ("is_not", None)
    assert compiler.apply(column, "between", (1, 2)) == ("between", 1, 2)
    assert compiler.apply(column, "eq", "Ada") == ("eq", "Ada")
    assert compiler.apply(column, "not_contains", "bot") == ("not",)
    assert compiler.apply(column, "starts_with", "A") == ("startswith", "A")

    with pytest.raises(ValueError, match="Unsupported expression operator"):
        compiler.apply(column, "missing_operator", "Ada")


def test_native_expression_compiler_boolean_relationship_and_order_branches():
    compiler = NativeExpressionCompiler()
    column = native_column()

    assert compiler.and_((NativeRecorder(), NativeRecorder()))[0] == "and"
    assert compiler.or_((NativeRecorder(), NativeRecorder()))[0] == "or"
    assert compiler.not_(NativeRecorder()) == ("not",)
    assert compiler.any_(column, None) == ("any", None)
    assert compiler.has(column, None) == ("has", None)
    assert compiler.order(column.asc()) == ("asc",)
    assert compiler.order(column.desc()) == ("desc",)


def test_native_expression_compiler_rejects_relationship_operator_on_scalar_native():
    compiler = NativeExpressionCompiler()
    column = Column(
        owner=Author,
        field_name="name",
        used_name="name",
        info=Author.__pydantic_fields__["name"],
        annotation=str,
        native=object(),
    )

    with pytest.raises(ValueError, match="collection relationship"):
        compiler.any_(column, None)
    with pytest.raises(ValueError, match="scalar relationship"):
        compiler.has(column, None)


def test_column_dunder_helpers_delegate_to_native():
    column = native_column()

    assert str(column) == str(column.native)
    assert hash(column) == hash(column.native)
    assert column.delegated() == ("delegated",)
    assert column.asc()() == column.native
    assert column.startswith("A").dump() == {"name": {"starts_with": "A"}}
    assert column.endswith("A").dump() == {"name": {"ends_with": "A"}}


def test_unwrap_and_dump_recurse_through_containers():
    column = native_column()
    expression = column == "Ada"
    order = column.desc()

    # unwrap compiles via the active materia's compiler; activate a base materia
    # (plain NativeExpressionCompiler) since NoOpMateria now compiles to JSON.
    with BaseMateria():
        assert unwrap((column, [expression, order])) == (
            column.native,
            [("eq", "Ada"), ("desc",)],
        )
    assert dump((column, [expression, order])) == [
        "name",
        [{"name": {"eq": "Ada"}}, "-name"],
    ]


def test_expression_rejects_malformed_any_has_and_dump_shapes():
    with pytest.raises(ValueError, match="Any expression requires a column"):
        Expression(kind="any")()
    with pytest.raises(ValueError, match="Has expression requires a column"):
        Expression(kind="has")()
    with pytest.raises(ValueError, match="requires a column and operator"):
        Expression(kind="comparison").dump()
    with pytest.raises(ValueError, match="Any expression requires a column"):
        Expression(kind="any").dump()
    with pytest.raises(ValueError, match="requires exactly one expression"):
        Expression(kind="not").dump()


def test_expression_rejects_unknown_kind():
    expression = Expression(kind="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Unsupported expression kind"):
        expression()
    with pytest.raises(ValueError, match="Unsupported expression kind"):
        expression.dump()
