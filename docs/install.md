# Installation

Arcanus requires **Python 3.11+**. Its only hard dependency is Pydantic v2; backend support is
opt-in through extras.

## Base install

```bash
pip install arcanus
```

This gives you the core transmuter machinery and the in-memory
[`NoOpMateria`](concepts/materia.md) — enough to define and validate transmuters with no backend.

## With a backend

=== "SQLAlchemy"

    ```bash
    pip install "arcanus[sqlalchemy]"
    ```

    Pulls in `sqlalchemy>=2.0` and `greenlet`. Required for `SqlalchemyMateria`, `Session`, and
    `AsyncSession`. You will also need a database driver for your engine, e.g.:

    ```bash
    pip install psycopg2-binary        # PostgreSQL (sync)
    pip install asyncpg                 # PostgreSQL (async)
    pip install aiosqlite               # SQLite (async)
    ```

=== "Redis"

    ```bash
    pip install "arcanus[redis]"
    ```

    !!! note
        The Redis materia is still in progress. SQLAlchemy is the only fully supported backend today.

## Next

Head to the [Quickstart](quickstart.md) to define your first transmuter.
