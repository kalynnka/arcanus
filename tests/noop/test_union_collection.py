from __future__ import annotations

from typing import Literal, Union

import pytest

from arcanus import BaseTransmuter, RelationCollection, Relationships
from tests.transmuters import ImageMedia, VideoMedia


class MediaCollection(BaseTransmuter):
    items: RelationCollection[ImageMedia | VideoMedia] = Relationships()


class LegacyMediaCollection(BaseTransmuter):
    items: RelationCollection[Union[ImageMedia, VideoMedia]] = Relationships()  # noqa: UP007


@pytest.mark.parametrize("owner_type", [MediaCollection, LegacyMediaCollection])
@pytest.mark.parametrize("item_type", [ImageMedia, VideoMedia])
@pytest.mark.parametrize("operation", ["append", "insert", "setitem"])
def test_union_collection_accepts_single_member(
    owner_type: type[MediaCollection | LegacyMediaCollection],
    item_type: type[ImageMedia | VideoMedia],
    operation: Literal["append", "insert", "setitem"],
) -> None:
    owner = owner_type()
    item = item_type(slot="media", name="new")

    if operation == "append":
        owner.items.append(item)
    elif operation == "insert":
        owner.items.insert(0, item)
    else:
        owner.items.extend([ImageMedia(slot="old", name="old")])
        owner.items[0] = item

    assert len(owner.items) == 1
    assert owner.items[0] is item


@pytest.mark.parametrize("owner_type", [MediaCollection, LegacyMediaCollection])
def test_union_collection_accepts_multiple_members(
    owner_type: type[MediaCollection | LegacyMediaCollection],
) -> None:
    owner = owner_type()
    image = ImageMedia(slot="image", name="image.png")
    video = VideoMedia(slot="video", name="video.mp4")

    owner.items.extend([image, video])
    assert len(owner.items) == 2
    assert owner.items[0] is image
    assert owner.items[1] is video

    owner.items[:] = [video, image]
    assert len(owner.items) == 2
    assert owner.items[0] is video
    assert owner.items[1] is image
