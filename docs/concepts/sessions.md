# Sessions & Async

Arcanus sessions wrap the backend's own session, blessing rows into transmuters on the way out and
syncing transmuter changes back in — while leaving transactions and atomicity to the backend.

!!! note "This page is being expanded"
    A fuller guide is on the way. The essentials are below.

## Synchronous sessions

Use `arcanus.materia.sqlalchemy.Session` in place of SQLAlchemy's native session:

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

## Asynchronous sessions

`AsyncSession` mirrors the sync API — `await` the I/O:

```python
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)
    book = Book(title="Async Book", author=Relation(author))
    session.add(book)
    await session.commit()
```

### Awaiting relationships

`await` on an association triggers its lazy load and returns the resolved value:

- `await relation` → the related object (same as `relation.value`)
- `await relation_collection` → a `list` of the related objects

```python
async with AsyncSession(async_engine) as session:
    author = await session.get_one(Author, 1)
    books = await author.books          # list[Book]

    book = await session.get_one(Book, 1)
    parent = await book.author          # Author
```

For eager strategies (`selectin`, `joined`) the data is already loaded; keeping the `await` is
recommended for consistency. With the default `lazy="select"`, the `await` is required — accessing
without it raises a greenlet error under async.

See the [`arcanus.materia.sqlalchemy` reference](../api/sqlalchemy.md).
