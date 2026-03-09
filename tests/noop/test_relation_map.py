"""Test RelationMap association fields with NoOpMateria."""

from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import ConfigDict, Field, ValidationError

from arcanus.association import RelationMap, RelationMaps
from arcanus.base import BaseTransmuter, Identity
from tests.transmuters import Catalog, LabeledCatalog, Tag


class TestRelationMapBasics:
    """Test basic RelationMap field behaviour."""

    def test_init_empty(self):
        catalog = Catalog(id=1, title="Test")
        assert isinstance(catalog.tags, RelationMap)
        assert len(catalog.tags) == 0

    def test_init_with_values(self):
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog = Catalog(id=1, title="Test", tags=RelationMap({"py": t1, "rs": t2}))
        assert isinstance(catalog.tags, RelationMap)
        assert len(catalog.tags) == 2

    def test_setitem(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        catalog.tags["py"] = t
        assert len(catalog.tags) == 1
        assert catalog.tags["py"] is t

    def test_getitem(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        catalog.tags["py"] = t
        assert catalog.tags["py"].name == "python"

    def test_getitem_missing_raises(self):
        catalog = Catalog(id=1, title="Test")
        with pytest.raises(KeyError):
            catalog.tags["missing"]

    def test_delitem(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        catalog.tags["py"] = t
        del catalog.tags["py"]
        assert len(catalog.tags) == 0

    def test_delitem_missing_raises(self):
        catalog = Catalog(id=1, title="Test")
        with pytest.raises(KeyError):
            del catalog.tags["missing"]

    def test_get_present(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        catalog.tags["py"] = t
        assert catalog.tags.get("py") is t

    def test_get_absent_returns_default(self):
        catalog = Catalog(id=1, title="Test")
        assert catalog.tags.get("missing") is None
        sentinel = Tag(id=99, name="default")
        assert catalog.tags.get("missing", sentinel) is sentinel

    def test_pop_present(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        catalog.tags["py"] = t
        popped = catalog.tags.pop("py")
        assert popped.name == "python"
        assert len(catalog.tags) == 0

    def test_pop_absent_raises(self):
        catalog = Catalog(id=1, title="Test")
        with pytest.raises(KeyError):
            catalog.tags.pop("missing")

    def test_pop_absent_with_default(self):
        catalog = Catalog(id=1, title="Test")
        sentinel = Tag(id=99, name="default")
        result = catalog.tags.pop("missing", sentinel)
        assert result is sentinel

    def test_popitem(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["py"] = Tag(id=1, name="python")
        key, val = catalog.tags.popitem()
        assert key == "py"
        assert val.name == "python"
        assert len(catalog.tags) == 0

    def test_popitem_empty_raises(self):
        catalog = Catalog(id=1, title="Test")
        with pytest.raises(KeyError):
            catalog.tags.popitem()

    def test_clear(self):
        catalog = Catalog(id=1, title="Test")
        for i in range(3):
            catalog.tags[f"t{i}"] = Tag(id=i, name=f"tag{i}")
        assert len(catalog.tags) == 3
        catalog.tags.clear()
        assert len(catalog.tags) == 0

    def test_setdefault_absent(self):
        catalog = Catalog(id=1, title="Test")
        t = Tag(id=1, name="python")
        result = catalog.tags.setdefault("py", t)
        assert result is t
        assert catalog.tags["py"] is t

    def test_setdefault_present(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        result = catalog.tags.setdefault("py", t2)
        assert result is t1


class TestRelationMapUpdate:
    """Test update operations."""

    def test_update_with_dict(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags.update({"py": t1, "rs": t2})
        assert len(catalog.tags) == 2
        assert catalog.tags["py"].name == "python"
        assert catalog.tags["rs"].name == "rust"

    def test_update_with_kwargs(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        catalog.tags.update(py=t1)
        assert catalog.tags["py"].name == "python"

    def test_update_overwrites(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="python3")
        catalog.tags["py"] = t1
        catalog.tags.update({"py": t2})
        assert catalog.tags["py"] is t2


class TestRelationMapKeysValuesItems:
    """Test keys(), values(), items() views."""

    def test_keys(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["py"] = Tag(id=1, name="python")
        catalog.tags["rs"] = Tag(id=2, name="rust")
        assert set(catalog.tags.keys()) == {"py", "rs"}

    def test_values(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        catalog.tags["rs"] = t2
        vals = list(catalog.tags.values())
        assert len(vals) == 2
        assert t1 in vals
        assert t2 in vals

    def test_items(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        catalog.tags["py"] = t1
        items = list(catalog.tags.items())
        assert items == [("py", t1)]


class TestRelationMapComparisons:
    """Test equality and comparison operations."""

    def test_eq_same_content(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        catalog.tags["py"] = t1
        assert catalog.tags == {"py": t1}

    def test_ne_different_content(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        assert catalog.tags != {"rs": t2}

    def test_eq_empty(self):
        catalog = Catalog(id=1, title="Test")
        assert catalog.tags == {}

    def test_ne_non_dict(self):
        catalog = Catalog(id=1, title="Test")
        assert catalog.tags != [1, 2, 3]
        assert catalog.tags != "hello"

    def test_eq_two_relation_maps(self):
        c1 = Catalog(id=1, title="A")
        c2 = Catalog(id=2, title="B")
        t = Tag(id=1, name="python")
        c1.tags["py"] = t
        c2.tags["py"] = t
        assert c1.tags == c2.tags


class TestRelationMapIteration:
    """Test iteration and membership operations."""

    def test_iter_yields_keys(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["py"] = Tag(id=1, name="python")
        catalog.tags["rs"] = Tag(id=2, name="rust")

        collected = list(catalog.tags)
        assert set(collected) == {"py", "rs"}

    def test_contains_key(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["py"] = Tag(id=1, name="python")
        assert "py" in catalog.tags
        assert "rs" not in catalog.tags

    def test_len(self):
        catalog = Catalog(id=1, title="Test")
        assert len(catalog.tags) == 0
        catalog.tags["py"] = Tag(id=1, name="python")
        assert len(catalog.tags) == 1
        catalog.tags["rs"] = Tag(id=2, name="rust")
        assert len(catalog.tags) == 2

    def test_bool_empty(self):
        catalog = Catalog(id=1, title="Test")
        assert not bool(catalog.tags)

    def test_bool_nonempty(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["py"] = Tag(id=1, name="python")
        assert bool(catalog.tags)

    def test_reversed(self):
        catalog = Catalog(id=1, title="Test")
        catalog.tags["a"] = Tag(id=1, name="alpha")
        catalog.tags["b"] = Tag(id=2, name="beta")
        catalog.tags["c"] = Tag(id=3, name="gamma")
        keys = list(reversed(catalog.tags))
        assert keys == ["c", "b", "a"]


class TestRelationMapInstanceIsolation:
    """Test that RelationMap instances are not shared between model instances."""

    def test_separate_instances_independent(self):
        c1 = Catalog(id=1, title="Catalog 1")
        c2 = Catalog(id=2, title="Catalog 2")

        t1 = Tag(id=1, name="tag1")
        t2 = Tag(id=2, name="tag2")

        c1.tags["a"] = t1
        c2.tags["b"] = t2

        assert len(c1.tags) == 1
        assert len(c2.tags) == 1
        assert "a" in c1.tags
        assert "b" in c2.tags
        assert "a" not in c2.tags
        assert "b" not in c1.tags

    def test_clear_one_does_not_affect_other(self):
        c1 = Catalog(id=1, title="Catalog 1")
        c2 = Catalog(id=2, title="Catalog 2")

        t = Tag(id=1, name="shared")
        c1.tags["x"] = t
        c2.tags["x"] = t

        c1.tags.clear()
        assert len(c1.tags) == 0
        assert len(c2.tags) == 1


class TestRelationMapSerialization:
    """Test serialization / deserialization with model_dump / model_validate."""

    def test_model_dump_empty(self):
        catalog = Catalog(id=1, title="Test")
        data = catalog.model_dump()
        assert data["tags"] == {}

    def test_model_dump_with_items(self):
        catalog = Catalog(
            id=1,
            title="Test",
            tags=RelationMap(
                {
                    "py": Tag(id=1, name="python"),
                    "rs": Tag(id=2, name="rust"),
                }
            ),
        )

        data = catalog.model_dump()
        assert isinstance(data["tags"], dict)
        assert set(data["tags"].keys()) == {"py", "rs"}
        assert data["tags"]["py"]["name"] == "python"
        assert data["tags"]["rs"]["name"] == "rust"

    def test_model_validate_with_dict_input(self):
        catalog_data = {
            "id": 1,
            "title": "Test",
            "tags": {
                "py": {"id": 1, "name": "python"},
                "rs": {"id": 2, "name": "rust"},
            },
        }
        catalog = Catalog.model_validate(catalog_data)
        assert isinstance(catalog.tags, RelationMap)
        assert len(catalog.tags) == 2
        assert catalog.tags["py"].name == "python"
        assert catalog.tags["rs"].name == "rust"

    def test_isinstance_check(self):
        catalog = Catalog(id=1, title="Test")
        assert isinstance(catalog.tags, RelationMap)


class TestRelationMapMergeOperators:
    """Test | and |= operators."""

    def test_or_operator(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        result = catalog.tags | {"rs": t2}
        assert isinstance(result, dict)
        assert len(result) == 2
        assert result["py"] is t1
        assert result["rs"] is t2

    def test_ior_operator(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        tags = catalog.tags
        tags |= {"rs": t2}
        assert len(catalog.tags) == 2
        assert "rs" in catalog.tags

    def test_or_does_not_mutate_original(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        _ = catalog.tags | {"rs": t2}
        assert len(catalog.tags) == 1


class TestRelationMapCopy:
    """Test copy operations."""

    def test_copy_returns_plain_dict(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        catalog.tags["py"] = t1
        catalog.tags["rs"] = t2

        result = catalog.tags.copy()
        assert isinstance(result, dict)
        assert not isinstance(result, RelationMap)
        assert len(result) == 2

    def test_repr(self):
        catalog = Catalog(id=1, title="Test")
        r = repr(catalog.tags)
        assert "RelationMap" in r
        assert "Tag" in r

    def test_repr_unprepared(self):
        """repr() must not raise AttributeError when __args__ is not yet set."""
        rm = RelationMap()
        r = repr(rm)
        assert "RelationMap" in r
        assert "?" in r


class TestRelationMapEdgeCases:
    """Test edge cases."""

    def test_empty_map_operations(self):
        catalog = Catalog(id=1, title="Test")

        assert len(catalog.tags) == 0
        assert list(catalog.tags) == []
        assert catalog.tags.copy() == {}

    def test_multiple_relation_maps_on_same_model(self):
        """Each RelationMap field should be independent."""

        class MultiCatalog(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
            title: str
            tags: RelationMap[str, Tag] = RelationMaps()
            labels: RelationMap[str, Tag] = RelationMaps()

        cat = MultiCatalog(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")

        cat.tags["x"] = t1
        cat.labels["y"] = t2

        assert len(cat.tags) == 1
        assert len(cat.labels) == 1
        assert "x" in cat.tags
        assert "y" in cat.labels
        assert "x" not in cat.labels
        assert "y" not in cat.tags

    def test_overwrite_existing_key(self):
        catalog = Catalog(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="python3")
        catalog.tags["py"] = t1
        catalog.tags["py"] = t2
        assert len(catalog.tags) == 1
        assert catalog.tags["py"] is t2

    def test_str(self):
        catalog = Catalog(id=1, title="Test")
        s = str(catalog.tags)
        assert isinstance(s, str)


class TestRelationMapLiteralKeys:
    """Test RelationMap with Literal key type to verify key blessing."""

    def test_valid_literal_key_setitem(self):
        cat = LabeledCatalog(id=1, title="Test")
        t = Tag(id=1, name="py")
        cat.tags["python"] = t
        assert cat.tags["python"] is t

    def test_invalid_literal_key_setitem_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        t = Tag(id=1, name="x")
        with pytest.raises(ValidationError):
            cat.tags["java"] = t  # type: ignore[index]

    def test_valid_literal_key_getitem(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["rust"] = Tag(id=1, name="rs")
        assert cat.tags["rust"].name == "rs"

    def test_invalid_literal_key_getitem_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            cat.tags["java"]  # type: ignore[index]

    def test_valid_literal_key_contains(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["go"] = Tag(id=1, name="g")
        assert "go" in cat.tags

    def test_invalid_literal_key_contains_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            "java" in cat.tags  # type: ignore[operator]

    def test_valid_literal_key_delitem(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["python"] = Tag(id=1, name="py")
        del cat.tags["python"]
        assert len(cat.tags) == 0

    def test_invalid_literal_key_delitem_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            del cat.tags["java"]  # type: ignore[arg-type]

    def test_valid_literal_key_get(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["rust"] = Tag(id=1, name="rs")
        assert cat.tags["rust"].name == "rs"
        assert cat.tags.get("python") is None

    def test_invalid_literal_key_get_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            cat.tags.get("java")  # type: ignore[arg-type]

    def test_valid_literal_key_pop(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["go"] = Tag(id=1, name="g")
        popped = cat.tags.pop("go")
        assert popped.name == "g"
        assert len(cat.tags) == 0

    def test_invalid_literal_key_pop_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            cat.tags.pop("java")  # type: ignore[arg-type]

    def test_valid_literal_key_setdefault(self):
        cat = LabeledCatalog(id=1, title="Test")
        t = Tag(id=1, name="py")
        result = cat.tags.setdefault("python", t)
        assert result is t
        assert cat.tags["python"] is t

    def test_invalid_literal_key_setdefault_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        t = Tag(id=1, name="x")
        with pytest.raises(ValidationError):
            cat.tags.setdefault("java", t)  # type: ignore[arg-type]

    def test_all_valid_keys(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags["python"] = Tag(id=1, name="py")
        cat.tags["rust"] = Tag(id=2, name="rs")
        cat.tags["go"] = Tag(id=3, name="g")
        assert len(cat.tags) == 3
        assert set(cat.tags.keys()) == {"python", "rust", "go"}

    def test_update_with_valid_keys(self):
        cat = LabeledCatalog(id=1, title="Test")
        cat.tags.update({"python": Tag(id=1, name="py"), "rust": Tag(id=2, name="rs")})
        assert len(cat.tags) == 2

    def test_update_with_invalid_key_raises(self):
        cat = LabeledCatalog(id=1, title="Test")
        with pytest.raises(ValidationError):
            cat.tags.update({"java": Tag(id=1, name="j")})  # type: ignore[dict-item]

    def test_init_with_valid_keys(self):
        t = Tag(id=1, name="py")
        cat = LabeledCatalog(
            id=1,
            title="Test",
            tags=RelationMap({"python": t}),
        )
        assert len(cat.tags) == 1
        assert cat.tags["python"] is t

    def test_init_with_invalid_key_raises(self):
        t = Tag(id=1, name="x")
        with pytest.raises(ValidationError):
            LabeledCatalog(
                id=1,
                title="Test",
                tags={"java": t},  # type: ignore[dict-item]
            )

    def test_model_validate_with_valid_keys(self):
        data = {
            "id": 1,
            "title": "Test",
            "tags": {"python": {"id": 1, "name": "py"}},
        }
        cat = LabeledCatalog.model_validate(data)
        assert len(cat.tags) == 1
        assert cat.tags["python"].name == "py"

    def test_model_validate_with_invalid_key_raises(self):
        data = {
            "id": 1,
            "title": "Test",
            "tags": {"java": {"id": 1, "name": "j"}},
        }
        with pytest.raises(ValidationError):
            LabeledCatalog.model_validate(data)
