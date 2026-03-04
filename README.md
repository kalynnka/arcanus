# Arcanus

[![Tests](https://github.com/kalynnka/arcanus/actions/workflows/tests.yml/badge.svg)](https://github.com/kalynnka/arcanus/actions/workflows/tests.yml)
[![Codecov](https://codecov.io/gh/kalynnka/arcanus/branch/main/graph/badge.svg)](https://codecov.io/gh/kalynnka/arcanus)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://codspeed.io/kalynnka/arcanus?utm_source=badge)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Arcanus** is a Python library designed to seamlessly bind Pydantic schemas with various datasources, eliminating the need to manually create templates, factories, and utilities repeatedly. It provides a unified interface for working with different data backends while maintaining type safety and validation through Pydantic.

> **⚠️ Warning:** This repository is still a work in progress and is currently at a minimum viable state. Expect bugs, breaking changes, and incomplete features.

> **⚠️ Note:** At the moment, SQLAlchemy is the only supported provider and is hardcoded as the default backend.

## Features

- 🔄 **Unified Interface**: Work with different data backends through a consistent API with Pydantic
- 🛡️ **Type Safety**: Full Pydantic validation and type checking
- 🔗 **Relationship Management**: Intuitive handling of one-to-one, one-to-many, and many-to-many relationships
- ⚡ **Async Support**: Native async/await support for SQLAlchemy
- 🎯 **Multiple Materia**: NoOpMateria for testing, SQLAlchemy Materia for database operations
- 📦 **Partial Models**: Built-in support for Create/Update operations

## Materia Types

Arcanus supports different "Materia" backends to handle data:

### NoOpMateria

A no-operation materia that's perfect for testing and development. It allows working with Pydantic models without any backend, making it ideal for unit tests and prototyping.

> **Note:** NoOpMateria is automatically active by default - no manual blessing required! Simply define transmuter classes and they'll work without any backend setup.

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, RelationCollection, Relationships
from pydantic import Field
from typing import Annotated, Optional

class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    field: str

    books: RelationCollection[Book] = Relationships()

class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    year: int
    author_id: int | None = None

    author: Relation[Author] = Relationships()

# Use them like regular Pydantic models
author = Author(id=1, name="Isaac Asimov", field="Science Fiction")
book = Book(id=1, title="Foundation", year=1951, author=Relation(author))

# Access relationships
print(book.author.value.name)  # Isaac Asimov
print(list(author.books))  # [Book(...)]
```

### Dataclass Transmuters

In addition to `BaseTransmuter` (which extends `BaseModel`), arcanus provides a
`@dataclass` decorator for lightweight transmuters built on **pydantic dataclasses**.

```python
from arcanus import dataclass

@dataclass
class SimpleTag:
    """A simple tag with no associations."""
    label: str

tag = SimpleTag(label="example")
tag.revalidate()          # transmuter method, injected at runtime
print(SimpleTag.Create)   # partial model, also available
```

The `@dataclass` decorator handles pydantic dataclass creation **and** transmuter
protocol injection automatically. It accepts plain classes, stdlib dataclasses,
and pydantic dataclasses as input.

#### Inheriting `Transmuter` (optional)

By default, `@dataclass` injects `Transmuter` as a base class **at runtime**.
This means transmuter methods (`revalidate()`, `Create`, `Update`, `shell()`,
`absorb()`, etc.) are always available on instances regardless of how the class
is declared.

However, since Python's type system cannot express intersection types
(`type[T & Transmuter]`), type checkers like pyright won't see the
transmuter-specific attributes unless you explicitly inherit from `Transmuter`:

```python
from arcanus import Transmuter, dataclass

# Option 1: Minimal — fields work, transmuter attrs not visible to type checkers
@dataclass
class Foo:
    name: str

foo = Foo(name="bar")
foo.revalidate()          # ✅ works at runtime
foo.revalidate()          # ❌ pyright: "revalidate" is not a known member

# Option 2: Full type safety — inherit Transmuter
@dataclass
class Bar(Transmuter):
    name: str

bar = Bar(name="baz")
bar.revalidate()          # ✅ works at runtime
bar.revalidate()          # ✅ pyright sees it
Bar.Create                # ✅ pyright sees it
```

Both forms are fully functional at runtime — the only difference is static type
visibility. Choose whichever style suits your project.

#### Rebuilding Forward References

When a `@dataclass` transmuter uses forward references to types defined later in
the module (just like `BaseModel.model_rebuild()` in pydantic), you must call
`rebuild_dataclass` after all referenced types are available:

```python
from arcanus import Transmuter, dataclass, rebuild_dataclass
from arcanus.base import BaseTransmuter
from arcanus.association import Relation, Relationship

# Category references Book, which isn't defined yet
@dataclass
class Category(Transmuter):
    name: str
    books: RelationCollection[Book] = Relationships()  # forward ref

# Book is defined after Category
class Book(BaseTransmuter):
    title: str
    categories: RelationCollection[Category] = Relationships()

# Resolve Category → Book now that Book exists
rebuild_dataclass(Category)
```

Forward references between dataclass transmuters are retried automatically when
new `@dataclass` transmuters are created. The explicit `rebuild_dataclass` call
is only needed when a dataclass transmuter references a `BaseTransmuter`
(BaseModel) type that is defined later.

### SQLAlchemy Materia

Connect schemas to SQLAlchemy ORM models for full database functionality, **enabling operations on Pydantic transmuter objects just like ORM objects**, seamlessly gluing together the best of both worlds.

> **⚠️ Important:** Use `arcanus.database.Session` instead of SQLAlchemy's native `sqlalchemy.orm.Session`. The arcanus Session handles the automatic "blessing" of ORM objects into transmuter schemas.

#### Bridging Pydantic and SQLAlchemy

Traditional Pydantic + SQLAlchemy patterns often involve some friction:

- **Manual conversion**: Validating Pydantic models and then converting them to ORM objects
- **Object duality**: Juggling both ORM objects and Pydantic objects throughout the codebase
- **Relationship complexity**: Managing relationships across two separate object systems
- **Boilerplate code**: Writing conversion utilities and factory functions

**SQLAlchemy Materia aims to reduce this friction** by:

**Work with unified objects** - Transmuter schemas are backed by ORM objects, reducing the need for manual conversion.

**Bi-directional sync** - Changes to transmuter objects reflect in the underlying ORM object and vice versa.

**Relationship handling** - Relationships can be accessed through Pydantic models with lazy loading support handled behind the scenes.

**Combined benefits** - Pydantic's validation and type checking work alongside SQLAlchemy's query capabilities.

**Single interface** - One consistent object interface instead of switching between ORM and Pydantic models.

#### Setup

Define SQLAlchemy ORM models and link them to transmuter schemas:

```python
from sqlalchemy import ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from arcanus.materia.sqlalchemy.base import SqlalchemyMateria
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, RelationCollection, Relationships
from arcanus.database import Session
from pydantic import Field
from typing import Annotated, Optional

# Define ORM models
class Base(DeclarativeBase): ...

class AuthorModel(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)

    books: Mapped[list["BookModel"]] = relationship(back_populates="author")

class BookModel(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey(AuthorModel.id), nullable=False)

    author: Mapped[AuthorModel] = relationship(back_populates="books")

# Initialize SQLAlchemy Materia and bless schemas
sqlalchemy_materia = SqlalchemyMateria()

@sqlalchemy_materia.bless(AuthorModel)
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    field: str

    books: RelationCollection[Book] = Relationships()

@sqlalchemy_materia.bless(BookModel)
class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    year: int
    author_id: int | None = None

    author: Relation[Author] = Relationships()

# Create engine
engine = create_engine("postgresql://user:password@localhost/dbname")
Base.metadata.create_all(engine)
```

#### Transmuter-ORM Proxying

All objects retrieved from arcanus Session are transmuter instances, wrapping the origianl ORM objects.

```python
with Session(engine) as session:
    author = session.get_one(Author, 1)

    # This is a transmuter object with Pydantic validation
    assert isinstance(author, Author)
    assert isinstance(author, BaseTransmuter)

    # Access the underlying ORM object via __transmuter_provided__
    orm_author = author.__transmuter_provided__
    assert isinstance(orm_author, AuthorModel)

    # Changes sync bi-directionally
    author.name = "Arthur C. Clarke"
    assert orm_author.name == "Arthur C. Clarke"  # Synced to ORM

    # ORM changes reflect in transmuter after revalidation
    orm_author.field = "Hard Science Fiction"
    author.revalidate()  # Sync ORM changes back to transmuter
    assert author.field == "Hard Science Fiction"

    # Related objects are also transmuters
    for book in author.books:
        assert isinstance(book, Book)
        assert hasattr(book, '__transmuter_provided__')

    session.commit()
```

#### Use Cases

##### Creating and Persisting Objects

```python
# Create objects with relationships
with Session(engine) as session:
    author = Author(name="Isaac Asimov", field="Science Fiction")
    book = Book(title="Foundation", year=1951, author=Relation(author))

    session.add(book)  # Adding book automatically adds author
    session.flush()

    # Sync server-generated values (autoincrement IDs)
    # PostgreSQL/SQLite with RETURNING support:
    author.revalidate()  # No extra query
    book.revalidate()

    # MySQL without RETURNING:
    # session.refresh(author)  # Issues SELECT
    # session.refresh(book)

    session.commit()
    print(f"Created book #{book.id}: {book.title}")
```

##### Querying Objects

```python
with Session(engine) as session:
    # By primary key
    author = session.get_one(Author, 1)

    # Using filters
    author = session.one(Author, name="Isaac Asimov")

    # With expressions
    from sqlalchemy import select
    stmt = select(Author).where(Author["field"] == "Science Fiction")
    result = session.execute(stmt)
    authors = result.scalars().all()

    # List with pagination
    books = session.list(Book, limit=10, offset=0,
                        order_bys=[Book["year"].desc()])
```

##### Accessing Relationships

```python
with Session(engine) as session:
    author = session.get_one(Author, 1)

    # Navigate one-to-many
    for book in author.books:
        print(f"{book.title} ({book.year})")

        # Navigate many-to-one (same object reference)
        assert book.author.value is author
```

##### Updating Objects

```python
with Session(engine) as session:
    # Direct update
    book = session.get_one(Book, 1)
    book.title = "Foundation (Revised)"
    session.commit()

    # Bulk update with RETURNING
    from sqlalchemy import update
    stmt = (
        update(Book)
        .where(Book["author_id"] == 1)
        .values(field="Updated")
        .returning(Book)
    )
    result = session.execute(stmt)
    updated_books = result.scalars().all()
    session.commit()
```

##### Using Partial Models (APIs)

```python
# Create partial (excludes identity fields)
create_data = Author.Create(name="New Author", field="Physics")
author = Author.shell(create_data)

with Session(engine) as session:
    session.add(author)
    session.commit()

# Update partial (respects frozen fields)
update_data = Author.Update(field="Quantum Physics")
author = session.get_one(Author, 1)
author.absorb(update_data)
session.commit()
```

##### Deleting Objects

```python
with Session(engine) as session:
    # Delete with cascade
    author = session.get_one(Author, 1)
    session.delete(author)  # Related books deleted by cascade
    session.commit()

    # Bulk delete with RETURNING
    from sqlalchemy import delete
    stmt = delete(Book).where(Book["year"] < 2000).returning(Book)
    result = session.execute(stmt)
    deleted_books = result.scalars().all()
    session.commit()
```

#### Session Helper Methods

**`get` / `get_one`** - Retrieve by primary key:

```python
author = session.get(Author, 1)  # Returns None if not found
author = session.get_one(Author, 1)  # Raises if not found
```

**`one` / `one_or_none`** - Single result with filters:

```python
author = session.one(Author, name="Isaac Asimov")
author = session.one_or_none(Author, name="Maybe Exists")
```

**`first`** - First result with ordering:

```python
author = session.first(Author, order_bys=[Author["name"]])
```

**`list`** - Multiple results with pagination:

```python
authors = session.list(Author, limit=10, offset=20,
                      expressions=[Author["field"].like("Science%")])
```

**`bulk`** - Multiple by IDs:

```python
authors = session.bulk(Author, [1, 2, 3, 4, 5])
```

**`count`** - Count matching rows:

```python
total = session.count(Author)
filtered = session.count(Author, expressions=[Author["field"] == "Physics"])
```

**`partitions`** - Stream large result sets:

```python
for partition in session.partitions(Author, size=100):
    for author in partition:
        process(author)
```

### Async Support

Arcanus supports asynchronous operations using SQLAlchemy's async engine. Use `arcanus.database.AsyncSession` instead of `sqlalchemy.ext.asyncio.AsyncSession`.

All operations work identically to the sync version - just use `AsyncSession` and await async operations:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from arcanus.database import AsyncSession

# Create async engine
async_engine = create_async_engine(
    "postgresql+asyncpg://user:password@localhost/dbname",
    echo=True
)

# All operations are awaitable
async with AsyncSession(async_engine, expire_on_commit=True) as session:
    # Query
    author = await session.get_one(Author, 1)

    # Create
    book = Book(title="Async Book", year=2024, author=Relation(author))
    session.add(book)
    await session.flush()
    await session.commit()

    # List with filters
    books = await session.list(Book, limit=10,
                               expressions=[Book["year"] > 2020])
```

#### Relationship Loading in Async

SQLAlchemy's relationship loading strategies work with arcanus transmuters. The await syntax depends on the loading strategy:

**Lazy loading (select)** - Requires await to trigger the query, otherwise a greenlet issue will be raised:

```python
class BookModel(Base):
    # Default lazy="select" - loads on access
    author: Mapped[AuthorModel] = relationship(lazy="select", back_populates="books")

async with AsyncSession(async_engine) as session:
    book = await session.get_one(Book, 1)

    # Must await for lazy loading - triggers SELECT query
    parent_author = await book.author  # Returns Author object directly
    parent_author is book.author.value # standerd usage, no need for await for the second time visit
    assert isinstance(parent_author, Author)
```

**Eager loading (selectin/joined)** - Loaded upfront, but keep await syntax for consistency:

```python
class BookModel(Base):
    # Eager loading strategies - data already loaded
    author: Mapped[AuthorModel] = relationship(lazy="selectin", back_populates="books")
    # or lazy="joined"

async with AsyncSession(async_engine) as session:
    book = await session.get_one(Book, 1)

    # No I/O needed (data already loaded), but await still works

    parent_author = await book.author  # Returns cached data

    book2 = await session.get_one(Book, 2)
    # also works without await for selectin/joined strategies
    # but recommended to keep await syntax consistent across strategies
    parent_author = book.author.value

```

**Syntactic sugar for await:**

- `await relation` (Relation) → Returns the related object directly (equivalent to `relation.value`)
- `await relation_collection` (RelationCollection) → Returns a shallow list copy of all related objects

```python
async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)

    # RelationCollection: await returns list of related objects
    books_list = await author.books  # Returns list[Book]
    for book in books_list:
        print(book.title)

    # Can also iterate the collection directly after await
    await author.books
    for book in author.books:  # Iterates the collection
        print(book.title)

    # Relation: await returns the related object
    book = await session.get_one(Book, 1)
    parent_author = await book.author  # Returns Author, not Relation[Author]
    assert parent_author.id == book.author_id
```

## Association Types

Arcanus provides several association types to model different relationship patterns. All association types work across all materia backends (NoOp, SQLAlchemy, etc.).

| Association | Relationship | Container | Example |
|---|---|---|---|
| `Relation[T]` | One-to-one / Many-to-one | Single value | `author: Relation[Author]` |
| `RelationCollection[T]` | One-to-many / Many-to-many | `list[T]` | `books: RelationCollection[Book]` |
| `RelationSet[T]` | Many-to-many (unique) | `set[T]` | `tags: RelationSet[Tag]` |
| `RelationMap[K, T]` | Keyed collection (homogeneous) | `dict[K, T]` | `settings: RelationMap[str, Setting]` |
| `TypedRelationMap[TD]` | Keyed collection (heterogeneous) | `dict` via TypedDict | `media: TypedRelationMap[MediaFiles]` |

Default factories are provided for convenience:

| Field Helper | Creates |
|---|---|
| `Relationship()` | `Field(default_factory=Relation, frozen=True)` |
| `Relationships()` | `Field(default_factory=RelationCollection, frozen=True)` |
| `RelationMaps()` | `Field(default_factory=RelationMap, frozen=True)` |
| `TypedRelationMaps()` | `Field(default_factory=TypedRelationMap, frozen=True)` |

### Relation

`Relation[T]` wraps a single related transmuter. Use it for one-to-one or many-to-one relationships.

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, Relationship
from pydantic import Field
from typing import Annotated, Optional

class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    author: Relation[Author] = Relationship()

# Assign at construction
author = Author(id=1, name="Isaac Asimov")
book = Book(id=1, title="Foundation", author=Relation(author))

# Access the value
print(book.author.value.name)  # Isaac Asimov

# Update the value
new_author = Author(id=2, name="Arthur C. Clarke")
book.author.value = new_author
print(book.author.value.name)  # Arthur C. Clarke

# Optional relation (defaults to None)
class Review(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    text: str
    book: Relation[Optional[Book]] = Relationship()

review = Review(id=1, text="Great book!")
print(review.book.value)  # None
```

### RelationCollection

`RelationCollection[T]` is a `list`-based association for one-to-many or many-to-many relationships.

```python
from arcanus.association import RelationCollection, Relationships

class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection[Book] = Relationships()

class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str

# Start empty, add items
author = Author(id=1, name="Asimov")
author.books.append(Book(id=1, title="Foundation"))
author.books.append(Book(id=2, title="I, Robot"))

# List operations
print(len(author.books))       # 2
print(author.books[0].title)   # Foundation

for book in author.books:
    print(book.title)

# Extend with multiple
author.books.extend([
    Book(id=3, title="Caves of Steel"),
    Book(id=4, title="The End of Eternity"),
])

# Remove, pop, clear
author.books.remove(author.books[0])
popped = author.books.pop()
author.books.clear()

# Initialize with values at construction
author = Author(
    id=1,
    name="Asimov",
    books=RelationCollection([
        Book(id=1, title="Foundation"),
        Book(id=2, title="I, Robot"),
    ]),
)
```

### RelationSet

`RelationSet[T]` is a `set`-based association for unique collections. Ideal for many-to-many relationships where duplicates are not allowed.

```python
from arcanus.association import RelationSet, Relationships

class Tag(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    name: str

class Article(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    title: str
    tags: RelationSet[Tag] = Relationships()

article = Article(id=1, title="Intro to Python")

# Add tags
python_tag = Tag(id=1, name="python")
article.tags.add(python_tag)
article.tags.add(Tag(id=2, name="tutorial"))

# Set operations
print(len(article.tags))          # 2
print(python_tag in article.tags)  # True

# Discard (no error if absent)
article.tags.discard(python_tag)

# Update with multiple
article.tags.update([
    Tag(id=3, name="beginner"),
    Tag(id=4, name="guide"),
])

# Set algebra
other_tags = {Tag(id=3, name="beginner"), Tag(id=5, name="advanced")}
common = article.tags & other_tags       # intersection
combined = article.tags | other_tags     # union
diff = article.tags - other_tags         # difference

# Initialize with values
article = Article(
    id=1,
    title="Intro",
    tags=RelationSet({Tag(id=1, name="python"), Tag(id=2, name="tutorial")}),
)
```

### RelationMap

`RelationMap[K, T]` is a `dict`-based association with **homogeneous** value types — all values share the same transmuter type. Use it for keyed one-to-many relationships.

```python
from arcanus.association import RelationMap, RelationMaps

class ShelfItem(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    label: str
    description: str

class Shelf(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    items: RelationMap[str, ShelfItem] = RelationMaps()

shelf = Shelf(id=1, name="Reference")

# Set items by key
shelf.items["python"] = ShelfItem(id=1, label="python", description="Python ref")
shelf.items["rust"] = ShelfItem(id=2, label="rust", description="Rust ref")

# Dict operations
print(shelf.items["python"].description)  # Python ref
print(len(shelf.items))                    # 2
print("python" in shelf.items)             # True

for key, item in shelf.items.items():
    print(f"{key}: {item.label}")

# Update, pop, clear
shelf.items.update({"go": ShelfItem(id=3, label="go", description="Go ref")})
removed = shelf.items.pop("rust")
shelf.items.clear()

# Literal-typed keys for stricter validation
from typing import Literal

class StrictCatalog(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    title: str
    tags: RelationMap[Literal["python", "rust", "go"], Tag] = RelationMaps()

catalog = StrictCatalog(id=1, title="Languages")
catalog.tags["python"] = Tag(id=1, name="Python")
# catalog.tags["java"] = ...  # raises ValidationError — key not in Literal
```

### TypedRelationMap

`TypedRelationMap[TD]` is a dict-based association where each key can have a **different Transmuter type**, defined through a `TypedDict`. This is ideal for polymorphic relationships where different keys correspond to different subclasses.

#### Defining Typed Media Slots

```python
from typing import Annotated, Optional
from typing_extensions import TypedDict
from pydantic import Field
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import TypedRelationMap, TypedRelationMaps

# Define polymorphic transmuter types
class MediaItem(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    slot: str = ""
    name: str

class ImageMedia(MediaItem):
    width: int = 0
    height: int = 0

class VideoMedia(MediaItem):
    duration: float = 0.0

# Define per-key types with TypedDict
class DocumentMedia(TypedDict):
    image: ImageMedia
    video: VideoMedia

# Use in a transmuter
class Gallery(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    media: TypedRelationMap[DocumentMedia] = TypedRelationMaps()
```

#### Basic Usage

```python
# Create with values
img = ImageMedia(id=1, name="photo", width=1920, height=1080)
vid = VideoMedia(id=2, name="clip", duration=120.0)

gallery = Gallery(id=1, name="My Gallery")
gallery.media["image"] = img
gallery.media["video"] = vid

# Type-safe per-key access
photo = gallery.media["image"]   # ImageMedia
clip = gallery.media["video"]    # VideoMedia

print(photo.width)    # 1920
print(clip.duration)  # 120.0
```

#### Construction with TypedRelationMap

```python
# Pass values at construction time
gallery = Gallery(
    id=1,
    name="My Gallery",
    media=TypedRelationMap({"image": img, "video": vid}),
)

# Or initialize from plain dicts (Pydantic validates and coerces)
gallery = Gallery(
    id=1,
    name="My Gallery",
    media=TypedRelationMap({
        "image": {"name": "photo", "width": 1920, "height": 1080},
        "video": {"name": "clip", "duration": 120.0},
    }),
)
```

#### Dict Operations

`TypedRelationMap` supports standard dict operations, with per-key type validation:

```python
gallery = Gallery(id=1, name="Test")

# Set items (validated against TypedDict key types)
gallery.media["image"] = ImageMedia(id=1, name="photo", width=800, height=600)

# Check membership
"image" in gallery.media  # True
len(gallery.media)         # 1

# Iterate
for key in gallery.media:
    print(key, gallery.media[key])

# Delete
del gallery.media["image"]

# Update with multiple items
gallery.media.update({
    "image": ImageMedia(id=1, name="new_photo", width=1024, height=768),
    "video": VideoMedia(id=2, name="intro", duration=30.0),
})

# Pop
removed = gallery.media.pop("video")
```

#### Optional Keys with `total=False`

Use `total=False` in the TypedDict to make all keys optional, allowing partial population:

```python
class OptionalMedia(TypedDict, total=False):
    image: ImageMedia
    video: VideoMedia

class FlexibleGallery(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    media: TypedRelationMap[OptionalMedia] = TypedRelationMaps()

# Only some keys need to be present
gallery = FlexibleGallery(id=1, name="Partial")
gallery.media["image"] = ImageMedia(id=1, name="photo", width=800, height=600)
# gallery.media["video"] is not required

data = gallery.model_dump()
# {"id": 1, "name": "Partial", "media": {"image": {...}}}
```

#### Serialization

```python
gallery = Gallery(id=1, name="Test")
gallery.media["image"] = ImageMedia(id=1, name="photo", width=800, height=600)
gallery.media["video"] = VideoMedia(id=2, name="clip", duration=30.0)

# Serialize to dict
data = gallery.model_dump()
# {
#     "id": 1, "name": "Test",
#     "media": {
#         "image": {"id": 1, "slot": "", "name": "photo", "media_type": "generic", "width": 800, "height": 600},
#         "video": {"id": 2, "slot": "", "name": "clip", "media_type": "generic", "duration": 30.0},
#     }
# }

# Round-trip: reconstruct from serialized data
restored = Gallery.model_validate(data)
assert isinstance(restored.media["image"], ImageMedia)
```

#### Key Validation

Invalid keys or wrong value types raise errors:

```python
gallery = Gallery(id=1, name="Test")

# Invalid key (not in TypedDict)
gallery.media["audio"] = some_value  # raises KeyError

# Wrong value type for key
gallery.media["image"] = VideoMedia(...)  # raises ValidationError
```
