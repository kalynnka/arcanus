"""Test polymorphic narrowing in model_formulate and model_construct caches.

When a base-type query (e.g. ``session.bulk(MediaItem, ids)``) caches an ORM
instance as the parent schema, later encounters of the *same* ORM instance
through a relationship that expects a concrete child schema must produce the
child type — not return the stale parent from the cache.

Test matrix (suggested in the bug write-up):
1. Base-then-child  — cache parent, then request child → narrowed
2. Child-then-base  — cache child, then request parent → cache hit (child IS parent)
3. Sibling types    — cache one child, request different child → re-validated
4. Same type        — cache child, request same child → cache hit
5. Cross-context    — narrowing only applies within one validation_context
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from arcanus.base import validation_context
from arcanus.materia.sqlalchemy import Session
from tests import models
from tests.transmuters import (
    Gallery,
    ImageMedia,
    MediaItem,
    VideoMedia,
)


def _create_gallery_with_media(session):
    """Persist a gallery with one image and one video, return their ids."""
    orm_gallery = models.GalleryORM(name="Narrowing Gallery")
    orm_image = models.ImageAttachment(
        slot="image",
        name="photo.jpg",
        media_type="image",
        width=1920,
        height=1080,
        gallery=orm_gallery,
    )
    orm_video = models.VideoAttachment(
        slot="video",
        name="clip.mp4",
        media_type="video",
        duration=120.5,
        gallery=orm_gallery,
    )
    session.add_all([orm_gallery, orm_image, orm_video])
    session.flush()
    return orm_gallery, orm_image, orm_video


class TestPolymorphicNarrowingValidate:
    """Polymorphic narrowing via model_validate / model_formulate."""

    def test_base_then_child_via_cache(self, engine: Engine):
        """Validate as parent, then validate same ORM as child → child type."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            # Re-load in a clean session so identity map is fresh
            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)
                assert orm_image

                with validation_context():
                    # Step 1: validate as base → MediaItem
                    base = MediaItem.model_validate(orm_image)
                    assert type(base) is MediaItem

                    # Step 2: validate same ORM instance as child → ImageMedia
                    child = ImageMedia.model_validate(orm_image)
                    assert type(child) is ImageMedia
                    assert isinstance(child, MediaItem)  # still IS-A parent
                    assert child.width == 1920
                    assert child.height == 1080

                    # Provider link is intact
                    assert child.__transmuter_provided__ is orm_image
                    assert orm_image.transmuter_proxy is child

    def test_child_then_base_cache_hit(self, engine: Engine):
        """Validate as child, then as parent → cache hit (child IS parent)."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    # Step 1: validate as child
                    child = ImageMedia.model_validate(orm_image)
                    assert type(child) is ImageMedia

                    # Step 2: validate same ORM as parent
                    parent = MediaItem.model_validate(orm_image)

                    # child IS-A MediaItem, so cache hit is valid
                    assert parent is child
                    assert isinstance(parent, MediaItem)

    def test_sibling_types_revalidated(self, engine: Engine):
        """Validate as ImageMedia, then as VideoMedia → re-validation attempted.

        Siblings share no IS-A relationship, so the cache must NOT return
        the wrong sibling.  With incompatible data (ImageAttachment ORM
        lacks a valid ``duration``), pydantic raises a ValidationError —
        proving the code bypassed the stale cache and attempted fresh
        validation.
        """
        import pydantic

        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)
                assert orm_image

                with validation_context():
                    image = ImageMedia.model_validate(orm_image)
                    assert type(image) is ImageMedia

                    # Sibling validation must NOT silently return the cached
                    # ImageMedia; it should attempt fresh validation which
                    # fails because the ORM data is incompatible.
                    with pytest.raises(pydantic.ValidationError):
                        VideoMedia.model_validate(orm_image)

    def test_same_type_cache_hit(self, engine: Engine):
        """Validate as ImageMedia twice → cache hit, same object."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    img1 = ImageMedia.model_validate(orm_image)
                    img2 = ImageMedia.model_validate(orm_image)
                    assert img1 is img2

    def test_cross_context_independence(self, engine: Engine):
        """Narrowing in one context doesn't affect another."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    base = MediaItem.model_validate(orm_image)
                    assert type(base) is MediaItem

                # New validation context — no stale cache
                with validation_context():
                    child = ImageMedia.model_validate(orm_image)
                    assert type(child) is ImageMedia
                    assert child is not base

    def test_gallery_base_then_typed_relation_map(self, engine: Engine):
        """Load media as base, then load gallery whose TypedRelationMap
        expects concrete child types → children are narrowed correctly."""
        with Session(engine) as session:
            with session.begin():
                orm_gallery, orm_image, orm_video = _create_gallery_with_media(session)
                gallery_id = orm_gallery.id
                image_id = orm_image.id
                video_id = orm_video.id

            with session.begin():
                # Pre-cache as base type
                orm_image = session.get(models.ImageAttachment, image_id)
                orm_video = session.get(models.VideoAttachment, video_id)

                with validation_context():
                    base_image = MediaItem.model_validate(orm_image)
                    base_video = MediaItem.model_validate(orm_video)
                    assert type(base_image) is MediaItem
                    assert type(base_video) is MediaItem

                    # Now load gallery — its TypedRelationMap expects
                    # ImageMedia / VideoMedia for each key.
                    orm_gallery = session.get(models.GalleryORM, gallery_id)
                    gallery = Gallery.model_validate(orm_gallery)

                    # The media dict should expose concrete child types
                    image_item = gallery.media["image"]
                    video_item = gallery.media["video"]

                    assert isinstance(image_item, ImageMedia)
                    assert isinstance(video_item, VideoMedia)


class TestPolymorphicNarrowingConstruct:
    """Polymorphic narrowing via model_construct."""

    def test_base_then_child_construct(self, engine: Engine):
        """Construct as parent, then construct same ORM as child → child type."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)
                assert orm_image

                with validation_context():
                    base = MediaItem.model_construct(data=orm_image)
                    assert type(base) is MediaItem

                    child = ImageMedia.model_construct(data=orm_image)
                    assert type(child) is ImageMedia
                    assert child.__transmuter_provided__ is orm_image
                    assert orm_image.transmuter_proxy is child

    def test_child_then_base_construct_cache_hit(self, engine: Engine):
        """Construct as child, then as parent → cache hit."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    child = ImageMedia.model_construct(data=orm_image)
                    parent = MediaItem.model_construct(data=orm_image)

                    # child IS-A MediaItem → valid cache hit
                    assert parent is child

    def test_sibling_construct_revalidated(self, engine: Engine):
        """Construct as ImageMedia, then as VideoMedia → re-constructed.

        model_construct skips validation, so the sibling is produced even
        though the underlying data is from a different subtype.  The key
        assertion is that the cache does NOT return the stale sibling.
        """
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    image = ImageMedia.model_construct(data=orm_image)
                    video = VideoMedia.model_construct(data=orm_image)

                    assert type(image) is ImageMedia
                    assert type(video) is VideoMedia
                    assert video is not image

    def test_same_type_construct_cache_hit(self, engine: Engine):
        """Construct as ImageMedia twice → cache hit."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    img1 = ImageMedia.model_construct(data=orm_image)
                    img2 = ImageMedia.model_construct(data=orm_image)
                    assert img1 is img2

    def test_cross_context_construct_independence(self, engine: Engine):
        """Each validation_context has its own cache."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)

                with validation_context():
                    base = MediaItem.model_construct(data=orm_image)
                    assert type(base) is MediaItem

                with validation_context():
                    child = ImageMedia.model_construct(data=orm_image)
                    assert type(child) is ImageMedia
                    assert child is not base


class TestTransmuterPathNarrowing:
    """When data itself is a parent Transmuter instance (not an ORM object),
    both model_validate and model_construct should narrow to the child type
    while preserving the ORM provider link."""

    def test_validate_parent_transmuter_as_child(self, engine: Engine):
        """model_validate a MediaItem instance as ImageMedia → narrowed."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)
                assert orm_image

                with validation_context():
                    parent = MediaItem.model_validate(orm_image)
                    assert type(parent) is MediaItem

                    # Now pass the *Transmuter* (not ORM) as data
                    child = ImageMedia.model_validate(parent)
                    assert type(child) is ImageMedia
                    assert child.__transmuter_provided__ is orm_image
                    assert orm_image.transmuter_proxy is child

    def test_construct_parent_transmuter_as_child(self, engine: Engine):
        """model_construct a MediaItem instance as ImageMedia → narrowed."""
        with Session(engine) as session:
            with session.begin():
                _, orm_image, _ = _create_gallery_with_media(session)
                image_id = orm_image.id

            with session.begin():
                orm_image = session.get(models.ImageAttachment, image_id)
                assert orm_image

                with validation_context():
                    parent = MediaItem.model_construct(data=orm_image)
                    assert type(parent) is MediaItem

                    # Pass Transmuter as data
                    child = ImageMedia.model_construct(data=parent)
                    assert type(child) is ImageMedia
                    assert child.__transmuter_provided__ is orm_image
                    assert orm_image.transmuter_proxy is child
