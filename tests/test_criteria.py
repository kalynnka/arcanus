from __future__ import annotations

import base64
import json

import pytest
from pydantic import BaseModel, ValidationError

from arcanus import (
    Criteria,
    Cursor,
    Expression,
    NestedCriteria,
    NestedCursor,
    Page,
)
from arcanus.criteria import (
    BaseCriteria,
    BookmarkCriteria,
    ExactCriteria,
    Ordering,
    TextCriteria,
)
from tests.transmuters import Author, Book, sqlalchemy_materia


def test_criteria_validation_rejects_unknown_or_association_fields():
    criteria_model = Criteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"books": {"eq": 1}})


def test_nested_criteria_accepts_one_layer_relationship_criteria():
    criteria_model = NestedCriteria[Author]

    criteria = criteria_model.model_validate(
        {
            "name": {"eq": "Ada"},
            "books": {"title": {"eq": "Notes"}},
        }
    )
    books = getattr(criteria, "books")

    assert books.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "title": {"eq": "Notes"}
    }
    assert criteria.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "name": {"eq": "Ada"},
        "books": {"title": {"eq": "Notes"}},
    }
    with sqlalchemy_materia:
        expressions = criteria.expressions

    assert tuple(expression.dump() for expression in expressions) == (
        {"name": {"eq": "Ada"}},
        {"books": {"title": {"eq": "Notes"}}},
    )


def test_nested_criteria_bool_branches_accept_one_layer_relationships():
    criteria_model = NestedCriteria[Author]

    criteria = criteria_model.model_validate(
        {
            "and": [
                {"name": {"eq": "Ada"}},
                {"books": {"title": {"eq": "Notes"}}},
            ],
        }
    )

    assert criteria.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "and": [
            {"name": {"eq": "Ada"}},
            {"books": {"title": {"eq": "Notes"}}},
        ]
    }
    with sqlalchemy_materia:
        expressions = criteria.expressions

    assert tuple(expression.dump() for expression in expressions) == (
        {"name": {"eq": "Ada"}},
        {"books": {"title": {"eq": "Notes"}}},
    )


def test_nested_criteria_bool_branches_keep_deeper_logic_scalar():
    criteria_model = NestedCriteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate(
            {
                "and": [
                    {
                        "and": [
                            {"books": {"title": {"eq": "Notes"}}},
                        ]
                    },
                ],
            }
        )


def test_nested_cursor_round_trips_relationship_criteria():
    with sqlalchemy_materia:
        cursor = NestedCursor[Author].from_expressions(
            expressions=(Author["books"].any(Book["title"] == "Notes"),),
            bookmark=Author["id"] < 123,
            order_bys=(Author["id"].desc(),),
            limit=10,
        )
        restored = NestedCursor[Author](str(cursor))

    assert restored.criteria is not None
    dumped = restored.criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert dumped == {"books": {"title": {"eq": "Notes"}}}
    assert restored.limit == 10
    assert restored.order_by == ("-id",)


def test_nested_cursor_round_trips_scalar_and_relationship_criteria():
    with sqlalchemy_materia:
        cursor = NestedCursor[Author].from_expressions(
            expressions=(
                (Author["name"] == "Ada")
                & Author["books"].any(Book["title"] == "Notes"),
            ),
            bookmark=Author["id"] < 123,
            order_bys=(Author["id"].desc(),),
            limit=10,
        )
        restored = NestedCursor[Author](str(cursor))

    assert restored.criteria is not None
    assert restored.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "and": [
            {"name": {"eq": "Ada"}},
            {"books": {"title": {"eq": "Notes"}}},
        ]
    }


def test_criteria_generics_require_transmuter_types():
    class PlainPydanticModel(BaseModel):
        id: int

    with pytest.raises(TypeError, match="transmuter"):
        Criteria[int]

    with pytest.raises(TypeError, match="transmuter"):
        Criteria[PlainPydanticModel]

    with pytest.raises(TypeError, match="transmuter"):
        Ordering[int]


def test_criteria_validation_rejects_wrong_value_types_and_operators():
    criteria_model = Criteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"id": {"lt": "not-an-int"}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"and": [{"name": {"like": 123}}]})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"id": {"in": [1, "bad"]}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"not": {"id": {"ge": "bad"}}})


def test_literal_fields_use_exact_value_criteria():
    criteria_model = Criteria[Author]

    criteria = criteria_model.model_validate(
        {"field": {"eq": "Physics", "in": ["Biology", "History"]}}
    )
    field_criteria: ExactCriteria[str] | None = getattr(criteria, "field")

    assert field_criteria is not None
    assert field_criteria.eq == "Physics"
    assert field_criteria.in_ == ("Biology", "History")

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"field": {"contains": "Physics"}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"field": {"eq": "Painting"}})


