# Expressions & Cursors

The query layer — `Column`, `Expression`, `Order`, `Criteria`, `Cursor`, `Page` — is **backend
neutral**. These classes live in `arcanus.expression` and `arcanus.criteria`, not in any backend, so
you build, serialize, and round-trip a query's *shape* with no backend active. This page introduces
them under the default `NoOpMateria`; [SQLAlchemy → Querying](../sqlalchemy/querying.md) runs the same
constructs against a live database.

!!! info "What works without a backend, and what needs one"
    Building columns and expressions, serializing them with `dump()`, validating/serializing
    `Criteria`, reading `criteria.expressions`, and assembling a `Cursor` token **all run under
    `NoOpMateria`** — they are pure, backend-neutral objects. Compiling into a **native backend**
    clause (real SQL) is the part that needs a blessed provider. Under `NoOpMateria`, `expr()` uses
    a JSON compiler instead, so it returns the same neutral dict as `expr.dump()`.

## Typed columns

Index a transmuter with a field name to get a `Column` — no backend required. The running example for
this page is an `Author` / `Book` pair:

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import (
    Relation,
    RelationCollection,
    Relationship,
    Relationships,
)
from pydantic import Field
from typing import Annotated, Literal, Optional


class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    field: Literal["Physics", "History", "Science Fiction"] = "Physics"
    books: RelationCollection["Book"] = Relationships()


class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    year: int = 0
    author: Relation[Author] = Relationship()


Author["name"]  # a Column
Book["year"]  # a Column
```

!!! warning "Column element typing is WIP"
    Indexing returns `Column[Any]` today, **not** `Column[str]` / `Column[int]` — the field's element
    type isn't propagated, so a type checker can't yet flag a mistake like `Author["id"] == "oops"`.
    Carrying the field type through `Transmuter[...]` needs a generated stub (a `__class_getitem__`
    overload per field), which isn't in place yet. Runtime behavior is unaffected.

With no provider bound, the column simply carries no native backend attribute — which only matters at
compile time (below). Everything else about it works.

## Expressions are a neutral AST

Operators and methods on a `Column` build an `Expression` — a typed, backend-neutral predicate — and
`.dump()` serializes it to plain JSON:

```python
(Author["name"] == "Ada").dump()
# {"name": {"eq": "Ada"}}

(Author["name"].like("A%") & (Author["field"] == "Physics")).dump()
# {
#   "and": [
#     {"name": {"like": "A%"}},
#     {"field": {"eq": "Physics"}}
#   ]
# }

(
    (Author["name"].contains("Ada") & (Author["field"] == "Physics"))
    | ~Author["id"].in_((1, 2))
).dump()
# {
#   "or": [
#     {
#       "and": [
#         {"name": {"contains": "Ada"}},
#         {"field": {"eq": "Physics"}}
#       ]
#     },
#     {"not": {"id": {"in": [1, 2]}}}
#   ]
# }
```

### Compiling to a native clause

An expression is **not** a backend clause until it's compiled — calling it (`expr()`) asks the active
materia's compiler to translate it. **Under `NoOpMateria` the compiler is the JSON one, so `expr()`
returns the same neutral dict as `expr.dump()`:**

```python
e = Author["name"] == "Ada"
e() == e.dump()  # True — under NoOpMateria, compiling just yields the JSON form
```

A real backend supplies a native compiler instead. Under SQLAlchemy you can print the SQL it
produces:

```python
# ⚠️ SQLAlchemy-materia examples — compilation targets the backend
with materia:
    clause = (Author["name"] == "Ada")()
    print(clause)  # authors.name = :name_1

    # a compound predicate compiles in one shot
    clause = (
        (Author["name"].like("A%") & (Author["field"] == "Physics"))
        | ~Author["id"].in_((1, 2))
    )()
    print(
        clause
    )  # authors.name LIKE :name_1 AND authors.field = :field_1 OR (authors.id NOT IN (...))
