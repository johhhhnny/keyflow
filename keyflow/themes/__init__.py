"""Visual theme presets (loaded from JSON data files) and background synthesis."""

from __future__ import annotations

import base64
import json
import random
import re
import struct
import zlib
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6})$")
_THEMES_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class ThemePreset:
    """Color, typography, and texture tokens for a KeyFlow presentation theme."""

    name: str
    description: str
    bg_rgb: tuple[int, int, int]
    bg_noise_amp: int
    title_rgb: tuple[float, float, float]
    subtitle_rgb: tuple[float, float, float]
    card_fill_rgb: tuple[float, float, float]
    card_border_rgb: tuple[float, float, float]
    subcard_fill_rgb: tuple[float, float, float]
    accent_fill_rgb: tuple[float, float, float]
    accent_border_rgb: tuple[float, float, float]
    success_fill_rgb: tuple[float, float, float]
    success_border_rgb: tuple[float, float, float]
    warn_fill_rgb: tuple[float, float, float]
    warn_border_rgb: tuple[float, float, float]
    group_fill_rgba: tuple[float, float, float, float]
    group_border_rgb: tuple[float, float, float]
    arrow_rgb: tuple[float, float, float]
    text_rgb: tuple[float, float, float]
    sublabel_rgb: tuple[float, float, float]
    badge_text_rgb: tuple[float, float, float]
    metric_text_rgb: tuple[float, float, float]
    accent_text_rgb: tuple[float, float, float]
    divider_rgb: tuple[float, float, float]
    flow_node_fill_rgb: tuple[float, float, float]
    flow_node_border_rgb: tuple[float, float, float]
    active_flow_fill_rgb: tuple[float, float, float]
    active_flow_border_rgb: tuple[float, float, float]
    chip_fill_rgb: tuple[float, float, float]
    action_banner_rgb: tuple[float, float, float]
    takeaway_pill_rgb: tuple[float, float, float]
    trend_up_rgb: tuple[float, float, float]
    trend_down_rgb: tuple[float, float, float]
    segment_palette: tuple[tuple[float, float, float], ...]
    font_title: str = "Helvetica Neue"
    font_body: str = "PingFang SC"
    bg_gradient_end_rgb: tuple[int, int, int] | None = None
    bg_gradient_angle: float = 135.0
    card_corner_px: float | None = None


def _rgb_int_tuple(val: Any, field_name: str) -> tuple[int, int, int]:
    if not isinstance(val, Sequence) or isinstance(val, (str, bytes)) or len(val) != 3:
        raise ValueError(f"Theme field '{field_name}' must be a 3-element integer RGB list.")
    return (int(val[0]), int(val[1]), int(val[2]))


def _rgb_float_tuple(val: Any, field_name: str) -> tuple[float, float, float]:
    if not isinstance(val, Sequence) or isinstance(val, (str, bytes)) or len(val) != 3:
        raise ValueError(f"Theme field '{field_name}' must be a 3-element float RGB list.")
    return (float(val[0]), float(val[1]), float(val[2]))


def _rgba_float_tuple(val: Any, field_name: str) -> tuple[float, float, float, float]:
    if not isinstance(val, Sequence) or isinstance(val, (str, bytes)) or len(val) != 4:
        raise ValueError(f"Theme field '{field_name}' must be a 4-element float RGBA list.")
    return (float(val[0]), float(val[1]), float(val[2]), float(val[3]))


