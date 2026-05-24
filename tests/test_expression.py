from __future__ import annotations

import pytest

from arcanus import Column, Expression, Order
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
            Author["name"].ilike("%ada%"),
            Author["name"].not_contains("bot"),
        ]

    assert [expression.dump() for expression in expressions] == [
        {"id": {"eq": 1}},
        {"id": {"ne": 2}},
        {"id": {"le": 3}},
        {"id": {"gt": 4}},
        {"name": {"ilike": "%ada%"}},
        {"name": {"not_contains": "bot"}},
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
