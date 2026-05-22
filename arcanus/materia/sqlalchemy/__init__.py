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

__all__ = [
    "SqlalchemyMateria",
    "Session",
    "AsyncSession",
    "SqlalchemyExpressionCompiler",
    "attribute_keyed_list_dict",
]
