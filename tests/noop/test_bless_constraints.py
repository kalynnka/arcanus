"""Test that a provider cannot be blessed to multiple transmuters in a single materia."""

from __future__ import annotations

import pytest
from pydantic import ConfigDict

from arcanus.base import BaseTransmuter, TransmuterProxiedMixin
from arcanus.materia.base import BaseMateria


class DummyProvider(TransmuterProxiedMixin):
    """A minimal provider for testing bless constraints."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestBlessConstraints:
    """A provider can only be blessed to one transmuter per materia."""

    def test_same_provider_to_two_transmuters_raises(self):
        """Blessing the same provider to a second transmuter should raise ValueError."""
        materia = BaseMateria()

        class TransmuterA(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        class TransmuterB(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        materia.bless(DummyProvider)(TransmuterA)

        with pytest.raises(ValueError, match="already blessed"):
            materia.bless(DummyProvider)(TransmuterB)

    def test_same_provider_same_transmuter_is_idempotent(self):
        """Re-blessing the same provider to the same transmuter should succeed."""
        materia = BaseMateria()

        class TransmuterC(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        materia.bless(DummyProvider)(TransmuterC)
        # Should not raise
        materia.bless(DummyProvider)(TransmuterC)

        assert materia[TransmuterC] is DummyProvider

    def test_different_providers_to_different_transmuters_ok(self):
        """Different providers can be blessed to different transmuters."""
        materia = BaseMateria()

        class ProviderX(TransmuterProxiedMixin):
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class ProviderY(TransmuterProxiedMixin):
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class TransmuterD(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        class TransmuterE(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        materia.bless(ProviderX)(TransmuterD)
        materia.bless(ProviderY)(TransmuterE)

        assert materia[TransmuterD] is ProviderX
        assert materia[TransmuterE] is ProviderY

    def test_error_message_includes_names(self):
        """The error message should name both the provider and the existing transmuter."""
        materia = BaseMateria()

        class TransmuterF(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        class TransmuterG(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        materia.bless(DummyProvider)(TransmuterF)

        with pytest.raises(ValueError, match="DummyProvider") as exc_info:
            materia.bless(DummyProvider)(TransmuterG)

        assert "TransmuterF" in str(exc_info.value)

    def test_separate_materia_can_bless_same_provider(self):
        """Different materia instances can independently bless the same provider."""
        materia1 = BaseMateria()
        materia2 = BaseMateria()

        class TransmuterH(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        class TransmuterI(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)
            name: str

        materia1.bless(DummyProvider)(TransmuterH)
        # Different materia, same provider, different transmuter — should work
        materia2.bless(DummyProvider)(TransmuterI)

        assert materia1[TransmuterH] is DummyProvider
        assert materia2[TransmuterI] is DummyProvider
