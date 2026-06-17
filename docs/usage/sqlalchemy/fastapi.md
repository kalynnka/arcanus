# Working with FastAPI

A transmuter **is** a Pydantic model, so it drops straight into [FastAPI](https://fastapi.tiangolo.com/):
one definition supplies your request bodies, your responses, your filters, and your pages — no
parallel `AuthorCreate` / `AuthorUpdate` / `AuthorResponse` classes to hand-maintain. This page wires
the [setup](index.md#setup) `Author` / `Book` models into a small app: CRUD with the generated
[partial schemas](../noop/schemas.md), filtering with [`Criteria`](querying.md#criteria), and keyset
pagination returning [`Page`](querying.md#cursor-pagination).

!!! warning "Partial schemas are experimental"
    `.Create` / `.Update` are still [experimental](../noop/schemas.md) — the generated surface may
    change.

## A session dependency

Yield an arcanus `Session` per request. Everything below depends on it.

```python
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from arcanus import Criteria, Cursor, Page
from arcanus.materia.sqlalchemy import Session

engine = create_engine("postgresql+psycopg://localhost/app")
app = FastAPI()

def get_session():
    with Session(engine) as session:        # blesses rows into transmuters on the way out
        yield session
```

## CRUD with partial schemas

`Author.Create` excludes identity fields; `Author.Update` makes every non-frozen field optional.
`shell()` turns a validated `Create` into a transmuter; `absorb()` applies an `Update` in place. The
**response model is the transmuter itself** (`response_model=Author`), so one class drives the create
body, the update body, and the response.

```python
@app.post("/authors", response_model=Author, status_code=201)
def create_author(body: Author.Create, session: Session = Depends(get_session)) -> Author:
    author = Author.shell(body)             # body already validated by FastAPI/Pydantic
    session.add(author)
    session.flush()                         # server-generated id synced back automatically
    session.commit()
    return author

@app.get("/authors/{author_id}", response_model=Author)
def get_author(author_id: int, session: Session = Depends(get_session)) -> Author:
    author = session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")
    return author

@app.patch("/authors/{author_id}", response_model=Author)
def update_author(
    author_id: int, body: Author.Update, session: Session = Depends(get_session)
) -> Author:
    author = session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")
    author.absorb(body)                     # only the fields the client actually sent change
    session.commit()
    return author

@app.delete("/authors/{author_id}", status_code=204)
def delete_author(author_id: int, session: Session = Depends(get_session)) -> None:
    author = session.get(Author, author_id)
    if author is not None:
        session.delete(author)
        session.commit()
```

Invalid bodies never reach your code — FastAPI returns a 422 from the generated schema — and every
shape shows up in the OpenAPI docs automatically.

## Filtering with `Criteria`

Type a parameter as `Criteria[Author]` and clients get rich, validated filtering from a single
field. The handler spreads `.expressions` into a query:

```python
@app.post("/authors/search", response_model=list[Author])
def search_authors(where: Criteria[Author], session: Session = Depends(get_session)) -> list[Author]:
    return list(session.execute(select(Author).where(*where.expressions)).scalars())
```

A client posts e.g. `{"name": {"contains": "Asimov"}}` and only valid operators/value types are
accepted — see [Criteria validation](../noop/querying.md#validation-is-just-pydantic).

## Keyset pagination with `Page`

For large collections, return a `Page[Author]` — `items` plus `total`, `has_more`, and an opaque
`next_cursor`. A small reusable helper works for any transmuter; the client pages by echoing back the
cursor (filter, ordering, and limit all travel inside the token):

```python
from typing import TypeVar
from arcanus.base import BaseTransmuter
from arcanus.expression import Expression, Order

T = TypeVar("T", bound=BaseTransmuter)

def paginate(
    session: Session,
    entity: type[T],
    *,
    expressions: tuple[Expression[bool], ...],
    order_bys: tuple[Order, ...],
    size: int,
    cursor: str | None = None,
) -> Page[T]:
    filters, orders, bookmark = expressions, order_bys, None
    if cursor:                                       # continue a previous page
        token = Cursor[entity](cursor)               # validates the opaque token
        filters = token.criteria.expressions if token.criteria else ()
        orders, bookmark = token.order_by.orders, token.bookmark.expression

    rows = session.execute(
        select(entity)
        .where(*filters, *((bookmark,) if bookmark is not None else ()))
        .order_by(*orders)
        .limit(size + 1)                             # +1 row reveals whether more exist
    ).scalars().all()
    items = tuple(rows[:size])
    total = session.execute(
        select(func.count()).select_from(entity).where(*filters)
    ).scalar_one()

    next_cursor = Cursor[entity].from_expressions(
        expressions=filters,
        bookmark=Cursor[entity].bookmark_from_item(items[-1], orders) if items else bookmark,
        order_bys=orders,
        limit=size,
    )
    return Page(items=items, total=total, next_cursor=str(next_cursor), has_more=len(rows) > size)


@app.post("/authors/page", response_model=Page[Author])
def page_authors(
    where: Criteria[Author], cursor: str | None = None, session: Session = Depends(get_session)
) -> Page[Author]:
    return paginate(
        session,
        Author,
        expressions=where.expressions,
        order_bys=(Author["id"].asc(),),
        size=20,
        cursor=cursor,
    )
```

The first call filters by `where`; each subsequent call passes the previous response's `next_cursor`
and ignores `where` (the criteria are carried in the token), giving stable keyset pagination that
doesn't drift when rows are inserted. Because the cursor is opaque and self-validating, a malformed
token is rejected before any query runs.

## Async

Everything above mirrors one-to-one onto `AsyncSession` — make the dependency and handlers `async`
and `await` the I/O:

```python
from arcanus.materia.sqlalchemy import AsyncSession

async def get_session():
    async with AsyncSession(async_engine) as session:
        yield session

@app.get("/authors/{author_id}", response_model=Author)
async def get_author(author_id: int, session: AsyncSession = Depends(get_session)) -> Author:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")
    return author
```

See [Lifecycle & Async](../../concepts/lifecycle.md) for the awaiting rules.
