# Querying

This page uses the **SQLAlchemy materia** and the `Author` / `Book` / `Category` models from the
[setup](index.md#setup). It expands the backend-neutral
[expressions & cursors](../noop/querying.md) by running them against a real database — where typed
columns resolve through the provider and expressions compile to SQL.

Arcanus gives you three layers for building queries, each converting into the next:

1. **Typed columns & expressions** — `Author["name"] == "Ada"`. A backend-neutral, typed query AST
   that compiles to native SQL.
2. **Criteria** — a generated, validated, JSON-serializable filter model. Round-trips to and from
   expressions, so it is the safe shape to accept over an API.
3. **Cursors** — a signed, opaque pagination token bundling criteria, ordering, a bookmark, and a
   limit, for stable keyset pagination.

## Typed columns

Indexing a transmuter class with a field name yields a typed `Column`:

```python
Author["name"]      # Column[str]
Book["title"]       # Column[str]
Book["author"]      # Column over the relationship
```

A `Column` proxies through to the underlying ORM attribute, so it drops straight into a SQLAlchemy
`select` — no separate table/column handle to import:

```python
from sqlalchemy import select

stmt = select(Author).where(Author["name"].like("Isaac%")).order_by(Author["id"].desc())
authors = session.execute(stmt).scalars().all()
```

## Expressions

Operators and methods on a `Column` build an Arcanus **`Expression`** — a typed, backend-neutral
description of a predicate:

```python
Author["name"] == "Ada"            # eq
Author["id"].in_((1, 2, 3))         # in
Author["name"].like("Isaac%")       # like / ilike / starts_with / ends_with / contains
Author["id"] >= 100                 # lt / le / gt / ge
Author["name"].is_(None)            # is_ / is_not
```

Combine them with `&` (and), `|` (or), and `~` (not):

```python
expr = (Author["name"].contains("Ada") & (Author["field"] == "Physics")) | ~Author["id"].in_((1, 2))
```

For relationship predicates, use `.any()` (collections) and `.has()` (scalars):

```python
# Authors who wrote a book titled "Notes"
Author["books"].any(Book["title"] == "Notes")

# Books whose author is named "Ada"
Book["author"].has(Author["name"] == "Ada")
```

Order with `.asc()` / `.desc()`, which produce `Order` objects. Expressions and orders drop straight
into a native `select`:

```python
from sqlalchemy import select

authors = session.execute(
    select(Author)
    .where(Author["field"] == "Physics")
    .order_by(Author["name"].asc(), Author["id"].desc())
).scalars().all()
```

### Expressions ⇄ native (materia) expressions

An Arcanus expression is **not** a SQLAlchemy clause until it is compiled. Calling it asks the active
materia's expression compiler to translate it into the backend's native form:

```python
with Session(engine):                       # a materia must be active to compile
    native = (Author["name"] == "Ada")()    # → a SQLAlchemy BinaryExpression
```

You rarely call this yourself: dropping an expression into `select(...).where(...)` compiles it for
you (so does a session helper's `expressions=` — see [Session Helpers](session.md)). Keeping the
expression backend-neutral until the last moment is what lets the same query AST target a different
materia later.

### Computed columns

A Pydantic `@computed_field` marked with `@provided` is backed by a provider-side expression (e.g. a
SQLAlchemy `hybrid_property`) and behaves like a plain column end to end — filterable, orderable, and
usable in cursors:

```python
from pydantic import computed_field
from arcanus import provided

@materia.bless(BookModel)
class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str

    @computed_field
    @provided                       # ← declares a backing provider expression
    @property
    def slug(self) -> str:
        return self.title.lower().replace(" ", "-")

Book["slug"] == "foundation"         # usable in expressions / criteria / order_by
```

A computed field *without* `@provided` stays serialization-only and is invisible to criteria,
`Book["…"]`, and ordering.

## Criteria

`Criteria[Author]` is a Pydantic model **generated from the transmuter's fields**. It validates
operator/value types, forbids unknown fields, and serializes to clean JSON — making it the shape to
accept from an untrusted client, instead of letting callers build raw expressions.

```python
from arcanus import Criteria

criteria = Criteria[Author].model_validate(
    {
        "name": {"contains": "Ada"},
        "field": {"eq": "Physics"},
        "not": {"id": {"in": [1, 2]}},
    }
)
```

The `and` / `or` / `not` keys nest recursively; each scalar field accepts the operators valid for its
type (`eq`, `ne`, `in`, `lt`/`le`/`gt`/`ge`, `like`, `contains`, `starts_with`, `is_null`, …).
`Literal` fields are restricted to their allowed values.

To use a criteria in a query, read its `.expressions` (a tuple of expressions, compiled against the
active materia) and spread it into a native `select`:

```python
from sqlalchemy import func, select

with Session(engine) as session:
    authors = session.execute(
        select(Author).where(*criteria.expressions)
    ).scalars().all()
    total = session.execute(
        select(func.count()).select_from(Author).where(*criteria.expressions)
    ).scalar_one()
```

(The [session helpers](session.md) take the tuple directly, e.g.
`session.list(Author, expressions=criteria.expressions)`.)

### Filtering across relationships

`Criteria[Author]` only covers scalar fields. To filter one layer into a relationship, use
`NestedCriteria`, which adds the relationship fields and compiles them to `.any()` / `.has()`:

```python
from arcanus import NestedCriteria

criteria = NestedCriteria[Author].model_validate(
    {
        "name": {"eq": "Ada"},
        "books": {"title": {"eq": "Notes"}},   # one layer into the relationship
    }
)
with Session(engine) as session:
    authors = session.execute(
        select(Author).where(*criteria.expressions)
    ).scalars().all()
```

### The two-way conversion

Expressions and criteria are the same information in two forms, and `dump()` / `model_validate()`
bridge them. This lets you build a query in code, ship it as JSON, and rebuild it on the other side —
or accept JSON and turn it into native SQL.

```python
import json
from arcanus import Criteria

with Session(engine):
    expr = (Author["name"].contains("Ada") & (Author["field"] == "Physics"))

    payload = expr.dump()                              # Expression → plain dict/JSON
    # {"and": [{"name": {"contains": "Ada"}}, {"field": {"eq": "Physics"}}]}

    criteria = Criteria[Author].model_validate(payload)  # JSON → validated Criteria
    rebuilt = criteria.expressions                       # Criteria → Expression tuple
    # rebuilt[…]() would compile back to native SQLAlchemy
```

So the full loop is:

```
Expression  ──expr.dump()──▶  JSON  ──Criteria.model_validate()──▶  Criteria
   ▲                                                                    │
   └──────────────────────  criteria.expressions  ◀─────────────────────┘
                                     │
                                     └── expr() ──▶  native SQLAlchemy clause
```

## Cursor pagination

A `Cursor` is an opaque, base64 token that carries everything needed to fetch the next page: the
filter `criteria`, the `order_by`, a `bookmark` (the keyset position after the last item), and a
`limit`. It enables stable keyset pagination that doesn't drift when rows are inserted, unlike
offset paging.

### Building the first page

```python
from arcanus import Cursor, Page

criteria = Criteria[Author].model_validate({"field": {"eq": "Science Fiction"}})
orders = (Author["id"].asc(),)
limit = 20

with Session(engine) as session:
    total = session.execute(
        select(func.count()).select_from(Author).where(*criteria.expressions)
    ).scalar_one()

    # Fetch one extra row to detect whether more pages exist.
    # Arcanus Expression/Order objects drop into native where()/order_by() directly.
    items = session.execute(
        select(Author).where(*criteria.expressions).order_by(*orders).limit(limit + 1)
    ).scalars().all()
    page_items = tuple(items[:limit])
    has_more = len(items) > limit

    # The bookmark is the keyset position derived from the last item on the page
    bookmark = Cursor[Author].bookmark_from_item(page_items[-1], orders)
    cursor = Cursor[Author].from_expressions(
        expressions=criteria.expressions,
        bookmark=bookmark,
        order_bys=orders,
        limit=limit,
    )

    page = Page(
        items=page_items,
        total=total,
        next_cursor=str(cursor),
        has_more=has_more,
    )
```

`Page` is an iterable container (`len`, indexing, iteration, `in`) over `items`, plus `total`,
`next_cursor`, and `has_more`.

### Following a cursor

Decode the token, recover its parts, and run the next query — appending the bookmark expression to
the original criteria:

```python
with Session(engine) as session:
    decoded = Cursor[Author](page.next_cursor)

    bookmark_expression = decoded.bookmark.expression       # keyset predicate, or None
    items = session.execute(
        select(Author)
        .where(
            *decoded.criteria.expressions,                  # original filter
            *((bookmark_expression,) if bookmark_expression is not None else ()),
        )
        .order_by(*decoded.order_by.orders)                 # Ordering → Order tuple
        .limit((decoded.limit or 0) + 1)
    ).scalars().all()
```

The cursor's pieces are all part of the same two-way design:

- `decoded.criteria` is a `Criteria[Author]`; `.expressions` compiles it back to expressions.
- `decoded.bookmark` is a `BookmarkCriteria`; `.expression` gives the keyset predicate.
- `decoded.order_by` is an `Ordering`; `.orders` gives back the `Order` tuple.

For filtering across relationships in the token, use `NestedCursor`, which pairs with
`NestedCriteria` the same way `Cursor` pairs with `Criteria`.
