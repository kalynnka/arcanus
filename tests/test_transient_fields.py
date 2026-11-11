from __future__ import annotations

import dataclasses
from typing import Annotated, ClassVar, Self

import pytest
from pydantic import (
    AfterValidator,
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from arcanus import BaseTransmuter, Criteria, Transient, Transmuter
from arcanus.base import TransmuterProxiedMixin, validation_context
from arcanus.dataclass import dataclass, rebuild_dataclass
from arcanus.materia.base import BaseMateria, NoOpMateria


class ConversationModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    name: str
    messages: Annotated[list[int], Transient] = Field(default_factory=list)
    new_message_index: Annotated[int | None, Transient()] = None


class ModelConversation(ConversationModel, BaseTransmuter):
    pass


@dataclasses.dataclass
class ConversationDataclass(Transmuter):
    name: str
    messages: Annotated[list[int], Transient] = dataclasses.field(default_factory=list)
    new_message_index: Annotated[int | None, Transient()] = dataclasses.field(
        default=None, compare=False
    )


@dataclass(config=ConfigDict(validate_assignment=True))
class DataclassConversation(ConversationDataclass):
    pass


class ConversationProvider(TransmuterProxiedMixin):
    name: str = ""

    def __init__(self, name: str) -> None:
        self.name = name


class StatefulConversationProvider(ConversationProvider):
    messages: list[int]
    new_message_index: int | None

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.messages = [99]
        self.new_message_index = 99


@pytest.fixture(params=[ModelConversation, DataclassConversation])
def schema(
    request: pytest.FixtureRequest,
) -> type[ModelConversation | DataclassConversation]:
    return request.param


def test_construction_validation_assignment_and_serialization(
    schema: type[ModelConversation | DataclassConversation],
) -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)

    with materia:
        instance = schema.model_validate(
            {"name": "conversation", "messages": ["1"], "new_message_index": "2"}
        )
        provider = instance.__transmuter_provided__
        assert isinstance(provider, ConversationProvider)
        assert provider.name == "conversation"
        assert not hasattr(provider, "messages")
        assert not hasattr(provider, "new_message_index")
        assert instance.messages == [1]
        assert instance.new_message_index == 2

        updates = {"messages": ["3"], "new_message_index": "4"}
        for name, value in updates.items():
            setattr(instance, name, value)
        assert instance.messages == [3]
        assert instance.new_message_index == 4
        instance.name = "renamed"
        assert provider.name == "renamed"
        assert not hasattr(provider, "messages")
        assert not hasattr(provider, "new_message_index")
        with pytest.raises(ValidationError, match="messages"):
            schema.model_validate({"name": "invalid", "messages": ["invalid"]})
        with pytest.raises(ValidationError, match="messages"):
            field_name = "messages"
            setattr(instance, field_name, ["invalid"])
        assert instance.__transmuter_provided__ is provider
        assert instance.__transmuter_revalidating__ is False

        adapter = TypeAdapter(schema)
        expected = {"name": "renamed", "messages": [3], "new_message_index": 4}
        assert adapter.dump_python(instance) == expected
        assert adapter.validate_json(adapter.dump_json(instance)).messages == [3]
        assert "messages" in adapter.json_schema()["properties"]
        assert "new_message_index" in adapter.json_schema()["properties"]


def test_direct_construction_uses_independent_defaults(
    schema: type[ModelConversation | DataclassConversation],
) -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)

    with materia:
        first = schema(name="first")
        second = schema(name="second")
        first.messages.append(1)
        assert first.messages == [1]
        assert second.messages == []
        assert first.new_message_index is None
        assert second.new_message_index is None


