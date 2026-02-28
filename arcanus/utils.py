from functools import lru_cache
from typing import TypeVar

from pydantic import TypeAdapter

T = TypeVar("T")


@lru_cache(maxsize=100)
def get_cached_adapter(type: type[T]) -> TypeAdapter[T]:
    """Cached TypeAdapter factory to avoid recreating adapters for the same type."""
    return TypeAdapter(type)
