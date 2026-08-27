# The Materia System

A **Materia** is the plugin that connects transmuters to a concrete backend. It is the layer that
makes "one object, not two" possible: it knows how to turn a backend record (a *provided* instance)
into a validated transmuter and how to keep the two in sync. This page is the design; to *use* a
materia, start at [Usage](../usage/index.md).

## Core vocabulary

| Term | Meaning |
|------|---------|
| **Transmuter** | The Pydantic object you work with. Validates, and wraps a *provided* instance. |
| **Provider** | The backend object **class** you bind a transmuter class to (e.g. the `AuthorModel` ORM class). |
| **Provided** | A backend object **instance** of that provider class — the record a transmuter instance wraps, reachable via `__transmuter_provided__`. |
| **Materia** | The plugin binding transmuters to a backend (`SqlalchemyMateria`, `NoOpMateria`, …). |
| **Transmuter Context** | A session-scoped cache mapping a *provided* instance → its transmuter. |

The split is by level: **provider** is the *class*, **provided** is the *instance*. So the
correspondence is class-to-class and instance-to-instance — a **transmuter class** is bound to a
**provider** (class), and each **transmuter instance** wraps one **provided** (instance) of it.

## Binding with `bless()`

`bless()` registers a two-way mapping between a transmuter class and a **provider** (class). After
blessing, the materia can construct a transmuter from any **provided** instance it sees — for example,
every ORM row a `Session` returns:

```python
materia = SqlalchemyMateria()


@materia.bless(AuthorModel)  # Author transmuter  <->  AuthorModel provider
class Author(BaseTransmuter): ...
```

### The registry

The mapping lives on the **materia instance**, in a `formulars` registry — a *bidirectional* dict
(`BidirectonDict`) keyed by transmuter class with provider class as the value. It is two-way because
both directions are needed at runtime:

- **transmuter → provider** drives validation and querying: when you build `Author["name"]` or
  validate a transmuter, the materia looks up `Author`'s provider class to resolve columns and
  expressions. `materia[Author]` returns that provider class (and `Author in materia` tests
  membership).
- **provider → transmuter** drives blessing on the way out: when a `Session` hands back an
  `AuthorModel` row, the materia uses `formulars.reverse` to find the matching transmuter class and
  wrap the row.

```python
materia[Author]  # → AuthorModel        (transmuter → provider)
materia.formulars.reverse[AuthorModel]  # → Author          (provider → reverse lookup)
Author in materia  # → True
```

Because the registry is per-instance, **the same transmuter class can be blessed by more than one
materia** — e.g. a `RedisMateria` and a `SqlalchemyMateria` each holding their own mapping for
`Author`. Which one is in effect is decided by *activation* (below), not by the class.

The default `NoOpMateria` needs no blessing at all — its `bless()` is a no-op and it is active
automatically, which is why transmuters behave like plain Pydantic models out of the box.

## Activating a materia

A materia only takes effect while it is the **active** one. Activation is a context manager backed by
a `ContextVar`, so it is scoped, thread/async-safe, and nestable:

```python
materia = SqlalchemyMateria()

with materia:  # activate for this block
    author = session.get_one(Author, 1)
    Author["name"] == "Ada"  # resolves against `materia`'s registry
# outside the block, the previous materia (NoOpMateria by default) is active again
```

`with materia:` activates the instance directly and raises if it is *already* active. To **nest** or
re-enter, call it — `with materia():` yields a shallow copy that shares the same `formulars` registry
but gets its own activation token:

```python
with outer_materia:
    ...
    with inner_materia():  # nested activation — note the ()
        ...  # inner_materia is active here
    ...  # back to outer_materia
```

### Switching materia at runtime

Because activation is just a context stack, you can switch backends mid-flow — the canonical example
being a **cache → database** read: try a fast cache materia first, fall back to the database, then
populate the cache. (Pseudo-code; `RedisMateria` is [work in progress](../usage/redis.md).)

```python
db = SqlalchemyMateria()
cache = RedisMateria()


@cache.bless("author")  # same transmuter, two materias
@db.bless(AuthorModel)
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str


def read_author(author_id: int) -> Author | None:
    with cache:  # 1. try the cache backend
        hit = redis.get(Author, author_id)  # pseudo: read-through cache
        if hit is not None:
            return hit

    with db, Session(engine) as session:  # 2. miss → read the database
        author = session.get_one(Author, author_id)

    with cache:  # 3. populate the cache for next time
        redis.set(author)
    return author
```

