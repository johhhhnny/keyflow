"""Reusable freeform canvas scene snippets for KeyFlow."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_SNIPPETS_DIR = Path(__file__).resolve().parent


def _load_raw_snippet(name_or_path: str | Path) -> dict[str, Any]:
    raw_str = str(name_or_path).strip()
    candidate = Path(raw_str)
    if raw_str.endswith(".json") or candidate.is_file():
        path = candidate
    else:
        path = _SNIPPETS_DIR / f"{raw_str}.json"
    if not path.is_file():
        available = ", ".join(item["id"] for item in list_snippets())
        raise KeyError(f"Unknown snippet {name_or_path!r}. Available built-in snippets: {available}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scene"), dict):
        raise ValueError(f"Invalid snippet file {path}: expected top-level 'scene' object.")
    return data


def list_snippets() -> list[dict[str, str]]:
    """Return metadata for all built-in canvas snippets."""
    items: list[dict[str, str]] = []
    for path in sorted(_SNIPPETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": str(data.get("id") or path.stem),
                "name": str(data.get("name") or path.stem),
                "description": str(data.get("description") or ""),
                "use_case": str(data.get("use_case") or ""),
            }
        )
    return items


def load_snippet(name_or_path: str | Path) -> dict[str, Any]:
    """Return a deep copy of the snippet's `scene` template dictionary."""
    data = _load_raw_snippet(name_or_path)
    return copy.deepcopy(data["scene"])


def instantiate_snippet(
    name_or_path: str | Path,
    *,
    scene_id: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
) -> dict[str, Any]:
    """Instantiate a canvas scene dict from a snippet with optional id/title overrides."""
    scene = load_snippet(name_or_path)
    if scene_id is not None:
        scene["id"] = scene_id
    if title is not None:
        scene["title"] = title
    if subtitle is not None:
        scene["subtitle"] = subtitle
    return scene


__all__ = ["list_snippets", "load_snippet", "instantiate_snippet"]
