"""Test that Pydantic computed fields are excluded from materia provider syncing.

Computed fields are derived properties that depend on normal fields.
They should NOT be passed to the provider constructor or synced via __setattr__.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import ConfigDict, Field, computed_field

from arcanus.base import BaseTransmuter, Identity, TransmuterProxiedMixin
from arcanus.materia.base import BaseMateria


class FakeProvider(TransmuterProxiedMixin):
    """A minimal materia provider that only accepts specific keyword arguments."""

    def __init__(self, **kwargs):
        allowed = {"id", "name", "price", "test_id"}
        unexpected = set(kwargs.keys()) - allowed
        if unexpected:
            raise TypeError(
                f"FakeProvider got unexpected keyword arguments: {unexpected}"
            )
        for k, v in kwargs.items():
            setattr(self, k, v)

    id: int | None
    name: str
    price: float


class TestComputedFieldExclusion:
    """Computed fields must not be shipped to the materia provider."""

    def test_computed_field_not_passed_to_provider_on_validation(self):
        """model_formulate (Normal validation) should exclude computed fields
        from the dict passed to the provider constructor."""
        materia = BaseMateria()

        class ProductTransmuter(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

        materia.bless(FakeProvider)(ProductTransmuter)

        with materia:
            # This triggers the "Normal validation" path in model_formulate
            product = ProductTransmuter(name="Widget", price=9.99)
            assert product.display_label == "Widget ($9.99)"
            assert product.__transmuter_provided__ is not None
            assert isinstance(product.__transmuter_provided__, FakeProvider)
            assert product.__transmuter_provided__.name == "Widget"
            assert product.__transmuter_provided__.price == 9.99
            # The provider should NOT have the computed field
            assert not hasattr(product.__transmuter_provided__, "display_label")

    def test_computed_field_not_passed_to_provider_on_construct(self):
        """model_construct (Normal construction) should exclude computed fields
        from the dict passed to the provider constructor."""
        materia = BaseMateria()

        class ProductTransmuter2(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

        materia.bless(FakeProvider)(ProductTransmuter2)

        with materia:
            # This triggers the "Normal construction" path in model_construct
            product = ProductTransmuter2.model_construct(name="Gadget", price=19.99)
            assert product.display_label == "Gadget ($19.99)"
            assert product.__transmuter_provided__ is not None
            assert isinstance(product.__transmuter_provided__, FakeProvider)
            assert product.__transmuter_provided__.name == "Gadget"
            assert product.__transmuter_provided__.price == 19.99
            assert not hasattr(product.__transmuter_provided__, "display_label")

    def test_computed_field_depending_on_another_computed(self):
        """Chained computed fields should also be excluded from provider syncing."""
        materia = BaseMateria()

        class ChainedTransmuter(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

            @computed_field
            @property
            def upper_label(self) -> str:
                return self.display_label.upper()

        materia.bless(FakeProvider)(ChainedTransmuter)

        with materia:
            item = ChainedTransmuter(name="Thing", price=5.00)
            assert item.upper_label == "THING ($5.00)"
            assert item.__transmuter_provided__ is not None
            assert not hasattr(item.__transmuter_provided__, "display_label")
            assert not hasattr(item.__transmuter_provided__, "upper_label")

    def test_setattr_does_not_sync_computed_fields(self):
        """__setattr__ should not try to sync computed fields to the provider."""
        materia = BaseMateria()

        class SetAttrTransmuter(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

        materia.bless(FakeProvider)(SetAttrTransmuter)

        with materia:
            item = SetAttrTransmuter(name="Old", price=1.00)
            assert item.__transmuter_provided__ is not None

            # Changing a normal field should sync to the provider
            item.name = "New"
            assert isinstance(item.__transmuter_provided__, FakeProvider)
            assert item.__transmuter_provided__.name == "New"
            assert item.display_label == "New ($1.00)"

            # The computed field should never appear on the provider
            assert not hasattr(item.__transmuter_provided__, "display_label")

    def test_computed_field_in_noop_materia(self):
        """Computed fields should work normally under NoOpMateria (default)."""

        class NoOpTransmuter(BaseTransmuter):
            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

        item = NoOpTransmuter(name="Simple", price=3.50)
        assert item.display_label == "Simple ($3.50)"
        assert item.__transmuter_provided__ is None

    def test_model_dump_still_includes_computed_fields(self):
        """model_dump on the transmuter itself should still include computed fields."""

        class DumpTransmuter(BaseTransmuter):
            name: str
            price: float

            @computed_field
            @property
            def display_label(self) -> str:
                return f"{self.name} (${self.price:.2f})"

        item = DumpTransmuter(name="Dump", price=7.77)
        dumped = item.model_dump()
        assert "display_label" in dumped
        assert dumped["display_label"] == "Dump ($7.77)"
