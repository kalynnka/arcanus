try:
    import redis as _redis  # noqa: F401
except ImportError as e:
    raise ImportError(
        "Install arcanus[redis] to use RedisMateria: pip install arcanus[redis]"
    ) from e

from arcanus.materia.redis.base import RedisMateria
from arcanus.materia.redis.client import AsyncClient, Client

__all__ = [
    "RedisMateria",
    "Client",
    "AsyncClient",
]
