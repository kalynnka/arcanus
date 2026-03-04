"""Test TypedRelationMap association with SQLAlchemy Materia.

Tests:
- CRUD operations with polymorphic dict-based relationships
  (Gallery <-> MediaAttachment via attribute_keyed_dict + single-table inheritance)
- Lazy and eager loading of typed dict relationships
- Serialization after ORM load
- Dict mutation operations persisted through SQLAlchemy
"""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from arcanus.association import TypedRelationMap
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Gallery, ImageMedia, VideoMedia


class TestTypedRelationMapCRUD:
    """Test basic CRUD operations with typed dict-based relationships."""

    def test_create_gallery_with_media(self, engine: Engine):
        """Test creating a Gallery with polymorphic media through TypedRelationMap."""
        with Session(engine) as session:
            gallery = Gallery(name="My Gallery")
            image = ImageMedia(slot="image", name="photo.jpg", width=1920, height=1080)
            video = VideoMedia(slot="video", name="clip.mp4", duration=120.5)
            gallery.media["image"] = image
            gallery.media["video"] = video

            session.add(gallery)
            session.flush()
            gallery.revalidate()
            image.revalidate()
            video.revalidate()

            assert gallery.id is not None
            assert image.id is not None
            assert video.id is not None
            assert len(gallery.media) == 2

    def test_create_gallery_empty(self, engine: Engine):
        """Test creating a Gallery with no media."""
        with Session(engine) as session:
            gallery = Gallery(name="Empty Gallery")
            session.add(gallery)
            session.flush()
            gallery.revalidate()

            assert gallery.id is not None
            assert len(gallery.media) == 0

    def test_add_media_to_existing_gallery(self, engine: Engine):
        """Test adding media to an existing Gallery."""
        with Session(engine) as session:
            gallery = Gallery(name="Growing Gallery")
            session.add(gallery)
            session.flush()

            image = ImageMedia(slot="image", name="added.png", width=800, height=600)
            gallery.media["image"] = image
            session.flush()
            image.revalidate()

            assert image.id is not None
            assert len(gallery.media) == 1
            assert gallery.media["image"].name == "added.png"

    def test_remove_media_from_gallery(self, engine: Engine):
        """Test removing media from a Gallery."""
        with Session(engine) as session:
            gallery = Gallery(name="Shrinking Gallery")
            image = ImageMedia(slot="image", name="temp.png", width=100, height=100)
            gallery.media["image"] = image
            session.add(gallery)
            session.flush()

            assert len(gallery.media) == 1
            del gallery.media["image"]
            session.flush()

            assert len(gallery.media) == 0

    def test_replace_media_in_gallery(self, engine: Engine):
        """Test replacing media at an existing key."""
        with Session(engine) as session:
            gallery = Gallery(name="Replace Gallery")
            original = ImageMedia(
                slot="image", name="original.png", width=640, height=480
            )
            gallery.media["image"] = original
            session.add(gallery)
            session.flush()

            replacement = ImageMedia(
                slot="image", name="replacement.png", width=1920, height=1080
            )
            gallery.media["image"] = replacement
            session.flush()

            assert gallery.media["image"].name == "replacement.png"

    def test_clear_all_media(self, engine: Engine):
        """Test clearing all media from a gallery."""
        with Session(engine) as session:
            gallery = Gallery(name="Clearable Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="img.png", width=100, height=100
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="vid.mp4", duration=30.0
            )
            session.add(gallery)
            session.flush()

            assert len(gallery.media) == 2
            gallery.media.clear()
            session.flush()

            assert len(gallery.media) == 0


