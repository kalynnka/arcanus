try:
    import sqlalchemy as _sqlalchemy  # noqa: F401
except ImportError as e:
    raise ImportError(
        "Install arcanus[sqlalchemy] to use SqlalchemyMateria: "
        "pip install arcanus[sqlalchemy]"
    ) from e

from arcanus.materia.sqlalchemy.base import (
    SqlalchemyExpressionCompiler,
    SqlalchemyMateria,
)
from arcanus.materia.sqlalchemy.collections import attribute_keyed_list_dict
from arcanus.materia.sqlalchemy.database import (
    AsyncSession,
    Session,
)
from arcanus.materia.sqlalchemy.options import (
    contains_eager,
    defaultload,
    defer,
    joinedload,
    lazyload,
    load_only,
    noload,
    raiseload,
    selectin_polymorphic,
    selectinload,
    subqueryload,
    undefer,
    with_polymorphic,
)

__all__ = [
    "SqlalchemyMateria",
    "Session",
    "AsyncSession",
    "SqlalchemyExpressionCompiler",
    "attribute_keyed_list_dict",
    "contains_eager",
    "defaultload",
    "defer",
    "joinedload",
    "lazyload",
    "load_only",
    "noload",
    "raiseload",
    "selectin_polymorphic",
    "selectinload",
    "subqueryload",
    "undefer",
    "with_polymorphic",
]
