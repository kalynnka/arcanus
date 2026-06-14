# Arcanus

[![Tests](https://github.com/kalynnka/arcanus/actions/workflows/tests.yml/badge.svg)](https://github.com/kalynnka/arcanus/actions/workflows/tests.yml)
[![Codecov](https://codecov.io/gh/kalynnka/arcanus/branch/main/graph/badge.svg)](https://codecov.io/gh/kalynnka/arcanus)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://codspeed.io/kalynnka/arcanus?utm_source=badge)
[![Docs](https://img.shields.io/badge/docs-github%20pages-blue.svg)](https://kalynnka.github.io/arcanus/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Arcanus** is a small library that binds [Pydantic](https://docs.pydantic.dev/) schemas to your
datasource. The idea is to let you work with one set of typed, validated objects that are backed by
your real backend records — so the templates, factories, and converters that usually sit between
*validation* and *persistence* mostly fall away. If that boilerplate has bothered you too, this is
the approach Arcanus takes to it.

It's a different take from [SQLModel](https://sqlmodel.tiangolo.com/), which *fuses* the Pydantic
model and the ORM table into one class. Arcanus instead keeps them separate and **binds** a schema
to your existing ORM model with `bless()`, so your SQLAlchemy models stay untouched and your
validation schema stays your own.

> **⚠️ Work in progress.** Arcanus is at an early, minimum-viable stage — expect bugs and breaking
> changes. SQLAlchemy is currently the only supported backend.

## Features

- 🔄 **Unified objects** — transmuters are backed by ORM objects; changes sync both ways, no manual conversion.
- 🛡️ **Type safety** — full Pydantic validation, plus typed column references like `Author["name"]`.
- 🔗 **Relationships** — one-to-one, one-to-many, many-to-many, and keyed maps that respect lazy loading.
- ⚡ **Async** — native `async`/`await` via `AsyncSession`.
- 🎯 **Pluggable backends** — `NoOpMateria` for tests, `SqlalchemyMateria` for databases.
- 📦 **Partial models** — built-in `Create` / `Update` shapes for API boundaries.

## Installation

```bash
pip install "arcanus[sqlalchemy]"
```

The base `pip install arcanus` ships the in-memory `NoOpMateria` (no backend needed) — ideal for
tests and prototyping.

## Quickstart

```python
from arcanus.base import BaseTransmuter, Identity
from arcanus.association import Relation, RelationCollection, Relationship, Relationships
from arcanus.materia.sqlalchemy import SqlalchemyMateria, Session
from pydantic import Field
from sqlalchemy import create_engine, select
from typing import Annotated, Optional

materia = SqlalchemyMateria()

@materia.bless(AuthorModel)          # bind to your existing SQLAlchemy model
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
    books: RelationCollection["Book"] = Relationships()

@materia.bless(BookModel)
class Book(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    title: str
    author: Relation[Author] = Relationship()

with Session(create_engine("sqlite://")) as session:
    author = Author(name="Isaac Asimov")
    session.add(Book(title="Foundation", author=Relation(author)))
    session.commit()

    # Plain SQLAlchemy reads — only the results come back as transmuters
    found = session.execute(
        select(Author).filter_by(name="Isaac Asimov")
    ).scalar_one()                                      # a transmuter, not a raw ORM row
    for book in found.books:                            # loads on access
        print(book.title, book.author.value is found)   # identity preserved
```

See the [Quickstart guide](https://kalynnka.github.io/arcanus/quickstart/) for the full walkthrough
including the ORM model definitions and async usage.

## Documentation

Full documentation lives at **[kalynnka.github.io/arcanus](https://kalynnka.github.io/arcanus/)**:

- [Why Arcanus](https://kalynnka.github.io/arcanus/) — the problem it solves.
- [Quickstart](https://kalynnka.github.io/arcanus/quickstart/) — define a transmuter and run CRUD.
- [The Materia System](https://kalynnka.github.io/arcanus/concepts/materia/) — binding and design philosophy.
- [API Reference](https://kalynnka.github.io/arcanus/api/) — the full public API.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, conventional commits, and the release flow.

## License

[MIT](LICENSE)
