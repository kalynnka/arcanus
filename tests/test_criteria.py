from __future__ import annotations

import base64
import json

import pytest
from pydantic import ValidationError

from arcanus import (
    Criteria,
    Cursor,
    Expression,
    Page,
    PagedCriteria,
    TextCriteria,
)
from tests.transmuters import Author, sqlalchemy_materia


def test_criteria_validation_rejects_unknown_or_association_fields():
    criteria_model = Criteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"books": {"eq": 1}})


def test_criteria_validation_rejects_wrong_value_types_and_operators():
    criteria_model = Criteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"id": {"lt": "not-an-int"}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"name": {"lt": "Ada"}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"and": [{"name": {"like": 123}}]})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"id": {"in": [1, "bad"]}})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"not": {"id": {"ge": "bad"}}})


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
    first_or_field_criteria: TextCriteria[str] | None = getattr(
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


def test_criteria_expression_property_returns_arcanus_expression():
    criteria_model = Criteria[Author]
    criteria = criteria_model.model_validate(
        {
            "name": {"contains": "Ada"},
            "field": {"eq": "Physics"},
            "not": {"id": {"in": [1, 2]}},
        }
    )

    with sqlalchemy_materia:
        expression = criteria.expression

    assert expression is not None
    assert expression is criteria.expression
    assert expression.dump() == {
        "and": [
            {"name": {"contains": "Ada"}},
            {"field": {"eq": "Physics"}},
            {"not": {"id": {"in": [1, 2]}}},
        ]
    }


def test_paged_criteria_order_by_is_model_specific_and_scalar_only():
    criteria_model = PagedCriteria[Author]

    criteria = criteria_model.model_validate({"order_by": ["+name", "-id"]})
    assert criteria.order_by == ("+name", "-id")

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"order_by": ["+books"]})


def test_paged_criteria_validation_rejects_bad_pagination_values():
    criteria_model = PagedCriteria[Author]

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"limit": 0})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"offset": -1})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"order_by": ["name"]})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"order_by": ["+not_a_field"]})

    with pytest.raises(ValidationError):
        criteria_model.model_validate({"bookmark": {"books": {"eq": 1}}})


def test_paged_criteria_properties_return_arcanus_expression_and_orders():
    criteria_model = PagedCriteria[Author]

    with sqlalchemy_materia:
        criteria = criteria_model.model_validate(
            {
                "name": {"like": "Ada%"},
                "order_by": ["+name"],
                "limit": 25,
                "offset": 5,
            }
        )
        expression = criteria.expression
        orders = criteria.orders

    assert criteria.limit == 25
    assert criteria.offset == 5
    assert expression is not None
    assert expression.dump() == {"name": {"like": "Ada%"}}
    assert len(orders) == 1
    assert orders[0].dump() == "+name"
    assert criteria.orders is orders


def test_paged_criteria_properties_compile_with_material_compiler():
    criteria = PagedCriteria[Author].model_validate(
        {
            "name": {"starts_with": "Ada"},
            "field": {"eq": "Physics"},
            "order_by": ["-name"],
            "limit": 10,
        }
    )

    with sqlalchemy_materia:
        assert criteria.expression is not None
        material_expression = criteria.expression()
        material_order_bys = tuple(order_by() for order_by in criteria.orders)

    assert material_expression is not None
    assert len(material_order_bys) == 1


def test_paged_criteria_expression_includes_bookmark_criteria():
    criteria = PagedCriteria[Author].model_validate(
        {
            "name": {"starts_with": "Ada"},
            "bookmark": {"id": {"gt": 123}},
            "order_by": ["+id"],
        }
    )

    with sqlalchemy_materia:
        expression = criteria.expression

    assert criteria.bookmark is not None
    assert expression is not None
    assert expression.dump() == {
        "and": [
            {"name": {"starts_with": "Ada"}},
            {"id": {"gt": 123}},
        ]
    }


def test_upper_criteria_handles_scalar_field_expression_translation():
    criteria = Criteria[Author].model_validate({"name": {"contains": "Ada"}})

    name_criteria: TextCriteria[str] | None = getattr(criteria, "name")

    assert name_criteria is not None
    assert name_criteria.contains == "Ada"
    with sqlalchemy_materia:
        assert criteria.expression is not None
        assert criteria.expression.dump() == {"name": {"contains": "Ada"}}


