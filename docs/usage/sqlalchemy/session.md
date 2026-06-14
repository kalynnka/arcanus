# Session Helpers

Uses the **SQLAlchemy materia** and the `Author` / `Book` / `Category` models from the
[setup](index.md#setup).

The arcanus `Session` / `AsyncSession` *is* a SQLAlchemy session — every native method
(`add`, `flush`, `commit`, `delete`, `execute`, `get`, …) works unchanged, except that whatever
comes back is a **transmuter**, not a raw ORM row. On top of that, Arcanus adds a small set of typed
query **convenience helpers** so common reads don't need a hand-built `select`. This page is the
reference for them.

Every helper exists on both `Session` (sync) and `AsyncSession` (async, `await` it) with the same
signature, and every result is a transmuter.

## Native methods, blessed results

These are plain SQLAlchemy methods — the signatures are SQLAlchemy's; Arcanus only blesses the
output:

```python
author = session.get(Author, 1)        # native: returns the transmuter, or None
author = session.get_one(Author, 1)     # native: returns the transmuter, or raises NoResultFound

rows = session.execute(                  # native: build any select yourself
    select(Author).where(Author["name"].like("Isaac%"))
).scalars().all()
```

## Added convenience helpers

The shared keyword arguments across these helpers:

- `**filters` — equality filters by field name (`name="Ada"`), i.e. SQLAlchemy `filter_by`.
- `expressions=` — a list of [expressions](../noop/querying.md) (arcanus or native) for the `WHERE`.
- `order_bys=` — native columns, arcanus `Column`s (`Author["name"]`), or `Order`s
  (`Author["name"].desc()`).
- `options=` — [loader options](loading.md) such as `selectinload(Author["books"])`.
- `execution_options=` — passed through to SQLAlchemy.

### `one` / `one_or_none` — a single row

```python
author = session.one(Author, name="Isaac Asimov")         # raises if 0 or >1 match
maybe = session.one_or_none(Author, name="Nobody")         # None if 0, raises if >1

# with expressions instead of keyword filters
author = session.one(Author, expressions=[Author["name"] == "Isaac Asimov"])
```

### `first` — the first row under an ordering

```python
newest = session.first(Author, order_bys=[Author["id"].desc()])   # None if no rows
```

### `list` — many rows, paged and ordered

```python
authors = session.list(
    Author,
    limit=10,            # default 100
    offset=20,
    order_bys=[Author["name"].asc()],
    expressions=[Author["name"].like("Isaac%")],
    options=[selectinload(Author["books"])],
)
```

### `bulk` — several by primary key

Returns results in the **same order as `idents`**, with `None` for any id that wasn't found
(composite primary keys work — pass tuples):

```python
authors = session.bulk(Author, [1, 2, 3])     # [Author|None, Author|None, Author|None]
```

### `count` — count matching rows

```python
total = session.count(Author)
filtered = session.count(Author, expressions=[Author["name"].like("Isaac%")])
```

### `partitions` — stream a large result set in chunks

```python
for chunk in session.partitions(Author, size=100):
    for author in chunk:
        ...
```

### `stream` — async streaming (AsyncSession only)

`AsyncSession` adds `stream(statement, ...)`, the async counterpart of `execute` for server-side
cursors:

```python
result = await session.stream(select(Author).where(Author["name"].like("Isaac%")))
async for author in result.scalars():
    ...
```

## Async — identical, awaited

```python
async with AsyncSession(async_engine) as session:
    author = await session.one(Author, name="Isaac Asimov")
    authors = await session.list(Author, limit=10, order_bys=[Author["id"].desc()])
    total = await session.count(Author)
    async for chunk in session.partitions(Author, size=100):
        ...
```

For the full method list see the [`arcanus.materia.sqlalchemy` reference](../../api/sqlalchemy.md).
For building the `expressions=` / `order_bys=` arguments, see [Querying](querying.md).
