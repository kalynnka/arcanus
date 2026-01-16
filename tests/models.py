from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, Uuid
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)

from arcanus.base import TransmuterProxiedMixin


class Base(DeclarativeBase, TransmuterProxiedMixin):
    """Base class for all test ORM models."""

    @declared_attr
    def test_id(cls) -> Mapped[UUID | None]:
        """Nullable test_id column for test case data isolation."""
        return mapped_column(Uuid, nullable=True, default=None)


# Secondary table for M-M relationship between Book and Category
class BookCategory(Base):
    __tablename__ = "book_category"

    book_id: Mapped[int] = mapped_column(
        ForeignKey("book.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.id", ondelete="CASCADE"),
        primary_key=True,
    )


# Publisher (1-M with Book)
class Publisher(Base):
    __tablename__ = "publisher"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False)

    books: Mapped[list[Book]] = relationship(
        back_populates="publisher",
        uselist=True,
        cascade="save-update, merge, delete, delete-orphan",
    )


# Author (1-M with Book)
class Author(Base):
    __tablename__ = "author"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g., "Physics", "Biology"

    books: Mapped[list[Book]] = relationship(
        back_populates="author",
        uselist=True,
        cascade="save-update, merge, delete, delete-orphan",
    )


# Translator (optional 1-1 with Book)
class Translator(Base):
    __tablename__ = "translator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)

    # Optional 1-1: A translator may have translated one book (or none in this simplified model)
    book: Mapped[Book | None] = relationship(
        back_populates="translator",
        uselist=False,
    )


# Book (M-1 with Author, M-1 with Publisher, 1-1 with BookDetail, M-M with Category, optional 1-1 with Translator)
class Book(Base):
    __tablename__ = "book"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    author_id: Mapped[int] = mapped_column(
        ForeignKey("author.id", ondelete="CASCADE"),
        nullable=False,
    )
    author: Mapped[Author] = relationship(back_populates="books", uselist=False)

    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publisher.id", ondelete="CASCADE"),
        nullable=False,
    )
    publisher: Mapped[Publisher] = relationship(
        back_populates="books", uselist=False, lazy="joined"
    )

    # Optional 1-1 relationship with Translator (for translated books)
    translator_id: Mapped[int | None] = mapped_column(
        ForeignKey("translator.id", ondelete="SET NULL"),
        nullable=True,
    )
    translator: Mapped[Translator | None] = relationship(
        back_populates="book",
        uselist=False,
    )

    # 1-1 relationship with BookDetail
    detail: Mapped[BookDetail | None] = relationship(
        back_populates="book",
        uselist=False,
        cascade="save-update, merge, delete, delete-orphan",
    )

    # M-M relationship with Category via secondary table
    categories: Mapped[list[Category]] = relationship(
        secondary=BookCategory.__table__,
        back_populates="books",
        uselist=True,
    )

    # Optional 1-M relationship with Review
    reviews: Mapped[list[Review]] = relationship(
        back_populates="book",
        uselist=True,
        cascade="save-update, merge, delete, delete-orphan",
    )


