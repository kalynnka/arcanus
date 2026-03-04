from __future__ import annotations

from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from arcanus.association import (
    Relation,
    RelationCollection,
    RelationMap,
    RelationMaps,
    Relationship,
    Relationships,
    TypedRelationMap,
    TypedRelationMaps,
)
from arcanus.base import BaseTransmuter, Identity, Transmuter
from arcanus.dataclass import dataclass
from arcanus.materia.sqlalchemy.base import SqlalchemyMateria
from tests import models

sqlalchemy_materia = SqlalchemyMateria()


class TestIdMixin(BaseModel):
    test_id: Optional[UUID] = Field(default=None, frozen=True, exclude=True)


# BookCategory schema (M-M association with composite PK)
@sqlalchemy_materia.bless(models.BookCategory)
class BookCategory(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    book_id: Annotated[int, Identity] = Field(frozen=True)
    category_id: Annotated[int, Identity] = Field(frozen=True)


# Publisher schema (1-M with Book)
@sqlalchemy_materia.bless(models.Publisher)
class Publisher(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    country: str

    books: RelationCollection[Book] = Relationships()


# Author schema (1-M with Book)
@sqlalchemy_materia.bless(models.Author)
class Author(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    field: Literal[
        "Physics",
        "Biology",
        "Chemistry",
        "Literature",
        "History",
        "Quantum Physics",
        "Astronomy",
        "Dystopian Fiction",
        "Astrophysics",
        "Robotics",
        "Cybernetics",
        "Xenobiology",
        "Quantum Physics",
        "Science Fiction",
    ]

    books: RelationCollection[Book] = Relationships()


# BookDetail schema (1-1 with Book)
@sqlalchemy_materia.bless(models.BookDetail)
class BookDetail(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    isbn: str
    pages: int
    abstract: str
    book_id: int | None = None

    book: Relation[Book] = Relationship()


# Category schema (M-M with Book) — dataclass transmuter
@sqlalchemy_materia.bless(models.Category)
@dataclass(config=ConfigDict(from_attributes=True))
class Category(Transmuter):
    name: str
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    description: str | None = None
    test_id: Optional[UUID] = Field(default=None, frozen=True, exclude=True)

    books: RelationCollection[Book] = Relationships()


# Translator schema (optional 1-1 with Book)
@sqlalchemy_materia.bless(models.Translator)
class Translator(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    language: str

    book: Relation[Optional[Book]] = Relationship()


# Review schema (optional M-1 with Book)
@sqlalchemy_materia.bless(models.Review)
class Review(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    reviewer_name: str
    rating: int = Field(ge=1, le=5)  # 1-5 stars
    comment: str
    book_id: int | None = None

    book: Relation[Optional[Book]] = Relationship()


# Company schema — dataclass transmuter (Relation + RelationCollection)
@sqlalchemy_materia.bless(models.Company)
@dataclass(config=ConfigDict(from_attributes=True))
class Company(Transmuter):
    """Schema for Company with circular references."""

    name: str
    industry: str
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    test_id: Optional[UUID] = Field(default=None, frozen=True, exclude=True)

    departments: RelationCollection[Department] = Relationships()
    employees: RelationCollection[Employee] = Relationships()
    ceo: Relation[Optional[Employee]] = Relationship()
    client_projects: RelationCollection[Project] = Relationships()


@sqlalchemy_materia.bless(models.Department)
class Department(TestIdMixin, BaseTransmuter):
    """Schema for Department with circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    budget: int

    company: Relation[Company] = Relationship()
    employees: RelationCollection[Employee] = Relationships()
    projects: RelationCollection[Project] = Relationships()
    teams: RelationCollection[Team] = Relationships()


@sqlalchemy_materia.bless(models.Employee)
class Employee(TestIdMixin, BaseTransmuter):
    """Schema for Employee - hub of circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    title: str
    salary: int

    company: Relation[Company] = Relationship()
    company_as_ceo: Relation[Optional[Company]] = Relationship()
    department: Relation[Department] = Relationship()
    led_projects: RelationCollection[Project] = Relationships()
    managed_teams: RelationCollection[Team] = Relationships()
    teams: RelationCollection[Team] = Relationships()


@sqlalchemy_materia.bless(models.Project)
class Project(TestIdMixin, BaseTransmuter):
    """Schema for Project with circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    description: str
    status: str

    department: Relation[Department] = Relationship()
    lead: Relation[Employee] = Relationship()
    team: Relation[Optional[Team]] = Relationship()
    client_company: Relation[Optional[Company]] = Relationship()


@sqlalchemy_materia.bless(models.Team)
class Team(TestIdMixin, BaseTransmuter):
    """Schema for Team completing circular paths."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    size: int

    department: Relation[Department] = Relationship()
    manager: Relation[Employee] = Relationship()
    project: Relation[Project] = Relationship()
    members: RelationCollection[Employee] = Relationships()


# Book schema (M-1 with Author, M-1 with Publisher, 1-1 with BookDetail, M-M with Category, optional 1-1 with Translator, optional 1-M with Reviews)
@sqlalchemy_materia.bless(models.Book)
class Book(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    year: int
    author_id: int | None = None
    publisher_id: int | None = None
    translator_id: int | None = None

    author: Relation[Author] = Relationship()
    publisher: Relation[Publisher] = Relationship()
    translator: Relation[Optional[Translator]] = Relationship()
    detail: Relation[Optional[BookDetail]] = Relationship()
    categories: RelationCollection[Category] = Relationships()
    reviews: RelationCollection[Review] = Relationships()  # Optional 1-M


# ShelfItem schema (M-1 with Shelf)
@sqlalchemy_materia.bless(models.ShelfItem)
class ShelfItem(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    label: str
    description: str
    shelf_id: int | None = None

    shelf: Relation[Shelf] = Relationship()


# Shelf schema (1-M dict-based with ShelfItem)
@sqlalchemy_materia.bless(models.Shelf)
class Shelf(TestIdMixin, BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

    items: RelationMap[str, ShelfItem] = RelationMaps()


# Unblessed transmuters for noop RelationMap tests
class Tag(BaseTransmuter):
    """Tag model used as dict value."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None)
    name: str


class Catalog(BaseTransmuter):
    """Catalog with dict-based tag mapping."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None)
    title: str

    tags: RelationMap[str, Tag] = RelationMaps()


class LabeledCatalog(BaseTransmuter):
    """Catalog with Literal-keyed tag mapping for key validation tests."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None)
    title: str

    tags: RelationMap[Literal["python", "rust", "go"], Tag] = RelationMaps()


class AuthorFlat(BaseTransmuter):
    """Flat Author transmuter without relationships (for benchmarks)."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    field: Literal[
        "Physics",
        "Biology",
        "Chemistry",
        "Literature",
        "History",
        "Quantum Physics",
        "Astronomy",
        "Dystopian Fiction",
        "Astrophysics",
        "Robotics",
        "Cybernetics",
        "Xenobiology",
        "Quantum Physics",
        "Science Fiction",
    ]


class PublisherFlat(BaseTransmuter):
    """Flat Publisher transmuter without relationships (for benchmarks)."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    country: str


@dataclass
class SimpleTag(Transmuter):
    """A simple tag with no associations."""

    label: str


tag = SimpleTag(label="example")


@dataclass
class SimpleUser(Transmuter):
    """A user with default fields."""

    name: str
    age: int = 25


@dataclass(config=ConfigDict(validate_assignment=True))
class ValidatedUser(Transmuter):
    """A user with validate_assignment enabled."""

    name: str
    age: int = 25


@dataclass
class IdentifiedUser(Transmuter):
    """A user with identity fields."""

    name: str
    email: str = ""
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)


@dataclass
class PydanticItem(Transmuter):
    """A plain pydantic dataclass."""

    name: str
    score: float = 0.0


@dataclass
class DCAuthor(Transmuter):
    """An author with a collection of books."""

    name: str
    field: Literal["Physics", "Biology", "Chemistry", "Literature", "History"] = (
        "Physics"
    )
    books: RelationCollection[DCBook] = Relationships()


@dataclass
class DCPublisher(Transmuter):
    """A publisher with books."""

    name: str
    country: str = "US"
    books: RelationCollection[DCBook] = Relationships()


@dataclass
class DCBook(Transmuter):
    """A book with multiple associations."""

    title: str
    year: int = 2024
    author: Relation[DCAuthor] = Relationship()
    publisher: Relation[DCPublisher] = Relationship()
    tags: RelationCollection[SimpleTag] = Relationships()


@sqlalchemy_materia.bless(models.MediaAttachment)
class MediaItem(TestIdMixin, BaseTransmuter):
    """Base media transmuter for polymorphic tests."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    slot: str = ""
    name: str
    media_type: str = "generic"


@sqlalchemy_materia.bless(models.ImageAttachment)
class ImageMedia(MediaItem):
    """Image subtype."""

    media_type: str = "image"
    width: int = 0
    height: int = 0


@sqlalchemy_materia.bless(models.VideoAttachment)
class VideoMedia(MediaItem):
    """Video subtype."""

    media_type: str = "video"
    duration: float = 0.0


class DocumentMedia(TypedDict):
    """TypedDict defining per-key types for a document's media attachments."""

    image: ImageMedia
    video: VideoMedia


class OptionalDocumentMedia(TypedDict, total=False):
    """TypedDict where all keys are optional."""

    image: ImageMedia
    video: VideoMedia


@sqlalchemy_materia.bless(models.GalleryORM)
class Gallery(TestIdMixin, BaseTransmuter):
    """A gallery with typed media attachments."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

    media: TypedRelationMap[DocumentMedia] = TypedRelationMaps()


class OptionalGallery(TestIdMixin, BaseTransmuter):
    """A gallery where media keys are optional."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

    media: TypedRelationMap[OptionalDocumentMedia] = TypedRelationMaps()
