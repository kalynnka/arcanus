# Usage

This section is the hands-on guide, **grouped by materia** — the backend a transmuter is bound to.
Read this overview first for the shared design ideas (what a materia is, how sessions and object
lifecycle work), then dive into the backend you're using.

| Materia | Backend | Session | Status | Start here |
|---------|---------|---------|--------|-----------|
| `NoOpMateria` | none (in-memory) | none | stable | [NoOp Materia](noop/index.md) |
| `SqlalchemyMateria` | a SQL database | session-scoped | stable | [SQLAlchemy Materia](sqlalchemy/index.md) |
| `RedisMateria` | Redis | — | **work in progress** | [Redis Materia](redis.md) |

## What a materia is

A **materia** is the plugin that connects transmuters to a concrete backend. The vocabulary, in
short (the full picture is in [The Materia System](../concepts/materia.md)):

- **Transmuter** — the Pydantic object you work with. It validates *and* wraps a *provided* instance.
- **Provider** — the backend object **class** you bind to (e.g. the `AuthorModel` ORM class).
- **Provided** — a backend object **instance** of that class — the record a transmuter wraps. The
  levels line up: transmuter class ↔ provider (class), transmuter instance ↔ provided (instance).
- **Materia** — the binding plugin (`NoOpMateria`, `SqlalchemyMateria`, …).
- **Transmuter Context** — a session-scoped cache mapping a provided instance → its transmuter, so
  the same backend record always resolves to the *same* transmuter.

The transmuter API — fields, relationships, expressions, partial schemas — is **the same across
every materia**. What changes between backends is the setup, the session, and the lifecycle. That's
why this guide introduces the backend-agnostic components once under [NoOp](noop/index.md), then
expands them with persistence detail under [SQLAlchemy](sqlalchemy/index.md).

## Sessions and object lifecycle

This is the design concept that most distinguishes one materia from another, so it's worth
understanding up front.

Arcanus's guiding rule is to **never fight the backend's own session, identity, and transaction
semantics** — it cooperates with them. A transmuter therefore does not own an independent
lifecycle; it follows its provided instance's, and that instance is owned by whatever the backend
uses to manage records:

- **No backend (`NoOpMateria`)** — there is no session at all. A transmuter is an ordinary Python
  object: it lives while something references it and is garbage-collected when nothing does. Nothing
  to open, flush, or close.
- **A database (`SqlalchemyMateria`)** — the **SQLAlchemy session** owns the provided instance and
  moves it through *pending → persistent → expired/detached*; the transmuter rides along. The
  Transmuter Context (a weak-keyed cache scoped to the session) keeps a transmuter alive only as long
  as its provided instance lives in the session. You manage the session; the transmuters follow. See
  [object lifecycle under the SQLAlchemy materia](../concepts/lifecycle.md#lifecycle-under-the-sqlalchemy-materia).

Because the lifecycle is the backend's, so are the boundaries where server-generated values appear
(after a `flush`/`commit`) — which is why `revalidate()` exists to sync them back into the
transmuter. Transactions and atomicity stay the backend's job.

## Where to next

<div class="grid cards" markdown>

- :material-flask-outline: **[NoOp Materia](noop/index.md)** — the backend-free baseline, and the home of every core component: relationships, expressions, cursors, partial schemas.
- :material-database: **[SQLAlchemy Materia](sqlalchemy/index.md)** — bind to a database, then CRUD, loading strategies, and querying in depth.
- :material-flash: **[Redis Materia](redis.md)** — work in progress.

</div>
