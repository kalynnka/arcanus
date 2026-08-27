from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TestIdMixin(BaseModel):
    test_id: UUID | None = Field(default=None, frozen=True, exclude=True)


# BookCategory schema (M-M association with composite PK)
class BookCategory(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: int = Field(frozen=True)
    category_id: int = Field(frozen=True)


# Publisher schema (1-M with Book)
class Publisher(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    country: str

    books: list[Book] = Field(default_factory=list)


# Author schema (1-M with Book)
class Author(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
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
        "Science Fiction",
    ]

    books: list[Book] = Field(default_factory=list)


class AuthorCreate(BaseModel):
    """Schema for creating/updating authors (no id field)."""

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
        "Science Fiction",
    ] = Field(alias="write_field")


class AuthorFlat(BaseModel):
    """Flat Author schema without relationships (for benchmarks)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
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
        "Science Fiction",
    ]


class PublisherFlat(BaseModel):
    """Flat Publisher schema without relationships (for benchmarks)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    country: str


class BookFlat(BaseModel):
    """Flat Book schema with flat nested author/publisher (for benchmarks)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    title: str
    year: int
    author_id: int | None = None
    publisher_id: int | None = None

    author: AuthorFlat
    publisher: PublisherFlat


class BookCreate(BaseModel):
    """Schema for creating books with nested author/publisher (for benchmarks)."""

    title: str
    year: int
    author: AuthorFlat
    publisher: PublisherFlat


# BookDetail schema (1-1 with Book)
class BookDetail(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    isbn: str
    pages: int
    abstract: str
    book_id: int | None = None

    book: Book


# Book schema (M-1 with Author, M-1 with Publisher, 1-1 with BookDetail, M-M with Category, optional 1-1 with Translator, optional 1-M with Reviews)
class Book(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    title: str
    year: int
    author_id: int | None = None
    publisher_id: int | None = None
    translator_id: int | None = None

    author: Author
    publisher: Publisher
    translator: Translator | None = None
    detail: BookDetail | None = None
    categories: list[Category] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)  # Optional 1-M


# Category schema (M-M with Book)
class Category(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    description: str | None = None

    books: list[Book] = Field(default_factory=list)


# Translator schema (optional 1-1 with Book)
class Translator(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    language: str

    book: Book | None = None


# Review schema (optional M-1 with Book)
class Review(TestIdMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    reviewer_name: str
    rating: int = Field(ge=1, le=5)  # 1-5 stars
    comment: str
    book_id: int | None = None

    book: Book | None = None


class Company(TestIdMixin, BaseModel):
    """Schema for Company with circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    industry: str

    departments: list[Department] = Field(default_factory=list)
    employees: list[Employee] = Field(default_factory=list)
    ceo: Employee | None = None
    client_projects: list[Project] = Field(default_factory=list)


class Department(TestIdMixin, BaseModel):
    """Schema for Department with circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    budget: int

    company: Company
    employees: list[Employee] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)


class Employee(TestIdMixin, BaseModel):
    """Schema for Employee - hub of circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    title: str
    salary: int

    company: Company
    company_as_ceo: Company | None = None
    department: Department
    led_projects: list[Project] = Field(default_factory=list)
    managed_teams: list[Team] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)


class Project(TestIdMixin, BaseModel):
    """Schema for Project with circular references."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    description: str
    status: str

    department: Department
    lead: Employee
    team: Team | None = None
    client_company: Company | None = None


class Team(TestIdMixin, BaseModel):
    """Schema for Team completing circular paths."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, frozen=True)
    name: str
    size: int

    department: Department
    manager: Employee
    project: Project
    members: list[Employee] = Field(default_factory=list)


class BlogPostFlat(BaseModel):
    """Blog post with association-proxy fields resolved to scalars."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None)
    title: str
    author_id: int
    author_name: str | None = None
    tag_labels: list[str] = Field(default_factory=list)


class BookChildCreate(BaseModel):
    """Flat book input for 1-M append benchmarks (author comes from the parent)."""

    title: str
    year: int
    publisher_id: int


class ShelfItemCreate(BaseModel):
    """Flat ShelfItem input for RelationMap-set benchmarks."""

    label: str
    description: str


class WarehouseItemCreate(BaseModel):
    """Flat WarehouseItem input for RelationGroupMap-set benchmarks."""

    category: str
    name: str
    quantity: int = 0
