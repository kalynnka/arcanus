"""Axis A (NoOpMateria) data + pre-validated object fixtures.

Raw dict/mocks payloads feed the validation benchmarks; pre-validated
model/transmuter objects feed the serialization benchmarks (so dump cost is
isolated from validation cost). Everything is session-scoped and built while the
default NoOpMateria is active. Imported by ``benchmark/noop/conftest.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from benchmark.data import builders, mocks
from tests import schemas as S
from tests import transmuters as T

N_SCALAR = 100
N_NESTED = 50
DEEP_AUTHORS = 10
DEEP_BOOKS = 10
N_SHAPE = 50
N_GRAPH = 10


@pytest.fixture(scope="session")
def author_data() -> list[dict[str, Any]]:
    return builders.author_dicts(N_SCALAR)


@pytest.fixture(scope="session")
def nested_book_data() -> list[dict[str, Any]]:
    return builders.nested_book_dicts(N_NESTED)


@pytest.fixture(scope="session")
def deep_data() -> list[dict[str, Any]]:
    return builders.deep_author_dicts(DEEP_AUTHORS, DEEP_BOOKS)


@pytest.fixture(scope="session")
def graph_data() -> list[dict[str, Any]]:
    return builders.graph_company_dicts(N_GRAPH)


@pytest.fixture(scope="session")
def catalog_data() -> list[dict[str, Any]]:
    return builders.catalog_dicts(N_SHAPE)


@pytest.fixture(scope="session")
def grouped_catalog_data() -> list[dict[str, Any]]:
    return builders.grouped_catalog_dicts(N_SHAPE)


@pytest.fixture(scope="session")
def gallery_data() -> list[dict[str, Any]]:
    return builders.gallery_dicts(N_SHAPE)


@pytest.fixture(scope="session")
def image_media_data() -> list[dict[str, Any]]:
    return builders.image_media_dicts(N_SCALAR)


@pytest.fixture(scope="session")
def mock_author_objects() -> list[mocks.MockAuthor]:
    return mocks.mock_authors(N_SCALAR)


@pytest.fixture(scope="session")
def mock_book_objects() -> list[mocks.MockBook]:
    return mocks.mock_books(N_SCALAR)


@pytest.fixture(scope="session")
def pydantic_flat_authors(author_data: list[dict[str, Any]]) -> list[S.AuthorFlat]:
    return [S.AuthorFlat.model_validate(d) for d in author_data]


@pytest.fixture(scope="session")
def transmuter_flat_authors(author_data: list[dict[str, Any]]) -> list[T.AuthorFlat]:
    return [T.AuthorFlat.model_validate(d) for d in author_data]


@pytest.fixture(scope="session")
def pydantic_authors(deep_data: list[dict[str, Any]]) -> list[S.Author]:
    return [S.Author.model_validate(d) for d in deep_data]


@pytest.fixture(scope="session")
def transmuter_authors(deep_data: list[dict[str, Any]]) -> list[T.Author]:
    return [T.Author.model_validate(d) for d in deep_data]
