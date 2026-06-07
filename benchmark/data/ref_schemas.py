"""Pure-Pydantic reference schemas for shapes the shared ``tests/schemas`` lacks.

These mirror the structure of the map/group-map/typed-map/polymorphic
transmuters in ``tests.transmuters`` so Axis-A shape benchmarks compare like for
like. They live here (not in ``tests/``) to keep the benchmark suite
self-contained and ``tests/`` a fixture of record.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict


class TagRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str


class CatalogRef(BaseModel):
    """Pure-Pydantic equivalent of the RelationMap-backed Catalog transmuter."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    tags: dict[str, TagRef] = Field(default_factory=dict)


class GroupedCatalogRef(BaseModel):
    """Pure-Pydantic equivalent of the RelationGroupMap-backed catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    tags: dict[str, list[TagRef]] = Field(default_factory=dict)


class BookScalarRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    year: int


class AuthorNameRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str


class AuthorWithBooksRef(BaseModel):
    """Author + its book collection as scalar children (loading-strategy ref)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str
    field: str
    books: list[BookScalarRef] = Field(default_factory=list)


class CategoryScalarRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str


class BookWithCategoriesRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    year: int
    categories: list[CategoryScalarRef] = Field(default_factory=list)


class ReviewScalarRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    reviewer_name: str
    rating: int
    comment: str


class BookWithReviewsRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    year: int
    reviews: list[ReviewScalarRef] = Field(default_factory=list)


class AuthorUpdateRef(BaseModel):
    """Partial-update reference mirroring the transmuter's generated Update model."""

    name: Optional[str] = None
    field: Optional[str] = None


class ImageMediaRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    slot: str = ""
    name: str
    media_type: str = "image"
    width: int = 0
    height: int = 0


class VideoMediaRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    slot: str = ""
    name: str
    media_type: str = "video"
    duration: float = 0.0


class GalleryMediaRef(TypedDict):
    image: ImageMediaRef
    video: VideoMediaRef


class GalleryRef(BaseModel):
    """Pure-Pydantic equivalent of the TypedRelationMap-backed Gallery."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str
    media: GalleryMediaRef
