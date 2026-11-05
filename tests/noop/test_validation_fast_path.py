from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ConfigDict, TypeAdapter, ValidationError

from arcanus.base import BaseTransmuter, Transmuter, TransmuterProxiedMixin
from arcanus.dataclass import dataclass
from arcanus.materia.base import BaseMateria


class Number(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)
    value: int


@dataclass
class DataclassNumber(Transmuter):
    value: int


class NumberProvider(TransmuterProxiedMixin):
    value: int

    def __init__(self, value: int) -> None:
        self.value = value


@pytest.mark.parametrize(
    "entry", ["init", "validate", "json", "adapter", "adapter_json"]
)
def test_noop_validation_initializes_state(entry: str) -> None:
    match entry:
        case "init":
            instance = Number(value=1)
        case "validate":
            instance = Number.model_validate({"value": "1"})
        case "json":
            instance = Number.model_validate_json('{"value": "1"}')
        case "adapter":
            instance = TypeAdapter(Number).validate_python({"value": "1"})
        case "adapter_json":
            instance = TypeAdapter(Number).validate_json('{"value": "1"}')
        case _:
            raise AssertionError(entry)

    assert instance.value == 1
    assert instance.__transmuter_provided__ is None
    assert instance.__transmuter_revalidating__ is False
    assert instance.revalidate() is instance


@pytest.mark.parametrize("model", [Number, DataclassNumber])
def test_existing_instance_keeps_provider_when_materia_changes(
    model: type[Number | DataclassNumber],
) -> None:
    materia = BaseMateria()
    materia.bless(NumberProvider)(model)
    provider = NumberProvider(value=1)

    with materia:
        instance = model.model_validate(provider, from_attributes=True)
        assert model.model_validate(provider, from_attributes=True) is instance

    assert model.model_validate(instance) is instance
    assert TypeAdapter(model).validate_python(instance) is instance
    assert instance.__transmuter_provided__ is provider
    assert provider.transmuter_proxy is instance

    unbound = model.model_validate({"value": "2"})
    assert unbound.value == 2
    assert unbound.__transmuter_provided__ is None
    assert unbound.__transmuter_revalidating__ is False
    with materia:
        assert model.model_validate(unbound) is unbound
        assert unbound.__transmuter_provided__ is None


@pytest.mark.parametrize("mode", ["always", "subclass-instances"])
def test_noop_revalidated_copy_has_initialized_state(
    mode: Literal["always", "subclass-instances"],
) -> None:
    class RevalidatedNumber(Number):
        model_config = ConfigDict(revalidate_instances=mode)

    class ChildNumber(RevalidatedNumber):
        pass

    original = ChildNumber(value=1)
    result = RevalidatedNumber.model_validate(original)

    assert result is not original
    assert type(result) is RevalidatedNumber
    assert result.value == 1
    assert result.__transmuter_provided__ is None
    assert result.__transmuter_revalidating__ is False
    assert result.revalidate() is result


def test_model_validate_uses_rebuilt_validator() -> None:
    class RebuiltNumber(Number):
        pass

    assert RebuiltNumber.model_validate({"value": "1"}).value == 1
    RebuiltNumber.model_config["strict"] = True
    RebuiltNumber.model_rebuild(force=True)

    with pytest.raises(ValidationError) as exc:
        RebuiltNumber.model_validate({"value": "1"})
    assert exc.value.errors()[0]["type"] == "int_type"
    assert exc.value.errors()[0]["loc"] == ("value",)
    assert RebuiltNumber.model_validate({"value": "1"}, strict=False).value == 1
