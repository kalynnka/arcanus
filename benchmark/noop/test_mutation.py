"""Axis A — in-memory mutation: collection ops, group-map ops, partial update.

No backend is involved (NoOpMateria); this isolates the overhead the association
wrappers add to plain list/dict mutation and to the ``absorb`` partial-update
path versus a hand-written validate-then-setattr loop.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from benchmark.data import ref_schemas as R
from tests import schemas as S
from tests import transmuters as T


class TestMutateCollection:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-mutation-collection")
    def test_pydantic_mutate_collection(
        self, benchmark: BenchmarkFixture, nested_book_data: list[dict[str, Any]]
    ):
        author = S.Author(id=1, name="Mutator", field="Physics")
        books = [S.Book.model_validate(d) for d in nested_book_data]
        extra = S.Book.model_validate(nested_book_data[0])

        def mutate() -> None:
            author.books.clear()
            author.books.extend(books)
            author.books.append(extra)
            author.books.remove(extra)

        benchmark(mutate)
        assert len(author.books) == len(books)

    @pytest.mark.benchmark(group="noop-mutation-collection")
    def test_transmuter_mutate_collection(
        self, benchmark: BenchmarkFixture, nested_book_data: list[dict[str, Any]]
    ):
        author = T.Author(id=1, name="Mutator", field="Physics")
        books = [T.Book.model_validate(d) for d in nested_book_data]
        extra = T.Book.model_validate(nested_book_data[0])

        def mutate() -> None:
            author.books.clear()
            author.books.extend(books)
            author.books.append(extra)
            author.books.remove(extra)

        benchmark(mutate)
        assert len(author.books) == len(books)


class TestMutateGroupMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-mutation-groupmap")
    def test_pydantic_mutate_groupmap(
        self, benchmark: BenchmarkFixture, grouped_catalog_data: list[dict[str, Any]]
    ):
        catalog = R.GroupedCatalogRef(id=1, title="Mutator")
        groups = {
            key: [R.TagRef.model_validate(t) for t in tags]
            for key, tags in grouped_catalog_data[0]["tags"].items()
        }

        def mutate() -> None:
            catalog.tags.clear()
            for key, tags in groups.items():
                catalog.tags[key] = tags

        benchmark(mutate)
        assert len(catalog.tags) == len(groups)

    @pytest.mark.benchmark(group="noop-mutation-groupmap")
    def test_transmuter_mutate_groupmap(
        self, benchmark: BenchmarkFixture, grouped_catalog_data: list[dict[str, Any]]
    ):
        catalog = T.GroupedCatalog(id=1, title="Mutator")
        groups = {
            key: [T.GroupedTag.model_validate(t) for t in tags]
            for key, tags in grouped_catalog_data[0]["tags"].items()
        }

        def mutate() -> None:
            catalog.tags.clear()
            for key, tags in groups.items():
                catalog.tags[key] = tags

        benchmark(mutate)
        assert len(catalog.tags) == len(groups)


class TestAbsorbUpdate:
    UPDATE: ClassVar[dict[str, str]] = {"name": "Updated Name", "field": "Biology"}

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-absorb-update")
    def test_pydantic_apply_update(self, benchmark: BenchmarkFixture):
        author = S.AuthorFlat(id=1, name="Original", field="Physics")

        def apply() -> None:
            partial = R.AuthorUpdateRef.model_validate(self.UPDATE)
            for key, value in partial.model_dump(exclude_unset=True).items():
                setattr(author, key, value)

        benchmark(apply)
        assert author.name == "Updated Name"

    @pytest.mark.benchmark(group="noop-absorb-update")
    def test_transmuter_absorb(self, benchmark: BenchmarkFixture):
        author = T.AuthorFlat(id=1, name="Original", field="Physics")

        def absorb() -> None:
            author.absorb(T.AuthorFlat.Update(**self.UPDATE))

        benchmark(absorb)
        assert author.name == "Updated Name"
