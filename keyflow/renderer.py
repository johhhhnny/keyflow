"""Render .keyx slides to PNG images via Apple Keynote for visual critique."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_RENDER_PNG = "KEYFLOW_RENDER_PNG"
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def is_render_enabled(render_png: bool | None = None) -> bool:
    """Resolve whether PNG rendering is enabled.

    Precedence:
    1. Explicit ``render_png`` boolean if provided.
    2. ``KEYFLOW_RENDER_PNG`` environment variable (1/true/yes/on vs 0/false/no/off).
    3. Default ``False`` (production-safe: emit .keyx only unless enabled).
    """
    if render_png is not None:
        return bool(render_png)
    raw = os.environ.get(ENV_RENDER_PNG, "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY or raw == "":
        return False
    return False


def can_render_png() -> bool:
    """Return True if running on macOS with osascript available."""
    return sys.platform == "darwin" and shutil.which("osascript") is not None


def render_keyx_to_pngs(keyx_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Export a .keyx presentation to per-slide PNGs using Apple Keynote on macOS."""
    if not can_render_png():
        raise RuntimeError(
            "PNG rendering requires macOS with Apple Keynote ('osascript' unavailable). "
            "Your .keyx presentation is still compiled and valid."
        )

    src = Path(keyx_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Keynote file not found: {src}")

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for old_png in out.glob("*.png"):
        old_png.unlink()

    applescript = """
on run argv
    set srcPath to POSIX file (item 1 of argv)
    set outPath to POSIX file (item 2 of argv)
    tell application id "com.apple.Keynote"
        set doc to open srcPath
        export doc to outPath as slide images with properties {image format:PNG}
        close doc saving no
    end tell
end run
"""
    proc = subprocess.run(
        ["osascript", "-e", applescript, str(src), str(out)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or (
            "Ensure Apple Keynote is installed and allowed to run AppleScript."
        )
        raise RuntimeError(f"Keynote PNG export failed: {detail}")

    return sorted(out.glob("*.png"))
