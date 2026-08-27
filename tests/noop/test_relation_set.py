"""Test RelationSet association fields with NoOpMateria."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import ConfigDict, Field

from arcanus.association import RelationSet, Relationships
from arcanus.base import BaseTransmuter, Identity


class Tag(BaseTransmuter):
    """Frozen Tag model for set-based operations."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[int | None, Identity] = Field(default=None)
    name: str


class Article(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[int | None, Identity] = Field(default=None)
    title: str

    tags: RelationSet[Tag] = Relationships(unique=True)


class TestRelationSetBasics:
    """Test basic RelationSet field behaviour."""

    def test_init_empty(self):
        article = Article(id=1, title="Test")
        assert isinstance(article.tags, RelationSet)
        assert len(article.tags) == 0

    def test_init_with_values(self):
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=2, name="rust")
        article = Article(id=1, title="Test", tags=RelationSet({t1, t2}))
        assert isinstance(article.tags, RelationSet)
        assert len(article.tags) == 2

    def test_add(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        assert len(article.tags) == 1
        assert t in article.tags

    def test_discard_present(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        article.tags.discard(t)
        assert len(article.tags) == 0

    def test_discard_absent(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.discard(t)
        assert len(article.tags) == 0

    def test_remove_present(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        article.tags.remove(t)
        assert len(article.tags) == 0

    def test_remove_absent_raises(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        with pytest.raises(KeyError):
            article.tags.remove(t)

    def test_pop(self):
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        popped = article.tags.pop()
        assert popped.name == "python"
        assert len(article.tags) == 0

    def test_pop_empty_raises(self):
        article = Article(id=1, title="Test")
        with pytest.raises(KeyError):
            article.tags.pop()

    def test_clear(self):
        article = Article(id=1, title="Test")
        tags = [Tag(id=i, name=f"tag{i}") for i in range(3)]
        for t in tags:
            article.tags.add(t)
        assert len(article.tags) == 3
        article.tags.clear()
        assert len(article.tags) == 0


class TestRelationSetNoDuplicates:
    """Test that RelationSet rejects duplicates."""

    def test_add_same_object_twice(self):
        """Adding the same object twice has no effect."""
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        article.tags.add(t)
        assert len(article.tags) == 1

    def test_different_objects_same_fields_coexist(self):
        """Two distinct objects with identical field values are separate (identity-based hash)."""
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="python")
        t2 = Tag(id=1, name="python")
        assert t1 is not t2
        article.tags.add(t1)
        article.tags.add(t2)
        assert len(article.tags) == 2

    def test_update_deduplicates(self):
        """update() with repeated objects should not create duplicates."""
        article = Article(id=1, title="Test")
        t = Tag(id=1, name="python")
        article.tags.add(t)
        article.tags.update([t, t, t])
        assert len(article.tags) == 1


class TestRelationSetOperations:
    """Test set algebra operations."""

    def test_union(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])

        result = article.tags.union({t2, t3})
        assert isinstance(result, set)
        assert len(result) == 3

    def test_intersection(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])

        result = article.tags.intersection({t2, t3})
        assert isinstance(result, set)
        assert result == {t2}

    def test_difference(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])

        result = article.tags.difference({t2})
        assert isinstance(result, set)
        assert result == {t1}

    def test_symmetric_difference(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])

        result = article.tags.symmetric_difference({t2, t3})
        assert isinstance(result, set)
        assert result == {t1, t3}

    def test_or_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.add(t1)
        result = article.tags | {t2}
        assert len(result) == 2

    def test_and_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        result = article.tags & {t1}
        assert result == {t1}

    def test_sub_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        result = article.tags - {t1}
        assert result == {t2}

    def test_xor_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])
        result = article.tags ^ {t2, t3}
        assert result == {t1, t3}


class TestRelationSetInPlaceOperators:
    """Test in-place set operators."""

    def test_ior(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.add(t1)
        tags = article.tags
        tags |= {t2}
        assert len(article.tags) == 2

    def test_iand(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        tags = article.tags
        tags &= {t1}
        assert len(article.tags) == 1
        assert t1 in article.tags

    def test_isub(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        tags = article.tags
        tags -= {t1}
        assert len(article.tags) == 1
        assert t2 in article.tags

    def test_ixor(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])
        tags = article.tags
        tags ^= {t2, t3}
        assert len(article.tags) == 2
        assert t1 in article.tags
        assert t3 in article.tags

    def test_intersection_update(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2, t3])
        article.tags.intersection_update({t1, t3})
        assert len(article.tags) == 2
        assert t2 not in article.tags

    def test_difference_update(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2, t3])
        article.tags.difference_update({t1, t3})
        assert len(article.tags) == 1
        assert t2 in article.tags

    def test_symmetric_difference_update(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])
        article.tags.symmetric_difference_update({t2, t3})
        assert len(article.tags) == 2
        assert t1 in article.tags
        assert t3 in article.tags


