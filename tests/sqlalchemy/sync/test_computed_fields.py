"""Test that computed fields are excluded when creating SQLAlchemy ORM instances.

When a transmuter with @computed_field is validated/constructed with a provider,
the computed field values must NOT be passed to the ORM model constructor.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field, computed_field
from sqlalchemy import Engine

from arcanus.base import BaseTransmuter, Identity, TransmuterProxiedMixin
from arcanus.materia.base import BaseMateria


class AuthorLikeProvider(TransmuterProxiedMixin):
    """A provider that mimics Author ORM columns without touching the shared materia."""

    def __init__(self, **kwargs):
        allowed = {"id", "name", "field", "test_id"}
        unexpected = set(kwargs.keys()) - allowed
        if unexpected:
            raise TypeError(
                f"AuthorLikeProvider got unexpected keyword arguments: {unexpected}"
            )
        for k, v in kwargs.items():
            setattr(self, k, v)

    id: int | None
    name: str
    field: str


class TestSQLAlchemyComputedFields:
    """Computed fields should be excluded from ORM instance creation."""

    def test_validation_excludes_computed_from_orm(self, engine: Engine):
        """Creating a transmuter with a computed field should not pass it
        to the ORM constructor."""
        materia = BaseMateria()

        class AuthorWithLabel(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str

            @computed_field
            @property
            def name_and_field(self) -> str:
                return f"{self.name} ({self.field})"

        materia.bless(AuthorLikeProvider)(AuthorWithLabel)

        with materia:
            author = AuthorWithLabel(name="Einstein", field="Physics")
            assert author.name_and_field == "Einstein (Physics)"
            assert author.__transmuter_provided__ is not None
            assert isinstance(author.__transmuter_provided__, AuthorLikeProvider)
            assert author.__transmuter_provided__.name == "Einstein"
            assert author.__transmuter_provided__.field == "Physics"
            assert not hasattr(author.__transmuter_provided__, "name_and_field")

    def test_construct_excludes_computed_from_orm(self, engine: Engine):
        """model_construct with a computed field should not pass it to ORM."""
        materia = BaseMateria()

        class AuthorWithLabel2(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            name: str
            field: str

            @computed_field
            @property
            def name_and_field(self) -> str:
                return f"{self.name} ({self.field})"

        materia.bless(AuthorLikeProvider)(AuthorWithLabel2)

        with materia:
            author = AuthorWithLabel2.model_construct(name="Curie", field="Chemistry")
            assert author.name_and_field == "Curie (Chemistry)"
            assert author.__transmuter_provided__ is not None
            assert isinstance(author.__transmuter_provided__, AuthorLikeProvider)
            assert not hasattr(author.__transmuter_provided__, "name_and_field")
