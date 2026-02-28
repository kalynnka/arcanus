from __future__ import annotations

from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
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
