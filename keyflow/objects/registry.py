"""Object pacer and renderer registries for KeyFlow freeform canvas objects."""

from __future__ import annotations

from typing import Any, Callable

ObjectPacer = Callable[..., list[tuple[dict[str, dict[str, Any]], str]]]
ObjectRenderer = Callable[..., list[Any]]

OBJECT_PACERS: dict[str, ObjectPacer] = {}
OBJECT_RENDERERS: dict[str, ObjectRenderer] = {}


def register_object_pacer(kind: str) -> Callable[[ObjectPacer], ObjectPacer]:
    """Register a progressive sub-stage pacer for a canvas object kind."""

    def _decorator(fn: ObjectPacer) -> ObjectPacer:
        OBJECT_PACERS[kind] = fn
        return fn

    return _decorator


def register_object_renderer(kind: str) -> Callable[[ObjectRenderer], ObjectRenderer]:
    """Register a slide object renderer for a canvas object kind."""

    def _decorator(fn: ObjectRenderer) -> ObjectRenderer:
        OBJECT_RENDERERS[kind] = fn
        return fn

    return _decorator