def test_provider_load_defaults_and_revalidation_preserves_runtime_values(
    schema: type[ModelConversation | DataclassConversation],
) -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)
    provider = StatefulConversationProvider("loaded")

    with materia, validation_context():
        instance = schema.model_validate(provider, from_attributes=True)
        assert instance.messages == []
        assert instance.new_message_index is None
        instance.messages = [1, 2]
        instance.new_message_index = 1
        messages = instance.messages
        provider.name = "refreshed"

        assert schema.model_validate(instance) is instance
        assert schema.model_validate(provider, from_attributes=True) is instance
        assert instance.revalidate() is instance
        assert instance.name == "refreshed"
        assert instance.messages == messages
        assert instance.new_message_index == 1
        assert provider.messages == [99]
        assert provider.new_message_index == 99


@pytest.mark.parametrize("runtime_value", ["2", "invalid"])
def test_revalidation_validates_runtime_state(
    schema: type[ModelConversation | DataclassConversation], runtime_value: str
) -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)
    with materia:
        instance = schema(name="runtime")
        object.__setattr__(instance, "messages", [runtime_value])
        if runtime_value == "invalid":
            with pytest.raises(ValidationError, match="messages"):
                instance.revalidate()
        else:
            assert instance.revalidate().messages == [2]


@pytest.mark.parametrize("dataclass_schema", [False, True])
def test_revalidation_keeps_field_validator_output(dataclass_schema: bool) -> None:
    class SortedModel(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        messages: Annotated[list[int], Transient, AfterValidator(sorted)]

    @dataclass
    class SortedDataclass(Transmuter):
        name: str
        messages: Annotated[list[int], Transient, AfterValidator(sorted)]

    schema = SortedDataclass if dataclass_schema else SortedModel
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)
    with materia:
        instance = schema(name="runtime", messages=[1, 2])
        instance.messages.reverse()
        assert instance.messages == [2, 1]
        assert instance.revalidate().messages == [1, 2]


@pytest.mark.parametrize("bound", [False, True])
def test_transient_fields_reject_expressions_and_stay_out_of_criteria(
    schema: type[ModelConversation | DataclassConversation], bound: bool
) -> None:
    materia = BaseMateria() if bound else NoOpMateria()
    materia.bless(ConversationProvider)(schema)
    with materia:
        for name in ("messages", "new_message_index"):
            with pytest.raises(
                KeyError, match=f"Transient field '{name}'.*database expressions"
            ):
                schema[name]
        assert schema["name"].field_name == "name"
        criteria = Criteria[schema]
        assert "name" in criteria.model_fields
        assert "messages" not in criteria.model_fields
        assert "new_message_index" not in criteria.model_fields


def test_model_construct_respects_transient_fields() -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(ModelConversation)
    with materia:
        instance = ModelConversation.model_construct(name="constructed", messages=[1])
        provider = instance.__transmuter_provided__
        assert isinstance(provider, ConversationProvider)
        assert provider.name == "constructed"
        assert instance.messages == [1]
        assert not hasattr(provider, "messages")

        source = StatefulConversationProvider("loaded")
        loaded = ModelConversation.model_construct(data=source)
        assert loaded.messages == []
        assert source.messages == [99]


def test_dataclass_field_semantics_are_preserved() -> None:
    fields = {field.name: field for field in dataclasses.fields(DataclassConversation)}
    assert fields["messages"].default_factory is list
    assert fields["new_message_index"].default is None
    assert fields["new_message_index"].compare is False


def test_transient_assignment_outside_materia_keeps_dataclass_provider() -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(DataclassConversation)
    with materia:
        instance = DataclassConversation(name="conversation")
        provider = instance.__transmuter_provided__
    instance.messages = [1]
    instance.new_message_index = 1
    assert instance.__transmuter_provided__ is provider
    assert instance.__transmuter_revalidating__ is False
    assert isinstance(provider, ConversationProvider)
    assert not hasattr(provider, "messages")
    assert not hasattr(provider, "new_message_index")