def test_cursor_from_criteria_round_trips_payload_and_token():
    criteria_model = PagedCriteria[Author]
    criteria = criteria_model.model_validate(
        {
            "name": {"starts_with": "Ada"},
            "limit": 20,
            "offset": 10,
            "order_by": ["+name", "-id"],
            "bookmark": {"id": {"gt": 42}},
        }
    )

    cursor = Cursor[Author].from_criteria(criteria=criteria)
    token = str(cursor)
    decoded = Cursor[Author].model_validate(token)
    constructed = Cursor[Author](token)

    assert str(decoded) == token
    assert str(constructed) == token
    assert decoded.entity == "Author"
    assert constructed.entity == "Author"
    assert decoded.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "name": {"starts_with": "Ada"},
        "limit": 20,
        "offset": 10,
        "order_by": ["+name", "-id"],
        "bookmark": {"id": {"gt": 42}},
    }


def test_cursor_from_expression_builds_criteria_from_expression_dump():
    with sqlalchemy_materia:
        expression = Author["name"].starts_with("Ada") & (Author["field"] == "Physics")
        bookmark = Author["id"] > 42
        cursor = Cursor[Author].from_expression(
            expression=expression,
            bookmark=bookmark,
            order_bys=(Author["name"].asc(), Author["id"].desc()),
            limit=20,
            offset=10,
        )

    decoded = Cursor[Author](str(cursor))

    assert decoded.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "and": [
            {"name": {"starts_with": "Ada"}},
            {"field": {"eq": "Physics"}},
        ],
        "limit": 20,
        "offset": 10,
        "order_by": ["+name", "-id"],
        "bookmark": {"id": {"gt": 42}},
    }


def test_cursor_validation_rejects_invalid_token_and_entity():
    criteria = PagedCriteria[Author].model_validate(
        {"name": {"eq": "Ada"}, "order_by": ["+id"]}
    )
    cursor = Cursor[Author].from_criteria(criteria=criteria)

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


def test_cursor_validation_hides_invalid_payload_as_cursor_error():
    criteria = PagedCriteria[Author].model_validate(
        {"name": {"eq": "Ada"}, "order_by": ["+id"]}
    )
    cursor = Cursor[Author].from_criteria(criteria=criteria)
    bad_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    bad_payload["criteria"]["limit"] = 0
    token = str(Cursor[Author].from_criteria(criteria=criteria))
    assert token

    invalid_token = (
        base64.urlsafe_b64encode(json.dumps(bad_payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author].model_validate(invalid_token)


def test_cursor_validation_rejects_bad_version_and_missing_parts():
    criteria = PagedCriteria[Author].model_validate(
        {"name": {"eq": "Ada"}, "order_by": ["+id"]}
    )
    cursor = Cursor[Author].from_criteria(criteria=criteria)
    payload = cursor.payload.model_dump(mode="json", by_alias=True)

    payload["version"] = 2
    bad_version_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](bad_version_token)

    del payload["criteria"]
    payload["version"] = 1
    missing_criteria_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](missing_criteria_token)


def test_page_unwraps_items_like_a_tuple():
    page = Page(items=("a", "b", "c"), next_cursor="next", has_more=True)

    assert page
    assert len(page) == 3
    assert page[0] == "a"
    assert page[1:] == ("b", "c")
    assert list(page) == ["a", "b", "c"]
    assert list(reversed(page)) == ["c", "b", "a"]
    assert "b" in page
    assert page.next_cursor == "next"
    assert page.has_more is True


def test_empty_page_is_false_and_has_no_cursor():
    page = Page[str](items=(), next_cursor=None, has_more=False)

    assert not page
    assert len(page) == 0
    assert list(page) == []
    assert page.next_cursor is None
    assert page.has_more is False


def test_expression_call_compiles_with_material_compiler():
    with sqlalchemy_materia:
        expression = Author["name"] == "Ada"
        compiled = expression()

    assert compiled is not None
