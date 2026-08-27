# Relationships

Arcanus models relationships with **association types**. They are backend-agnostic, so everything on
this page runs under the default `NoOpMateria` with no setup. Under a real backend the same fields
gain lazy loading and persistence — see [SQLAlchemy → CRUD & Relationships](../sqlalchemy/crud.md#relationship-crud)
and [Loading Strategies](../sqlalchemy/loading.md).

## The association types

| Association | Relationship | Container | Example |
|-------------|--------------|-----------|---------|
| `Relation[T]` | one-to-one / many-to-one | single value | `author: Relation[Author]` |
| `RelationCollection[T]` | one-to-many / many-to-many | `list[T]` | `books: RelationCollection[Book]` |
| `RelationSet[T]` | many-to-many (unique) | `set[T]` | `tags: RelationSet[Tag]` |
| `RelationMap[K, T]` | keyed (homogeneous) | `dict[K, T]` | `settings: RelationMap[str, Setting]` |
| `TypedRelationMap[TD]` | keyed (heterogeneous) | `dict` via `TypedDict` | `media: TypedRelationMap[MediaFiles]` |

## Field helpers

Default factories keep declarations terse:

| Helper | Creates |
|--------|---------|
| `Relationship()` | `Field(default_factory=Relation, frozen=True)` |
| `Relationships()` | `Field(default_factory=RelationCollection, frozen=True)` |
| `RelationMaps()` | `Field(default_factory=RelationMap, frozen=True)` |
| `TypedRelationMaps()` | `Field(default_factory=TypedRelationMap, frozen=True)` |

## `Relation` — single value

`Relation[T]` wraps one related transmuter. Use it for one-to-one or many-to-one.

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


author = Author(id=1, name="Isaac Asimov")
book = Book(id=1, title="Foundation", author=Relation(author))

book.author.value.name  # "Isaac Asimov"
book.author.value = Author(id=2, name="Arthur C. Clarke")  # reassign


# Optional relation (defaults to None)
class Review(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    text: str
    book: Relation[Optional[Book]] = Relationship()


Review(id=1, text="Great!").book.value  # None
```

## `RelationCollection` — list

A `list`-based association for one-to-many or many-to-many.

```python
from arcanus.association import RelationCollection, Relationships


class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection["Book"] = Relationships()


author = Author(id=1, name="Asimov")
author.books.append(Book(id=1, title="Foundation"))
author.books.extend([Book(id=2, title="I, Robot"), Book(id=3, title="Caves of Steel")])

len(author.books)  # 3
author.books[0].title  # "Foundation"
author.books.remove(author.books[0])
author.books.pop()

# Or initialize at construction
Author(id=1, name="Asimov", books=RelationCollection([Book(id=1, title="Foundation")]))
```

## `RelationSet` — set

A `set`-based association for unique many-to-many collections.

```python
from arcanus.association import RelationSet, Relationships


class Tag(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    name: str


class Article(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    title: str
    tags: RelationSet[Tag] = Relationships()


article = Article(id=1, title="Intro")
python = Tag(id=1, name="python")
article.tags.add(python)
article.tags.add(Tag(id=2, name="tutorial"))

python in article.tags  # True
article.tags.discard(python)  # no error if absent
article.tags.update([Tag(id=3, name="guide")])

# Set algebra works too
other = {Tag(id=3, name="guide"), Tag(id=5, name="advanced")}
article.tags & other  # intersection
article.tags | other  # union
```

## `RelationMap` — keyed, homogeneous

A `dict`-based association where every value is the same transmuter type.

```python
from arcanus.association import RelationMap, RelationMaps


class Setting(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    value: str


class App(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    settings: RelationMap[str, Setting] = RelationMaps()


app = App(id=1, name="demo")
app.settings["theme"] = Setting(id=1, value="dark")
app.settings["lang"] = Setting(id=2, value="en")

app.settings["theme"].value  # "dark"
"theme" in app.settings  # True
for key, setting in app.settings.items():
    ...
```

`Literal`-typed keys are validated against the allowed set:

```python
from typing import Literal


class StrictApp(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None)
    settings: RelationMap[Literal["theme", "lang"], Setting] = RelationMaps()


StrictApp(id=1).settings["color"] = Setting(...)  # raises ValidationError — bad key
```

## `TypedRelationMap` — keyed, heterogeneous

A `dict`-based association where each key can hold a **different** transmuter type, declared with a
`TypedDict`. Ideal for polymorphic slots.

```python
from typing import Annotated, Optional
from typing_extensions import TypedDict
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import TypedRelationMap, TypedRelationMaps
from pydantic import Field


class MediaItem(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str


class ImageMedia(MediaItem):
    width: int = 0
    height: int = 0


class VideoMedia(MediaItem):
    duration: float = 0.0


class GalleryMedia(TypedDict):
    image: ImageMedia
    video: VideoMedia


class Gallery(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    media: TypedRelationMap[GalleryMedia] = TypedRelationMaps()


gallery = Gallery(id=1, name="My Gallery")
gallery.media["image"] = ImageMedia(id=1, name="photo", width=1920, height=1080)
gallery.media["video"] = VideoMedia(id=2, name="clip", duration=120.0)

gallery.media["image"].width  # 1920 — typed per key
gallery.media["video"].duration  # 120.0
```

Per-key validation rejects bad keys and wrong value types, and the map round-trips through
`model_dump()` / `model_validate()`. Use `total=False` on the `TypedDict` to make all keys optional.
For the full surface see the [`arcanus.association` reference](../../api/association.md).

## Access & identity

Related objects compare by identity, and a back-reference resolves to the very same instance:

```python
for book in author.books:
    assert book.author.value is author  # same object, not a copy
```

Under `NoOpMateria` access is immediate. Under a backend, access is what *triggers* a lazy load —
see [Loading Strategies](../sqlalchemy/loading.md).