class TestRelationSetComparisons:
    """Test set comparison operators."""

    def test_issubset(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags.issubset({t1, t2})
        assert article.tags.issubset({t1, t2, Tag(id=3, name="c")})
        assert not article.tags.issubset({t1})

    def test_issuperset(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags.issuperset({t1})
        assert article.tags.issuperset({t1, t2})
        assert not article.tags.issuperset({t1, t2, Tag(id=3, name="c")})

    def test_isdisjoint(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update([t1, t2])
        assert article.tags.isdisjoint({t3})
        assert not article.tags.isdisjoint({t1, t3})

    def test_le_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1])
        assert article.tags <= {t1, t2}
        assert article.tags <= {t1}

    def test_lt_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1])
        assert article.tags < {t1, t2}
        assert not (article.tags < {t1})

    def test_ge_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags >= {t1}
        assert article.tags >= {t1, t2}

    def test_gt_operator(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags > {t1}
        assert not (article.tags > {t1, t2})

    def test_eq(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags == {t1, t2}

    def test_ne(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])
        assert article.tags != {t1}


class TestRelationSetIteration:
    """Test iteration and membership operations."""

    def test_iter(self):
        article = Article(id=1, title="Test")
        tags = [Tag(id=i, name=f"tag{i}") for i in range(3)]
        for t in tags:
            article.tags.add(t)

        collected = set(article.tags)
        assert len(collected) == 3

    def test_contains(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.add(t1)
        assert t1 in article.tags
        assert t2 not in article.tags

    def test_len(self):
        article = Article(id=1, title="Test")
        assert len(article.tags) == 0
        article.tags.add(Tag(id=1, name="a"))
        assert len(article.tags) == 1
        article.tags.add(Tag(id=2, name="b"))
        assert len(article.tags) == 2

    def test_bool_empty(self):
        article = Article(id=1, title="Test")
        assert not bool(article.tags)

    def test_bool_nonempty(self):
        article = Article(id=1, title="Test")
        article.tags.add(Tag(id=1, name="a"))
        assert bool(article.tags)


class TestRelationSetInstanceIsolation:
    """Test that RelationSet instances are not shared between model instances."""

    def test_separate_instances_independent(self):
        a1 = Article(id=1, title="Article 1")
        a2 = Article(id=2, title="Article 2")

        t1 = Tag(id=1, name="tag1")
        t2 = Tag(id=2, name="tag2")

        a1.tags.add(t1)
        a2.tags.add(t2)

        assert len(a1.tags) == 1
        assert len(a2.tags) == 1
        assert t1 in a1.tags
        assert t2 in a2.tags
        assert t1 not in a2.tags
        assert t2 not in a1.tags

    def test_clear_one_does_not_affect_other(self):
        a1 = Article(id=1, title="Article 1")
        a2 = Article(id=2, title="Article 2")

        t = Tag(id=1, name="shared")
        a1.tags.add(t)
        a2.tags.add(t)

        a1.tags.clear()
        assert len(a1.tags) == 0
        assert len(a2.tags) == 1


class TestRelationSetSerialization:
    """Test serialization / deserialization with model_dump / model_validate."""

    def test_model_dump_empty(self):
        article = Article(id=1, title="Test")
        data = article.model_dump()
        assert data["tags"] == []

    def test_model_dump_with_items(self):
        article = Article(id=1, title="Test")
        article.tags.add(Tag(id=1, name="python"))
        article.tags.add(Tag(id=2, name="rust"))

        data = article.model_dump()
        assert isinstance(data["tags"], list)
        names = {t["name"] for t in data["tags"]}
        assert names == {"python", "rust"}

    def test_model_validate_with_set_input(self):
        article_data = {
            "id": 1,
            "title": "Test",
            "tags": [
                {"id": 1, "name": "python"},
                {"id": 2, "name": "rust"},
            ],
        }
        article = Article.model_validate(article_data)
        assert isinstance(article.tags, RelationSet)
        assert len(article.tags) == 2
        names = {t.name for t in article.tags}
        assert names == {"python", "rust"}

    def test_isinstance_check(self):
        article = Article(id=1, title="Test")
        assert isinstance(article.tags, RelationSet)


class TestRelationSetCopy:
    """Test copy operations."""

    def test_copy_returns_plain_set(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        article.tags.update([t1, t2])

        result = article.tags.copy()
        assert isinstance(result, set)
        assert not isinstance(result, RelationSet)
        assert len(result) == 2

    def test_repr(self):
        article = Article(id=1, title="Test")
        r = repr(article.tags)
        assert "RelationSet" in r
        assert "Tag" in r

    def test_repr_unprepared(self):
        """repr() must not raise AttributeError when __args__ is not yet set."""
        rs = RelationSet()
        r = repr(rs)
        assert "RelationSet" in r
        assert "?" in r


class TestRelationSetEdgeCases:
    """Test edge cases."""

    def test_empty_set_operations(self):
        article = Article(id=1, title="Test")

        assert len(article.tags) == 0
        assert list(article.tags) == []
        assert article.tags.copy() == set()

    def test_multiple_relation_sets_on_same_model(self):
        """Each RelationSet field should be independent."""

        class MultiArticle(BaseTransmuter):
            model_config = ConfigDict(from_attributes=True)

            id: Annotated[int | None, Identity] = Field(default=None, frozen=True)
            title: str
            tags: RelationSet[Tag] = Relationships(unique=True)
            labels: RelationSet[Tag] = Relationships(unique=True)

        art = MultiArticle(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")

        art.tags.add(t1)
        art.labels.add(t2)

        assert len(art.tags) == 1
        assert len(art.labels) == 1
        assert t1 in art.tags
        assert t2 in art.labels
        assert t1 not in art.labels
        assert t2 not in art.tags

    def test_update_with_multiple_iterables(self):
        article = Article(id=1, title="Test")
        t1 = Tag(id=1, name="a")
        t2 = Tag(id=2, name="b")
        t3 = Tag(id=3, name="c")
        article.tags.update({t1}, {t2, t3})
        assert len(article.tags) == 3

    def test_str(self):
        article = Article(id=1, title="Test")
        s = str(article.tags)
        assert isinstance(s, str)
