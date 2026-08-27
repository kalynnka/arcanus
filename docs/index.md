# Why Arcanus

**Arcanus** is a small library that binds [Pydantic](https://docs.pydantic.dev/) schemas to your
datasource. The idea is to let you work with one set of typed, validated objects that are backed by
your real backend records — so the templates, factories, and converters that usually sit between
*validation* and *persistence* mostly fall away. If that boilerplate has bothered you too, this is
the approach Arcanus takes to it.

!!! warning "Work in progress"
    Arcanus is at an early, minimum-viable stage. Expect bugs, breaking changes, and incomplete
    features. SQLAlchemy is currently the only supported backend.

## One object, not two

This is the core idea, and the one that shapes everything else. Normally a Pydantic-plus-ORM
codebase keeps **two** representations of every entity: an ORM instance for persistence and a
schema instance for validation and API boundaries. You spend real effort moving between them 
`Schema.model_validate(orm_obj)` one way, `Model(**schema.model_dump())` the other and you have
to remember, at every function boundary, *which* of the two you are holding. A function that takes
"a user" might mean either; the type system gives you `UserModel | UserSchema` and the bugs that
come with it.

A `Transmuter` collapses the two into **one** object. It *is* a validated Pydantic object, and it
*wraps* the backing provided instance rather than copying out of it — so there is a single type to
pass around, with both validation and persistence behind it.

!!! info "Examples use the SQLAlchemy materia"
    Transmuters are backend-agnostic — with the default `NoOpMateria` they behave like plain
    Pydantic models, no backend at all. The code on this page illustrates the ideas with the
    **SQLAlchemy materia** (and its `Session`) because that's where binding to real records pays
    off. See [Pick a Materia](usage/index.md) for each backend's setup.

**1. Start from your SQLAlchemy model — plain, untouched.**

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase): ...