```

`print(clause)` shows bind-parameter placeholders (`:name_1`); render literal SQL with
`clause.compile(compile_kwargs={"literal_binds": True})`. The operator reference below shows that
literal form for readability.

## Operators

Every operator below builds a neutral `Expression`; the comment shows the SQLAlchemy SQL it compiles
to (literal binds) once the `Author` / `Book` above are blessed onto ORM models.

### Comparison

```python
Author["name"] == "Ada"  # authors.name = 'Ada'
Author["name"] != "Ada"  # authors.name != 'Ada'
Author["id"] >= 100  # authors.id >= 100      (also <, <=, >)
```

### Text & pattern

```python
Author["name"].like("Isaac%")  # authors.name LIKE 'Isaac%'
Author["name"].ilike("isaac%")  # lower(authors.name) LIKE lower('isaac%')
Author["name"].contains("sim")  # authors.name LIKE '%' || 'sim' || '%'
Author["name"].starts_with("Isaac")  # authors.name LIKE 'Isaac' || '%'
Author["name"].ends_with("mov")  # authors.name LIKE '%' || 'mov'
```

Also available: `not_like`, `not_ilike`, `not_contains`, the case-insensitive `icontains` /
`istartswith` / `iendswith`, and `match` / `regexp_match`.

### Membership

```python
Author["id"].in_((1, 2, 3))  # authors.id IN (1, 2, 3)
Author["id"].not_in((1, 2))  # (authors.id NOT IN (1, 2))
```

### Null

```python
Author["name"].is_(None)  # authors.name IS NULL
Author["name"].is_not(None)  # authors.name IS NOT NULL
```

### Range

```python
Author["id"].between(1, 10)  # authors.id BETWEEN 1 AND 10
```

### Boolean logic

Combine any expressions with `&` (AND), `|` (OR), `~` (NOT):

```python
(Author["name"].like("A%") & (Author["field"] == "Physics")) | ~Author["id"].in_((1, 2))
# authors.name LIKE 'A%' AND authors.field = 'Physics' OR (authors.id NOT IN (1, 2))
```

### Relationship subqueries — `any` / `has`

`.any()` on a collection relationship and `.has()` on a scalar relationship compile to `EXISTS`
subqueries. The inner argument is itself any expression:

```python
# authors who wrote a book titled "Notes"
Author["books"].any(Book["title"] == "Notes")
# EXISTS (SELECT 1 FROM books, authors WHERE authors.id = books.author_id AND books.title = 'Notes')

# books whose author is named "Ada"
Book["author"].has(Author["name"] == "Ada")
# EXISTS (SELECT 1 FROM authors, books WHERE authors.id = books.author_id AND authors.name = 'Ada')

# the inner predicate can be compound
Author["books"].any(Book["title"].like("Found%") & (Book["year"] >= 1950))
# EXISTS (SELECT 1 FROM books, authors
#         WHERE authors.id = books.author_id AND books.title LIKE 'Found%' AND books.year >= 1950)
```

### Ordering

```python
Author["name"].asc()  # authors.name ASC
Author["id"].desc()  # authors.id DESC
```

See [SQLAlchemy → Querying](../sqlalchemy/querying.md) for compiling and executing these against a
database.

## Computed fields with `@provided`

A Pydantic `@computed_field` is **serialization-only by default** — it appears in `model_dump()` but
not in the query layer. Mark it with `@provided` to declare it's backed by a provider-side
expression, and it joins everything a stored column does: `Schema["name"]`, expressions, criteria,
ordering, and cursor bookmarks.

```python
from pydantic import computed_field
from arcanus import provided


class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str

    @computed_field
    @provided  # ← joins the query layer
    @property
    def slug(self) -> str:
        return self.title.lower().replace(" ", "-")

    @computed_field  # no @provided → serialization-only
    @property
    def label(self) -> str:
        return f"book:{self.title}"


