"""Custom SQLAlchemy collection classes for arcanus associations."""

from __future__ import annotations

from collections.abc import Callable
from operator import attrgetter
from typing import Any

from sqlalchemy.orm.collections import collection


class KeyFuncListDict(dict):
    """A dict-of-lists collection class for SQLAlchemy relationships.

    Groups ORM objects by a key function into ``dict[str, list[ORM]]``.
    Unlike ``attribute_keyed_dict`` which maps each key to a single value
    (silently overwriting duplicates), this collection keeps all values
    under the same key in a list.

    Usage with SQLAlchemy::

        relationship(
            "Child",
            collection_class=attribute_keyed_list_dict("role"),
            ...
        )
    """

    def __init__(self, keyfunc: Callable[[Any], Any]):
        super().__init__()
        self.keyfunc = keyfunc

    @collection.appender  # type: ignore[misc]
    def set(self, value: Any, _sa_initiator: Any = None) -> None:
        """Append *value* to the list at ``keyfunc(value)``."""
        key = self.keyfunc(value)
        if key not in self:
            dict.__setitem__(self, key, [])
        dict.__getitem__(self, key).append(value)

    @collection.remover  # type: ignore[misc]
    def remove(self, value: Any, _sa_initiator: Any = None) -> None:
        """Remove *value* from the list at ``keyfunc(value)``."""
        key = self.keyfunc(value)
        lst = dict.__getitem__(self, key)
        lst.remove(value)
        if not lst:
            dict.__delitem__(self, key)

    @collection.iterator  # type: ignore[misc]
    def _values(self):
        """Yield every individual ORM object across all keys."""
        for lst in dict.values(self):
            yield from lst

    def __repr__(self) -> str:
        return f"KeyFuncListDict({dict.__repr__(self)})"


def attribute_keyed_list_dict(attr_name: str) -> type[KeyFuncListDict]:
    """Collection class factory grouping ORM objects by attribute into lists.

    Drop-in replacement for ``attribute_keyed_dict`` when multiple rows
    may share the same key value.

    Usage::

        relationship(
            "ArticleGeneratedFile",
            collection_class=attribute_keyed_list_dict("role"),
            ...
        )

    Args:
        attr_name: The attribute name on the child ORM model used as grouping key.

    Returns:
        A callable that constructs a :class:`KeyFuncListDict`.
    """
    getter = attrgetter(attr_name)

    class _Factory(KeyFuncListDict):
        def __init__(self) -> None:
            super().__init__(keyfunc=getter)

    _Factory.__name__ = f"KeyFuncListDict(keyfunc={attr_name!r})"
    _Factory.__qualname__ = _Factory.__name__
    return _Factory