class AuthorModel(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
```

**2. Bless a transmuter with the model** — the ORM model is the hat put on the transmuter.

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.materia.sqlalchemy import SqlalchemyMateria
from pydantic import Field
from typing import Annotated, Optional

materia = SqlalchemyMateria()


@materia.bless(AuthorModel)
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
```

**3. Open a session and bring objects back** with a normal `select`.

!!! warning "This `Session` is arcanus's"
    Import `Session` from `arcanus.materia.sqlalchemy`, not SQLAlchemy's own — it's what blesses ORM
    rows into transmuters as they come out of queries.

```python
from sqlalchemy import create_engine, select
from arcanus.materia.sqlalchemy import Session

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)

with Session(engine) as session:
    session.add(Author(name="Isaac Asimov"))
    session.commit()

    author = session.execute(
        select(Author).where(Author["name"].like("Isaac%"))  # typed column, same object
    ).scalar_one()
```

**4. It's one object** — a validated Pydantic model *and* a transmuter wrapping the ORM row.

```python
isinstance(author, Author)  # ✅ a Pydantic model — validated, typed
isinstance(author, BaseTransmuter)  # ✅ and a transmuter
author.__transmuter_provided__  # the underlying AuthorModel ORM instance, if you need it

author.name = "Arthur C. Clarke"  # mutate the transmuter…
author.__transmuter_provided__.name  # …and the ORM object already reflects it — no model_dump()
```

What this buys you:

- **No conversion layer.** Reads and writes go through the transmuter and sync to the ORM object
  in place; there is no `model_dump()` / re-construct round-trip and no parallel set of factory
  functions to maintain.
- **One type at every boundary.** Functions accept and return `Author`, never "ORM-or-schema". The
  ambiguity — and the defensive `isinstance` checks it breeds — simply goes away.
- **Identity semantics that match the ORM.** Transmuters compare by identity (`is`, an `id()`-based
  hash), not by field values. The same row resolves to the *same* transmuter within a session, so a
  transmuter is hashable, usable in sets/dict keys, and aligned with SQLAlchemy's identity map
  instead of triggering expensive deep value comparisons.
- **Typed column references for queries.** `Author["name"]` yields a typed column, so query building
  stays on the same object: `select(Author).where(Author["name"].like("Isaac%"))` — no separate
  table/column handle to import.
- **Attribute pass-through.** Anything not mapped as a transmuter field falls through to the wrapped
  provided instance, so ORM-only attributes and methods remain reachable without unwrapping.
- **Lightweight variant.** When a full `BaseModel` is more than you need, the
  [`@dataclass`](concepts/transmuters.md) decorator gives the same transmuter behavior on a Pydantic
  dataclass.

## The schema ↔ persistence gap

Most applications keep two parallel object worlds: Pydantic models for validation and API
boundaries, and ORM models for storage. Keeping them in sync means writing conversion utilities,
factory functions, and mapping boilerplate — over and over.

[**SQLModel**](https://sqlmodel.tiangolo.com/) tackles this same gap, but by *fusing* the two:
a single class is both the Pydantic model **and** the ORM table. That coupling is convenient until
your validation schema and your storage schema need to differ — at which point one definition has
to serve two masters.

Arcanus takes the opposite stance: **bind, don't fuse**. Your SQLAlchemy models stay exactly as
they are, your validation schema stays a separate concern, and a *transmuter* is bound to an
existing ORM model with `bless()`:

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.materia.sqlalchemy import SqlalchemyMateria
from pydantic import Field
from typing import Annotated, Optional

materia = SqlalchemyMateria()


@materia.bless(AuthorModel)  # bind to an existing ORM model
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
```

The two schemas evolve independently; Arcanus keeps them in sync at the boundary.

!!! info "Why `bless`?"
    The name is borrowed from Perl. There, every object is just an ordinary data structure with a
    "hat" on it — `bless` is the operator that associates a plain reference with a package, turning
    bare data into an object of that class without changing the data itself. Arcanus reuses the
    word for exactly that pattern: just as Perl's `bless $ref, $package` puts the *package* hat on
    a plain reference, `@materia.bless(AuthorModel)` puts the *ORM model* hat on a transmuter. It is
    composition, not inheritance — the transmuter stays a plain validated structure; blessing simply
    gives it a backend identity on top.

## Relationships & lazy loading

Relationships are first-class on transmuters — one-to-one, one-to-many, many-to-many, keyed maps —
and they **respect the backend's lazy loading**. Related rows are not eagerly materialized during
validation; they load when you access them, the way SQLAlchemy intends.

```python
for book in author.books:  # loads on access, not during validation
    print(book.title, book.author.value is author)  # identity preserved
```

### The validation-triggers-lazy-load trap

This is the single hardest part of putting Pydantic in front of an ORM, and the reason naïve
"just validate the ORM object" approaches fall apart at scale.

Pydantic validates **eagerly**: to build a model from an ORM object (`from_attributes=True`), it
*reads every mapped field*, including relationship attributes. But on a SQLAlchemy model a
relationship attribute is a lazy loader — touching `author.books` **emits a SQL query**. So the act
of validation alone walks the entire object graph and fires a query per relationship, per row:

```python
authors = session.scalars(select(AuthorModel)).all()  # 1 query
for a in authors:
    AuthorSchema.model_validate(a)  # each validation reads a.books -> +1 query each
# → classic N+1: 1 + N queries, none of which you asked for
```

It gets worse: validation recurses, so validating each `Book` would touch `book.author`, which
re-reads the parent, and so on — an eager traversal of data you may never use, plus a thicket of
queries. Under async it isn't merely slow — a lazy load triggered outside a coroutine raises a
greenlet error outright, so eager validation *breaks*.

Arcanus sidesteps this by **never reading a relationship during validation**. A relationship field
is validated into a deferred association — a placeholder that records *how* to load, not the loaded
data. The query fires only when you actually access `author.books`, and only then, honoring whatever
loading strategy (`selectinload`, `joinedload`, `lazy="select"`, …) you configured on the ORM model.
No accidental N+1, no surprise traversal, and async stays safe.

See [Relationships](usage/noop/relationships.md).

## Async support

A transmuter is, for the most part, a **synchronous** object — validation, construction, field
access, and mutation all run inline, exactly like the plain Pydantic model underneath it. There is
nothing to `await` there.

Async only enters where the **backend actually does I/O**, and that's almost entirely about
**relationship loading**. So Arcanus makes the relationship associations *awaitable*: awaiting an
association *ensures* its data is loaded from the backend — it loads only if not already present —
and then hands you the result.

- `await relation` → the related object (same as `relation.value`)
- `await relation_collection` → a `list` of the related objects

```python
# SQLAlchemy-materia example — AsyncSession is provided by the SQLAlchemy backend
async with AsyncSession(engine) as session:
    author = await session.get(Author, 1)  # native session.get → I/O, so await
    books = await author.books  # awaits the lazy load → list[Book]

    for book in author.books:  # already loaded → plain sync iteration
        print(book.title)
```

Whether the `await` is *required* depends on the backend's strategy (under SQLAlchemy's default
`lazy="select"`, a lazy load triggered outside a coroutine raises a greenlet error). Backends that hold all
data in memory — like the default `NoOpMateria` — never do I/O, so relationship access there is
purely synchronous; the awaitable form still works for API consistency.

See [Lifecycle & Async](concepts/lifecycle.md) and [Loading Strategies](usage/sqlalchemy/loading.md).

## Where to next

<div class="grid cards" markdown>

- :material-rocket-launch: **[Quickstart](quickstart.md)** — define your first transmuter and run CRUD in minutes.
- :material-database-edit: **[Usage](usage/index.md)** — pick a materia, then CRUD, loading strategies, and querying in depth.
- :material-cog: **[The Materia System](concepts/materia.md)** — how binding works and the design philosophy behind it.
- :material-book-open-variant: **[API Reference](api/index.md)** — the full public API.

</div>