@pytest.mark.parametrize("active_materia", [False, True])
@pytest.mark.parametrize("value", ["2", "invalid", "-1"])
def test_direct_dataclass_assignment_preserves_state(
    active_materia: bool, value: str
) -> None:
    @dataclass(config=ConfigDict(validate_assignment=True))
    class State(Transmuter):
        name: str
        cursor: Annotated[int, Transient] = 0

        @model_validator(mode="after")
        def nonnegative_cursor(self) -> Self:
            if self.cursor < 0:
                raise ValueError("cursor must be nonnegative")
            return self

    materia = BaseMateria()
    materia.bless(ConversationProvider)(State)
    with materia:
        instance = State(name="conversation")
    provider = instance.__transmuter_provided__
    assert isinstance(provider, ConversationProvider)
    object.__setattr__(instance, "__transmuter_revalidating__", True)

    with materia if active_materia else NoOpMateria():
        validator = State.__pydantic_validator__
        if value == "2":
            assert validator.validate_assignment(instance, "cursor", value) is instance
            assert instance.cursor == 2
        else:
            match = "int_parsing" if value == "invalid" else "nonnegative"
            with pytest.raises(ValidationError, match=match):
                validator.validate_assignment(instance, "cursor", value)
        assert instance.__transmuter_provided__ is provider
        assert instance.__transmuter_revalidating__ is True
        assert provider.name == "conversation"
        assert not hasattr(provider, "cursor")

        instance.cursor = 3
        instance.name = "updated"
        assert instance.__transmuter_provided__ is provider
        assert provider.name == "updated"


def test_rebuild_finalizes_transient_forward_references() -> None:
    class DeferredConversation(BaseTransmuter):
        name: str
        messages: Annotated[list[DeferredMessage], Transient] = Field(
            default_factory=list
        )

    class DeferredMessage(BaseModel):
        text: str

    DeferredConversation.model_rebuild()
    materia = BaseMateria()
    materia.bless(ConversationProvider)(DeferredConversation)
    with materia:
        instance = DeferredConversation(name="deferred")
        assert instance.messages == []
        assert not hasattr(instance.__transmuter_provided__, "messages")
        with pytest.raises(KeyError, match="Transient field 'messages'"):
            DeferredConversation["messages"]


def test_dataclass_rebuild_refreshes_field_classification() -> None:
    rebuild_dataclass(DataclassConversation)
    materia = BaseMateria()
    materia.bless(ConversationProvider)(DataclassConversation)
    with materia:
        instance = DataclassConversation(name="rebuilt", messages=[1])
        assert instance.messages == [1]
        instance.messages = [2]
        instance.name = "updated"
        provider = instance.__transmuter_provided__
        assert isinstance(provider, ConversationProvider)
        assert provider.name == "updated"
        assert not hasattr(instance.__transmuter_provided__, "messages")
        with pytest.raises(KeyError, match="Transient field 'messages'"):
            DataclassConversation["messages"]


@pytest.mark.parametrize("field_name", ["value", "cursor"])
def test_dataclass_assignment_uses_rebuilt_validator(field_name: str) -> None:
    @dataclass(config=ConfigDict(validate_assignment=True))
    class State(Transmuter):
        __pydantic_config__: ClassVar[ConfigDict]
        value: int
        cursor: Annotated[int, Transient] = 0

    class Provider(TransmuterProxiedMixin):
        def __init__(self, value: int) -> None:
            self.value: int = value

    materia = BaseMateria()
    materia.bless(Provider)(State)
    with materia:
        instance = State(value=1)
        provider = instance.__transmuter_provided__
        assert isinstance(provider, Provider)
        for strict in (True, False, True):
            State.__pydantic_config__["strict"] = strict
            rebuild_dataclass(State, force=True)
            previous = getattr(instance, field_name)
            if strict:
                with pytest.raises(ValidationError, match="int_type"):
                    setattr(instance, field_name, "2")
                assert getattr(instance, field_name) == previous
            else:
                setattr(instance, field_name, "2")
                assert getattr(instance, field_name) == 2
            assert provider.value == instance.value
            setattr(instance, field_name, 3)
            assert getattr(instance, field_name) == 3
            assert provider.value == instance.value
            assert instance.__transmuter_provided__ is provider
            assert instance.__transmuter_revalidating__ is False
            assert not hasattr(provider, "cursor")


