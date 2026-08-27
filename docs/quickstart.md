# Quickstart

This page takes you from zero to persisting objects. We start with **no backend at all**, then bind
to SQLAlchemy.

## Without a backend (NoOpMateria)

The default [`NoOpMateria`](concepts/materia.md) is active automatically — define transmuters and
use them like regular Pydantic models, no setup required. Great for tests and prototyping.

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
from pydantic import Field
from typing import Annotated, Optional


class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

    books: RelationCollection["Book"] = Relationships()


class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    author_id: int | None = None

    author: Relation[Author] = Relationship()


author = Author(id=1, name="Isaac Asimov")
book = Book(id=1, title="Foundation", author=Relation(author))

print(book.author.value.name)  # Isaac Asimov
print(list(author.books))  # [Book(...)]
```

## With SQLAlchemy

### 1. Define ORM models

Your SQLAlchemy models are plain, untouched SQLAlchemy:

```python
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase): ...


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
```

### 2. Bind transmuters with `bless()`

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
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
```

### 3. Use the arcanus `Session`

!!! important
    Use `arcanus.materia.sqlalchemy.Session` (not SQLAlchemy's native `Session`). The arcanus
    session automatically "blesses" ORM rows into transmuters as they come out of queries.

```python
from sqlalchemy import create_engine
from arcanus.materia.sqlalchemy import Session

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
```

#### Create

Adding the book cascades to its author. After a flush, server-generated ids are
synced back onto the transmuters automatically.

```python
with Session(engine) as session:
    author = Author(name="Isaac Asimov")
    book = Book(title="Foundation", author=Relation(author))

    session.add(book)  # adding the book also adds its author
    session.flush()  # INSERT; server-generated ids synced to the transmuters
    session.commit()
    print(book.id)  # e.g. 1
```

#### Read

Every result is a transmuter, not a raw ORM row. Reads are plain SQLAlchemy — `session.get` and
`session.execute(select(...))` — and typed column references (`Author["name"]`) drop straight into a
`select`.

```python
from sqlalchemy import select

with Session(engine) as session:
    author = session.get_one(Author, 1)  # by primary key (raises if missing)

    author = session.execute(  # by filter
        select(Author).filter_by(name="Isaac Asimov")
    ).scalar_one()

    authors = (
        session.execute(  # many, with filter + ordering + paging
            select(Author)
            .where(Author["name"].like("Isaac%"))
            .order_by(Author["name"].asc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    books = (
        session.execute(select(Book).where(Book["title"].like("Found%")))
        .scalars()
        .all()
    )
```

!!! tip "Typed shortcuts"
    For common reads, Arcanus also adds typed helpers to the session — `one`, `first`, `list`,
    `count`, `bulk`, `partitions` — so the above can be one-liners. See
    [Session Helpers](usage/sqlalchemy/session.md).

#### Navigate relationships

Related rows load on access and keep their identity.

```python
with Session(engine) as session:
    author = session.get_one(Author, 1)
    for book in author.books:  # loads on access
        assert book.author.value is author  # same instance — identity preserved
```

#### Update & delete

Mutating a transmuter syncs to its ORM row in place — no `model_dump()` round-trip.

```python
with Session(engine) as session:
    book = session.get_one(Book, 1)
    book.title = "Foundation (Revised)"  # synced to the ORM row
    session.commit()

    session.delete(book)  # follows your ORM cascade rules
    session.commit()
```

#### Partial models at the boundary

Generated `.Create` / `.Update` models validate incomplete payloads; `shell()` / `absorb()` move
between a partial and a full transmuter.

!!! warning "Experimental — for API boundaries (e.g. FastAPI)"
    The `.Create` / `.Update` partials are **experimental** (the generated surface may change). They
    exist for request/response boundaries — validating untrusted, incomplete bodies in a FastAPI
    handler and the like. If you're just working with objects in memory, you don't need them:
    construct and mutate the transmuter directly.

```python
with Session(engine) as session:
    author = Author.shell(Author.Create(name="New Author"))  # Create excludes the id
    session.add(author)
    session.flush()  # id synced back automatically

    author.absorb(Author.Update(name="Renamed"))  # applies only what's set
    session.commit()
```

## Async

Swap `Session` for `AsyncSession` and `await` the I/O — the API is otherwise identical. Awaiting a
relationship triggers its lazy load. See [Lifecycle & Async](concepts/lifecycle.md).

```python
from sqlalchemy.ext.asyncio import create_async_engine
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(create_async_engine("sqlite+aiosqlite://")) as session:
    author = await session.get_one(Author, 1)
    books = await author.books  # awaits the lazy load → list[Book]

    session.add(Book(title="Async Book", author=Relation(author)))
    await session.commit()
```

## Next

- [Usage](usage/index.md) — the full guide, grouped by materia: relationships, loading, querying,
  and partial schemas in depth.
- [The Materia System](concepts/materia.md) — what `bless()` does and the design philosophy.
- [API Reference](api/index.md).
