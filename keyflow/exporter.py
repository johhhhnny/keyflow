"""Optional macOS Apple Keynote PNG preview exporter."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def export_slide_pngs(keyx_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Optional macOS Keynote helper: export a .keyx file as PNG slide previews."""
    if sys.platform != "darwin" or shutil.which("osascript") is None:
        raise RuntimeError(
            "PNG preview export requires macOS with Apple Keynote ('osascript' is unavailable here). "
            "Your .keyx presentation can still be compiled cleanly on any OS."
        )

    src = Path(keyx_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Keynote file not found: {src}")

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

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
        detail = proc.stderr.strip() or "Make sure Apple Keynote is installed and allowed to run AppleScript."
        raise RuntimeError(f"Keynote PNG export failed: {detail}")
    return sorted(out.glob("*.png"))