@pytest.mark.parametrize("dataclass_schema", [False, True])
def test_rebuild_resolves_transient_validation_alias(dataclass_schema: bool) -> None:
    class ModelSchema(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        message: Annotated[DeferredMessage | None, Transient] = Field(
            default=None, validation_alias="runtime"
        )

    @dataclass
    class DataclassSchema(Transmuter):
        name: str
        message: Annotated[DeferredMessage | None, Transient] = Field(
            default=None, validation_alias="runtime"
        )

    class DeferredMessage(BaseModel):
        text: str

    schema = DataclassSchema if dataclass_schema else ModelSchema
    types_namespace = {"DeferredMessage": DeferredMessage}
    if dataclass_schema:
        rebuild_dataclass(DataclassSchema, _types_namespace=types_namespace)
    else:
        ModelSchema.model_rebuild(_types_namespace=types_namespace)
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)
    with materia, validation_context():
        first = schema.model_validate({"name": "first", "runtime": {"text": "one"}})
        second = schema.model_validate({"name": "second", "runtime": {"text": "two"}})
        assert first.message == DeferredMessage(text="one")
        assert second.message == DeferredMessage(text="two")
        assert first.revalidate().message == DeferredMessage(text="one")
        assert second.revalidate().message == DeferredMessage(text="two")
        assert not hasattr(first.__transmuter_provided__, "message")


def test_transient_fields_remain_in_partial_schemas() -> None:
    materia = BaseMateria()
    materia.bless(ConversationProvider)(ModelConversation)
    with materia:
        instance = ModelConversation.shell(
            ModelConversation.Create(name="created", messages=[1], new_message_index=0)
        )
        instance.absorb(ModelConversation.Update(messages=[2], new_message_index=1))
        assert instance.messages == [2]
        assert instance.new_message_index == 1
        assert not hasattr(instance.__transmuter_provided__, "messages")


