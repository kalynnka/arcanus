"""Axis A — validation: pure Pydantic (reference) vs Transmuter under NoOpMateria.

Each group pairs ``test_pydantic_*`` (baseline) with ``test_transmuter_*``; the
gap = transmuter / pydantic. Inputs are identical dicts/objects so the only
difference measured is the transmuter machinery (associations + the
``model_formulate`` wrap-validator taking its NoOp fast path).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter
from pytest_benchmark.fixture import BenchmarkFixture

from benchmark.data import mocks
from tests import schemas as S
from tests import transmuters as T


class TestValidateScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-scalar")
    def test_pydantic_validate_scalar(
        self, benchmark: BenchmarkFixture, author_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [S.Author.model_validate(d) for d in author_data])
        assert len(result) == len(author_data)

    @pytest.mark.benchmark(group="noop-validate-scalar")
    def test_transmuter_validate_scalar(
        self, benchmark: BenchmarkFixture, author_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [T.Author.model_validate(d) for d in author_data])
        assert len(result) == len(author_data)


class TestValidateScalarAdapter:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-scalar-adapter")
    def test_pydantic_validate_scalar_adapter(
        self, benchmark: BenchmarkFixture, author_data: list[dict[str, Any]]
    ):
        adapter = TypeAdapter(list[S.Author])
        result = benchmark(lambda: adapter.validate_python(author_data))
        assert len(result) == len(author_data)

    @pytest.mark.benchmark(group="noop-validate-scalar-adapter")
    def test_transmuter_validate_scalar_adapter(
        self, benchmark: BenchmarkFixture, author_data: list[dict[str, Any]]
    ):
        adapter = TypeAdapter(list[T.Author])
        result = benchmark(lambda: adapter.validate_python(author_data))
        assert len(result) == len(author_data)


class TestValidateNested:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-nested")
    def test_pydantic_validate_nested(
        self, benchmark: BenchmarkFixture, nested_book_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [S.Book.model_validate(d) for d in nested_book_data])
        assert isinstance(result[0].author, S.Author)

    @pytest.mark.benchmark(group="noop-validate-nested")
    def test_transmuter_validate_nested(
        self, benchmark: BenchmarkFixture, nested_book_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [T.Book.model_validate(d) for d in nested_book_data])
        assert isinstance(result[0].author.value, T.Author)


class TestValidateDeep:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-deep")
    def test_pydantic_validate_deep(
        self, benchmark: BenchmarkFixture, deep_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [S.Author.model_validate(d) for d in deep_data])
        assert len(result[0].books) >= 1

    @pytest.mark.benchmark(group="noop-validate-deep")
    def test_transmuter_validate_deep(
        self, benchmark: BenchmarkFixture, deep_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [T.Author.model_validate(d) for d in deep_data])
        assert len(result[0].books) >= 1


class TestValidateFromAttrsScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-from-attrs-scalar")
    def test_pydantic_validate_from_attrs_scalar(
        self,
        benchmark: BenchmarkFixture,
        mock_author_objects: list[mocks.MockAuthor],
    ):
        result = benchmark(
            lambda: [S.Author.model_validate(o) for o in mock_author_objects]
        )
        assert len(result) == len(mock_author_objects)

    @pytest.mark.benchmark(group="noop-validate-from-attrs-scalar")
    def test_transmuter_validate_from_attrs_scalar(
        self,
        benchmark: BenchmarkFixture,
        mock_author_objects: list[mocks.MockAuthor],
    ):
        result = benchmark(
            lambda: [T.Author.model_validate(o) for o in mock_author_objects]
        )
        assert len(result) == len(mock_author_objects)


class TestValidateFromAttrsNested:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-from-attrs-nested")
    def test_pydantic_validate_from_attrs_nested(
        self, benchmark: BenchmarkFixture, mock_book_objects: list[mocks.MockBook]
    ):
        result = benchmark(
            lambda: [S.Book.model_validate(o) for o in mock_book_objects]
        )
        assert isinstance(result[0].author, S.Author)

    @pytest.mark.benchmark(group="noop-validate-from-attrs-nested")
    def test_transmuter_validate_from_attrs_nested(
        self, benchmark: BenchmarkFixture, mock_book_objects: list[mocks.MockBook]
    ):
        result = benchmark(
            lambda: [T.Book.model_validate(o) for o in mock_book_objects]
        )
        assert isinstance(result[0].author.value, T.Author)


class TestValidateGraph:
    """Wide multi-relation graph (collections + scalar relation), acyclic + finite."""

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-validate-graph")
    def test_pydantic_validate_graph(
        self, benchmark: BenchmarkFixture, graph_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [S.Company.model_validate(d) for d in graph_data])
        assert len(result[0].departments) >= 1

    @pytest.mark.benchmark(group="noop-validate-graph")
    def test_transmuter_validate_graph(
        self, benchmark: BenchmarkFixture, graph_data: list[dict[str, Any]]
    ):
        result = benchmark(lambda: [T.Company.model_validate(d) for d in graph_data])
        assert len(result[0].departments) >= 1