def test_text_criteria_accepts_range_operators():
    criteria_model = Criteria[Author]

    criteria = criteria_model.model_validate(
        {"name": {"lt": "Grace", "le": "Grace", "gt": "Ada", "ge": "Ada"}}
    )
    name_criteria: TextCriteria[str] | None = getattr(criteria, "name")

    assert name_criteria is not None
    assert name_criteria.lt == "Grace"
    assert name_criteria.le == "Grace"
    assert name_criteria.gt == "Ada"
    assert name_criteria.ge == "Ada"
    with sqlalchemy_materia:
        expressions = criteria.expressions
    assert tuple(expression.dump() for expression in expressions) == (
        {"name": {"lt": "Grace"}},
        {"name": {"le": "Grace"}},
        {"name": {"gt": "Ada"}},
        {"name": {"ge": "Ada"}},
    )


def test_criteria_validation_accepts_nested_logical_fields():
    criteria_model = Criteria[Author]

    criteria = criteria_model.model_validate(
        {
            "name": {"like": "Ada%"},
            "or": [
                {"field": {"eq": "Physics"}},
                {"field": {"eq": "History"}},
            ],
        }
    )

    assert criteria.or_ is not None
    name_criteria: TextCriteria[str] | None = getattr(criteria, "name")
    first_or_field_criteria: BaseCriteria[str] | None = getattr(
        criteria.or_[0], "field"
    )

    assert name_criteria is not None
    assert first_or_field_criteria is not None
    assert name_criteria.like == "Ada%"
    assert first_or_field_criteria.eq == "Physics"


def test_expression_dump_round_trips_through_criteria_json():
    criteria_model = Criteria[Author]

    with sqlalchemy_materia:
        expression = (
            Author["name"].contains("Ada") & (Author["field"] == "Physics")
        ) | ~(Author["id"].in_((1, 2)))

    assert isinstance(expression, Expression)
    payload = expression.dump()
    criteria = criteria_model.model_validate_json(json.dumps(payload))
    dumped = criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
    restored = criteria_model.model_validate_json(json.dumps(dumped))

    assert dumped == payload
    assert restored.model_dump(mode="json", by_alias=True, exclude_none=True) == payload


def test_criteria_expressions_property_returns_arcanus_expressions():
    criteria_model = Criteria[Author]
    criteria = criteria_model.model_validate(
        {
            "name": {"contains": "Ada"},
            "field": {"eq": "Physics"},
            "not": {"id": {"in": [1, 2]}},
        }
    )

    with sqlalchemy_materia:
        expressions = criteria.expressions

    assert expressions is criteria.expressions
    assert tuple(expression.dump() for expression in expressions) == (
        {"name": {"contains": "Ada"}},
        {"field": {"eq": "Physics"}},
        {"not": {"id": {"in": [1, 2]}}},
    )


def test_criteria_json_schema_uses_recursive_objects_for_logical_fields():
    schema = Criteria[Author].model_json_schema(by_alias=True)
    definition = schema["$defs"]["Criteria_Author_"]

    assert definition["properties"]["and"]["anyOf"][0]["items"] == {
        "$ref": "#/$defs/Criteria_Author_"
    }
    assert definition["properties"]["or"]["anyOf"][0]["items"] == {
        "$ref": "#/$defs/Criteria_Author_"
    }
    assert definition["properties"]["not"]["anyOf"][0] == {
        "$ref": "#/$defs/Criteria_Author_"
    }
    and_example = definition["properties"]["and"]["examples"][0][0]["test_id"]
    or_example = definition["properties"]["or"]["examples"][0][1]["id"]
    not_example = definition["properties"]["not"]["examples"][0]["test_id"]

    assert and_example["eq"] == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    assert and_example["in"] == ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]
    assert and_example["lt"] == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    assert or_example["ne"] == 1
    assert or_example["not_in"] == [1]
    assert not_example["ge"] == "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def test_cursor_payload_bookmark_is_separate_from_paged_criteria():
    criteria = Criteria[Author].model_validate(
        {
            "name": {"starts_with": "Ada"},
        }
    )
    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            expressions=criteria.expressions,
            bookmark=Author["id"] > 123,
            order_bys=(Author["id"].asc(),),
            limit=100,
        )
    decoded = Cursor[Author](str(cursor))

    with sqlalchemy_materia:
        assert decoded.criteria is not None
        criteria_expressions = decoded.criteria.expressions
        bookmark_expression = decoded.bookmark.expression

    assert tuple(expression.dump() for expression in criteria_expressions) == (
        {"name": {"starts_with": "Ada"}},
    )
    assert bookmark_expression is not None
    assert bookmark_expression.dump() == {"id": {"gt": 123}}


