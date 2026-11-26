"""Reusable freeform canvas scene snippets for KeyFlow."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

_SNIPPETS_DIR = Path(__file__).resolve().parent
_BUILTIN_SNIPPET_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _parse_snippet_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid snippet JSON in {path.name}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("scene"), dict):
        raise ValueError(f"Invalid snippet file {path.name}: expected top-level 'scene' object.")
    return data


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
    return _parse_snippet_file(path)


def list_snippets() -> list[dict[str, str]]:
    """Return metadata for all built-in canvas snippets."""
    items: list[dict[str, str]] = []
    snippets_root = _SNIPPETS_DIR.resolve()
    for path in sorted(_SNIPPETS_DIR.glob("*.json")):
        if path.is_symlink() or not path.resolve().is_relative_to(snippets_root):
            continue
        data = _parse_snippet_file(path)
        items.append(
            {
                "id": str(data.get("id") or path.stem),
                "name": str(data.get("name") or path.stem),
                "description": str(data.get("description") or ""),
                "use_case": str(data.get("use_case") or ""),
            }
        )
    return items


def load_builtin_snippet(snippet_id: str) -> dict[str, Any]:
    """Safely load a built-in snippet by strict ID only (used by MCP entrypoints)."""
    clean_id = str(snippet_id).strip()
    if not _BUILTIN_SNIPPET_ID_RE.fullmatch(clean_id):
        raise ValueError(
            f"Invalid built-in snippet ID {snippet_id!r}: only lowercase letters, digits, and '_' are allowed."
        )
    snippets_root = _SNIPPETS_DIR.resolve()
    candidate = _SNIPPETS_DIR / f"{clean_id}.json"
    if candidate.is_symlink():
        raise ValueError(f"Refusing symlinked snippet file for ID {clean_id!r}.")
    if not candidate.exists():
        available = ", ".join(item["id"] for item in list_snippets())
        raise KeyError(f"Unknown built-in snippet {clean_id!r}. Available: {available}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(snippets_root) or not resolved.is_file():
        raise ValueError(f"Snippet {clean_id!r} resolves outside built-in snippets directory.")
    return copy.deepcopy(_parse_snippet_file(resolved)["scene"])


def load_snippet(name_or_path: str | Path) -> dict[str, Any]:
    """Return a deep copy of the snippet's `scene` template dictionary (supports custom paths in Python API)."""
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


__all__ = ["list_snippets", "load_builtin_snippet", "load_snippet", "instantiate_snippet"]
