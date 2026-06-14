# SQLAlchemy Materia

`SqlalchemyMateria` binds transmuters to a SQLAlchemy database. Your ORM models stay exactly as they
are; a transmuter is blessed *on top* of an existing model. This section expands the backend-agnostic
components from [NoOp](../noop/index.md) — [relationships](../noop/relationships.md),
[expressions & cursors](../noop/querying.md), [partial schemas](../noop/schemas.md) — with real
persistence: CRUD, loading strategies, and querying against a live database.

## Setup

### 1. Define ORM models

Plain SQLAlchemy — Arcanus does not touch these:

```python
from sqlalchemy import Column as SAColumn, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): ...

book_category = Table(
    "book_category",
    Base.metadata,
    SAColumn("book_id", ForeignKey("books.id"), primary_key=True),
    SAColumn("category_id", ForeignKey("categories.id"), primary_key=True),
)

class AuthorModel(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    books: Mapped[list["BookModel"]] = relationship(back_populates="author")

class BookModel(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int] = mapped_column(ForeignKey(AuthorModel.id))
    author: Mapped[AuthorModel] = relationship(back_populates="books")
    categories: Mapped[list["CategoryModel"]] = relationship(
        secondary=book_category, back_populates="books"
    )

class CategoryModel(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    books: Mapped[list[BookModel]] = relationship(
        secondary=book_category, back_populates="categories"
    )
```

### 2. Bless transmuters

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, RelationCollection, Relationship, Relationships
from arcanus.materia.sqlalchemy import SqlalchemyMateria
from pydantic import Field
from typing import Annotated, Optional

materia = SqlalchemyMateria()

@materia.bless(AuthorModel)
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection["Book"] = Relationships()

@materia.bless(BookModel)
class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    author_id: int | None = None
    author: Relation[Author] = Relationship()
    categories: RelationCollection["Category"] = Relationships()

@materia.bless(CategoryModel)
class Category(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection[Book] = Relationships()
```

The `id` field carries `Identity` (so Arcanus knows the primary key) and is `frozen=True` (a row's
identity shouldn't change after assignment). See [Partial Schemas](../noop/schemas.md) for how those
annotations shape `.Create` / `.Update`.

### 3. Use the arcanus `Session`

!!! important "Use the arcanus session, not SQLAlchemy's"
    Import `Session` / `AsyncSession` from `arcanus.materia.sqlalchemy`, **not** from
    `sqlalchemy.orm`. The arcanus session blesses ORM rows into transmuters as they come out of
    queries and activates the validation context for its lifetime.

```python
from sqlalchemy import create_engine
from arcanus.materia.sqlalchemy import Session

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)

with Session(engine) as session:
    author = session.get_one(Author, 1)   # a transmuter, not a raw ORM row
    assert isinstance(author, Author)
```

The `Author` / `Book` / `Category` models defined here are the **running example** for the rest of
this section.

## Session and lifecycle

Under this materia a transmuter does **not** have a lifecycle of its own — it follows its ORM row's,
and the row is owned by the SQLAlchemy session:

- It becomes pending on `add`, persistent on `flush` / `commit`.
- The validation context (a weak-keyed `provided-instance → transmuter` cache, scoped to the session)
  keeps a transmuter alive only as long as its provided instance lives in the session. Close,
  expunge, or expire the session and the transmuter is released with its row.
- Server-generated values (e.g. autoincrement ids) are SQLAlchemy's to produce; `revalidate()` syncs
  them into the transmuter after a flush.

There is no separate "save the Pydantic object" step — manage the `Session`, and the transmuters
follow. The full design is in
[object lifecycle under the SQLAlchemy materia](../../concepts/lifecycle.md#lifecycle-under-the-sqlalchemy-materia).

## In this section

<div class="grid cards" markdown>

- :material-database-edit: **[CRUD & Relationships](crud.md)** — create, read, update, delete, and relationship CRUD with cascades.
- :material-function-variant: **[Session Helpers](session.md)** — the typed query helpers added to the session: `one`, `first`, `list`, `bulk`, `count`, `partitions`.
- :material-download-network: **[Loading Strategies](loading.md)** — `lazy`, `selectin`, `joined`, `raise`, per-query options, and async awaiting.
- :material-filter: **[Querying](querying.md)** — typed columns, expressions, criteria, and cursor pagination against the database.
- :material-code-braces: **[SQL Statements](statements.md)** — fully-typed `select` / `update` / `delete`, and the typed loader-option & polymorphic wrappers.
- :material-api: **[Working with FastAPI](fastapi.md)** — CRUD with partial schemas, `Criteria` filtering, and `Page` pagination, end to end.

</div>