def theme_from_dict(raw: Mapping[str, Any]) -> ThemePreset:
    """Construct a ThemePreset from a parsed JSON dictionary."""
    if not isinstance(raw, Mapping):
        raise ValueError("Theme JSON must be an object.")
    seg_raw = raw.get("segment_palette")
    if not isinstance(seg_raw, Sequence) or isinstance(seg_raw, (str, bytes)) or not seg_raw:
        raise ValueError("Theme field 'segment_palette' must be a non-empty list of RGB tuples.")
    segments = tuple(_rgb_float_tuple(c, "segment_palette[]") for c in seg_raw)

    end_raw = raw.get("bg_gradient_end_rgb")
    bg_end = _rgb_int_tuple(end_raw, "bg_gradient_end_rgb") if end_raw is not None else None

    return ThemePreset(
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        bg_rgb=_rgb_int_tuple(raw["bg_rgb"], "bg_rgb"),
        bg_noise_amp=int(raw.get("bg_noise_amp", 0)),
        title_rgb=_rgb_float_tuple(raw["title_rgb"], "title_rgb"),
        subtitle_rgb=_rgb_float_tuple(raw["subtitle_rgb"], "subtitle_rgb"),
        card_fill_rgb=_rgb_float_tuple(raw["card_fill_rgb"], "card_fill_rgb"),
        card_border_rgb=_rgb_float_tuple(raw["card_border_rgb"], "card_border_rgb"),
        subcard_fill_rgb=_rgb_float_tuple(raw["subcard_fill_rgb"], "subcard_fill_rgb"),
        accent_fill_rgb=_rgb_float_tuple(raw["accent_fill_rgb"], "accent_fill_rgb"),
        accent_border_rgb=_rgb_float_tuple(raw["accent_border_rgb"], "accent_border_rgb"),
        success_fill_rgb=_rgb_float_tuple(raw["success_fill_rgb"], "success_fill_rgb"),
        success_border_rgb=_rgb_float_tuple(raw["success_border_rgb"], "success_border_rgb"),
        warn_fill_rgb=_rgb_float_tuple(raw["warn_fill_rgb"], "warn_fill_rgb"),
        warn_border_rgb=_rgb_float_tuple(raw["warn_border_rgb"], "warn_border_rgb"),
        group_fill_rgba=_rgba_float_tuple(raw["group_fill_rgba"], "group_fill_rgba"),
        group_border_rgb=_rgb_float_tuple(raw["group_border_rgb"], "group_border_rgb"),
        arrow_rgb=_rgb_float_tuple(raw["arrow_rgb"], "arrow_rgb"),
        text_rgb=_rgb_float_tuple(raw["text_rgb"], "text_rgb"),
        sublabel_rgb=_rgb_float_tuple(raw["sublabel_rgb"], "sublabel_rgb"),
        badge_text_rgb=_rgb_float_tuple(raw["badge_text_rgb"], "badge_text_rgb"),
        metric_text_rgb=_rgb_float_tuple(raw["metric_text_rgb"], "metric_text_rgb"),
        accent_text_rgb=_rgb_float_tuple(raw["accent_text_rgb"], "accent_text_rgb"),
        divider_rgb=_rgb_float_tuple(raw["divider_rgb"], "divider_rgb"),
        flow_node_fill_rgb=_rgb_float_tuple(raw["flow_node_fill_rgb"], "flow_node_fill_rgb"),
        flow_node_border_rgb=_rgb_float_tuple(raw["flow_node_border_rgb"], "flow_node_border_rgb"),
        active_flow_fill_rgb=_rgb_float_tuple(raw["active_flow_fill_rgb"], "active_flow_fill_rgb"),
        active_flow_border_rgb=_rgb_float_tuple(raw["active_flow_border_rgb"], "active_flow_border_rgb"),
        chip_fill_rgb=_rgb_float_tuple(raw["chip_fill_rgb"], "chip_fill_rgb"),
        action_banner_rgb=_rgb_float_tuple(raw["action_banner_rgb"], "action_banner_rgb"),
        takeaway_pill_rgb=_rgb_float_tuple(raw["takeaway_pill_rgb"], "takeaway_pill_rgb"),
        trend_up_rgb=_rgb_float_tuple(raw["trend_up_rgb"], "trend_up_rgb"),
        trend_down_rgb=_rgb_float_tuple(raw["trend_down_rgb"], "trend_down_rgb"),
        segment_palette=segments,
        font_title=str(raw.get("font_title", "Helvetica Neue")),
        font_body=str(raw.get("font_body", "PingFang SC")),
        bg_gradient_end_rgb=bg_end,
        bg_gradient_angle=float(raw.get("bg_gradient_angle", 135.0)),
        card_corner_px=float(raw["card_corner_px"]) if raw.get("card_corner_px") is not None else None,
    )


def load_theme_file(path: str | Path) -> ThemePreset:
    """Load and validate a ThemePreset from an external JSON file."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Theme file not found: '{p}'.")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return theme_from_dict(raw)


def _load_builtin_themes() -> dict[str, ThemePreset]:
    themes: dict[str, ThemePreset] = {}
    for p in sorted(_THEMES_DIR.glob("*.json")):
        preset = load_theme_file(p)
        themes[preset.name] = preset
    return themes


THEMES: dict[str, ThemePreset] = _load_builtin_themes()


def get_theme(name_or_path: str) -> ThemePreset:
    """Resolve a built-in theme preset by name or load an external theme JSON file."""
    if name_or_path in THEMES:
        return THEMES[name_or_path]
    p = Path(name_or_path)
    if p.suffix.lower() == ".json" or p.exists():
        return load_theme_file(p)
    available = ", ".join(sorted(THEMES))
    raise ValueError(f"Unknown theme '{name_or_path}'. Available themes: {available} (or path to a .json file)")


def is_valid_hex_color(value: str) -> bool:
    """Return True when value is a #RRGGBB hex color string."""
    return isinstance(value, str) and bool(_HEX_COLOR_RE.match(value.strip()))


