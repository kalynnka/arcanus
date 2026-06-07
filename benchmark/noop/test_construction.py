"""Axis A — construction via the ``Model(**kwargs)`` init path (not model_validate).

Exercises the constructor entry point rather than the classmethod validate path,
which can differ in overhead for transmuters. Pure Pydantic (reference) vs
Transmuter under NoOpMateria.
"""

from __future__ import annotations

import pytest

from tests import schemas as S
from tests import transmuters as T


class TestConstructScalar:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-construct-scalar")
    def test_pydantic_construct_scalar(self, benchmark, author_data):
        result = benchmark(lambda: [S.AuthorFlat(**d) for d in author_data])
        assert len(result) == len(author_data)

    @pytest.mark.benchmark(group="noop-construct-scalar")
    def test_transmuter_construct_scalar(self, benchmark, author_data):
        result = benchmark(lambda: [T.AuthorFlat(**d) for d in author_data])
        assert len(result) == len(author_data)


class TestConstructNested:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-construct-nested")
    def test_pydantic_construct_nested(self, benchmark, nested_book_data):
        result = benchmark(lambda: [S.Book(**d) for d in nested_book_data])
        assert isinstance(result[0].author, S.Author)

    @pytest.mark.benchmark(group="noop-construct-nested")
    def test_transmuter_construct_nested(self, benchmark, nested_book_data):
        result = benchmark(lambda: [T.Book(**d) for d in nested_book_data])
        assert isinstance(result[0].author.value, T.Author)