# BookDetail (1-1 with Book)
class BookDetail(Base):
    __tablename__ = "book_detail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    isbn: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)

    book_id: Mapped[int] = mapped_column(
        ForeignKey("book.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    book: Mapped[Book] = relationship(back_populates="detail", uselist=False)


# Category (M-M with Book)
class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    books: Mapped[list[Book]] = relationship(
        secondary=BookCategory.__table__,
        back_populates="categories",
        uselist=True,
    )


# Review (optional 1-M with Book)
class Review(Base):
    __tablename__ = "review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reviewer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 stars
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional M-1: A review may optionally be associated with a book
    book_id: Mapped[int | None] = mapped_column(
        ForeignKey("book.id", ondelete="CASCADE"),
        nullable=True,
    )
    book: Mapped[Book | None] = relationship(back_populates="reviews", uselist=False)


# M-M secondary table for Team-Employee membership
team_employee = Table(
    "team_employee",
    Base.metadata,
    Column(
        "team_id", Integer, ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "employee_id",
        Integer,
        ForeignKey("employee.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Company(Base):
    """Company entity - part of multiple circular paths."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)

    # 1-M: Company -> Department
    departments: Mapped[list[Department]] = relationship(
        "Department",
        back_populates="company",
        foreign_keys="[Department.company_id]",
        cascade="all, delete-orphan",
    )

    # 1-M: Company -> Employee
    employees: Mapped[list[Employee]] = relationship(
        "Employee",
        back_populates="company",
        foreign_keys="[Employee.company_id]",
        cascade="all, delete-orphan",
    )

    # 1-1: Company -> Employee (CEO) - circular reference
    # No FK constraint to avoid circular dependency in DDL
    ceo_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    ceo: Mapped[Employee | None] = relationship(
        "Employee",
        back_populates="company_as_ceo",
        foreign_keys=[ceo_id],
        primaryjoin="Company.ceo_id == Employee.id",
        post_update=True,  # Break circular dependency during flush
        uselist=False,
    )

    # 1-M: Company as client for Projects - circular reference
    client_projects: Mapped[list[Project]] = relationship(
        "Project",
        back_populates="client_company",
        foreign_keys="[Project.client_company_id]",
        primaryjoin="Company.id == foreign(Project.client_company_id)",
        cascade="all, delete-orphan",
    )


class Department(Base):
    """Department entity - part of multiple circular paths."""

    __tablename__ = "department"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    budget: Mapped[int] = mapped_column(Integer, nullable=False)

    # M-1: Department -> Company
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
    )
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="departments",
        foreign_keys=[company_id],
    )

    # 1-M: Department -> Employee
    employees: Mapped[list[Employee]] = relationship(
        "Employee",
        back_populates="department",
        foreign_keys="[Employee.department_id]",
        cascade="all, delete-orphan",
    )

    # 1-M: Department -> Project
    projects: Mapped[list[Project]] = relationship(
        "Project",
        back_populates="department",
        foreign_keys="[Project.department_id]",
        cascade="all, delete-orphan",
    )

    # 1-M: Department -> Team
    teams: Mapped[list[Team]] = relationship(
        "Team",
        back_populates="department",
        foreign_keys="[Team.department_id]",
        cascade="all, delete-orphan",
    )


class Employee(Base):
    """Employee entity - central hub in circular relationships."""

    __tablename__ = "employee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    salary: Mapped[int] = mapped_column(Integer, nullable=False)

    # M-1: Employee -> Company
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
    )
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="employees",
        foreign_keys=[company_id],
    )

    # 1-1: Employee as CEO of Company - circular reference
    company_as_ceo: Mapped[Company | None] = relationship(
        "Company",
        back_populates="ceo",
        foreign_keys="[Company.ceo_id]",
        primaryjoin="Employee.id == foreign(Company.ceo_id)",
        viewonly=True,  # viewonly to avoid circular dependency during flush
        uselist=False,
    )

    # M-1: Employee -> Department
    department_id: Mapped[int] = mapped_column(
        ForeignKey("department.id", ondelete="CASCADE"),
        nullable=False,
    )
    department: Mapped[Department] = relationship(
        "Department",
        back_populates="employees",
        foreign_keys=[department_id],
    )

    # 1-M: Employee leads Projects
    led_projects: Mapped[list[Project]] = relationship(
        "Project",
        back_populates="lead",
        foreign_keys="[Project.lead_id]",
        cascade="save-update",
    )

    # 1-M: Employee manages Teams
    managed_teams: Mapped[list[Team]] = relationship(
        "Team",
        back_populates="manager",
        foreign_keys="[Team.manager_id]",
        cascade="save-update",
    )

    # M-M: Employee is member of Teams
    teams: Mapped[list[Team]] = relationship(
        "Team",
        secondary=team_employee,
        back_populates="members",
    )


class Project(Base):
    """Project entity - part of circular paths through multiple routes."""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # M-1: Project -> Department
    department_id: Mapped[int] = mapped_column(
        ForeignKey("department.id", ondelete="CASCADE"),
        nullable=False,
    )
    department: Mapped[Department] = relationship(
        "Department",
        back_populates="projects",
        foreign_keys=[department_id],
    )

    # M-1: Project -> Employee (lead) - circular reference
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead: Mapped[Employee] = relationship(
        "Employee",
        back_populates="led_projects",
        foreign_keys=[lead_id],
    )

    # 1-1: Project -> Team - circular reference
    team: Mapped[Team | None] = relationship(
        "Team",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # M-1: Project -> Company (client) - circular reference
    # No FK constraint to avoid circular dependency in DDL
    client_company_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    client_company: Mapped[Company | None] = relationship(
        "Company",
        back_populates="client_projects",
        foreign_keys=[client_company_id],
        primaryjoin="Project.client_company_id == Company.id",
        remote_side="Company.id",
    )


class Team(Base):
    """Team entity - completes circular paths."""

    __tablename__ = "team"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)

    # M-1: Team -> Department - circular reference
    department_id: Mapped[int] = mapped_column(
        ForeignKey("department.id", ondelete="CASCADE"),
        nullable=False,
    )
    department: Mapped[Department] = relationship(
        "Department",
        back_populates="teams",
        foreign_keys=[department_id],
    )

    # M-1: Team -> Employee (manager) - circular reference
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"),
        nullable=False,
    )
    manager: Mapped[Employee] = relationship(
        "Employee",
        back_populates="managed_teams",
        foreign_keys=[manager_id],
    )

    # 1-1: Team -> Project - circular reference
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    project: Mapped[Project] = relationship(
        "Project",
        back_populates="team",
        foreign_keys=[project_id],
    )

    # M-M: Team has Employee members
    members: Mapped[list[Employee]] = relationship(
        "Employee",
        secondary=team_employee,
        back_populates="teams",
    )


__all__ = [
    "Base",
    "Publisher",
    "Author",
    "Book",
    "BookDetail",
    "Category",
    "BookCategory",
    "Translator",
    "Review",
    "Company",
    "Department",
    "Employee",
    "Project",
    "Team",
    "team_employee",
]