def test_upper_criteria_handles_scalar_field_expression_translation():
    criteria = Criteria[Author].model_validate({"name": {"contains": "Ada"}})

    name_criteria: TextCriteria[str] | None = getattr(criteria, "name")

    assert name_criteria is not None
    assert name_criteria.contains == "Ada"
    with sqlalchemy_materia:
        expressions = criteria.expressions
        assert expressions
        assert expressions[0].dump() == {"name": {"contains": "Ada"}}


def test_cursor_from_expression_round_trips_payload_and_token():
    criteria_model = Criteria[Author]
    criteria = criteria_model.model_validate(
        {
            "name": {"starts_with": "Ada"},
        }
    )

    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            expressions=criteria.expressions,
            bookmark=Author["id"] > 42,
            order_bys=(Author["name"].asc(), Author["id"].desc()),
            limit=20,
        )
    token = str(cursor)
    decoded = Cursor[Author].model_validate(token)
    constructed = Cursor[Author](token)

    assert str(decoded) == token
    assert str(constructed) == token
    assert decoded.entity == "Author"
    assert constructed.entity == "Author"
    assert decoded.criteria is not None
    assert decoded.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "name": {"starts_with": "Ada"},
    }
    assert decoded.payload.limit == 20
    assert decoded.payload.order_by == ("+name", "-id")
    assert decoded.bookmark is not None
    assert decoded.bookmark.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {"id": {"gt": 42}}


def test_cursor_from_expression_builds_criteria_from_expression_dump():
    with sqlalchemy_materia:
        expression = Author["name"].starts_with("Ada") & (Author["field"] == "Physics")
        bookmark = Author["id"] > 42
        cursor = Cursor[Author].from_expressions(
            expressions=(expression,),
            bookmark=bookmark,
            order_bys=(Author["name"].asc(), Author["id"].desc()),
            limit=20,
        )

    decoded = Cursor[Author](str(cursor))

    assert decoded.criteria is not None
    assert decoded.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "and": [
            {"name": {"starts_with": "Ada"}},
            {"field": {"eq": "Physics"}},
        ],
    }
    assert decoded.payload.limit == 20
    assert decoded.payload.order_by == ("+name", "-id")
    assert decoded.bookmark is not None
    assert decoded.bookmark.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {"id": {"gt": 42}}


def test_ordering_validates_model_scalar_fields_as_root_model():
    order_by_model = Ordering[Author]
    order_by = order_by_model.model_validate(["+name", "-id"])

    assert order_by == ("+name", "-id")
    assert tuple(order_by) == ("+name", "-id")
    assert order_by.model_dump(mode="json") == ["+name", "-id"]
    with sqlalchemy_materia:
        assert [order.dump() for order in order_by.orders] == ["+name", "-id"]
        assert order_by.orders is order_by.orders

    with pytest.raises(ValidationError):
        order_by_model.model_validate(["books"])

    with pytest.raises(ValidationError):
        order_by_model.model_validate(["-books"])


def test_bookmark_criteria_uses_implicit_or_branches():
    bookmark_model = BookmarkCriteria[Author]

    bookmark = bookmark_model.model_validate(
        {
            "or": [
                {"name": {"gt": "Ada"}},
                {"and": [{"name": {"eq": "Ada"}}, {"id": {"lt": 42}}]},
            ]
        }
    )

    assert bookmark.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "or": [
            {"name": {"gt": "Ada"}},
            {"and": [{"name": {"eq": "Ada"}}, {"id": {"lt": 42}}]},
        ]
    }
    with sqlalchemy_materia:
        expression = bookmark.expression
        assert expression is not None
        assert expression.dump() == {
            "or": [
                {"name": {"gt": "Ada"}},
                {
                    "and": [
                        {"name": {"eq": "Ada"}},
                        {"id": {"lt": 42}},
                    ]
                },
            ]
        }

    with pytest.raises(ValidationError):
        bookmark_model.model_validate({"name": {"starts_with": "Ada"}})

    with pytest.raises(ValidationError):
        bookmark_model.model_validate({"id": {"in": [42]}})

    with pytest.raises(ValidationError):
        bookmark_model.model_validate({"id": {"le": 42}})

    with pytest.raises(ValidationError):
        bookmark_model.model_validate({"id": {"ge": 42}})


