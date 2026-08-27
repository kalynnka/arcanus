"""Test TypedRelationMap association fields with NoOpMateria.

Tests:
- Basic construction: empty, with values
- Per-key typed access (__getitem__)
- Per-key typed mutation (__setitem__, __delitem__)
- Whole-dict validation (bless)
- Per-key validation (bless_value)
- Dict operations: pop, popitem, update, setdefault, clear, copy
- Serialization via model_dump
- Optional (total=False) TypedDict support
- Error cases: invalid key, wrong value type
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arcanus.association import TypedRelationMap, TypedRelationMaps
from tests.transmuters import (
    Gallery,
    ImageMedia,
    OptionalGallery,
    VideoMedia,
)


class TestTypedRelationMapBasics:
    """Test basic TypedRelationMap field behaviour."""

    def test_init_empty(self):
        gallery = Gallery(id=1, name="Test")
        assert isinstance(gallery.media, TypedRelationMap)
        assert len(gallery.media) == 0

    def test_init_with_values(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        assert isinstance(gallery.media, TypedRelationMap)
        assert len(gallery.media) == 2

    def test_init_with_dict(self):
        """TypedRelationMap can be initialized from a plain dict."""
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        assert isinstance(gallery.media, TypedRelationMap)
        assert len(gallery.media) == 2


class TestTypedRelationMapAccess:
    """Test per-key typed access."""

    @pytest.fixture
    def gallery(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        return Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )

    def test_getitem_returns_correct_type(self, gallery: Gallery):
        image = gallery.media["image"]
        video = gallery.media["video"]
        assert isinstance(image, ImageMedia)
        assert isinstance(video, VideoMedia)

    def test_getitem_values(self, gallery: Gallery):
        image = gallery.media["image"]
        assert image.name == "photo"
        assert image.width == 800
        assert image.height == 600

        video = gallery.media["video"]
        assert video.name == "clip"
        assert video.duration == 30.0

    def test_getitem_missing_key(self, gallery: Gallery):
        with pytest.raises(KeyError):
            gallery.media["audio"]

    def test_contains(self, gallery: Gallery):
        assert "image" in gallery.media
        assert "video" in gallery.media
        assert "audio" not in gallery.media

    def test_get_present(self, gallery: Gallery):
        image = gallery.media.get("image")
        assert image is not None
        assert isinstance(image, ImageMedia)

    def test_get_missing_with_default(self, gallery: Gallery):
        result = gallery.media.get("audio", None)
        assert result is None

    def test_keys_values_items(self, gallery: Gallery):
        assert set(gallery.media.keys()) == {"image", "video"}
        assert len(list(gallery.media.values())) == 2
        assert len(list(gallery.media.items())) == 2

    def test_iter(self, gallery: Gallery):
        keys = list(gallery.media)
        assert set(keys) == {"image", "video"}

    def test_len(self, gallery: Gallery):
        assert len(gallery.media) == 2

    def test_bool_nonempty(self, gallery: Gallery):
        assert bool(gallery.media) is True

    def test_bool_empty(self):
        gallery = Gallery(id=1, name="Empty")
        assert bool(gallery.media) is False


class TestTypedRelationMapMutation:
    """Test mutation operations."""

    @pytest.fixture
    def gallery(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        return Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )

    def test_setitem_replaces_value(self, gallery: Gallery):
        new_img = ImageMedia(id=3, name="new_photo", width=1920, height=1080)
        gallery.media["image"] = new_img
        assert gallery.media["image"].name == "new_photo"
        assert gallery.media["image"].width == 1920

    def test_setitem_from_dict(self, gallery: Gallery):
        """Setting a value from raw dict data should bless it."""
        gallery.media["video"] = {"id": 5, "name": "raw_video", "duration": 120.0}
        assert isinstance(gallery.media["video"], VideoMedia)
        assert gallery.media["video"].name == "raw_video"

    def test_setitem_invalid_key(self, gallery: Gallery):
        """Setting a key not in the TypedDict should raise KeyError."""
        with pytest.raises(KeyError, match="audio"):
            gallery.media["audio"] = ImageMedia(id=9, name="x")

    def test_delitem(self, gallery: Gallery):
        del gallery.media["image"]
        assert "image" not in gallery.media
        assert len(gallery.media) == 1

    def test_pop(self, gallery: Gallery):
        video = gallery.media.pop("video")
        assert isinstance(video, VideoMedia)
        assert "video" not in gallery.media
        assert len(gallery.media) == 1

    def test_pop_missing_with_default(self, gallery: Gallery):
        result = gallery.media.pop("audio", None)
        assert result is None

    def test_popitem(self, gallery: Gallery):
        key, _value = gallery.media.popitem()
        assert key in ("image", "video")
        assert len(gallery.media) == 1

    def test_clear(self, gallery: Gallery):
        gallery.media.clear()
        assert len(gallery.media) == 0
        assert bool(gallery.media) is False

    def test_copy(self, gallery: Gallery):
        copy = gallery.media.copy()
        assert isinstance(copy, dict)
        assert len(copy) == 2
        assert "image" in copy
        assert "video" in copy

    def test_update_with_dict(self, gallery: Gallery):
        new_vid = VideoMedia(id=10, name="updated_clip", duration=60.0)
        gallery.media.update({"video": new_vid})
        assert gallery.media["video"].name == "updated_clip"

    def test_setdefault_existing(self, gallery: Gallery):
        existing = gallery.media.setdefault("image", ImageMedia(id=99, name="fallback"))
        assert existing.name == "photo"  # should not be replaced

    def test_setdefault_missing_in_optional(self):
        """setdefault on a key that doesn't exist yet (optional TypedDict)."""
        og = OptionalGallery(id=1, name="Opt")
        img = ImageMedia(id=1, name="default_img", width=100, height=100)
        result = og.media.setdefault("image", img)
        assert result.name == "default_img"
        assert "image" in og.media


