"""Axis A conftest — pure Pydantic vs Transmuter under NoOpMateria.

This subtree activates NO materia: the default ``active_materia`` is the
NoOpMateria singleton, so blessed transmuters take their no-backend fast path.
The autouse guard fails loudly if a future refactor ever leaks a real materia
activation into Axis A (which would silently corrupt the gap).
"""

from __future__ import annotations

import pytest

from arcanus.materia.base import NoOpMateria, active_materia
from benchmark.fixtures.noop_fixtures import *


@pytest.fixture(autouse=True)
def _assert_noop_materia():
    assert isinstance(active_materia.get(), NoOpMateria), (
        "Axis A benchmarks must run under NoOpMateria; a real materia leaked in."
    )
