from __future__ import annotations

from typing import Literal

import pytest
from pydantic import create_model

from arcanus import Column
from arcanus.base import BaseTransmuter, Transmuter
from arcanus.materia.base import BaseMateria, NoOpMateria
from tests.transmuters import Author, DCAuthor, sqlalchemy_materia


@pytest.mark.parametrize("materia", [NoOpMateria(), sqlalchemy_materia])
@pytest.mark.parametrize(
    ("schema", "field_name"),
    [
        (Author, "name"),
        (Author, "id"),
        (Author, "books"),
        (DCAuthor, "name"),
    ],
)
def test_query_columns_require_bracket_access(
    materia: BaseMateria, schema: type[Transmuter], field_name: str
) -> None:
    with materia:
        assert not hasattr(schema, field_name)
        with pytest.raises(AttributeError, match=field_name):
            getattr(schema, field_name)

        column = schema[field_name]
        assert isinstance(column, Column)
        assert column.owner is schema
        assert column.field_name == field_name


@pytest.mark.filterwarnings("error:Field name .* shadows an attribute in parent")
def test_inherited_field_narrowing_does_not_warn() -> None:
    class File(BaseTransmuter):
        media_type: str

    Text = create_model(
        "Text", __base__=File, media_type=(Literal["text/plain"], "text/plain")
    )

    assert File(media_type="image/png").media_type == "image/png"
    assert Text.model_validate({}).media_type == "text/plain"
    assert not hasattr(File, "media_type")
    assert not hasattr(Text, "media_type")
    assert Text["media_type"].annotation == Literal["text/plain"]
    assert (Text["media_type"] == "text/plain").dump() == {
        "media_type": {"eq": "text/plain"}
    }
