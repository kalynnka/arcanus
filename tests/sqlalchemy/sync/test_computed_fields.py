"""Test that computed fields are excluded when creating SQLAlchemy ORM instances.

When a transmuter with @computed_field is validated/constructed with a provider,
the computed field values must NOT be passed to the ORM model constructor.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import ConfigDict, Field, computed_field
from sqlalchemy import Engine

from arcanus.base import BaseTransmuter, Identity
from tests import models


class TestSQLAlchemyComputedFields:
    """Computed fields should be excluded from ORM instance creation."""

    def test_validation_excludes_computed_from_orm(self, engine: Engine):
        """Creating a transmuter with a computed field should not pass it
        to the ORM constructor."""
        from tests.transmuters import sqlalchemy_materia

        class AuthorWithLabel(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
            name: str
            field: str

            @computed_field
            @property
            def name_and_field(self) -> str:
                return f"{self.name} ({self.field})"

        sqlalchemy_materia.bless(models.Author)(AuthorWithLabel)

        try:
            author = AuthorWithLabel(name="Einstein", field="Physics")
            assert author.name_and_field == "Einstein (Physics)"
            assert author.__transmuter_provided__ is not None
            assert isinstance(author.__transmuter_provided__, models.Author)
            assert author.__transmuter_provided__.name == "Einstein"
            assert author.__transmuter_provided__.field == "Physics"
            assert not hasattr(author.__transmuter_provided__, "name_and_field")
        finally:
            # Clean up the blessing to not interfere with other tests
            sqlalchemy_materia.formulars.pop(AuthorWithLabel, None)

    def test_construct_excludes_computed_from_orm(self, engine: Engine):
        """model_construct with a computed field should not pass it to ORM."""
        from tests.transmuters import sqlalchemy_materia

        class AuthorWithLabel2(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
            name: str
            field: str

            @computed_field
            @property
            def name_and_field(self) -> str:
                return f"{self.name} ({self.field})"

        sqlalchemy_materia.bless(models.Author)(AuthorWithLabel2)

        try:
            author = AuthorWithLabel2.model_construct(name="Curie", field="Chemistry")
            assert author.name_and_field == "Curie (Chemistry)"
            assert author.__transmuter_provided__ is not None
            assert isinstance(author.__transmuter_provided__, models.Author)
            assert not hasattr(author.__transmuter_provided__, "name_and_field")
        finally:
            sqlalchemy_materia.formulars.pop(AuthorWithLabel2, None)