Book["slug"]  # a Column — usable in expressions / criteria / ordering
(Book["slug"] == "foundation").dump()  # {"slug": {"eq": "foundation"}}
"slug" in Criteria[Book].model_fields  # True
Book["label"]  # KeyError — label is serialization-only
```

`@provided` only *declares* that the field is provider-backed; what actually backs it is the
materia's job. Under SQLAlchemy that's a same-named `hybrid_property` that compiles to SQL — see
[SQLAlchemy → Querying → Computed columns](../sqlalchemy/querying.md#computed-columns).

## Criteria — the declarative, validated shape

`Criteria[Author]` is a Pydantic model **generated from a transmuter's fields**. It validates
operator/value types, forbids unknown fields, and serializes to clean JSON — which makes it the right
thing to accept at an API boundary:

```python
from arcanus import Criteria

criteria = Criteria[Author].model_validate(
    {
        "name": {"contains": "Ada"},
        "field": {"eq": "Physics"},
        "or": [{"field": {"eq": "History"}}],
    }
)
criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
# {"name": {"contains": "Ada"}, "field": {"eq": "Physics"}, "or": [{"field": {"eq": "History"}}]}

Criteria[Author].model_json_schema(by_alias=True)  # full JSON Schema, for OpenAPI etc.
```

**Sibling fields and operators are combined with `AND` by default.** In the example above,
`name.contains` **and** `field.eq` **and** the `or` branch must all hold; multiple operators inside
one field (e.g. `{"name": {"gt": "Ada", "lt": "Grace"}}`) are `AND`ed too. Reach for the explicit
`and` / `or` / `not` keys — which nest recursively — when you need anything other than that default
conjunction. Each scalar field accepts only the operators valid for its type, and `Literal` fields
are restricted to their allowed values. To filter one layer into a relationship, use `NestedCriteria`,
which maps relationship keys to `.any()` / `.has()`.

### Validation is just Pydantic

The point of `Criteria` is that **bad filters are rejected by ordinary Pydantic validation** — there
is no custom parsing to trust. A wrong value type, an operator that doesn't apply to a field's type,
an out-of-set `Literal`, or an unknown/relationship field all raise `ValidationError`:

```python
from pydantic import ValidationError

Criteria[Author].model_validate({"id": {"lt": "not-an-int"}})  # ✗ id expects int
Criteria[Author].model_validate({"name": {"like": 123}})  # ✗ like expects str
Criteria[Author].model_validate(
    {"field": {"contains": "Phys"}}
)  # ✗ Literal field has no `contains`
Criteria[Author].model_validate(
    {"field": {"eq": "Painting"}}
)  # ✗ not an allowed Literal value
Criteria[Author].model_validate({"books": {"eq": 1}})  # ✗ unknown / association field
```

!!! tip "Built for API request bodies"
    This is what makes `Criteria` a good fit for **API boundaries**: drop `Criteria[Author]` straight
    into a request model (e.g. a FastAPI handler) and clients get validated, self-documenting filters
    — `model_json_schema()` feeds OpenAPI — with no hand-written query parsing and no way to smuggle
    in an invalid operator, value type, or field.

### With FastAPI

Type a single endpoint parameter as `Criteria[Author]` and you get rich, validated filtering in one
shot — FastAPI validates the incoming filter against the generated schema, rejects bad ones with a
422 before your code runs, and documents every operator in OpenAPI. Your handler just spreads
`.expressions` into the query:

```python
from fastapi import FastAPI
from sqlalchemy import select
from arcanus import Criteria
from arcanus.materia.sqlalchemy import Session  # SQLAlchemy materia runs the query

app = FastAPI()


@app.post("/authors/search")
def search_authors(where: Criteria[Author]) -> list[Author]:
    # `where` is already validated — an invalid filter never reaches this body
    with Session(engine) as session:
        return list(session.execute(select(Author).where(*where.expressions)).scalars())
```

A client posts, say, `{"name": {"contains": "Asimov"}, "field": {"eq": "Science Fiction"}}` and gets
fully-typed, validated filtering from one parameter — no per-field query args, no parsing, no
injection of unsupported operators.

Read `.expressions` to turn a criteria into an expression tuple — still backend-free:

```python
expressions = criteria.expressions  # tuple[Expression[bool], ...]
```

Only *compiling* or *running* those expressions needs a backend. See
[SQLAlchemy → Querying](../sqlalchemy/querying.md#criteria) for the full filtering flow against a
database.

## The two-way conversion

Expressions and criteria are the same information in two forms, bridged by `dump()` /
`model_validate()`. The whole loop is backend-neutral — only the final compile to a native clause
needs a provider:

```
Expression  ──expr.dump()──▶  JSON  ──Criteria.model_validate()──▶  Criteria
   ▲                                                                    │
   └──────────────────────  criteria.expressions  ◀─────────────────────┘
                                     │
                                     └── expr() ──▶  native clause (needs a provider)
