"""Computed fields paired with SQLAlchemy hybrid attributes.

A pydantic ``@computed_field`` on a transmuter, backed by a same-named
``hybrid_property`` on the ORM provider, behaves like a regular column end
to end: filterable and orderable through criteria/expressions, readable in
serialization, usable in cursor bookmarks, and writable when the property
has a setter. Reads never fire relationship loading — ``Relation.peek()``
resolves only what is already in memory.

The Memo/SourceDoc pair models the common "user override falls back to the
related row's value" shape (e.g. a note's title falling back to its
article's title).
"""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import uuid4

import pytest
from pydantic import ConfigDict, Field, ValidationError, computed_field
from pydantic_core import PydanticCustomError
from sqlalchemy import ForeignKey, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arcanus import Criteria, Cursor, Relation, Relationship, provided
from arcanus.base import BaseTransmuter, Identity
from arcanus.materia.base import BaseMateria
from arcanus.materia.sqlalchemy import AsyncSession, selectinload
from tests.models import Base
from tests.transmuters import sqlalchemy_materia


class ComputedSource(Base):
    __tablename__ = "computed_source"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ComputedMemo(Base):
    __tablename__ = "computed_memo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("computed_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[ComputedSource] = relationship(uselist=False)

    @hybrid_property
    def title(self) -> Optional[str]:
        if self.title_override is not None:
            return self.title_override
        source = self.source
        return source.title if source is not None else None

    @title.inplace.setter
    def _title_setter(self, value: Optional[str]) -> None:
        self.title_override = value

    @title.inplace.expression
    @classmethod
    def _title_expression(cls):
        return func.coalesce(
            cls.title_override,
            select(ComputedSource.title)
            .where(ComputedSource.id == cls.source_id)
            .scalar_subquery(),
        )


