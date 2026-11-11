# Transmuters & Providers

A **transmuter** is a Pydantic object that wraps a *provided* instance — a backend object whose class
(the **provider**) the transmuter is bound to. It is how Arcanus collapses the usual two object
worlds — validation schema and storage model — into one. The vocabulary and the binding mechanics
live in [The Materia System](materia.md); this page is about the transmuter object itself.

## The forms a transmuter takes

- **`BaseTransmuter`** — the `BaseModel`-derived base class; what you subclass most of the time.
- **`Transmuter`** — the protocol/mixin carrying the transmuter methods (`revalidate()`, `shell()`,
  `absorb()`, and the generated `Create` / `Update` partials — see
  [Partial Schemas](../usage/noop/schemas.md)).
- **`@dataclass`** — a lightweight transmuter built on Pydantic dataclasses, for when a full
  `BaseModel` is more than you need:

  ```python
  from arcanus.dataclass import dataclass


  @dataclass
  class SimpleTag:
      label: str
  ```

  Transmuter methods are injected at runtime. To make them visible to type checkers, inherit
  `Transmuter` explicitly:

  ```python
  from arcanus import Transmuter
  from arcanus.dataclass import dataclass


  @dataclass
  class Tag(Transmuter):
      label: str
  ```

  When a dataclass transmuter forward-references a `BaseTransmuter` defined later, call
  `rebuild_dataclass(Tag)` once the referenced type exists.

## Identity & proxying

Transmuters use **identity equality** (`is`, `id()`-based hash) to align with the backend identity
map, and proxy unmapped attribute access through to their provided instance via
`__transmuter_provided__`.

## Transient fields

Use `Annotated[T, Transient]` for runtime state that belongs to a transmuter and
has no provider mapping:

```python
from typing import Annotated

from pydantic import Field

from arcanus import BaseTransmuter, Transient


class Conversation(BaseTransmuter):
    name: str
    messages: Annotated[list[str], Transient] = Field(default_factory=list)
    new_message_index: Annotated[int | None, Transient] = None
```

`Transient()` is also accepted. The marker works on inherited fields and on
transmuter dataclasses, including fields declared with `dataclasses.field()`.
Supplied transient values are validated normally; assignment validation follows
the model's configuration. Serialization, defaults, and dataclass field options
retain their usual behavior. `Field(exclude=True)` still controls serialization
separately.

Transient fields are omitted from provider constructors and assignment
synchronization. Loading a new transmuter from a provider uses their normal
defaults; `revalidate()` uses the existing runtime values as validation input.
Pydantic may coerce, normalize, or copy them. A transient field without a default
still requires a value, so it cannot be loaded from a provider unless an existing
transmuter supplies that value.

Transient fields are omitted from generated query criteria. Accessing one as a
database expression, such as `Conversation["new_message_index"]`, raises `KeyError`
explaining that it has no provider mapping. The generated `Create` and `Update`
schemas retain transient fields for constructing and updating runtime state.

See the [API reference](../api/base.md) for the full surface.
