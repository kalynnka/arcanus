# Relationships

Arcanus models relationships with **association types**. They work across every materia backend and
respect the backend's lazy loading — related objects load on access, not during validation.

!!! note "This page is being expanded"
    A fuller guide with end-to-end examples is on the way.

## Association types

| Association | Relationship | Container | Example |
|-------------|--------------|-----------|---------|
| `Relation[T]` | one-to-one / many-to-one | single value | `author: Relation[Author]` |
| `RelationCollection[T]` | one-to-many / many-to-many | `list[T]` | `books: RelationCollection[Book]` |
| `RelationSet[T]` | many-to-many (unique) | `set[T]` | `tags: RelationSet[Tag]` |
| `RelationMap[K, T]` | keyed (homogeneous) | `dict[K, T]` | `settings: RelationMap[str, Setting]` |
| `TypedRelationMap[TD]` | keyed (heterogeneous) | `dict` via `TypedDict` | `media: TypedRelationMap[MediaFiles]` |

## Field helpers

Default factories keep field declarations terse:

| Helper | Creates |
|--------|---------|
| `Relationship()` | `Field(default_factory=Relation, frozen=True)` |
| `Relationships()` | `Field(default_factory=RelationCollection, frozen=True)` |

```python
class Author(BaseTransmuter):
    books: RelationCollection["Book"] = Relationships()

class Book(BaseTransmuter):
    author: Relation[Author] = Relationship()
```

## Access & identity

```python
for book in author.books:            # loads on access
    assert book.author.value is author   # same instance — identity preserved
```

For loading strategies under async, see [Sessions & Async](sessions.md). For the full API, see the
[`arcanus.association` reference](../api/association.md).
