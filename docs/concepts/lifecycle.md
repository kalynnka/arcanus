# Lifecycle & Async

A transmuter does not own an independent lifecycle — it **follows its backend**. How that lifecycle
is managed differs by materia, and not every materia has a session at all. This page covers the
shared model, the SQLAlchemy session that concretizes it, and where async fits.

!!! note "This page is being expanded"
    A fuller guide is on the way. The essentials are below.

## The transmuter follows its backend

Arcanus never fights the backend's own ownership and transaction semantics. So a transmuter's
lifetime is governed by whatever the backend uses to manage records:

- **No backend (`NoOpMateria`)** — there is **no session**. A transmuter is an ordinary Python
  object: it lives while referenced and is garbage-collected when nothing holds it. Nothing to open,
  flush, or close.
- **A database (`SqlalchemyMateria`)** — a **session** owns the underlying provided instance and
  moves it through *pending → persistent → expired/detached*; the transmuter rides along. See
  [object lifecycle under the SQLAlchemy materia](materia.md#lifecycle-under-the-sqlalchemy-materia).

The rest of this page is therefore **materia-specific** where it talks about a session.

## SQLAlchemy sessions

Use `arcanus.materia.sqlalchemy.Session` in place of SQLAlchemy's native session — it blesses rows
into transmuters on the way out and syncs changes back in, while leaving transactions to SQLAlchemy:

```python
from arcanus.materia.sqlalchemy import Session

with Session(engine) as session:
    author = session.get_one(Author, 1)   # a transmuter, not a raw ORM row
    author.name = "Updated"
    session.commit()
```

Convenience helpers: `get` / `get_one`, `one` / `one_or_none`, `first`, `list`, `bulk`, `count`,
`partitions`. Server-generated values (autoincrement ids) are pulled into a transmuter with
`revalidate()` after `flush`.

`AsyncSession` mirrors the sync API — `await` the I/O:

```python
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)
    book = Book(title="Async Book", author=Relation(author))
    session.add(book)
    await session.commit()
```

## Async is about backend I/O

A transmuter is mostly a **synchronous** object — validation, construction, field access, and
mutation run inline, just like the plain Pydantic model underneath. Async enters only where the
**backend does I/O**, which is almost entirely **relationship loading**. So the relationship
associations are made *awaitable*: awaiting one ensures its data is loaded from the backend (loading
only if not already present) and returns the resolved value.

- `await relation` → the related object (same as `relation.value`)
- `await relation_collection` → a `list` of the related objects

```python
async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)
    books = await author.books          # list[Book]

    book = await session.get_one(Book, 1)
    parent = await book.author          # Author
```

Whether the `await` is *required* depends on the backend's loading strategy. With SQLAlchemy's
default `lazy="select"`, a lazy load triggered outside a coroutine raises a greenlet error, so the
`await` is required; for eager strategies (`selectin`, `joined`) the data is already loaded and the
`await` is optional but recommended for consistency. In-memory backends like `NoOpMateria` never do
I/O, so association access is purely synchronous there.

See the [`arcanus.materia.sqlalchemy` reference](../api/sqlalchemy.md) and
[Loading Strategies](../usage/sqlalchemy/loading.md).