def hex_to_rgb_float(value: str) -> tuple[float, float, float]:
    """Convert a #RRGGBB hex string into normalized (r, g, b) floats in [0.0, 1.0]."""
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Invalid hex color '{value}'; expected #RRGGBB.")
    r = int(cleaned[0:2], 16) / 255.0
    g = int(cleaned[2:4], 16) / 255.0
    b = int(cleaned[4:6], 16) / 255.0
    return (round(r, 4), round(g, 4), round(b, 4))


def hex_to_rgb_int(value: str) -> tuple[int, int, int]:
    """Convert a #RRGGBB hex string into integer (r, g, b) channels in [0, 255]."""
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Invalid hex color '{value}'; expected #RRGGBB.")
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """Compute WCAG 2.x relative luminance for an sRGB (0..1) tuple."""
    def _lin(ch: float) -> float:
        return ch / 12.92 if ch <= 0.03928 else ((ch + 0.055) / 1.055) ** 2.4

    r, g, b = (_lin(max(0.0, min(1.0, c))) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    """Compute WCAG contrast ratio (>= 1.0) between foreground and background sRGB colors."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def apply_palette_overrides(
    base: ThemePreset,
    palette: Mapping[str, object] | None,
) -> ThemePreset:
    """Return a ThemePreset with optional freeform palette hex token overrides applied."""
    if not palette:
        return base

    updates: dict[str, object] = {}
    if isinstance(palette.get("bg_hex"), str):
        updates["bg_rgb"] = hex_to_rgb_int(palette["bg_hex"])
        if not isinstance(palette.get("bg_gradient_end_hex"), str):
            updates["bg_gradient_end_rgb"] = None
    if isinstance(palette.get("bg_gradient_end_hex"), str):
        updates["bg_gradient_end_rgb"] = hex_to_rgb_int(palette["bg_gradient_end_hex"])

    float_map = {
        "title_hex": "title_rgb",
        "subtitle_hex": "subtitle_rgb",
        "text_hex": "text_rgb",
        "card_fill_hex": "card_fill_rgb",
        "card_border_hex": "card_border_rgb",
        "accent_fill_hex": "accent_fill_rgb",
        "accent_border_hex": "accent_border_rgb",
        "success_fill_hex": "success_fill_rgb",
        "warn_fill_hex": "warn_fill_rgb",
        "arrow_hex": "arrow_rgb",
    }
    for src_key, dst_field in float_map.items():
        val = palette.get(src_key)
        if isinstance(val, str):
            updates[dst_field] = hex_to_rgb_float(val)

    if "accent_fill_rgb" in updates and "accent_border_rgb" not in updates:
        af = updates["accent_fill_rgb"]
        if isinstance(af, tuple) and len(af) == 3:
            is_dark_bg = (updates.get("bg_rgb", base.bg_rgb)[0] < 128)
            delta = 0.12 if is_dark_bg else -0.12
            updates["accent_border_rgb"] = tuple(max(0.0, min(1.0, c + delta)) for c in af)

    if "card_fill_rgb" in updates and isinstance(updates["card_fill_rgb"], tuple):
        updates["subcard_fill_rgb"] = updates["card_fill_rgb"]
    if "title_rgb" in updates and isinstance(updates["title_rgb"], tuple):
        updates["accent_text_rgb"] = updates["title_rgb"]
        updates["metric_text_rgb"] = updates["title_rgb"]

    series = palette.get("series_colors")
    if isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
        parsed_series = tuple(hex_to_rgb_float(c) for c in series if isinstance(c, str) and is_valid_hex_color(c))
        if parsed_series:
            updates["segment_palette"] = parsed_series

    return replace(base, **updates) if updates else base


@lru_cache(maxsize=8)
def render_textured_bg_png_b64(
    rgb: tuple[int, int, int],
    noise_amp: int,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Synthesize a crisp 1920x1080 fine-grain textured PNG using fast row-bank composition."""
    rng = random.Random((rgb[0] << 16) ^ (rgb[1] << 8) ^ rgb[2] ^ noise_amp)
    r0, g0, b0 = rgb

    bank_size = 32
    double_w = width * 2
    bank: list[bytes] = []
    for _ in range(bank_size):
        row = bytearray(double_w * 3)
        for i in range(double_w):
            delta = rng.randint(-noise_amp, noise_amp) if noise_amp > 0 else 0
            idx = i * 3
            row[idx] = max(0, min(255, r0 + delta))
            row[idx + 1] = max(0, min(255, g0 + delta))
            row[idx + 2] = max(0, min(255, b0 + delta))
        bank.append(bytes(row))

    row_bytes = width * 3
    raw_rows = bytearray()
    for _ in range(height):
        raw_rows.append(0)
        pattern = bank[rng.randrange(bank_size)]
        offset = rng.randrange(width) * 3
        raw_rows.extend(pattern[offset : offset + row_bytes])

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw_rows), level=1))
        + _chunk(b"IEND", b"")
    )
    return base64.b64encode(png_bytes).decode("ascii")
