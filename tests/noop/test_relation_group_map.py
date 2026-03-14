"""Test RelationGroupMap association fields with NoOpMateria."""

from __future__ import annotations

import pytest

from arcanus.association import RelationGroupMap
from tests.transmuters import GroupedCatalog, GroupedTag


class TestRelationGroupMapBasics:
    """Test basic RelationGroupMap field behaviour."""

    def test_init_empty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert isinstance(catalog.tags, RelationGroupMap)
        assert len(catalog.tags) == 0

    def test_init_with_values(self):
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        t3 = GroupedTag(id=3, name="go")
        catalog = GroupedCatalog(
            id=1,
            title="Test",
            tags=RelationGroupMap({"lang": [t1, t2], "other": [t3]}),
        )
        assert isinstance(catalog.tags, RelationGroupMap)
        assert len(catalog.tags) == 2
        assert len(catalog.tags["lang"]) == 2
        assert len(catalog.tags["other"]) == 1

    def test_setitem(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags["lang"] = [t]
        assert len(catalog.tags) == 1
        assert catalog.tags["lang"][0] is t

    def test_getitem(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags["lang"] = [t]
        items = catalog.tags["lang"]
        assert len(items) == 1
        assert items[0].name == "python"

    def test_getitem_missing_raises(self):
        catalog = GroupedCatalog(id=1, title="Test")
        with pytest.raises(KeyError):
            catalog.tags["missing"]

    def test_delitem(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags["lang"] = [t]
        del catalog.tags["lang"]
        assert len(catalog.tags) == 0

    def test_delitem_missing_raises(self):
        catalog = GroupedCatalog(id=1, title="Test")
        with pytest.raises(KeyError):
            del catalog.tags["missing"]

    def test_get_present(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags["lang"] = [t]
        result = catalog.tags.get("lang")
        assert result is not None
        assert len(result) == 1

    def test_get_absent_default(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert catalog.tags.get("missing") is None
        assert catalog.tags.get("missing", []) == []


class TestRelationGroupMapAppendExtendRemove:
    """Test the convenience methods: append, extend, discard, flatten."""

    def test_append_creates_group(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags.append("lang", t)
        assert len(catalog.tags) == 1
        assert len(catalog.tags["lang"]) == 1
        assert catalog.tags["lang"][0] is t

    def test_append_to_existing_group(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        catalog.tags.append("lang", t1)
        catalog.tags.append("lang", t2)
        assert len(catalog.tags["lang"]) == 2

    def test_extend(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        catalog.tags.extend("lang", [t1, t2])
        assert len(catalog.tags["lang"]) == 2

    def test_extend_existing_group(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        t3 = GroupedTag(id=3, name="go")
        catalog.tags.append("lang", t1)
        catalog.tags.extend("lang", [t2, t3])
        assert len(catalog.tags["lang"]) == 3

    def test_discard(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        catalog.tags["lang"] = [t1, t2]
        catalog.tags.discard("lang", t1)
        assert len(catalog.tags["lang"]) == 1
        assert catalog.tags["lang"][0] is t2

    def test_discard_deletes_empty_group(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="python")
        catalog.tags["lang"] = [t]
        catalog.tags.discard("lang", t)
        assert "lang" not in catalog.tags
        assert len(catalog.tags) == 0

    def test_flatten(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="python")
        t2 = GroupedTag(id=2, name="rust")
        t3 = GroupedTag(id=3, name="go")
        catalog.tags["lang"] = [t1, t2]
        catalog.tags["other"] = [t3]
        flat = catalog.tags.flatten()
        assert len(flat) == 3
        names = {t.name for t in flat}
        assert names == {"python", "rust", "go"}

    def test_flatten_empty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert catalog.tags.flatten() == []


class TestRelationGroupMapDictOperations:
    """Test dict operations: keys, values, items, pop, popitem, update, setdefault, clear, copy."""

    def test_keys(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        catalog.tags["b"] = [GroupedTag(id=2, name="y")]
        assert set(catalog.tags.keys()) == {"a", "b"}

    def test_values(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t1]
        vals = list(catalog.tags.values())
        assert len(vals) == 1
        assert len(vals[0]) == 1

    def test_items(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t1]
        items = list(catalog.tags.items())
        assert len(items) == 1
        assert items[0][0] == "a"
        assert len(items[0][1]) == 1

    def test_pop(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t]
        result = catalog.tags.pop("a")
        assert len(result) == 1
        assert "a" not in catalog.tags

    def test_pop_missing_raises(self):
        catalog = GroupedCatalog(id=1, title="Test")
        with pytest.raises(KeyError):
            catalog.tags.pop("missing")

    def test_pop_missing_with_default(self):
        catalog = GroupedCatalog(id=1, title="Test")
        result = catalog.tags.pop("missing", [])
        assert result == []

    def test_popitem(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        key, items = catalog.tags.popitem()
        assert key == "a"
        assert len(items) == 1
        assert len(catalog.tags) == 0

    def test_update(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        catalog.tags.update({"a": [t1], "b": [t2]})
        assert len(catalog.tags) == 2
        assert len(catalog.tags["a"]) == 1
        assert len(catalog.tags["b"]) == 1

    def test_update_replaces_existing_key(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        catalog.tags["a"] = [t1]
        catalog.tags.update({"a": [t2]})
        assert len(catalog.tags["a"]) == 1
        assert catalog.tags["a"][0].name == "y"

    def test_setdefault_absent(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        result = catalog.tags.setdefault("a", [t])
        assert len(result) == 1
        assert "a" in catalog.tags

    def test_setdefault_present(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        catalog.tags["a"] = [t1]
        result = catalog.tags.setdefault("a", [t2])
        assert len(result) == 1
        assert result[0].name == "x"

    def test_setdefault_no_default(self):
        catalog = GroupedCatalog(id=1, title="Test")
        result = catalog.tags.setdefault("a")
        assert result == []
        assert "a" in catalog.tags

    def test_clear(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        catalog.tags["b"] = [GroupedTag(id=2, name="y")]
        catalog.tags.clear()
        assert len(catalog.tags) == 0

    def test_copy(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t]
        copied = catalog.tags.copy()
        assert isinstance(copied, dict)
        assert not isinstance(copied, RelationGroupMap)
        assert list(copied.keys()) == ["a"]
        assert len(copied["a"]) == 1


class TestRelationGroupMapIteration:
    """Test iteration, length, containment, bool."""

    def test_iter(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        catalog.tags["b"] = [GroupedTag(id=2, name="y")]
        keys = list(catalog.tags)
        assert set(keys) == {"a", "b"}

    def test_len(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert len(catalog.tags) == 0
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        assert len(catalog.tags) == 1

    def test_contains(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        assert "a" in catalog.tags
        assert "b" not in catalog.tags

    def test_bool_empty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert not catalog.tags

    def test_bool_nonempty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        assert catalog.tags

    def test_reversed(self):
        catalog = GroupedCatalog(id=1, title="Test")
        catalog.tags["a"] = [GroupedTag(id=1, name="x")]
        catalog.tags["b"] = [GroupedTag(id=2, name="y")]
        keys = list(reversed(catalog.tags))
        assert keys == ["b", "a"]


class TestRelationGroupMapComparisons:
    """Test equality and merge operators."""

    def test_eq_same(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t]
        assert catalog.tags == {"a": [t]}

    def test_eq_different(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t]
        assert catalog.tags != {"b": [t]}

    def test_ne(self):
        catalog = GroupedCatalog(id=1, title="Test")
        assert catalog.tags != {"a": []}

    def test_or_merge(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        catalog.tags["a"] = [t1]
        result = catalog.tags | {"b": [t2]}
        assert set(result.keys()) == {"a", "b"}
        assert isinstance(result, dict)

    def test_ior_merge(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        catalog.tags["a"] = [t1]
        tags = catalog.tags
        tags |= {"b": [t2]}
        assert len(catalog.tags) == 2


class TestRelationGroupMapSerialization:
    """Test model_dump and model_dump_json."""

    def test_model_dump(self):
        t = GroupedTag(id=1, name="x")
        catalog = GroupedCatalog(
            id=1,
            title="Test",
            tags=RelationGroupMap({"a": [t]}),
        )
        data = catalog.model_dump()
        assert "tags" in data
        assert "a" in data["tags"]
        assert len(data["tags"]["a"]) == 1
        assert data["tags"]["a"][0]["name"] == "x"

    def test_model_dump_empty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        data = catalog.model_dump()
        assert data["tags"] == {}


class TestRelationGroupMapRepr:
    """Test __repr__ and __str__."""

    def test_repr_empty(self):
        catalog = GroupedCatalog(id=1, title="Test")
        r = repr(catalog.tags)
        assert "RelationGroupMap" in r
        assert "GroupedTag" in r

    def test_str(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t = GroupedTag(id=1, name="x")
        catalog.tags["a"] = [t]
        s = str(catalog.tags)
        assert "a" in s


class TestRelationGroupMapIsolation:
    """Test that different instances don't share state."""

    def test_separate_instances(self):
        c1 = GroupedCatalog(id=1, title="A")
        c2 = GroupedCatalog(id=2, title="B")
        t = GroupedTag(id=1, name="x")
        c1.tags["a"] = [t]
        assert len(c1.tags) == 1
        assert len(c2.tags) == 0

    def test_multiple_items_same_key(self):
        catalog = GroupedCatalog(id=1, title="Test")
        t1 = GroupedTag(id=1, name="x")
        t2 = GroupedTag(id=2, name="y")
        t3 = GroupedTag(id=3, name="z")
        catalog.tags["lang"] = [t1, t2, t3]
        assert len(catalog.tags["lang"]) == 3
        names = [t.name for t in catalog.tags["lang"]]
        assert names == ["x", "y", "z"]
