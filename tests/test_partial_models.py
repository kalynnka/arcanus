from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

import pytest
from pydantic import UUID7, Field, ValidationError

from arcanus import BaseTransmuter, Transmuter
from arcanus.dataclass import dataclass


class ModelFields(BaseTransmuter):
    run_id: UUID7
    optional_run_id: UUID7 | None = None
    count: Annotated[int, Field(gt=0)] = 1


@dataclass
class DataclassFields(Transmuter):
    run_id: UUID7
    optional_run_id: UUID7 | None = None
    count: Annotated[int, Field(gt=0)] = 1


@pytest.mark.parametrize("schema", [ModelFields, DataclassFields])
def test_update_preserves_constraints_inside_nullable_fields(
    schema: type[ModelFields | DataclassFields],
) -> None:
    update = schema.Update
    value = UUID("019a78e8-8b7e-7000-8000-000000000001")
    assert update().model_dump(exclude_unset=True) == {}
    assert update(run_id=None, count=None).model_dump(exclude_unset=True) == {
        "run_id": None,
        "count": None,
    }
    assert update(run_id=str(value), optional_run_id=str(value), count=2).model_dump(
        exclude_unset=True
    ) == {"run_id": value, "optional_run_id": value, "count": 2}
    for field in ("run_id", "optional_run_id"):
        with pytest.raises(ValidationError, match="UUID version 7 expected"):
            update.model_validate({field: uuid4()})
    with pytest.raises(ValidationError, match="greater than 0"):
        update(count=0)
    properties = update.model_json_schema()["properties"]
    assert properties["run_id"]["anyOf"] == [
        {"format": "uuid7", "type": "string"},
        {"type": "null"},
    ]
    assert schema.__pydantic_fields__["run_id"].is_required()
    with pytest.raises(ValidationError, match="UUID version 7 expected"):
        schema.Create(run_id=uuid4())