def test_cursor_requires_order_and_bookmark():
    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            bookmark=Author["id"] < 123,
            order_bys=(Author["id"].desc(),),
        )

    assert cursor.bookmark.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {"id": {"lt": 123}}
    assert cursor.order_by == ("-id",)

    with (
        sqlalchemy_materia,
        pytest.raises(ValidationError, match="Cursor requires order_by"),
    ):
        Cursor[Author].from_expressions(bookmark=Author["id"] > 0, order_bys=())

    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(order_bys=(Author["id"].desc(),))

    assert cursor.bookmark.expression is None
    assert (
        cursor.bookmark.model_dump(mode="json", by_alias=True, exclude_none=True) == {}
    )


def test_cursor_validation_rejects_invalid_token_and_entity():
    criteria = Criteria[Author].model_validate({"name": {"eq": "Ada"}})
    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            expressions=criteria.expressions,
            bookmark=Author["id"] > 0,
            order_bys=(Author["id"].asc(),),
            limit=100,
        )

    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author].model_validate("not-base64-json")

    bad_entity_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    bad_entity_payload["entity"] = "Book"
    bad_entity_token = (
        base64.urlsafe_b64encode(json.dumps(bad_entity_payload).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(ValidationError, match="Cursor entity does not match"):
        Cursor[Author].model_validate(bad_entity_token)

    bad_bookmark_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    bad_bookmark_payload["bookmark"] = {"name": {"gt": "Ada"}}
    bad_bookmark_token = (
        base64.urlsafe_b64encode(json.dumps(bad_bookmark_payload).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author].model_validate(bad_bookmark_token)


def test_cursor_validation_hides_invalid_payload_as_cursor_error():
    criteria = Criteria[Author].model_validate({"name": {"eq": "Ada"}})
    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            expressions=criteria.expressions,
            bookmark=Author["id"] > 0,
            order_bys=(Author["id"].asc(),),
            limit=100,
        )
        token = str(
            Cursor[Author].from_expressions(
                expressions=criteria.expressions,
                bookmark=Author["id"] > 0,
                order_bys=(Author["id"].asc(),),
                limit=100,
            )
        )
    bad_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    bad_payload["criteria"]["limit"] = 0
    assert token

    invalid_token = (
        base64.urlsafe_b64encode(json.dumps(bad_payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author].model_validate(invalid_token)


def test_cursor_validation_rejects_bad_version_and_missing_required_payload_fields():
    criteria = Criteria[Author].model_validate({"name": {"eq": "Ada"}})
    with sqlalchemy_materia:
        cursor = Cursor[Author].from_expressions(
            expressions=criteria.expressions,
            bookmark=Author["id"] > 0,
            order_bys=(Author["id"].asc(),),
            limit=100,
        )
    payload = cursor.payload.model_dump(mode="json", by_alias=True)

    payload["version"] = 2
    bad_version_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](bad_version_token)

    missing_order_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    del missing_order_payload["order_by"]
    missing_order_token = (
        base64.urlsafe_b64encode(json.dumps(missing_order_payload).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](missing_order_token)

    del payload["bookmark"]
    payload["version"] = 1
    missing_bookmark_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](missing_bookmark_token)

    payload["bookmark"] = cursor.payload.bookmark.model_dump(mode="json", by_alias=True)
    del payload["criteria"]
    missing_criteria_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    cursor_without_criteria = Cursor[Author](missing_criteria_token)

    assert cursor_without_criteria.criteria is None
    assert cursor_without_criteria.payload.limit == 100
    assert cursor_without_criteria.payload.order_by == ("+id",)


def test_page_unwraps_items_like_a_tuple():
    page = Page(items=("a", "b", "c"), total=9, next_cursor="next", has_more=True)

    assert page
    assert page.total == 9
    assert len(page) == 3
    assert page[0] == "a"
    assert page[1:] == ("b", "c")
    assert list(page) == ["a", "b", "c"]
    assert list(reversed(page)) == ["c", "b", "a"]
    assert "b" in page
    assert page.next_cursor == "next"
    assert page.has_more is True


def test_empty_page_is_false_and_has_no_cursor():
    page = Page[str](items=(), next_cursor="next", has_more=False)

    assert not page
    assert page.total == 0
    assert len(page) == 0
    assert list(page) == []
    assert page.next_cursor == "next"
    assert page.has_more is False


def test_expression_call_compiles_with_material_compiler():
    with sqlalchemy_materia:
        expression = Author["name"] == "Ada"
        compiled = expression()

    assert compiled is not None