def test_required_transient_field_still_requires_a_value() -> None:
    class RequiredConversation(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        cursor: Annotated[int, Transient]

    materia = BaseMateria()
    materia.bless(ConversationProvider)(RequiredConversation)
    with materia:
        instance = RequiredConversation(name="required", cursor=2)
        assert instance.revalidate().cursor == 2
        with pytest.raises(ValidationError, match="cursor"):
            RequiredConversation.model_validate(ConversationProvider("missing"))


@pytest.mark.parametrize(
    "alias",
    [
        "cursor",
        AliasChoices("cursor", "offset"),
        AliasPath("runtime", "cursor"),
        AliasPath("runtime", "source"),
        AliasPath("runtime", "paths"),
        AliasPath("runtime", "instance"),
        AliasPath("runtime", "roots"),
        AliasPath("runtime", 0),
        AliasPath("runtime", -1),
    ],
)
def test_revalidation_preserves_required_transient_with_validation_alias(
    alias: str | AliasChoices | AliasPath,
) -> None:
    class AliasedConversation(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        index: Annotated[int, Transient] = Field(validation_alias=alias)

    materia = BaseMateria()
    materia.bless(ConversationProvider)(AliasedConversation)
    runtime_key = alias.path[-1] if isinstance(alias, AliasPath) else "cursor"
    runtime = [2] if isinstance(runtime_key, int) else {runtime_key: 2}
    with materia:
        instance = AliasedConversation.model_validate(
            {"name": "aliased", "cursor": 2, "runtime": runtime}
        )
        assert instance.revalidate().index == 2


def test_serialization_exclusion_does_not_disable_persistence() -> None:
    class HiddenName(BaseTransmuter):
        name: str = Field(exclude=True)
        cursor: Annotated[int, Transient] = 0

    materia = BaseMateria()
    materia.bless(ConversationProvider)(HiddenName)
    with materia:
        instance = HiddenName(name="hidden")
        provider = instance.__transmuter_provided__
        assert isinstance(provider, ConversationProvider)
        assert provider.name == "hidden"
        instance.name = "updated"
        assert provider.name == "updated"
        assert instance.model_dump() == {"cursor": 0}


@pytest.mark.parametrize("with_transient", [False, True])
def test_unmarked_validation_alias_still_loads(with_transient: bool) -> None:
    class AliasedProvider(ConversationProvider):
        @property
        def source(self) -> str:
            return self.name

    class Plain(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str = Field(validation_alias="source")

    class Marked(Plain):
        runtime: Annotated[int, Transient] = 0

    schema = Marked if with_transient else Plain
    materia = BaseMateria()
    materia.bless(AliasedProvider)(schema)
    with materia, validation_context():
        assert schema.model_validate(AliasedProvider("example")).name == "example"


@pytest.mark.parametrize("with_transient", [False, True])
def test_dictionary_hook_still_loads(with_transient: bool) -> None:
    class DictionaryMateria(BaseMateria):
        @staticmethod
        def transmuter_before_validator(transmuter_type, materia, info):
            return {"name": materia.name}

    class Plain(BaseTransmuter):
        name: str

    class Marked(Plain):
        runtime: Annotated[int, Transient] = 0

    schema = Marked if with_transient else Plain
    materia = DictionaryMateria()
    materia.bless(ConversationProvider)(schema)
    with materia, validation_context():
        assert schema.model_validate(ConversationProvider("example")).name == "example"


@pytest.mark.parametrize("construct", [False, True])
def test_provider_validation_alias_does_not_supply_transient_value(
    construct: bool,
) -> None:
    class Schema(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        runtime: Annotated[int, Transient] = Field(
            default=0, validation_alias=AliasChoices("new_message_index", "messages")
        )

    materia = BaseMateria()
    materia.bless(StatefulConversationProvider)(Schema)
    with materia, validation_context():
        provider = StatefulConversationProvider("example")
        instance = (
            Schema.model_construct(data=provider)
            if construct
            else Schema.model_validate(provider)
        )
        assert instance.runtime == 0
        assert provider.new_message_index == 99
        assert provider.messages == [99]


@pytest.mark.parametrize("dataclass_schema", [False, True])
@pytest.mark.parametrize("last_index", [1, -1])
def test_revalidation_preserves_transient_fields_sharing_alias_list(
    dataclass_schema: bool, last_index: int
) -> None:
    class ModelSchema(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        first: Annotated[int, Transient] = Field(validation_alias=AliasPath("state", 0))
        second: Annotated[int, Transient] = Field(
            validation_alias=AliasPath("state", last_index)
        )

    @dataclass
    class DataclassSchema(Transmuter):
        name: str
        first: Annotated[int, Transient] = Field(validation_alias=AliasPath("state", 0))
        second: Annotated[int, Transient] = Field(
            validation_alias=AliasPath("state", last_index)
        )

    schema = DataclassSchema if dataclass_schema else ModelSchema
    materia = BaseMateria()
    materia.bless(ConversationProvider)(schema)
    with materia, validation_context():
        instance = schema.model_validate({"name": "example", "state": [10, 20]})
        assert instance.revalidate() is instance
        assert (instance.first, instance.second) == (10, 20)


@pytest.mark.parametrize("construct", [False, True])
def test_transient_alias_path_keeps_unmarked_sibling_input(construct: bool) -> None:
    class Provider(ConversationProvider):
        def __init__(self, name: str) -> None:
            super().__init__(name)
            self.state = [name, 99]

    class Schema(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str = Field(validation_alias=AliasPath("state", 0))
        cursor: Annotated[int, Transient] = Field(
            default=0, validation_alias=AliasPath("state", 1)
        )

    materia = BaseMateria()
    materia.bless(Provider)(Schema)
    with materia, validation_context():
        provider = Provider("example")
        instance = (
            Schema.model_construct(data=provider)
            if construct
            else Schema.model_validate(provider)
        )
        assert instance.name == "example"
        assert instance.cursor == 0
        instance.cursor = 2
        provider.state[0] = "refreshed"
        assert instance.revalidate() is instance
        assert (instance.name, instance.cursor) == ("refreshed", 2)
        assert provider.state == ["refreshed", 99]