```

This is what lets you build a query in code, ship it as JSON, accept it from a client, and rebuild it
on the other side — all without a backend in the loop.

## Cursor helpers

For stable keyset pagination, Arcanus ships pre-built helpers:

- **`Cursor[T]`** — an opaque, base64 token bundling the filter `criteria`, the `order_by`, a
  `bookmark` (keyset position after the last item), and a `limit`.
- **`Page[T]`** — an iterable result container (`items`, `total`, `next_cursor`, `has_more`) with
  `len`, indexing, iteration, and `in`.
- **`NestedCursor[T]`** — pairs with `NestedCriteria` for relationship filters in the token.

A cursor is built from expressions and decoded back to its parts (`cursor.criteria` is a `Criteria`,
`cursor.order_by` an `Ordering`, `cursor.bookmark` a `BookmarkCriteria`) — all backend-free:

```python
from arcanus import Cursor

cursor = Cursor[Author].from_expressions(
    expressions=criteria.expressions,
    bookmark=Author["id"] > 100,
    order_bys=(Author["id"].asc(),),
    limit=20,
)
decoded = Cursor[Author](str(cursor))  # round-trips the token
decoded.criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
```

Only *running* a cursor's query against data needs a backend; the full paginate-and-follow flow is
shown with the SQLAlchemy materia in
[SQLAlchemy → Querying → Cursor pagination](../sqlalchemy/querying.md#cursor-pagination).

### With FastAPI

The same pairing pays off at an API boundary: accept a validated `Criteria` plus an opaque cursor
token, and return a `Page[Author]` — `items` together with `total`, `has_more`, and the
`next_cursor` to fetch the following page. The client filters once and pages by echoing back
`next_cursor`; the criteria, ordering, and limit ride inside the token.

```python
from fastapi import FastAPI
from sqlalchemy import func, select
from arcanus import Criteria, Cursor, Page
from arcanus.materia.sqlalchemy import Session  # SQLAlchemy materia runs the query

app = FastAPI()
PAGE = 20


@app.post("/authors/page")
def page_authors(where: Criteria[Author], cursor: str | None = None) -> Page[Author]:
    # First call uses `where`; later calls just echo back the previous next_cursor.
    if cursor:
        token = Cursor[Author](cursor)  # validates the opaque token
        filters = token.criteria.expressions if token.criteria else ()
        orders, bookmark = token.order_by.orders, token.bookmark.expression
    else:
        filters, orders, bookmark = where.expressions, (Author["id"].asc(),), None

    with Session(engine) as session:
        rows = (
            session.execute(
                select(Author)
                .where(*filters, *((bookmark,) if bookmark is not None else ()))
                .order_by(*orders)
                .limit(PAGE + 1)  # +1 row reveals whether more exist
            )
            .scalars()
            .all()
        )
        items, has_more = tuple(rows[:PAGE]), len(rows) > PAGE
        total = session.execute(
            select(func.count()).select_from(Author).where(*filters)
        ).scalar_one()

    next_cursor = Cursor[Author].from_expressions(
        expressions=filters,
        bookmark=Cursor[Author].bookmark_from_item(items[-1], orders)
        if items
        else bookmark,
        order_bys=orders,
        limit=PAGE,
    )
    return Page(
        items=items, total=total, next_cursor=str(next_cursor), has_more=has_more
    )
```

`Page[Author]` is the response model, so FastAPI serializes `{items, total, next_cursor, has_more}`
and documents it in OpenAPI — and because the cursor is opaque and self-validating, an out-of-shape
token is rejected before any query runs.
