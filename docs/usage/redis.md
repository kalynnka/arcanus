# Redis Materia

!!! warning "Work in progress"
    `RedisMateria` is **experimental and incomplete**. The API shown here is provisional and will
    change; relationship loading and querying are not implemented. Don't build on it yet — use
    [SQLAlchemy](sqlalchemy/index.md) for real persistence, or [NoOp](noop/index.md) for backend-free
    objects.

The Redis backend maps each transmuter to a key space and stores records under `{prefix}:{identity}`.
You install it as an extra and bless transmuters with an optional key prefix:

```bash
pip install "arcanus[redis]"
```

```python
from arcanus.materia.redis import RedisMateria, Redis   # AsyncRedis for async

materia = RedisMateria()

@materia.bless("author")        # key prefix; defaults to the class name if omitted
class Author(BaseTransmuter):
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str
# keys are stored as "author:{id}"
```

## Status

What exists today is the binding and key-prefix registration plus a client wrapper (`Redis` /
`AsyncRedis`). Relationship loading is a no-op and there is no query/expression layer, so the
backend-neutral [expressions & cursors](noop/querying.md) do not yet target Redis.

This page will grow as the backend matures. Track progress on the
[repository](https://github.com/kalynnka/arcanus).
