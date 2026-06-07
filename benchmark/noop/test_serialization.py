"""Axis A — serialization: pure Pydantic (reference) vs Transmuter under NoOpMateria.

Pre-validated objects are dumped so cost reflects serialization only. Both sides
use identical include/exclude so the gap is apples-to-apples (the old suite
mistakenly excluded relationships on one side only).
"""

from __future__ import annotations

import pytest


class TestDumpDictScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-dump-dict-scalar")
    def test_pydantic_dump_dict_scalar(self, benchmark, pydantic_flat_authors):
        result = benchmark(lambda: [m.model_dump() for m in pydantic_flat_authors])
        assert "name" in result[0]

    @pytest.mark.benchmark(group="noop-dump-dict-scalar")
    def test_transmuter_dump_dict_scalar(self, benchmark, transmuter_flat_authors):
        result = benchmark(lambda: [m.model_dump() for m in transmuter_flat_authors])
        assert "name" in result[0]


class TestDumpJsonScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-dump-json-scalar")
    def test_pydantic_dump_json_scalar(self, benchmark, pydantic_flat_authors):
        result = benchmark(lambda: [m.model_dump_json() for m in pydantic_flat_authors])
        assert len(result) == len(pydantic_flat_authors)

    @pytest.mark.benchmark(group="noop-dump-json-scalar")
    def test_transmuter_dump_json_scalar(self, benchmark, transmuter_flat_authors):
        result = benchmark(
            lambda: [m.model_dump_json() for m in transmuter_flat_authors]
        )
        assert len(result) == len(transmuter_flat_authors)


class TestDumpDictWithRel:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-dump-dict-with-rel")
    def test_pydantic_dump_dict_with_rel(self, benchmark, pydantic_authors):
        result = benchmark(lambda: [m.model_dump() for m in pydantic_authors])
        assert "books" in result[0]

    @pytest.mark.benchmark(group="noop-dump-dict-with-rel")
    def test_transmuter_dump_dict_with_rel(self, benchmark, transmuter_authors):
        result = benchmark(lambda: [m.model_dump() for m in transmuter_authors])
        assert "books" in result[0]


class TestDumpDictExclRel:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-dump-dict-excl-rel")
    def test_pydantic_dump_dict_excl_rel(self, benchmark, pydantic_authors):
        result = benchmark(
            lambda: [m.model_dump(exclude={"books"}) for m in pydantic_authors]
        )
        assert "books" not in result[0]

    @pytest.mark.benchmark(group="noop-dump-dict-excl-rel")
    def test_transmuter_dump_dict_excl_rel(self, benchmark, transmuter_authors):
        result = benchmark(
            lambda: [m.model_dump(exclude={"books"}) for m in transmuter_authors]
        )
        assert "books" not in result[0]


class TestDumpJsonWithRel:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-dump-json-with-rel")
    def test_pydantic_dump_json_with_rel(self, benchmark, pydantic_authors):
        result = benchmark(lambda: [m.model_dump_json() for m in pydantic_authors])
        assert len(result) == len(pydantic_authors)

    @pytest.mark.benchmark(group="noop-dump-json-with-rel")
    def test_transmuter_dump_json_with_rel(self, benchmark, transmuter_authors):
        result = benchmark(lambda: [m.model_dump_json() for m in transmuter_authors])
        assert len(result) == len(transmuter_authors)
