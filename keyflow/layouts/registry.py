"""Layout solver registry for KeyFlow scenes."""

from __future__ import annotations

from typing import Any, Callable

LayoutSolver = Callable[..., Any]

LAYOUT_REGISTRY: dict[str, LayoutSolver] = {}


def register_layout(name: str) -> Callable[[LayoutSolver], LayoutSolver]:
    """Register a layout solver under a scene layout name."""

    def _decorator(fn: LayoutSolver) -> LayoutSolver:
        LAYOUT_REGISTRY[name] = fn
        return fn

    return _decorator


def get_layout_solver(name: str) -> LayoutSolver:
    """Return the registered solver for `name`, raising KeyError if unknown."""
    if name not in LAYOUT_REGISTRY:
        raise KeyError(f"Unknown layout solver: {name!r}. Registered: {sorted(LAYOUT_REGISTRY)}")
    return LAYOUT_REGISTRY[name]