class TestTypedRelationMapLoading:
    """Test lazy and eager loading of typed dict-based relationships."""

    def test_lazy_load_media(self, engine: Engine):
        """Test that media items are lazily loaded when accessed."""
        with Session(engine) as session:
            gallery = Gallery(name="Lazy Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="lazy_img.png", width=800, height=600
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="lazy_vid.mp4", duration=45.0
            )
            session.add(gallery)
            session.flush()
            gallery.revalidate()
            gallery_id = gallery.id
            session.commit()

        # New session to test lazy loading
        with Session(engine) as session:
            stmt = select(Gallery).where(Gallery["id"] == gallery_id)
            gallery = session.scalars(stmt).unique().one()
            assert isinstance(gallery, Gallery)
            assert isinstance(gallery.media, TypedRelationMap)

            # Accessing media triggers lazy load
            assert len(gallery.media) == 2
            assert gallery.media["image"].name == "lazy_img.png"
            assert gallery.media["video"].name == "lazy_vid.mp4"

    def test_eager_load_selectinload(self, engine: Engine):
        """Test eager loading media with selectinload."""
        with Session(engine) as session:
            gallery = Gallery(name="Eager Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="eager_img.png", width=400, height=300
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="eager_vid.mp4", duration=90.0
            )
            session.add(gallery)
            session.flush()
            gallery.revalidate()
            gallery_id = gallery.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Gallery)
                .where(Gallery["id"] == gallery_id)
                .options(selectinload(Gallery["media"]))
            )
            gallery = session.scalars(stmt).unique().one()
            assert isinstance(gallery, Gallery)
            assert len(gallery.media) == 2

    def test_load_preserves_keys(self, engine: Engine):
        """Test that dict keys are preserved after loading from DB."""
        with Session(engine) as session:
            gallery = Gallery(name="Key Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="key_img.png", width=100, height=100
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="key_vid.mp4", duration=10.0
            )
            session.add(gallery)
            session.flush()
            gallery.revalidate()
            gallery_id = gallery.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Gallery).where(Gallery["id"] == gallery_id)
            gallery = session.scalars(stmt).unique().one()
            assert set(gallery.media.keys()) == {"image", "video"}

    def test_load_preserves_polymorphic_types(self, engine: Engine):
        """Test that polymorphic subtypes are preserved after loading from DB."""
        with Session(engine) as session:
            gallery = Gallery(name="Poly Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="poly_img.png", width=1024, height=768
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="poly_vid.mp4", duration=60.0
            )
            session.add(gallery)
            session.flush()
            gallery.revalidate()
            gallery_id = gallery.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Gallery).where(Gallery["id"] == gallery_id)
            gallery = session.scalars(stmt).unique().one()
            assert isinstance(gallery.media["image"], ImageMedia)
            assert isinstance(gallery.media["video"], VideoMedia)
            assert gallery.media["image"].width == 1024
            assert gallery.media["video"].duration == 60.0


class TestTypedRelationMapSerialization:
    """Test serialization of TypedRelationMap after ORM operations."""

    def test_model_dump_after_create(self, engine: Engine):
        """Test model_dump after creating gallery with media."""
        with Session(engine) as session:
            gallery = Gallery(name="Dump Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="dump_img.png", width=640, height=480
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="dump_vid.mp4", duration=15.0
            )
            session.add(gallery)
            session.flush()

            data = gallery.model_dump()
            assert isinstance(data["media"], dict)
            assert set(data["media"].keys()) == {"image", "video"}
            assert data["media"]["image"]["name"] == "dump_img.png"
            assert data["media"]["image"]["width"] == 640
            assert data["media"]["video"]["duration"] == 15.0

    def test_model_dump_after_load(self, engine: Engine):
        """Test model_dump after loading from DB with selectinload."""
        with Session(engine) as session:
            gallery = Gallery(name="Load Dump Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="ld_img.png", width=320, height=240
            )
            session.add(gallery)
            session.flush()
            gallery.revalidate()
            gallery_id = gallery.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Gallery)
                .where(Gallery["id"] == gallery_id)
                .options(selectinload(Gallery["media"]))
            )
            gallery = session.scalars(stmt).unique().one()
            data = gallery.model_dump()
            assert isinstance(data["media"], dict)
            assert "image" in data["media"]
            assert data["media"]["image"]["name"] == "ld_img.png"

    def test_model_dump_empty_media(self, engine: Engine):
        """Test model_dump with empty media dict."""
        with Session(engine) as session:
            gallery = Gallery(name="Empty Dump Gallery")
            session.add(gallery)
            session.flush()

            data = gallery.model_dump()
            assert data["media"] == {}


