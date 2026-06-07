"""Axis A — relationship shapes the basic groups don't cover.

RelationMap (dict), RelationGroupMap (dict-of-lists), TypedRelationMap (typed
keys) and a polymorphic subtype, each vs the closest pure-Pydantic structure.
Measures validation cost of the map-like / polymorphic association machinery.
"""

from __future__ import annotations

import pytest

from benchmark.data import ref_schemas as R
from tests import transmuters as T


class TestShapeRelMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-shape-relmap")
    def test_pydantic_relmap(self, benchmark, catalog_data):
        result = benchmark(
            lambda: [R.CatalogRef.model_validate(d) for d in catalog_data]
        )
        assert len(result[0].tags) >= 1

    @pytest.mark.benchmark(group="noop-shape-relmap")
    def test_transmuter_relmap(self, benchmark, catalog_data):
        result = benchmark(lambda: [T.Catalog.model_validate(d) for d in catalog_data])
        assert len(result[0].tags) >= 1


class TestShapeGroupMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-shape-groupmap")
    def test_pydantic_groupmap(self, benchmark, grouped_catalog_data):
        result = benchmark(
            lambda: [
                R.GroupedCatalogRef.model_validate(d) for d in grouped_catalog_data
            ]
        )
        assert len(result[0].tags) >= 1

    @pytest.mark.benchmark(group="noop-shape-groupmap")
    def test_transmuter_groupmap(self, benchmark, grouped_catalog_data):
        result = benchmark(
            lambda: [T.GroupedCatalog.model_validate(d) for d in grouped_catalog_data]
        )
        assert len(result[0].tags) >= 1


class TestShapeTypedMap:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-shape-typedmap")
    def test_pydantic_typedmap(self, benchmark, gallery_data):
        result = benchmark(
            lambda: [R.GalleryRef.model_validate(d) for d in gallery_data]
        )
        assert result[0].media["image"].name

    @pytest.mark.benchmark(group="noop-shape-typedmap")
    def test_transmuter_typedmap(self, benchmark, gallery_data):
        result = benchmark(lambda: [T.Gallery.model_validate(d) for d in gallery_data])
        assert result[0].media["image"].name


class TestShapePolymorphic:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="noop-shape-polymorphic")
    def test_pydantic_polymorphic(self, benchmark, image_media_data):
        result = benchmark(
            lambda: [R.ImageMediaRef.model_validate(d) for d in image_media_data]
        )
        assert result[0].media_type == "image"

    @pytest.mark.benchmark(group="noop-shape-polymorphic")
    def test_transmuter_polymorphic(self, benchmark, image_media_data):
        result = benchmark(
            lambda: [T.ImageMedia.model_validate(d) for d in image_media_data]
        )
        assert result[0].media_type == "image"
