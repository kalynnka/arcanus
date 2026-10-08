from __future__ import annotations

from typing import Any, assert_type

import pytest
from pydantic import Field, computed_field
from sqlalchemy import inspect, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Load, Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Join

from arcanus import Column, provided
from arcanus.base import BaseTransmuter, Transmuter, TransmuterProxiedMixin
from arcanus.materia.sqlalchemy import (
    SqlalchemyMateria,
    TransmuterAlias,
    aliased,
    contains_eager,
    joinedload,
)
from tests.transmuters import Author, Book, Category, PdfAsset


class LedgerBase(DeclarativeBase, TransmuterProxiedMixin): ...


class LedgerModel(LedgerBase):
    __tablename__ = "thread_ledgers"

    ledger_id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column()

    @hybrid_property
    def next_thread_id(self) -> int:
        return self.thread_id + 1

    @next_thread_id.inplace.expression
    @classmethod
    def next_thread_expression(cls) -> ColumnElement[int]:
        return cls.thread_id + 1


ledger_materia = SqlalchemyMateria()


@ledger_materia.bless(LedgerModel)
class ThreadLedger(BaseTransmuter):
    ledger_id: int
    thread_id: int
    thread: int = Field(alias="thread_id")
    missing: int = 0

    @computed_field
    @provided
    @property
    def next_thread_id(self) -> int:
        return self.thread_id + 1


def test_alias_column_compilation_and_type() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger)

        assert_type(a, TransmuterAlias[ThreadLedger])
        assert_type(a["thread_id"], Column[Any])
        assert str(select(a["thread_id"])) == (
            "SELECT thread_ledgers_1.thread_id \n"
            "FROM thread_ledgers AS thread_ledgers_1"
        )
        assert not hasattr(a, "thread_id")


def test_alias_rejects_undecorated_transmuter() -> None:
    class UndecoratedTransmuter(Transmuter): ...

    native = aliased(Author).native

    with pytest.raises(TypeError, match="^Aliasing requires a transmuter class$"):
        TransmuterAlias(UndecoratedTransmuter, native)


def test_alias_and_unaliased_columns_keep_both_froms() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger)
        stmt = select(ThreadLedger["thread_id"]).where(
            ThreadLedger["ledger_id"] == a["ledger_id"]
        )

        assert str(stmt) == (
            "SELECT thread_ledgers.thread_id \n"
            "FROM thread_ledgers, thread_ledgers AS thread_ledgers_1 \n"
            "WHERE thread_ledgers.ledger_id = thread_ledgers_1.ledger_id"
        )


def test_join_between_aliases() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger)
        b = aliased(ThreadLedger)
        stmt = select(a["thread_id"]).join(b, b["thread_id"] == a["ledger_id"])

        assert str(stmt) == (
            "SELECT thread_ledgers_1.thread_id \n"
            "FROM thread_ledgers AS thread_ledgers_1 "
            "JOIN thread_ledgers AS thread_ledgers_2 "
            "ON thread_ledgers_2.thread_id = thread_ledgers_1.ledger_id"
        )


def test_exists_correlates_only_the_unaliased_table() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger)
        inner = select(a["thread_id"]).where(
            a["ledger_id"] == ThreadLedger["ledger_id"]
        )
        stmt = select(ThreadLedger["thread_id"]).where(inner.exists())

        assert str(stmt) == (
            "SELECT thread_ledgers.thread_id \n"
            "FROM thread_ledgers \n"
            "WHERE EXISTS (SELECT thread_ledgers_1.thread_id \n"
            "FROM thread_ledgers AS thread_ledgers_1 \n"
            "WHERE thread_ledgers_1.ledger_id = thread_ledgers.ledger_id)"
        )


def test_alias_uses_field_aliases_and_provided_computed_fields() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger, name="history")
        column = a["thread"]

        assert column.owner is ThreadLedger
        assert column.field_name == "thread"
        assert column.used_name == "thread_id"
        assert column.info is ThreadLedger["thread"].info
        assert column.annotation is int
        assert column.native is a.native.thread_id
        assert column.dump() == "thread_id"
        assert (column == 1).dump() == {"thread_id": {"eq": 1}}
        assert str(select(a["next_thread_id"])) == (
            "SELECT history.thread_id + :thread_id_1 AS next_thread_id \n"
            "FROM thread_ledgers AS history"
        )


def test_alias_rejects_unknown_fields_and_missing_provider_columns() -> None:
    with ledger_materia:
        a = aliased(ThreadLedger)

        with pytest.raises(KeyError, match="Field 'unknown' is not defined"):
            a["unknown"]
        with pytest.raises(KeyError, match="Column 'missing'.*not defined"):
            a["missing"]


def test_inspection_and_relationship_loader_options_use_the_alias() -> None:
    a = aliased(Author)
    b = aliased(Book)
    relationship = a["books"]

    assert inspect(a) is inspect(a.native)
    assert inspect(a).mapper.class_ is Author.__transmuter_provider__
    assert relationship.owner is Author
    assert relationship.is_association
    assert relationship.dump() == "books"
    inspected_relationship = inspect(relationship)
    assert inspected_relationship is not None
    assert inspected_relationship.parent is inspect(a)
    assert Load(inspect(a)).path[0] is inspect(a)
    option = joinedload(relationship)
    assert isinstance(option, Load)
    assert option.path[0] is inspect(a)
    stmt = (
        select(Author)
        .join(b, Author["id"] == b["author_id"])
        .options(contains_eager(Author["books"], alias=b))
    )
    assert "JOIN book AS book_1 ON author.id = book_1.author_id" in str(stmt)


def test_dataclass_transmuter_alias() -> None:
    a = aliased(Category, name="categories")

    assert_type(a, TransmuterAlias[Category])
    assert a["name"].owner is Category
    assert str(select(a["name"])) == (
        "SELECT categories.name \nFROM category AS categories"
    )


def test_flat_alias_of_joined_inheritance() -> None:
    nested = aliased(PdfAsset)
    flat = aliased(PdfAsset, flat=True)

    assert not isinstance(inspect(nested).selectable, Join)
    assert isinstance(inspect(flat).selectable, Join)
    sql = str(select(flat["name"], flat["pages"]))
    assert "FROM library_asset AS library_asset_1 JOIN pdf_asset AS pdf_asset_1" in sql
