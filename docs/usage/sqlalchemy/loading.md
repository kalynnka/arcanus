# Loading Strategies

This page uses the **SQLAlchemy materia** and the `Author` / `Book` / `Category` models from the
[setup](index.md#setup). Loading strategies are what the backend-free
[relationships](../noop/relationships.md) gain once a database is behind them.

Arcanus **never reads a relationship during validation** — a relationship field validates into a
deferred association that records *how* to load, not the loaded data. The query fires only when you
access the field, and it honors whatever loading strategy you configured on the ORM model or
attached to the query. This is what keeps a transmuter from triggering the accidental N+1 that
"just validate the ORM object" approaches fall into (see
[the validation-triggers-lazy-load trap](../../index.md#the-validation-triggers-lazy-load-trap)).

Because loading is the backend's job, the *strategy* is configured with SQLAlchemy's own mechanisms.
Arcanus only makes the typed `Column` references usable wherever SQLAlchemy expects an attribute.

## Strategy on the ORM model

Set the default strategy with `lazy=` on the `relationship()`. Arcanus respects it as-is.

```python
from sqlalchemy.orm import Mapped, relationship

class BookModel(Base):
    # "select" (default): emit a SELECT on first access
    author: Mapped[AuthorModel] = relationship(lazy="select", back_populates="books")

    # "selectin": batch-load related rows in a second SELECT ... IN (...)
    # author: Mapped[AuthorModel] = relationship(lazy="selectin", back_populates="books")

    # "joined": load via an outer JOIN in the same query
    # author: Mapped[AuthorModel] = relationship(lazy="joined", back_populates="books")

    # "raise": forbid loading — accessing the relationship raises instead of querying
    # author: Mapped[AuthorModel] = relationship(lazy="raise", back_populates="books")
```

| `lazy=` | When related rows load | Good for |
|---------|------------------------|----------|
| `"select"` (default) | on first access, one query each | small graphs, uncertain access |
| `"selectin"` | up front, one batched `IN` query per level | collections you'll iterate |
| `"joined"` | up front, via outer join in the same query | many-to-one you always need |
| `"subquery"` | up front, via a correlated subquery | legacy alternative to `selectin` |
| `"raise"` | never — raises on access | catching unintended lazy loads |

The strategy chosen on the model is the *default*; any query can override it per-statement.

## Strategy per query

Arcanus re-exports SQLAlchemy's loader options from `arcanus.materia.sqlalchemy`, wrapped so they
accept Arcanus's typed `Column` references (e.g. `Author["books"]`) in addition to native attributes.
Pass them via the `options=` argument of the session helpers, or `.options(...)` on a `select`.

```python
from sqlalchemy import select
from arcanus.materia.sqlalchemy import (
    selectinload, joinedload, raiseload, load_only, defer, contains_eager,
)

with Session(engine) as session:
    # Eager-load a collection for the whole result set (avoids N+1 on iteration)
    authors = session.execute(
        select(Author).options(selectinload(Author["books"]))
    ).scalars().all()
    for author in authors:
        for book in author.books:        # already loaded — no extra query
            ...

    # Eager-load a many-to-one via JOIN (native get accepts options=)
    book = session.get_one(Book, 1, options=[joinedload(Book["author"])])

    # Forbid a lazy load on this query — access raises instead of querying
    book = session.get_one(Book, 1, options=[raiseload(Book["categories"])])

    # Column-level: only fetch some columns, or defer an expensive one
    authors = session.execute(
        select(Author).options(load_only(Author["name"]))
    ).scalars().all()
    books = session.execute(
        select(Book).options(defer(Book["title"]))
    ).scalars().all()
```

Loader options chain for nested paths, exactly as in SQLAlchemy:

```python
# Load each author's books, and each book's categories, in batched queries
authors = session.execute(
    select(Author).options(selectinload(Author["books"]).selectinload(Book["categories"]))
).scalars().all()
```

(The same `options=` also works on the [session helpers](session.md), e.g.
`session.list(Author, options=[selectinload(Author["books"])])`.)

Other re-exported options: `lazyload`, `subqueryload`, `noload`, `undefer`, `defaultload`,
`contains_eager`, plus `selectin_polymorphic` and `with_polymorphic` for polymorphic hierarchies.
See the [`arcanus.materia.sqlalchemy` reference](../../api/sqlalchemy.md).

## Async and awaiting relationships

Under `AsyncSession`, **how** you access a relationship depends on its strategy — because a lazy load
is I/O, and I/O must be awaited.

`await` on an association triggers its load and returns the resolved value:

- `await relation` → the related object (same as `relation.value`)
- `await relation_collection` → a `list` of the related objects

```python
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)

    books = await author.books          # awaits the lazy load → list[Book]
    for book in author.books:           # already resolved — plain iteration
        ...

    book = await session.get_one(Book, 1)
    parent = await book.author          # → Author
    assert parent is book.author.value  # second access needs no await
```

!!! warning "Lazy access without `await` is a hard error under async"
    With the default `lazy="select"`, touching a relationship **without** awaiting it emits SQL
    outside the greenlet and raises a `MissingGreenlet` error — it does not silently block. For
    eager strategies (`selectin`, `joined`) the data is already loaded so no I/O happens, but
    keeping the `await` is recommended for consistency across strategies.

The fix for an unexpected greenlet error is almost always to eager-load with `selectinload` /
`joinedload` on the query, or to `await` the access.
