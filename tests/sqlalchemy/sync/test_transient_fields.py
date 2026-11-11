from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import ConfigDict
from sqlalchemy import Engine, event, inspect, select

from arcanus import BaseTransmuter, Transient
from arcanus.materia.sqlalchemy import Session, SqlalchemyMateria
from tests import models
from tests.test_transient_fields import DataclassConversation, ModelConversation


@pytest.mark.parametrize("schema", [ModelConversation, DataclassConversation])
def test_transient_changes_do_not_dirty_session_or_write(
    engine: Engine, schema: type[ModelConversation | DataclassConversation]
) -> None:
    materia = SqlalchemyMateria()
    materia.bless(models.Author)(schema)

    with materia, Session(engine) as session, session.begin():
        provider = models.Author(name="conversation", field="test")
        session.add(provider)
        session.flush()
        instance = schema.model_validate(provider)
        assert instance.__transmuter_provided__ is provider
        assert inspect(provider).persistent
        assert instance.messages == []
        assert instance.new_message_index is None

        statements: list[str] = []

        def record_statement(
            connection, cursor, statement: str, parameters, context, executemany: bool
        ) -> None:
            statements.append(statement)

        connection = session.connection()
        event.listen(connection, "before_cursor_execute", record_statement)
        try:
            instance.messages = [2]
            instance.messages.append(3)
            instance.new_message_index = 1
            assert not session.dirty
            assert not session.is_modified(instance)
            session.flush()
            assert statements == []
        finally:
            event.remove(connection, "before_cursor_execute", record_statement)

        assert not hasattr(provider, "messages")
        assert not hasattr(provider, "new_message_index")
        instance.name = "persisted"
        assert provider in session.dirty
        session.flush()
        assert (
            session.scalar(select(schema).where(models.Author.id == provider.id))
            is instance
        )
        assert instance.messages == [2, 3]
        assert instance.new_message_index == 1


@pytest.mark.parametrize("use_construct", [False, True])
def test_provider_load_ignores_transient_column(
    engine: Engine, use_construct: bool
) -> None:
    class AuthorState(BaseTransmuter):
        model_config = ConfigDict(from_attributes=True)
        name: str
        field: Annotated[str, Transient] = "runtime default"

    materia = SqlalchemyMateria()
    materia.bless(models.Author)(AuthorState)
    with materia, Session(engine) as session, session.begin():
        provider = models.Author(name="author", field="stored value")
        session.add(provider)
        session.flush()
        instance = (
            AuthorState.model_construct(data=provider)
            if use_construct
            else AuthorState.model_validate(provider)
        )
        assert instance.field == "runtime default"
        instance.field = "runtime change"
        assert not session.dirty
        assert instance.revalidate().field == "runtime change"
        assert provider.field == "stored value"
        with pytest.raises(KeyError, match="Transient field 'field'"):
            AuthorState["field"]
