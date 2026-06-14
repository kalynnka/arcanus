# SQL Statements

Arcanus doesn't replace SQLAlchemy's statement API — you write `select`, `update`, `delete`, and
`session.execute` exactly as you normally would. What you gain is that **transmuters and typed
columns flow through with full static typing**: a statement over `Author` is a `Select[tuple[Author]]`,
and executing it yields `Author` transmuters — not `Any`, not raw ORM rows. This page uses the
[setup](index.md#setup) models; the `reveal_type(...)` comments are what a type checker infers.

## `select`

```python
from sqlalchemy import select

stmt = select(Author).where(Author["name"].like("Isaac%")).order_by(Author["id"].desc())
reveal_type(stmt)            # Select[tuple[Author]]

with Session(engine) as session:
    authors = session.execute(stmt).scalars().all()
    reveal_type(authors)     # Sequence[Author]

    author = session.execute(stmt).scalar_one()
    reveal_type(author)      # Author
```

Build the `WHERE` / `ORDER BY` with [typed columns and expressions](querying.md); the rows are
blessed into transmuters automatically on the way out.

## `update` / `delete` with `RETURNING`

`update(Author)` and `delete(Author)` are typed too, and `.returning(Author)` carries the transmuter
type through, so the affected rows come back as transmuters:

```python
from sqlalchemy import update, delete

ustmt = update(Author).where(Author["id"] == 1).values(name="Renamed").returning(Author)
reveal_type(ustmt)           # ReturningUpdate[tuple[Author]]

dstmt = delete(Book).where(Book["author_id"] == 1).returning(Book)
reveal_type(dstmt)           # ReturningDelete[tuple[Book]]

with Session(engine) as session:
    renamed = session.execute(ustmt).scalars().all()   # Sequence[Author]
    session.commit()
```

For single-row create/read/update/delete the [CRUD](crud.md) flow and [session helpers](session.md)
are terser; reach for raw statements when you need set-based writes or full control.

## Loader options & polymorphic helpers

Loader options and polymorphic constructs take **typed columns** (`Author["books"]`) and
**transmuter classes** (`Author`), not ORM attributes/classes. SQLAlchemy's own `orm.selectinload` /
`orm.with_polymorphic` *do* recognize them at runtime — the columns and classes carry the hooks
SQLAlchemy inspects — but their signatures don't know about transmuters, so a type checker rejects
the arguments. Arcanus therefore re-exports **wrapper versions** from `arcanus.materia.sqlalchemy`
that accept these inputs and stay properly typed. Prefer the wrappers:

```python
from arcanus.materia.sqlalchemy import (
    selectinload, joinedload, raiseload, load_only, defer, with_polymorphic, selectin_polymorphic,
)

opt = selectinload(Author["books"])       # LoadOption — typed (native orm.selectinload would error)
reveal_type(opt)                           # LoadOption

poly = with_polymorphic(Book, (Book,))     # pass the subclasses as a tuple
reveal_type(poly)                          # AliasedClass[Book]
```

`with_polymorphic` is overloaded so a tuple of subclasses yields a precise union —
`with_polymorphic(Media, (Image, Video))` is typed `AliasedClass[Image | Video]`. Use the alias in a
statement just like a transmuter: `select(poly).where(...)`.

The full set: `selectinload`, `joinedload`, `subqueryload`, `lazyload`, `noload`, `raiseload`,
`contains_eager`, `defaultload`, `load_only`, `defer`, `undefer`, plus `with_polymorphic` and
`selectin_polymorphic`. They behave identically to SQLAlchemy's — see [Loading Strategies](loading.md)
for what each one loads. Attach them with `.options(...)` on a statement, or the `options=` argument
of the [session helpers](session.md):

```python
stmt = select(Author).options(selectinload(Author["books"]))
```

!!! tip "Why the wrappers, if the originals work?"
    The native `orm.*` options run fine at runtime. The wrappers add **nothing** at runtime — they
    exist purely so the type checker accepts `Author["books"]` / `Author` and infers `LoadOption` /
    `AliasedClass[Author]` instead of flagging the argument. It's typing sugar, and nice to have.