@sqlalchemy_materia.bless(ComputedSource)
class SourceSchema(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: Optional[str] = None
    summary: Optional[str] = None


@sqlalchemy_materia.bless(ComputedMemo)
class MemoSchema(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title_override: Optional[str] = None
    source_id: Optional[int] = None
    source: Relation[Optional[SourceSchema]] = Relationship()

    @computed_field
    @provided
    @property
    def title(self) -> Optional[str]:
        if self.title_override is not None:
            return self.title_override
        source = self.source.peek()
        return source.title if source is not None else None

    @title.setter
    def title(self, value: Optional[str]) -> None:
        self.title_override = value

    # Display-only computed field: serialized, but NOT @provided — it must
    # stay invisible to criteria, Schema[name], and ordering.
    @computed_field
    @property
    def label(self) -> str:
        return f"memo:{self.title_override or 'untitled'}"


async def _seed_memo(
    session: AsyncSession, source_title: Optional[str], override: Optional[str] = None
) -> MemoSchema:
    source = SourceSchema(title=source_title, summary=f"About {source_title}")
    session.add(source)
    await session.flush()
    source.revalidate()

    memo = MemoSchema(source_id=source.id, title_override=override)
    session.add(memo)
    await session.flush()
    memo.revalidate()
    return memo


class TestComputedFieldCriteria:
    def test_subscript_resolves_hybrid_expression(self):
        expression = MemoSchema["title"].ilike("%quantum%")
        sql = str(select(ComputedMemo).where(expression))
        assert "coalesce" in sql.lower()
        assert "computed_source" in sql

    def test_criteria_model_includes_computed_field(self):
        criteria = Criteria[MemoSchema].model_validate({"title": {"ilike": "%q%"}})
        (expression,) = criteria.expressions
        sql = str(select(ComputedMemo).where(expression))
        assert "coalesce" in sql.lower()

    def test_computed_field_inside_or_combinator(self):
        criteria = Criteria[MemoSchema].model_validate(
            {
                "or": [
                    {"title": {"ilike": "%q%"}},
                    {"title_override": {"eq": "exact"}},
                ]
            }
        )
        (expression,) = criteria.expressions
        sql = str(select(ComputedMemo).where(expression))
        assert " or " in sql.lower()
        assert "coalesce" in sql.lower()


class TestComputedFieldQuerying:
    @pytest.mark.asyncio
    async def test_filtering_matches_fallback_and_override(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            fallback_memo = await _seed_memo(session, f"Quantum {marker} Primer")
            override_memo = await _seed_memo(
                session,
                f"Banana {marker} Recipe",
                override=f"Quantum {marker} Override",
            )

            matched = await session.list(
                MemoSchema,
                expressions=(MemoSchema["title"].ilike(f"%Quantum {marker}%"),),
            )
            assert {memo.id for memo in matched} == {
                fallback_memo.id,
                override_memo.id,
            }

            # The override masks the source title: coalesce, not OR.
            masked = await session.list(
                MemoSchema,
                expressions=(MemoSchema["title"].ilike(f"%Banana {marker}%"),),
            )
            assert masked == []

    @pytest.mark.asyncio
    async def test_order_by_effective_title(self, async_engine: AsyncEngine):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            zebra = await _seed_memo(session, f"{marker} Zebra")
            apple = await _seed_memo(session, f"{marker} Apple")
            mango = await _seed_memo(session, f"Ignored {marker}", f"{marker} Mango")

            memos = await session.list(
                MemoSchema,
                expressions=(MemoSchema["title"].ilike(f"%{marker}%"),),
                order_bys=(MemoSchema["title"].desc(),),
            )
            assert [memo.id for memo in memos] == [zebra.id, mango.id, apple.id]

    @pytest.mark.asyncio
    async def test_cursor_bookmark_reads_computed_value(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            for letter in ("Alpha", "Beta", "Gamma"):
                await _seed_memo(session, f"{marker} {letter}")

            expressions = (MemoSchema["title"].ilike(f"%{marker}%"),)
            orders = (MemoSchema["title"].asc(),)
            options = (selectinload(MemoSchema["source"]),)

            first_items = await session.list(
                MemoSchema,
                limit=2,
                order_bys=orders,
                options=options,
                expressions=expressions,
            )
            assert [memo.title for memo in first_items] == [
                f"{marker} Alpha",
                f"{marker} Beta",
            ]

            bookmark = Cursor[MemoSchema].bookmark_from_item(first_items[-1], orders)
            cursor = Cursor[MemoSchema].from_expressions(
                expressions=expressions,
                bookmark=bookmark,
                order_bys=orders,
                limit=2,
            )
            decoded = Cursor[MemoSchema](str(cursor))
            # The bookmark must carry the REAL computed value through the
            # encode/decode round trip — an unpopulated value would be
            # silently dropped by exclude_none and the cursor would never
            # advance. Ascending keys also cover the trailing NULLS LAST
            # region.
            assert decoded.bookmark.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == {
                "or": [
                    {"title": {"gt": f"{marker} Beta"}},
                    {"title": {"is_null": True}},
                ]
            }
            bookmark_expression = decoded.bookmark.expression
            assert bookmark_expression is not None
            second_items = await session.list(
                MemoSchema,
                limit=2,
                order_bys=decoded.order_by.orders,
                options=options,
                expressions=(*expressions, bookmark_expression),
            )
            assert [memo.title for memo in second_items] == [f"{marker} Gamma"]


class TestComputedFieldReads:
    @pytest.mark.asyncio
    async def test_serialization_resolves_effective_value(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            fallback_memo = await _seed_memo(session, f"Quantum {marker}")
            override_memo = await _seed_memo(
                session, f"Banana {marker}", override=f"Override {marker}"
            )

            memos = await session.list(
                MemoSchema,
                expressions=(
                    MemoSchema["id"].in_([fallback_memo.id, override_memo.id]),
                ),
                order_bys=(MemoSchema["id"].asc(),),
                options=(selectinload(MemoSchema["source"]),),
            )
            dumped = [memo.model_dump()["title"] for memo in memos]
            assert dumped == [f"Quantum {marker}", f"Override {marker}"]

    @pytest.mark.asyncio
    async def test_peek_never_fires_relationship_loading(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            seeded = await _seed_memo(session, f"Quantum {marker}")
            await session.commit()

        async with AsyncSession(async_engine) as session:
            memo = await session.get_one(MemoSchema, seeded.id)

            # The source relationship is NOT loaded: peek must not fire the
            # lazy load (which would raise MissingGreenlet in async), and the
            # computed field degrades to None instead of crashing.
            assert memo.source.loaded is False
            assert memo.source.peek() is None
            assert memo.title is None
            assert memo.model_dump()["title"] is None

            await memo.source
            assert memo.source.loaded is True
            assert memo.source.peek() is not None
            assert memo.title == f"Quantum {marker}"

    @pytest.mark.asyncio
    async def test_setter_writes_through_to_provider(self, async_engine: AsyncEngine):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            memo = await _seed_memo(session, f"Quantum {marker}")

            memo.title = f"Edited {marker}"
            assert memo.title_override == f"Edited {marker}"
            provided = memo.__transmuter_provided__
            assert isinstance(provided, ComputedMemo)
            assert provided.title_override == f"Edited {marker}"
            await session.commit()

        async with AsyncSession(async_engine) as session:
            reloaded = await session.get_one(MemoSchema, memo.id)
            assert reloaded.title_override == f"Edited {marker}"
            assert reloaded.title == f"Edited {marker}"


class TestProvidedGate:
    """Only @provided computed fields join the expression layer."""

    def test_unmarked_computed_field_rejected_as_criteria(self):
        with pytest.raises(ValidationError):
            Criteria[MemoSchema].model_validate({"label": {"eq": "memo:x"}})

    def test_unmarked_computed_field_has_no_column(self):
        with pytest.raises(KeyError):
            MemoSchema["label"]

    @pytest.mark.asyncio
    async def test_unmarked_computed_field_still_serializes(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            memo = await _seed_memo(session, f"Quantum {marker}", override=marker)
            assert memo.model_dump()["label"] == f"memo:{marker}"


class TestIsNullOperator:
    def test_is_null_true_compiles_to_is_null(self):
        criteria = Criteria[MemoSchema].model_validate(
            {"title_override": {"is_null": True}}
        )
        (expression,) = criteria.expressions
        sql = str(select(ComputedMemo).where(expression))
        assert "is null" in sql.lower()

    def test_is_null_false_compiles_to_is_not_null(self):
        criteria = Criteria[MemoSchema].model_validate(
            {"title_override": {"is_null": False}}
        )
        (expression,) = criteria.expressions
        sql = str(select(ComputedMemo).where(expression))
        assert "is not null" in sql.lower()

    @pytest.mark.asyncio
    async def test_is_null_on_computed_field_filters_rows(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            titled = await _seed_memo(session, f"Quantum {marker}")
            untitled = await _seed_memo(session, None)

            scope = MemoSchema["id"].in_([titled.id, untitled.id])
            null_titled = await session.list(
                MemoSchema,
                expressions=(scope, MemoSchema["title"].operate("is_null", True)),
            )
            assert [memo.id for memo in null_titled] == [untitled.id]


class TestNullableCursorPagination:
    """Cursor pagination over a nullable order key (ASC NULLS LAST / DESC
    NULLS FIRST), with the null region reached and crossed via bookmarks."""

    async def _seed(self, session: AsyncSession, marker: str) -> list[MemoSchema]:
        memos = [
            await _seed_memo(session, f"{marker} Alpha"),
            await _seed_memo(session, f"{marker} Beta"),
            await _seed_memo(session, None, override=None),
            await _seed_memo(session, None, override=None),
        ]
        return memos

    async def _walk(
        self,
        session: AsyncSession,
        expressions: tuple,
        orders: tuple,
    ) -> list[int | None]:
        options = (selectinload(MemoSchema["source"]),)
        collected: list[int | None] = []
        bookmark_expression = None
        for _ in range(8):
            page_expressions = expressions + (
                (bookmark_expression,) if bookmark_expression is not None else ()
            )
            items = await session.list(
                MemoSchema,
                limit=1,
                order_bys=orders,
                options=options,
                expressions=page_expressions,
            )
            if not items:
                break
            collected.append(items[-1].id)
            bookmark = Cursor[MemoSchema].bookmark_from_item(items[-1], orders)
            cursor = Cursor[MemoSchema].from_expressions(
                expressions=expressions,
                bookmark=bookmark,
                order_bys=orders,
                limit=1,
            )
            decoded = Cursor[MemoSchema](str(cursor))
            bookmark_expression = decoded.bookmark.expression
            assert bookmark_expression is not None
        return collected

    @pytest.mark.asyncio
    async def test_ascending_nulls_last_walk(self, async_engine: AsyncEngine):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            memos = await self._seed(session, marker)
            scope = (MemoSchema["id"].in_([memo.id for memo in memos]),)
            orders = (MemoSchema["title"].asc(), MemoSchema["id"].asc())

            collected = await self._walk(session, scope, orders)
            assert collected == [memos[0].id, memos[1].id, memos[2].id, memos[3].id]

    @pytest.mark.asyncio
    async def test_descending_nulls_first_walk(self, async_engine: AsyncEngine):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            memos = await self._seed(session, marker)
            scope = (MemoSchema["id"].in_([memo.id for memo in memos]),)
            orders = (MemoSchema["title"].desc(), MemoSchema["id"].desc())

            collected = await self._walk(session, scope, orders)
            assert collected == [memos[3].id, memos[2].id, memos[1].id, memos[0].id]

    @pytest.mark.asyncio
    async def test_null_bookmark_round_trips_via_is_null(
        self, async_engine: AsyncEngine
    ):
        marker = uuid4().hex[:8]
        async with AsyncSession(async_engine) as session:
            memos = await self._seed(session, marker)
            orders = (MemoSchema["title"].asc(), MemoSchema["id"].asc())

            bookmark = Cursor[MemoSchema].bookmark_from_item(memos[2], orders)
            cursor = Cursor[MemoSchema].from_expressions(
                expressions=(MemoSchema["id"].in_([memo.id for memo in memos]),),
                bookmark=bookmark,
                order_bys=orders,
                limit=1,
            )
            decoded = Cursor[MemoSchema](str(cursor))
            dumped = decoded.bookmark.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            assert dumped == {
                "and": [
                    {"title": {"is_null": True}},
                    {
                        "or": [
                            {"id": {"gt": memos[2].id}},
                            {"id": {"is_null": True}},
                        ]
                    },
                ]
            }


class TestAssociationLoadedHook:
    def test_base_materia_treats_associations_as_loaded(self):
        relation: Relation[SourceSchema] = Relation()
        assert BaseMateria().association_loaded(relation) is True

    def test_sqlalchemy_materia_without_provider_is_loaded(self):
        # Unprepared relation: no owner instance, so no provider to inspect.
        relation: Relation[SourceSchema] = Relation()
        assert sqlalchemy_materia.association_loaded(relation) is True


@pytest.mark.asyncio
async def test_all_null_bookmark_without_tiebreak_raises(async_engine: AsyncEngine):
    async with AsyncSession(async_engine) as session:
        memo = await _seed_memo(session, None)
        with pytest.raises(PydanticCustomError, match="non-null unique tiebreak"):
            Cursor[MemoSchema].bookmark_from_item(memo, (MemoSchema["title"].asc(),))
