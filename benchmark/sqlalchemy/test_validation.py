"""Provider conversion cost, excluding SQL and ORM object construction.

Each timed batch receives fresh providers so neither weak proxies nor the
validation context can turn a cold conversion into an identity-cache hit.
"""

from __future__ import annotations

from typing import Never

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from arcanus.base import validation_context
from arcanus.materia.sqlalchemy import SqlalchemyMateria
from tests import models, schemas, transmuters

provider_materia = SqlalchemyMateria()


@provider_materia.bless(models.Author)
class ProviderAuthor(transmuters.AuthorFlat):
    pass


def provider_batch() -> tuple[tuple[list[models.Author]], dict[str, Never]]:
    providers = [
        models.Author(id=i, name=f"Author {i}", field="Physics") for i in range(100)
    ]
    return (providers,), {}


@pytest.mark.baseline
@pytest.mark.benchmark(group="validate-provider-cold")
def test_pydantic_sqlalchemy_validate_provider_cold(benchmark: BenchmarkFixture):
    def validate(providers: list[models.Author]) -> list[schemas.AuthorFlat]:
        return [schemas.AuthorFlat.model_validate(provider) for provider in providers]

    result = benchmark.pedantic(
        validate, setup=provider_batch, rounds=100, iterations=1
    )
    assert len(result) == 100
    assert result[0].name == "Author 0"


@pytest.mark.benchmark(group="validate-provider-cold")
def test_arcanus_validate_provider_cold(benchmark: BenchmarkFixture):
    def validate(providers: list[models.Author]) -> list[ProviderAuthor]:
        with provider_materia, validation_context():
            return [ProviderAuthor.model_validate(provider) for provider in providers]

    result = benchmark.pedantic(
        validate, setup=provider_batch, rounds=100, iterations=1
    )
    assert len(result) == 100
    assert result[0].name == "Author 0"
    assert isinstance(result[0].__transmuter_provided__, models.Author)


@pytest.mark.baseline
@pytest.mark.benchmark(group="construct-provider-cold")
def test_pydantic_sqlalchemy_construct_provider_cold(benchmark: BenchmarkFixture):
    def construct(providers: list[models.Author]) -> list[schemas.AuthorFlat]:
        return [
            schemas.AuthorFlat.model_construct(**provider.__dict__)
            for provider in providers
        ]

    result = benchmark.pedantic(
        construct, setup=provider_batch, rounds=100, iterations=1
    )
    assert len(result) == 100
    assert result[0].name == "Author 0"


@pytest.mark.benchmark(group="construct-provider-cold")
def test_arcanus_construct_provider_cold(benchmark: BenchmarkFixture):
    def construct(providers: list[models.Author]) -> list[ProviderAuthor]:
        with provider_materia, validation_context():
            return [
                ProviderAuthor.model_construct(data=provider) for provider in providers
            ]

    result = benchmark.pedantic(
        construct, setup=provider_batch, rounds=100, iterations=1
    )
    assert len(result) == 100
    assert result[0].name == "Author 0"
    assert isinstance(result[0].__transmuter_provided__, models.Author)
