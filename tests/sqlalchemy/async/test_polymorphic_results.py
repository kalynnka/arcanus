from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from arcanus.materia.sqlalchemy import AsyncSession
from tests.transmuters import (
    AbstractImageMedia,
    AbstractMedia,
    AbstractVideoMedia,
    AudioAsset,
    LibraryAsset,
    PdfAsset,
)


@pytest.mark.asyncio
async def test_async_list_polymorphic_result_uses_abstract_children(
    async_engine: AsyncEngine,
):
    prefix = f"async-poly-{uuid4()}"
    async with AsyncSession(async_engine) as session:
        session.add(
            AbstractImageMedia.model_validate(
                {
                    "name": f"{prefix}-image",
                    "width": 800,
                    "height": 600,
                }
            )
        )
        session.add(
            AbstractVideoMedia.model_validate(
                {
                    "name": f"{prefix}-video",
                    "duration": 45.0,
                }
            )
        )
        await session.commit()

    async with AsyncSession(async_engine) as session:
        items = await session.list(
            AbstractMedia,
            limit=None,
            expressions=[AbstractMedia["name"].like(f"{prefix}%")],
            order_bys=[AbstractMedia["name"]],
        )

    assert [type(item) for item in items] == [AbstractImageMedia, AbstractVideoMedia]


@pytest.mark.asyncio
async def test_async_list_joined_table_polymorphic_result_uses_children(
    async_engine: AsyncEngine,
):
    prefix = f"async-poly-joined-{uuid4()}"
    async with AsyncSession(async_engine) as session:
        session.add(PdfAsset.model_validate({"name": f"{prefix}-pdf", "pages": 42}))
        session.add(
            AudioAsset.model_validate({"name": f"{prefix}-audio", "duration": 13.0})
        )
        await session.commit()

    async with AsyncSession(async_engine) as session:
        items = await session.list(
            LibraryAsset,
            limit=None,
            expressions=[LibraryAsset["name"].like(f"{prefix}%")],
            order_bys=[LibraryAsset["name"]],
        )

    assert [type(item) for item in items] == [AudioAsset, PdfAsset]