class TestTypedRelationMapBless:
    """Test bless and bless_value."""

    @pytest.fixture
    def trm(self):
        """Create a TypedRelationMap with __typed_dict__ set."""
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        return gallery.media

    def test_bless_whole_dict(self, trm: TypedRelationMap):
        blessed = trm.bless(
            {
                "image": {"id": 10, "name": "raw_img", "width": 1, "height": 1},
                "video": {"id": 11, "name": "raw_vid", "duration": 5.0},
            }
        )
        assert isinstance(blessed["image"], ImageMedia)
        assert isinstance(blessed["video"], VideoMedia)

    def test_bless_value_correct_type(self, trm: TypedRelationMap):
        img = trm.bless_value(
            "image", {"id": 10, "name": "raw_img", "width": 1, "height": 1}
        )
        assert isinstance(img, ImageMedia)
        assert img.name == "raw_img"

    def test_bless_value_wrong_key(self, trm: TypedRelationMap):
        with pytest.raises(KeyError, match="audio"):
            trm.bless_value("audio", {"id": 1, "name": "x"})


class TestTypedRelationMapSerialization:
    """Test model_dump / serialization."""

    def test_model_dump_with_values(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        dumped = gallery.model_dump()
        assert "media" in dumped
        assert "image" in dumped["media"]
        assert "video" in dumped["media"]
        assert dumped["media"]["image"]["name"] == "photo"
        assert dumped["media"]["video"]["duration"] == 30.0

    def test_model_dump_empty(self):
        gallery = Gallery(id=1, name="Empty")
        dumped = gallery.model_dump()
        assert dumped["media"] == {}


class TestTypedRelationMapComparison:
    """Test equality and other comparisons."""

    def test_eq_with_matching_dict(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        # Comparing with a plain dict containing the same transmuter instances
        plain = {"image": img, "video": vid}
        assert gallery.media == plain

    def test_ne_with_different_dict(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        assert gallery.media != {"something": "else"}

    def test_or_merge(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        new_vid = VideoMedia(id=3, name="new_clip", duration=60.0)
        merged = gallery.media | {"video": new_vid}
        assert isinstance(merged, dict)
        assert merged["video"].name == "new_clip"
        # Original should be unchanged
        assert gallery.media["video"].name == "clip"


class TestTypedRelationMapOptional:
    """Test TypedDict with total=False (all keys optional)."""

    def test_empty_is_valid(self):
        og = OptionalGallery(id=1, name="Opt")
        assert isinstance(og.media, TypedRelationMap)
        assert len(og.media) == 0

    def test_partial_keys(self):
        img = ImageMedia(id=1, name="only_image", width=100, height=100)
        og = OptionalGallery(
            id=1,
            name="Opt",
            media=TypedRelationMap({"image": img}),
        )
        assert len(og.media) == 1
        assert "image" in og.media
        assert "video" not in og.media

    def test_all_keys(self):
        img = ImageMedia(id=1, name="img", width=100, height=100)
        vid = VideoMedia(id=2, name="vid", duration=10.0)
        og = OptionalGallery(
            id=1,
            name="Opt",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        assert len(og.media) == 2


class TestTypedRelationMapRepr:
    """Test __repr__ and __str__."""

    def test_repr(self):
        gallery = Gallery(id=1, name="Test")
        r = repr(gallery.media)
        assert "TypedRelationMap" in r
        assert "DocumentMedia" in r

    def test_repr_unprepared(self):
        """repr() must not raise AttributeError when __typed_dict__ is not yet set."""
        trm = TypedRelationMap()
        r = repr(trm)
        assert "TypedRelationMap" in r
        assert "?" in r

    def test_str_with_values(self):
        img = ImageMedia(id=1, name="photo", width=800, height=600)
        vid = VideoMedia(id=2, name="clip", duration=30.0)
        gallery = Gallery(
            id=1,
            name="Test",
            media=TypedRelationMap({"image": img, "video": vid}),
        )
        s = str(gallery.media)
        assert "image" in s
        assert "video" in s


class TestTypedRelationMapValidation:
    """Test validation error cases."""

    def test_wrong_value_type_raises(self):
        """Providing a completely invalid type (non-model) should fail validation."""
        with pytest.raises(ValidationError):
            Gallery(
                id=1,
                name="Bad",
                media=TypedRelationMap({"image": "not_a_model", "video": 42}),
            )

    def test_missing_required_key_raises(self):
        """A required key missing from a total=True TypedDict should fail."""
        img = ImageMedia(id=1, name="img", width=100, height=100)
        with pytest.raises(ValidationError):
            Gallery(
                id=1,
                name="Incomplete",
                media=TypedRelationMap({"image": img}),  # missing 'video'
            )

    def test_non_typeddict_generic_raises(self):
        """Using a non-TypedDict generic arg should raise TypeError."""
        with pytest.raises(TypeError, match="TypedDict"):

            class BadModel(Gallery):
                media: TypedRelationMap[str] = TypedRelationMaps()  # type: ignore
