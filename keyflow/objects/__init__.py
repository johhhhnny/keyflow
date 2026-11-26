"""Modular canvas object renderers and progressive pacers for KeyFlow."""

from __future__ import annotations

from keyflow.objects import charts as _charts  # noqa: F401 (registers chart renderer)
from keyflow.objects import pacers as _pacers  # noqa: F401 (registers chart/table/diagram pacers)
from keyflow.objects import table as _table  # noqa: F401 (registers table renderer)
from keyflow.objects.registry import (
    OBJECT_PACERS,
    OBJECT_RENDERERS,
    register_object_pacer,
    register_object_renderer,
)

__all__ = [
    "OBJECT_PACERS",
    "OBJECT_RENDERERS",
    "register_object_pacer",
    "register_object_renderer",
]
