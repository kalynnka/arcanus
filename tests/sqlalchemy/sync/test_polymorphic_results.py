from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Engine, select

from arcanus.materia.sqlalchemy import (
    Session,
    selectin_polymorphic,
    with_polymorphic,
)
from tests.transmuters import (
    AbstractImageMedia,
    AbstractMedia,
    AbstractVideoMedia,
    AudioAsset,
    Gallery,
    ImageMedia,
    LibraryAsset,
    MediaItem,
    PdfAsset,
    VideoMedia,
)


def persist_gallery_media(
    engine: Engine,
    prefix: str,
    *,
    include_base: bool = False,
) -> None:
    with Session(engine) as session:
        gallery = Gallery.model_validate({"name": f"{prefix}-gallery"})
        gallery.media["image"] = ImageMedia.model_validate(
            {
                "slot": f"{prefix}-image",
                "name": f"{prefix}-image",
                "width": 1024,
                "height": 768,
            }
        )
        gallery.media["video"] = VideoMedia.model_validate(
            {
                "slot": f"{prefix}-video",
                "name": f"{prefix}-video",
                "duration": 30.0,
            }
        )
        session.add(gallery)
        session.flush()
        if include_base:
            gallery.revalidate()
            session.add(
                MediaItem.model_validate(
                    {
                        "slot": f"{prefix}-base",
                        "name": f"{prefix}-base",
                        "gallery_id": gallery.id,
                    }
                )
            )
        session.commit()


def persist_abstract_media(engine: Engine, prefix: str) -> None:
    with Session(engine) as session:
        session.add(
            AbstractImageMedia.model_validate(
                {
                    "name": f"{prefix}-image",
                    "width": 800,
                    "height": 600,
                }
            )
        )
        session.add(
            AbstractVideoMedia.model_validate(
                {
                    "name": f"{prefix}-video",
                    "duration": 45.0,
                }
            )
        )
        session.commit()


def persist_library_assets(engine: Engine, prefix: str, *, include_base: bool = False):
    with Session(engine) as session:
        if include_base:
            session.add(LibraryAsset.model_validate({"name": f"{prefix}-base"}))
        session.add(PdfAsset.model_validate({"name": f"{prefix}-pdf", "pages": 42}))
        session.add(
            AudioAsset.model_validate({"name": f"{prefix}-audio", "duration": 13.0})
        )
        session.commit()


def test_parent_polymorphic_select_adapts_fresh_orm_children(engine: Engine):
    prefix = f"poly-fresh-{uuid4()}"
    persist_gallery_media(engine, prefix)

    with Session(engine) as session:
        items = session.scalars(
            select(MediaItem)
            .where(MediaItem["name"].like(f"{prefix}%"))
            .order_by(MediaItem["name"])
        ).all()

    assert [type(item) for item in items] == [ImageMedia, VideoMedia]


def test_session_list_polymorphic_result_keeps_concrete_base_fallback(
    engine: Engine,
):
    prefix = f"poly-base-{uuid4()}"
    persist_gallery_media(engine, prefix, include_base=True)

    with Session(engine) as session:
        items = session.list(
            MediaItem,
            limit=None,
            expressions=[MediaItem["name"].like(f"{prefix}%")],
            order_bys=[MediaItem["name"]],
        )

    assert [type(item) for item in items] == [MediaItem, ImageMedia, VideoMedia]
    assert [item.media_type for item in items] == ["generic", "image", "video"]


def test_abstract_parent_polymorphic_select_uses_children_only(engine: Engine):
    prefix = f"poly-abstract-{uuid4()}"
    persist_abstract_media(engine, prefix)

    with Session(engine) as session:
        items = session.scalars(
            select(AbstractMedia)
            .where(AbstractMedia["name"].like(f"{prefix}%"))
            .order_by(AbstractMedia["name"])
        ).all()

    assert [type(item) for item in items] == [AbstractImageMedia, AbstractVideoMedia]


def test_with_polymorphic_wrapper_uses_sqlalchemy_alias_inspection(engine: Engine):
    prefix = f"poly-explicit-{uuid4()}"
    persist_gallery_media(engine, prefix)

    polymorphic_media = with_polymorphic(MediaItem, (ImageMedia, VideoMedia))
    assert not hasattr(polymorphic_media, "__transmuter_result_type__")

    with Session(engine) as session:
        items = session.scalars(
            select(polymorphic_media)
            .where(polymorphic_media.name.like(f"{prefix}%"))
            .order_by(polymorphic_media.name)
        ).all()

    assert [type(item) for item in items] == [ImageMedia, VideoMedia]


def test_selectin_polymorphic_wrapper_accepts_transmuter_tuple(engine: Engine):
    prefix = f"poly-selectin-{uuid4()}"
    persist_gallery_media(engine, prefix)

    with Session(engine) as session:
        items = session.scalars(
            select(MediaItem)
            .options(selectin_polymorphic(MediaItem, (ImageMedia, VideoMedia)))
            .where(MediaItem["name"].like(f"{prefix}%"))
            .order_by(MediaItem["name"])
        ).all()

    assert [type(item) for item in items] == [ImageMedia, VideoMedia]


def test_joined_table_parent_polymorphic_select_adapts_children(engine: Engine):
    prefix = f"poly-joined-{uuid4()}"
    persist_library_assets(engine, prefix)

    with Session(engine) as session:
        items = session.scalars(
            select(LibraryAsset)
            .where(LibraryAsset["name"].like(f"{prefix}%"))
            .order_by(LibraryAsset["name"])
        ).all()

    assert [type(item) for item in items] == [AudioAsset, PdfAsset]
    assert [item.name for item in items] == [f"{prefix}-audio", f"{prefix}-pdf"]
    assert items[0].duration == 13.0
    assert items[1].pages == 42


def test_joined_table_polymorphic_keeps_concrete_base_fallback(engine: Engine):
    prefix = f"poly-joined-base-{uuid4()}"
    persist_library_assets(engine, prefix, include_base=True)

    with Session(engine) as session:
        items = session.list(
            LibraryAsset,
            limit=None,
            expressions=[LibraryAsset["name"].like(f"{prefix}%")],
            order_bys=[LibraryAsset["name"]],
        )

    assert [type(item) for item in items] == [AudioAsset, LibraryAsset, PdfAsset]
    assert [item.asset_type for item in items] == ["audio", "asset", "pdf"]


def test_joined_table_with_polymorphic_uses_alias_inspection(engine: Engine):
    prefix = f"poly-joined-explicit-{uuid4()}"
    persist_library_assets(engine, prefix)

    polymorphic_asset = with_polymorphic(LibraryAsset, (PdfAsset, AudioAsset))
    with Session(engine) as session:
        items = session.scalars(
            select(polymorphic_asset)
            .where(polymorphic_asset.name.like(f"{prefix}%"))
            .order_by(polymorphic_asset.name)
        ).all()

    assert [type(item) for item in items] == [AudioAsset, PdfAsset]
