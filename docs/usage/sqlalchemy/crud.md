# CRUD & Relationships

This page uses the **SQLAlchemy materia** and the `Author` / `Book` / `Category` models from the
[setup](index.md#setup). It expands the backend-free [relationships](../noop/relationships.md) and
[partial schemas](../noop/schemas.md) with persistence. Every object that goes in or comes out of the
session is a transmuter — a validated Pydantic object wrapping its ORM row — so you read and write
the same object you query.

!!! note "Lifecycle follows SQLAlchemy"
    Under the SQLAlchemy materia, a transmuter's lifecycle **is** its ORM row's lifecycle: it
    becomes pending on `add`, persistent on `flush`/`commit`, and is detached/expired exactly when
    the session says so. There is no separate "save the Pydantic object" step. See
    [object lifecycle](../../concepts/lifecycle.md#lifecycle-under-the-sqlalchemy-materia).

## Create

Construct a transmuter, `add` it, and `flush` to hit the database. Server-generated values (such as
an autoincrement `id`) are written to the row at flush time and **synced back onto the transmuter
automatically** — read them straight after the flush, no manual step.

```python
with Session(engine) as session:
    author = Author(name="Isaac Asimov")
    session.add(author)
    session.flush()  # INSERT; id assigned on the row and synced to `author`
    print(author.id)  # e.g. 1
    session.commit()
```

!!! info "What syncs automatically — and what still needs `refresh()`"
    An `after_flush` hook re-validates each freshly **inserted** transmuter against its row, so the
    autoincrement `id` (and any value the `INSERT` returns) appears without a manual step — including
    the implicit flush inside `commit()`. Updates are **not** re-validated: values you set are
    already on the transmuter via write-through, so only an insert's server-assigned values need
    syncing. Loaded relationships are re-deferred by the insert re-validation but reload without a
    query, since the row stays loaded.

    The autoincrement key arrives via `cursor.lastrowid` on every backend. *Other* server-side
    columns (a `server_default`, a server `onupdate`) only ride along when the dialect fetches them
    at flush — via `RETURNING` (PostgreSQL/SQLite) or `eager_defaults`. For a server-side `onupdate`,
    or any value the database changed after the row was expired, fall back to
    `session.refresh(author)`. `author.revalidate()` is the same full re-validation done by hand.

## Read

Reads are plain SQLAlchemy — `session.get` for primary keys, `session.execute(select(...))` for
everything else — only the results come back as transmuters. Typed column references
(`Author["name"]`) drop straight into a `select`:

```python
from sqlalchemy import func, select

with Session(engine) as session:
    # By primary key
    author = session.get(Author, 1)  # None if missing
    author = session.get_one(Author, 1)  # raises NoResultFound if missing

    # Single row by filter
    author = session.execute(select(Author).filter_by(name="Isaac Asimov")).scalar_one()
    maybe = session.execute(
        select(Author).filter_by(name="Nobody")
    ).scalar_one_or_none()

    # First row under an ordering
    newest = (
        session.execute(select(Author).order_by(Author["id"].desc())).scalars().first()
    )

    # Many rows, with filter + ordering + pagination
    authors = (
        session.execute(
            select(Author)
            .where(Author["name"].like("Isaac%"))
            .order_by(Author["name"].asc())
            .limit(10)
            .offset(0)
        )
        .scalars()
        .all()
    )

    # Count matching rows
    total = session.execute(
        select(func.count()).select_from(Author).where(Author["name"].like("Isaac%"))
    ).scalar_one()
```

!!! tip "Typed shortcuts for these reads"
    Arcanus adds typed helpers that collapse the patterns above into one call — `one`,
    `one_or_none`, `first`, `list`, `count` — plus `bulk` (several by primary key, order preserved)
    and `partitions` (chunked streaming), which have no tidy native one-liner. See
    [Session Helpers](session.md). `Author["name"]`, the operators, and ordering are covered in
    [Querying](querying.md).

## Update

Mutate the transmuter and commit. Writes sync to the wrapped ORM row in place — no `model_dump()`,
no re-construction.

```python
with Session(engine) as session:
    book = session.get_one(Book, 1)
    book.title = "Foundation (Revised)"  # synced to the ORM row immediately
    session.commit()
```

For set-based updates, use a SQLAlchemy `update()` with `RETURNING`; the returned rows come back as
transmuters:

```python
from sqlalchemy import update

stmt = (
    update(Book).where(Book["author_id"] == 1).values(title="Reissue").returning(Book)
)
reissued = session.execute(stmt).scalars().all()
session.commit()
```

## Delete

```python
with Session(engine) as session:
    author = session.get_one(Author, 1)
    session.delete(author)  # related rows follow your ORM cascade rules
    session.commit()
```

Bulk delete with `RETURNING` works the same way:

```python
from sqlalchemy import delete

stmt = delete(Book).where(Book["author_id"] == 1).returning(Book)
deleted = session.execute(stmt).scalars().all()
session.commit()
```

## Relationship CRUD

Relationships are first-class transmuter fields. You assign and mutate them with the same objects
you query, and Arcanus cascades them into the session the way SQLAlchemy does. See
[Relationships](../noop/relationships.md) for every association type.

### Many-to-one — assign a parent

`Relation[T]` holds a single related transmuter. Adding the child cascades the parent in:

```python
with Session(engine) as session:
    author = Author(name="Isaac Asimov")
    book = Book(title="Foundation", author=Relation(author))

    session.add(book)  # adding the book also adds its author
    session.flush()
    author.revalidate()
    book.revalidate()
    session.commit()

    # Reassign later
    other = Author(name="Arthur C. Clarke")
    book.author.value = other
    session.commit()
```

### One-to-many — manage a collection

`RelationCollection[T]` behaves like a `list`. Append, extend, remove, pop, clear:

```python
with Session(engine) as session:
    author = session.get_one(Author, 1)

    author.books.append(Book(title="I, Robot"))
    author.books.extend(
        [Book(title="Caves of Steel"), Book(title="The Gods Themselves")]
    )

    for book in author.books:  # loads on access
        assert book.author.value is author  # back-reference, same instance

    author.books.remove(author.books[0])
    session.commit()
```

### Many-to-many — both sides are collections

A `secondary` relationship is just a collection on each side; assign in whichever direction reads
best:

```python
with Session(engine) as session:
    book = session.get_one(Book, 1)
    sci_fi = Category(name="Science Fiction")

    book.categories.append(sci_fi)  # link from the book side
    # sci_fi.books.append(book)               # …or from the category side — same link

    session.commit()
```

## Partial models for API boundaries

Every transmuter exposes generated `Create` and `Update` partials, plus `shell()` and `absorb()` to
move between a partial and a full transmuter. These are ideal at HTTP boundaries where you accept
untrusted, incomplete payloads. For a full FastAPI walkthrough — CRUD, filtering, and pagination —
see [Working with FastAPI](fastapi.md).

```python
# Create: excludes *generated* identities (the server assigns them); a natural/composite
# key declared Identity(server_side=False) stays in Create for the client to supply.
payload = Author.Create(name="New Author")
author = Author.shell(payload)  # a full transmuter, not yet persisted

with Session(engine) as session:
    session.add(author)
    session.flush()
    author.revalidate()
    session.commit()

# Update: excludes frozen (write-once) fields, applies only what's set
with Session(engine) as session:
    author = session.get_one(Author, 1)
    author.absorb(Author.Update(name="Renamed Author"))
    session.commit()
```

The read/response shape is the transmuter itself — there is no separate `Read` partial. A field
marked `Field(exclude=True)` (e.g. a password) is dropped from `model_dump()` (and any serialized
response) while staying a real, writable, attribute-readable field in the backend. See
[Partial Schemas](../noop/schemas.md) for the full set of pydantic-native flags.

## Serializing relationships & reference cycles

`model_dump()` (and `model_dump_json()`) include whatever relationships are loaded. Bidirectional
relationships are inherently cyclic — a parent's children point back at the parent, and a
back-reference resolves to the *same* instance (`book.author.value is author`). After a flush the
inserted rows are revalidated so server-assigned values sync back, which marks the relationships on
*both* sides as loaded — and a finite JSON tree cannot represent that cycle.

Arcanus handles it with **tree projection**: while dumping it tracks the transmuters on the current
serialization stack, and when a relationship points back at one that is already an *ancestor* it cuts
that edge instead of recursing into it.

```python
with Session(engine) as session:
    author = Author(name="Isaac Asimov")
    author.books.append(Book(title="Foundation"))
    session.add(author)
    session.flush()  # both directions now loaded

    author.model_dump()
    # {
    #     "id": 1, "name": "Isaac Asimov",
    #     "books": [
    #         {"id": 1, "title": "Foundation",
    #          "author_id": 1,     # foreign-key scalar — kept
    #          "author": None},    # relationship back-edge — cut
    #     ],
    # }
```

The cut is lossless in practice: only the relationship *object* is dropped, while the foreign-key
scalar (`author_id`) still serializes, so the parent stays identifiable. It is ancestor-scoped, not a
global de-duplication — an object reached twice *without* forming a cycle (a "diamond") is serialized
in full both times; only an edge that would close a cycle is cut. For collections, the cyclic element
is dropped from the list or dict.

!!! note "Excluding a relationship explicitly"
    To drop a relationship from the output regardless of cycles, use Pydantic's standard `exclude` —
    `author.model_dump(exclude={"books": {"__all__": {"author"}}})`.

## Async

Swap `Session` for `AsyncSession` and `await` the I/O — the API is otherwise identical. Awaiting a
relationship triggers its lazy load; see [Loading Strategies](loading.md#async-and-awaiting-relationships)
and [Lifecycle & Async](../../concepts/lifecycle.md).

```python
from sqlalchemy.ext.asyncio import create_async_engine
from arcanus.materia.sqlalchemy import AsyncSession

async with AsyncSession(create_async_engine("sqlite+aiosqlite://")) as session:
    author = await session.get_one(Author, 1)
    books = await author.books  # awaits the lazy load → list[Book]

    session.add(Book(title="Async Book", author=Relation(author)))
    await session.commit()
```
