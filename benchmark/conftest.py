"""Benchmark suite root config.

Fixtures live in ``benchmark/fixtures`` and are re-exported by the per-axis
conftests; this root only registers the shared ``baseline`` marker. See
``benchmark/README.md`` for the two-axis design and the gap report.
"""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "baseline: reference/control benchmark (pure Pydantic, pure ORM, or "
        "Pydantic+SQLAlchemy) the candidate gap is measured against.",
    )
