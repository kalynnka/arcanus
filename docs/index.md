# Why Arcanus

**Arcanus** binds [Pydantic](https://docs.pydantic.dev/) schemas to your datasource, so you stop
hand-writing the templates, factories, and converters that usually sit between *validation* and
*persistence*. You work with one set of typed, validated objects — and they are backed by your real
backend records.

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
*wraps* the backing ORM instance rather than copying out of it — so there is a single type to pass
around, with both validation and persistence behind it.

```python
author = session.get_one(Author, 1)

isinstance(author, Author)          # ✅ a Pydantic model — validated, typed
isinstance(author, BaseTransmuter)  # ✅ and a transmuter
author.__transmuter_provided__      # the underlying AuthorModel ORM instance, if you need it

author.name = "Arthur C. Clarke"    # mutate the transmuter…
author.__transmuter_provided__.name # …and the ORM object already reflects it — no model_dump()
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
  provider, so ORM-only attributes and methods remain reachable without unwrapping.
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

@materia.bless(AuthorModel)          # bind to an existing ORM model
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
for book in author.books:        # loads on access, not during validation
    print(book.title, book.author.value is author)   # identity preserved
```

### The validation-triggers-lazy-load trap

This is the single hardest part of putting Pydantic in front of an ORM, and the reason naïve
"just validate the ORM object" approaches fall apart at scale.

Pydantic validates **eagerly**: to build a model from an ORM object (`from_attributes=True`), it
*reads every mapped field*, including relationship attributes. But on a SQLAlchemy model a
relationship attribute is a lazy loader — touching `author.books` **emits a SQL query**. So the act
of validation alone walks the entire object graph and fires a query per relationship, per row:

```python
authors = session.scalars(select(AuthorModel)).all()   # 1 query
for a in authors:
    AuthorSchema.model_validate(a)   # each validation reads a.books -> +1 query each
# → classic N+1: 1 + N queries, none of which you asked for
```

It gets worse: validation recurses, so validating each `Book` would touch `book.author`, which
re-reads the parent, and so on — an eager traversal of data you may never use, plus a thicket of
queries. Under async it isn't merely slow — a lazy load outside an `await` raises a greenlet error
outright, so eager validation *breaks*.

Arcanus sidesteps this by **never reading a relationship during validation**. A relationship field
is validated into a deferred association — a placeholder that records *how* to load, not the loaded
data. The query fires only when you actually access `author.books`, and only then, honoring whatever
loading strategy (`selectinload`, `joinedload`, `lazy="select"`, …) you configured on the ORM model.
No accidental N+1, no surprise traversal, and async stays safe.

See [Relationships](concepts/relationships.md).

## Async support

Native `async`/`await` through `AsyncSession`, mirroring the synchronous API one-to-one.

```python
async with AsyncSession(engine) as session:
    author = await session.get_one(Author, 1)
    books = await author.books      # awaits lazy load, returns list[Book]
```

See [Sessions & Async](concepts/sessions.md).

## Where to next

<div class="grid cards" markdown>

- :material-rocket-launch: **[Quickstart](quickstart.md)** — define your first transmuter and run CRUD in minutes.
- :material-cog: **[The Materia System](concepts/materia.md)** — how binding works and the design philosophy behind it.
- :material-book-open-variant: **[API Reference](api/index.md)** — the full public API.

</div>
