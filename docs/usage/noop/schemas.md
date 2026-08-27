# Partial Schemas

!!! warning "Experimental"
    The `.Create` / `.Update` partial models and the rules that shape them are **experimental** —
    the surface (which fields are included, how nested associations are handled) may change. Today
    nested associations are not yet included in either partial.

## The problem this solves

A single entity usually drags a **pile of near-duplicate schemas** behind it: `UserCreate`,
`UserUpdate`, `UserResponse`, `UserPatch`, and so on — each a hand-maintained subset of the same
fields, all needing to stay in sync as the model evolves. That duplication is exactly the
schema/persistence boilerplate Arcanus exists to remove.

So a transmuter **derives those shapes for you** instead. From one definition, it exposes two
**runtime-generated** Pydantic models — `.Create` and `.Update` — plus the `shell()` / `absorb()`
methods that move between a partial and a full transmuter. The read/response shape is the
transmuter **itself** — there is no `.Read`. One source of truth, no `xxxCreate` / `xxxUpdate` /
`xxxResponse` trio. None of this needs a backend, so it all runs under the default `NoOpMateria`.

## How a field lands in each partial

Apart from the `Identity` marker, the rules lean on **stock pydantic field flags** — `frozen` and
`exclude` — so there's nothing arcanus-specific to learn:

| How you declare the field | `.Create` | `.Update` | response (`model_dump()`) |
| --- | --- | --- | --- |
| Ordinary scalar — `name: str` | ✅ (same shape) | ✅ optional | ✅ |
| Generated identity — `Annotated[Optional[int], Identity] = Field(default=None, frozen=True)` | ❌ | ❌ | ✅ |
| Natural / composite identity — `Annotated[int, Identity(server_side=False)] = Field(frozen=True)` | ✅ required | ❌ | ✅ |
| Write-once — `Field(frozen=True)` | ✅ | ❌ | ✅ |
| Masked — `Field(exclude=True)` | ✅ | ✅ | ❌ |
| Association — `Relation[...]` / `Relationships()` | ❌ | ❌ | ✅ |

## The `Identity` annotation

`Identity` marks the field(s) that form a record's identity, following SQLAlchemy's primary-key
concept. By default an identity is **generated** — server-assigned (autoincrement), so it's dropped
from `.Create`. Pass `Identity(server_side=False)` for a **natural**/composite key the client must
supply, which keeps it in `.Create`. The marker works bare (`Identity`, taking the defaults) or
instantiated (`Identity(...)`). Freeze it to keep it immutable:

```python
from arcanus import BaseTransmuter, Identity
from pydantic import Field
from typing import Annotated, Optional


class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(
        default=None, frozen=True
    )  # generated
    name: str
    field: str = "Physics"


class BookCategory(BaseTransmuter):
    book_id: Annotated[int, Identity(server_side=False)] = Field(
        frozen=True
    )  # natural key
    category_id: Annotated[int, Identity(server_side=False)] = Field(frozen=True)
```

## `.Create` — drop generated identities

`Author.Create` drops **generated identity fields** (the backend assigns them) and associations,
keeping every other field with its original required/optional shape. An identity declared
`Identity(server_side=False)` instead **stays** in `.Create`, so the client can supply it:

```python
list(Author.Create.model_fields)  # ['name', 'field'] — generated 'id' dropped
Author.Create.model_fields["name"].is_required()  # True — required stays required

payload = Author.Create(name="Isaac Asimov")  # validates an incoming create body

# A natural/composite key stays in Create (and keeps its required shape):
list(BookCategory.Create.model_fields)  # ['book_id', 'category_id']
```

`shell()` turns a validated `Create` into a full (not-yet-persisted) transmuter:

```python
author = Author.shell(payload)  # Author(id=None, name="Isaac Asimov", field="Physics")
```

## `.Update` — exclude frozen (write-once), all optional

`Author.Update` drops **frozen fields** and associations, then makes every remaining field optional.
Because identities are frozen they're excluded too. `frozen=True` is therefore how you mark any
**write-once** field — settable at create, never on update:

```python
list(Author.Update.model_fields)  # ['name', 'field'] — no 'id' (frozen)

patch = Author.Update(field="History")  # only 'field' is set
```

`absorb()` applies a validated `Update` onto an existing transmuter, touching **only the fields that
were actually set** (`exclude_unset`):

```python
author = Author.shell(Author.Create(name="Isaac Asimov"))
author.absorb(Author.Update(field="History"))
author.field  # "History"
author.name  # "Isaac Asimov" — untouched, because it wasn't set on the patch
```

## Masking a field from the response

There is no separate `.Read` model: the transmuter **is** the response shape. To keep a field
functional in the backend but hidden from the API, mark it `Field(exclude=True)` — stock pydantic.
It stays a real, writable, attribute-readable field; it's simply dropped from `model_dump()` (and so
from any serialized response):

```python
class Account(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    username: str
    password: str = Field(exclude=True)  # masked from responses, still writable


account = Account.shell(Account.Create(username="neo", password="trinity"))
account.password  # "trinity" — usable in backend logic
account.model_dump()  # {'id': None, 'username': 'neo'} — no password
```

`password` still appears in `.Create` / `.Update` (the client can set and change it); only the
response side hides it. Combine with `frozen=True` for a write-once secret (set at create, never
updated, never returned).

## At an API boundary

The pattern these enable, end to end (still no backend — swap in a real session under
[SQLAlchemy](../sqlalchemy/crud.md#partial-models-for-api-boundaries)):

```python
def create_author(body: dict) -> Author:
    return Author.shell(
        Author.Create.model_validate(body)
    )  # 422-style validation on bad input


def update_author(author: Author, body: dict) -> Author:
    return author.absorb(
        Author.Update.model_validate(body)
    )  # only provided fields change
```

## With FastAPI

Because `.Create` / `.Update` are real Pydantic models, you type them directly as request bodies —
no hand-written `AuthorCreate` / `AuthorUpdate` classes to keep in sync. FastAPI validates the body
against the generated schema (rejecting bad input with a 422) and documents it in OpenAPI; `shell()`
and `absorb()` bridge to the transmuter:

```python
from fastapi import FastAPI
from sqlalchemy import select
from arcanus.materia.sqlalchemy import Session  # SQLAlchemy materia persists the result

app = FastAPI()


@app.post("/authors")
def create_author(body: Author.Create) -> Author:
    author = Author.shell(body)  # Create excludes the id; body is validated
    with Session(engine) as session:
        session.add(author)
        session.flush()  # server-generated id synced back automatically
        session.commit()
    return author


@app.patch("/authors/{author_id}")
def update_author(author_id: int, body: Author.Update) -> Author:
    with Session(engine) as session:
        author = session.get_one(Author, author_id)
        author.absorb(body)  # applies only the fields the client sent
        session.commit()
        return author
```

The response model is the transmuter itself (`-> Author`), so one definition drives the create body,
the update body, **and** the response — the `xxxCreate` / `xxxUpdate` / `xxxResponse` trio collapses
into a single source of truth.
