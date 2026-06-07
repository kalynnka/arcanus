"""Axis B conftest — Pydantic+SQLAlchemy vs SQLAlchemy materia.

Re-exports the sync DB fixtures (incl. the autouse ``materia`` activation), the
rich seeds, and the async-suite fixtures. All seeds are session-scoped and
read-only; write benchmarks roll back so the seeds are never polluted.
"""

from __future__ import annotations

from benchmark.fixtures.db import *  # noqa: F401,F403
from benchmark.fixtures.db_async import *  # noqa: F401,F403
from benchmark.fixtures.seeds import *  # noqa: F401,F403
