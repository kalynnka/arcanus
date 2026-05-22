from __future__ import annotations

import base64
import json

import pytest
from pydantic import ValidationError

from arcanus import Criteria, Cursor, Expression, Page, PagedCriteria
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
    name_criteria = getattr(criteria, "name")
    first_or_field_criteria = getattr(criteria.or_[0], "field")

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


def test_paged_criteria_order_expressions_return_arcanus_orders():
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
        order_bys = criteria.order_expressions()

    assert criteria.limit == 25
    assert criteria.offset == 5
    assert len(order_bys) == 1
    assert order_bys[0].dump() == "+name"


def test_cursor_from_criteria_round_trips_payload_and_token():
    criteria_model = PagedCriteria[Author]
    criteria = criteria_model.model_validate(
        {
            "name": {"starts_with": "Ada"},
            "limit": 20,
            "offset": 10,
            "order_by": ["+name", "-id"],
        }
    )

    cursor = Cursor[Author].from_criteria(criteria=criteria, position=(42, "Ada"))
    decoded = Cursor[Author].model_validate(cursor.root)
    constructed = Cursor[Author](cursor.root)

    assert decoded.root == cursor.root
    assert constructed.root == cursor.root
    assert decoded.entity == "Author"
    assert constructed.entity == "Author"
    assert decoded.position == (42, "Ada")
    assert constructed.position == (42, "Ada")
    assert decoded.criteria.model_dump(
        mode="json", by_alias=True, exclude_none=True
    ) == {
        "name": {"starts_with": "Ada"},
        "limit": 20,
        "offset": 10,
        "order_by": ["+name", "-id"],
    }


def test_cursor_validation_rejects_invalid_token_and_entity():
    criteria = PagedCriteria[Author].model_validate({"name": {"eq": "Ada"}})
    cursor = Cursor[Author].from_criteria(criteria=criteria, position=(1,))

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
    criteria = PagedCriteria[Author].model_validate({"name": {"eq": "Ada"}})
    cursor = Cursor[Author].from_criteria(criteria=criteria, position=(1,))
    bad_payload = cursor.payload.model_dump(mode="json", by_alias=True)
    bad_payload["criteria"]["limit"] = 0
    token = Cursor[Author].from_criteria(criteria=criteria, position=(1,)).root
    assert token

    invalid_token = (
        base64.urlsafe_b64encode(json.dumps(bad_payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author].model_validate(invalid_token)


def test_cursor_validation_rejects_bad_version_and_missing_parts():
    criteria = PagedCriteria[Author].model_validate({"name": {"eq": "Ada"}})
    cursor = Cursor[Author].from_criteria(criteria=criteria, position=(1,))
    payload = cursor.payload.model_dump(mode="json", by_alias=True)

    payload["version"] = 2
    bad_version_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](bad_version_token)

    del payload["position"]
    payload["version"] = 1
    missing_position_token = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    with pytest.raises(ValidationError, match="Invalid cursor token"):
        Cursor[Author](missing_position_token)


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