class TestTypedRelationMapDictOperations:
    """Test dict operations through the ORM."""

    def test_get_existing_key(self, engine: Engine):
        """Test get() on a loaded gallery."""
        with Session(engine) as session:
            gallery = Gallery(name="Get Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="get_img.png", width=100, height=100
            )
            session.add(gallery)
            session.flush()

            assert gallery.media.get("image") is not None
            assert gallery.media["image"].name == "get_img.png"
            assert gallery.media.get("video") is None

    def test_pop_from_gallery(self, engine: Engine):
        """Test pop() removes and returns the media item."""
        with Session(engine) as session:
            gallery = Gallery(name="Pop Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="pop_img.png", width=100, height=100
            )
            session.add(gallery)
            session.flush()

            item = gallery.media.pop("image")
            assert item.name == "pop_img.png"
            assert len(gallery.media) == 0

    def test_keys_values_items(self, engine: Engine):
        """Test keys(), values(), items() views."""
        with Session(engine) as session:
            gallery = Gallery(name="Views Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="v_img.png", width=100, height=100
            )
            gallery.media["video"] = VideoMedia(
                slot="video", name="v_vid.mp4", duration=5.0
            )
            session.add(gallery)
            session.flush()

            assert set(gallery.media.keys()) == {"image", "video"}
            assert len(list(gallery.media.values())) == 2
            assert len(list(gallery.media.items())) == 2

    def test_contains_key(self, engine: Engine):
        """Test key membership check."""
        with Session(engine) as session:
            gallery = Gallery(name="Contains Gallery")
            gallery.media["image"] = ImageMedia(
                slot="image", name="c_img.png", width=100, height=100
            )
            session.add(gallery)
            session.flush()

            assert "image" in gallery.media
            assert "video" not in gallery.media

    def test_update_dict(self, engine: Engine):
        """Test update() with new media items."""
        with Session(engine) as session:
            gallery = Gallery(name="Update Gallery")
            session.add(gallery)
            session.flush()

            gallery.media.update(
                {
                    "image": ImageMedia(
                        slot="image", name="u_img.png", width=200, height=200
                    ),
                    "video": VideoMedia(slot="video", name="u_vid.mp4", duration=25.0),
                }
            )
            session.flush()

            assert len(gallery.media) == 2
            assert gallery.media["image"].name == "u_img.png"

    def test_setdefault(self, engine: Engine):
        """Test setdefault() inserts only if key is absent."""
        with Session(engine) as session:
            gallery = Gallery(name="Setdefault Gallery")
            existing = ImageMedia(
                slot="image", name="original.png", width=100, height=100
            )
            gallery.media["image"] = existing
            session.add(gallery)
            session.flush()

            new = ImageMedia(slot="image", name="new.png", width=200, height=200)
            result = gallery.media.setdefault("image", new)
            assert result.name == "original.png"


class TestTypedRelationMapBackReference:
    """Test back-reference from media item to Gallery."""

    def test_media_has_gallery_reference(self, engine: Engine):
        """Test that a media item can reference its parent Gallery."""
        with Session(engine) as session:
            gallery = Gallery(name="BackRef Gallery")
            image = ImageMedia(
                slot="image", name="backref_img.png", width=100, height=100
            )
            gallery.media["image"] = image
            session.add(gallery)
            session.flush()

            # Access via the ORM provider's back-reference
            assert image.__transmuter_provided__ is not None
            assert image.__transmuter_provided__.gallery.name == "BackRef Gallery"  # type: ignore
