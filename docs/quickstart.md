# Quickstart

This page takes you from zero to persisting objects. We start with **no backend at all**, then bind
to SQLAlchemy.

## Without a backend (NoOpMateria)

The default [`NoOpMateria`](concepts/materia.md) is active automatically — define transmuters and
use them like regular Pydantic models, no setup required. Great for tests and prototyping.

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, RelationCollection, Relationship, Relationships
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

print(book.author.value.name)   # Isaac Asimov
print(list(author.books))       # [Book(...)]
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
```

### 3. Use the arcanus `Session`

!!! important
    Use `arcanus.materia.sqlalchemy.Session` (not SQLAlchemy's native `Session`). The arcanus
    session automatically "blesses" ORM rows into transmuters as they come out of queries.

```python
from sqlalchemy import create_engine, select
from arcanus.materia.sqlalchemy import Session

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)

with Session(engine) as session:
    # Create — adding the book cascades to its author
    author = Author(name="Isaac Asimov")
    book = Book(title="Foundation", author=Relation(author))
    session.add(book)
    session.flush()
    author.revalidate()          # sync server-generated id (RETURNING)
    session.commit()

    # Query — results are transmuters, not raw ORM objects
    found = session.one(Author, name="Isaac Asimov")
    assert isinstance(found, Author)

    stmt = select(Book).where(Book["title"].like("Found%"))
    books = session.execute(stmt).scalars().all()

    # Mutate — changes sync to the underlying ORM object
    found.name = "Arthur C. Clarke"
    session.commit()
```

## Async

Swap `Session` for `AsyncSession` and `await` the I/O — the API is otherwise identical. See
[Sessions & Async](concepts/sessions.md).

```python
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)
    books = await author.books     # awaits the lazy load
```

## Next

- [The Materia System](concepts/materia.md) — what `bless()` does and the design philosophy.
- [Relationships](concepts/relationships.md) — every association type.
- [API Reference](api/index.md).
