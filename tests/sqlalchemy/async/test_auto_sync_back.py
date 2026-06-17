"""Async coverage for automatic sync-back of server-assigned values.

The ``after_flush`` listener runs on the sync ``Session`` that ``AsyncSession``
drives via greenlet, so the autoincrement id is synced after an async flush too.
Comprehensive cases live in the sync suite (test_auto_sync_back.py).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from arcanus.materia.sqlalchemy import AsyncSession
from tests.transmuters import Author


class TestAsyncFlushSyncsServerValues:
    @pytest.mark.asyncio
    async def test_async_flush_syncs_id(self, async_engine: AsyncEngine, test_id: UUID):
        async with AsyncSession(async_engine) as session:
            author = Author(name="Async Sync Asimov", field="Physics", test_id=test_id)
            assert author.id is None
            session.add(author)
            await session.flush()
            # No revalidate() — synced by the after_flush listener.
            assert author.id is not None