Each `with` block decides which registry — and which expression compiler, identity rules, and
loading semantics — is in effect for the code inside it. The transmuter class is the same throughout;
only the active materia changes.

## Design philosophy: respect the backend

Arcanus's guiding rule is that it **never fights the target backend's session, atom, and
transaction semantics** — it cooperates with them:

- **Defer, don't pre-load.** Relationships are marked deferred during validation and only loaded on
  access, so Arcanus honors the backend's own lazy-loading strategy instead of forcing eager I/O.
- **Don't duplicate the identity map.** Within a session, a given provided instance always resolves
  to the *same* transmuter. Arcanus leans on the backend's identity map rather than inventing a
  second one.
- **Sync at the backend's boundaries.** Server-generated values land after `flush`/`commit`; Arcanus
  syncs them onto the transmuter automatically after each flush (`revalidate()` is the explicit full
  re-sync). Transactions remain the backend's job.

A new backend is "correct" precisely when it upholds these guarantees.

## Implementing a new Materia

Building a backend means upholding the lifecycle guarantees — the strong/weak reference design in
[Lifecycle & Async → the reference architecture](lifecycle.md#the-reference-architecture). There are
three required components.

### 1. Provider mixin

Provider objects must carry the weak back-reference to their transmuter. Mix in
`TransmuterProxiedMixin`, which supplies `_transmuter_proxy` and the `transmuter_proxy` weakref
property:

```python
from arcanus.base import TransmuterProxiedMixin


class YourProviderBase(TransmuterProxiedMixin):
    """Base class for your backend's provider objects."""

    # provides: _transmuter_proxy + transmuter_proxy (weakref getter/setter)
```

### 2. Session / context manager

Own a `WeakKeyDictionary[provided, transmuter]` and activate it as the validation context for the
session's lifetime, so validation resolves providers to the *same* transmuter:

```python
from weakref import WeakKeyDictionary
from arcanus.base import validation_context


class YourSession:
    def __init__(self) -> None:
        self._transmuter_context = WeakKeyDictionary()

    def __enter__(self):
        self._cm = validation_context(self._transmuter_context)
        self._cm.__enter__()
        return self

    def __exit__(self, *exc):
        self._cm.__exit__(*exc)
```

When you `add` a transmuter, store its provider in the context (strongly, as the dict value) and
cascade to already-proxied related providers so they resolve to the same transmuters:

```python
def add(self, transmuter):
    provided = transmuter.__transmuter_provided__
    self._identity_map_add(provided)  # backend owns it strongly
    self._transmuter_context[provided] = transmuter
    for related in self._cascade(provided):
        if (t := getattr(related, "transmuter_proxy", None)) is not None:
            self._transmuter_context[related] = t
```

### 3. Registration

Implement `bless()` to record the transmuter-class ↔ provider-class mapping in `formulars`:

```python
from arcanus.materia.base import BaseMateria


class YourMateria(BaseMateria):
    def bless(self, provider_cls):
        def decorator(transmuter_cls):
            self.formulars[transmuter_cls] = provider_cls
            return transmuter_cls

        return decorator
```

!!! note "Memory-safety checklist"
    - Provided → Transmuter is a **weakref** (prevents the strong cycle).
    - The context is a **`WeakKeyDictionary`** (weak keys, strong values) — entries auto-clear when a
      provided instance is collected.
    - The session holds provided instances **strongly**; the transmuter holds its provided instance
      **strongly** via `__transmuter_provided__`.
    - There is **no other** strong reference from the provided instance back to the transmuter.

### Testing a new materia

Three checks catch the common mistakes:

- **Identity / no duplicates** — build many related objects in a loop, then verify each provider
  resolves to a single transmuter (not a fresh one per access).
- **Circular references** — set up a bidirectional relationship and assert `child.parent is parent`
  (same instance, via the context cache).
- **No leaks** — hold a `weakref` to a transmuter, close the session, `gc.collect()`, and assert the
  weakref is dead — proving the context released it with its provider.
