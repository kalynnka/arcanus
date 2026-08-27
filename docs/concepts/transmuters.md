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

See the [API reference](../api/base.md) for the full surface.
