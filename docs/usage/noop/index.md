# NoOp Materia

`NoOpMateria` is the default, backend-free materia. It is **active automatically** — you don't
instantiate it or `bless()` anything. Just define transmuters and use them like ordinary Pydantic
models: no engine, no session, no setup.

```python
from arcanus.base import BaseTransmuter, Identity
from pydantic import Field
from typing import Annotated, Optional

class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str

author = Author(name="Isaac Asimov")     # works immediately, no backend
```

Because there is no backend, there is **no session and no lifecycle to manage** — a transmuter is a
plain Python object that lives while referenced and is collected when it isn't.

## When to use it — and when not to

!!! warning "Don't reach for NoOp just to get objects"
    If you only need plain validated objects and have **no other backend in play**, use Pydantic
    directly — `NoOpMateria` is pure overhead over raw Pydantic and buys you nothing on its own. It
    exists so that the *transmuter machinery* (relationships, expressions, partial schemas, the
    provider-binding protocol) works **before** a real backend is attached: in unit tests, in
    prototyping, and as the fallback when no other materia is registered. Choosing it deliberately
    as your "object layer" is a waste.

The legitimate uses:

- **Tests & prototyping** — exercise transmuter logic without standing up a database.
- **The default fallback** — code written against transmuters keeps working with no backend
  configured, then gains persistence the moment you bind a `SqlalchemyMateria`.

## A note on performance

A materia is not free. Arcanus adds machinery on top of your objects — validation that defers
relationship loading, provider proxying, an identity-aligned context — and that machinery costs
CPU. Be clear-eyed about two distinct gaps the project tracks (and measures; see the
[benchmark suite](https://github.com/kalynnka/arcanus/blob/main/benchmark/README.md) and the
CodSpeed dashboard):

- **Schema overhead (NoOp vs pure Pydantic).** A transmuter under `NoOpMateria` is measurably
  slower than the equivalent plain Pydantic model — that delta *is* the transmuter machinery, with
  no backend to justify it. This is exactly why NoOp is not a thing to adopt for its own sake.
- **Backend overhead (a materia vs hand-rolled glue).** Against the hand-written "validate with
  Pydantic, then build/realize ORM objects" pattern, a real materia (e.g. `SqlalchemyMateria`) adds
  overhead too — you are paying for the unified object, the deferred loading, and the bookkeeping.
  The trade is fewer conversion bugs and one object instead of two, not raw speed.

In short: reach for a materia when its *backend integration* earns the cost. If nothing needs a
backend, plain Pydantic wins.

!!! note "We're working to shrink the gap"
    Narrowing this overhead is an active focus — we really are trying (the
    [benchmark suite](https://github.com/kalynnka/arcanus/blob/main/benchmark/README.md) exists
    precisely to keep us honest about it). It's hard, and progress is incremental. If performance is
    your thing, **contributions are very welcome** — profiles, fixes, and ideas all help.

## The components, introduced here

Every core component is backend-agnostic, so this NoOp section is where each is introduced with the
fewest moving parts. The [SQLAlchemy](../sqlalchemy/index.md) section then expands each with
persistence detail and real-world examples.

<div class="grid cards" markdown>

- :material-relation-many-to-many: **[Relationships](relationships.md)** — `Relation`, `RelationCollection`, `RelationSet`, `RelationMap`, `TypedRelationMap`, and the field helpers.
- :material-filter: **[Expressions & Cursors](querying.md)** — typed columns, expressions, criteria, and the pre-built cursor/pagination helpers.
- :material-form-select: **[Partial Schemas](schemas.md)** — the runtime-only `.Create` / `.Update` models and the `Identity` annotation. *(experimental)*

</div>
