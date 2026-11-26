"""Visual theme presets and fast 1920x1080 fine-grain textured background synthesis."""

from __future__ import annotations

import base64
import random
import re
import struct
import zlib
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Mapping, Sequence

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6})$")


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


_DARK_SEGMENTS: tuple[tuple[float, float, float], ...] = (
    (0.92, 0.84, 0.40),  # warm yellow
    (0.58, 0.85, 0.38),  # lime green
    (0.86, 0.49, 0.46),  # coral salmon
    (0.42, 0.82, 0.80),  # aqua cyan
    (0.66, 0.56, 0.86),  # soft violet
    (0.44, 0.72, 0.96),  # sky blue
)

_LIGHT_SEGMENTS: tuple[tuple[float, float, float], ...] = (
    (0.85, 0.62, 0.12),
    (0.24, 0.64, 0.30),
    (0.82, 0.34, 0.32),
    (0.14, 0.58, 0.66),
    (0.46, 0.36, 0.76),
    (0.20, 0.48, 0.82),
)


THEMES: dict[str, ThemePreset] = {
    "slate_dark": ThemePreset(
        name="slate_dark",
        description="Charcoal slate gradient background, warm yellow title, deep navy cards, dashed blue group containers, crisp white arrows.",
        bg_rgb=(74, 74, 74),
        bg_noise_amp=5,
        bg_gradient_end_rgb=(54, 56, 60),
        title_rgb=(0.95, 0.86, 0.36),
        subtitle_rgb=(0.82, 0.85, 0.90),
        card_fill_rgb=(0.125, 0.259, 0.427),
        card_border_rgb=(0.44, 0.56, 0.72),
        subcard_fill_rgb=(0.125, 0.259, 0.427),
        accent_fill_rgb=(0.175, 0.365, 0.575),
        accent_border_rgb=(0.95, 0.86, 0.36),
        success_fill_rgb=(0.095, 0.295, 0.285),
        success_border_rgb=(0.28, 0.80, 0.66),
        warn_fill_rgb=(0.345, 0.215, 0.145),
        warn_border_rgb=(0.94, 0.62, 0.24),
        group_fill_rgba=(0.14, 0.20, 0.28, 0.16),
        group_border_rgb=(0.56, 0.67, 0.80),
        arrow_rgb=(1.0, 1.0, 1.0),
        text_rgb=(1.0, 1.0, 1.0),
        sublabel_rgb=(0.78, 0.85, 0.94),
        badge_text_rgb=(0.62, 0.85, 1.0),
        metric_text_rgb=(0.95, 0.86, 0.36),
        accent_text_rgb=(0.95, 0.86, 0.36),
        divider_rgb=(0.52, 0.60, 0.70),
        flow_node_fill_rgb=(0.17, 0.40, 0.68),
        flow_node_border_rgb=(0.44, 0.64, 0.86),
        active_flow_fill_rgb=(0.89, 0.49, 0.13),
        active_flow_border_rgb=(0.98, 0.76, 0.44),
        chip_fill_rgb=(0.43, 0.44, 0.46),
        action_banner_rgb=(0.30, 0.62, 0.16),
        takeaway_pill_rgb=(0.74, 0.24, 0.17),
        trend_up_rgb=(0.90, 0.36, 0.32),
        trend_down_rgb=(0.48, 0.84, 0.36),
        segment_palette=_DARK_SEGMENTS,
    ),
    "midnight_indigo": ThemePreset(
        name="midnight_indigo",
        description="Deep midnight navy gradient, amber title, slate-indigo cards, cyan-tinted dashed containers.",
        bg_rgb=(26, 33, 50),
        bg_noise_amp=4,
        bg_gradient_end_rgb=(16, 20, 32),
        title_rgb=(0.98, 0.75, 0.24),
        subtitle_rgb=(0.68, 0.75, 0.86),
        card_fill_rgb=(0.118, 0.184, 0.310),
        card_border_rgb=(0.35, 0.52, 0.78),
        subcard_fill_rgb=(0.145, 0.224, 0.369),
        accent_fill_rgb=(0.17, 0.34, 0.56),
        accent_border_rgb=(0.98, 0.75, 0.24),
        success_fill_rgb=(0.08, 0.27, 0.27),
        success_border_rgb=(0.24, 0.82, 0.68),
        warn_fill_rgb=(0.32, 0.18, 0.14),
        warn_border_rgb=(0.96, 0.60, 0.22),
        group_fill_rgba=(0.12, 0.22, 0.36, 0.20),
        group_border_rgb=(0.42, 0.68, 0.90),
        arrow_rgb=(0.94, 0.96, 1.0),
        text_rgb=(0.98, 0.99, 1.0),
        sublabel_rgb=(0.72, 0.82, 0.95),
        badge_text_rgb=(0.48, 0.84, 0.98),
        metric_text_rgb=(0.98, 0.75, 0.24),
        accent_text_rgb=(0.98, 0.75, 0.24),
        divider_rgb=(0.38, 0.52, 0.72),
        flow_node_fill_rgb=(0.16, 0.36, 0.66),
        flow_node_border_rgb=(0.40, 0.62, 0.90),
        active_flow_fill_rgb=(0.92, 0.50, 0.14),
        active_flow_border_rgb=(0.99, 0.78, 0.42),
        chip_fill_rgb=(0.28, 0.34, 0.46),
        action_banner_rgb=(0.24, 0.62, 0.22),
        takeaway_pill_rgb=(0.78, 0.24, 0.20),
        trend_up_rgb=(0.95, 0.38, 0.34),
        trend_down_rgb=(0.42, 0.88, 0.44),
        segment_palette=_DARK_SEGMENTS,
    ),
    "paper_light": ThemePreset(
        name="paper_light",
        description="Warm off-white gradient canvas, deep slate title, crisp blue-tinted cards, dark slate arrows.",
        bg_rgb=(246, 244, 238),
        bg_noise_amp=3,
        bg_gradient_end_rgb=(234, 231, 224),
        title_rgb=(0.12, 0.20, 0.35),
        subtitle_rgb=(0.36, 0.42, 0.50),
        card_fill_rgb=(0.14, 0.29, 0.49),
        card_border_rgb=(0.10, 0.22, 0.38),
        subcard_fill_rgb=(0.20, 0.37, 0.59),
        accent_fill_rgb=(0.82, 0.38, 0.14),
        accent_border_rgb=(0.56, 0.22, 0.06),
        success_fill_rgb=(0.09, 0.42, 0.36),
        success_border_rgb=(0.06, 0.30, 0.25),
        warn_fill_rgb=(0.68, 0.32, 0.12),
        warn_border_rgb=(0.48, 0.20, 0.06),
        group_fill_rgba=(0.14, 0.29, 0.49, 0.08),
        group_border_rgb=(0.25, 0.40, 0.60),
        arrow_rgb=(0.18, 0.24, 0.34),
        text_rgb=(1.0, 1.0, 1.0),
        sublabel_rgb=(0.84, 0.90, 0.97),
        badge_text_rgb=(0.98, 0.88, 0.54),
        metric_text_rgb=(0.99, 0.88, 0.44),
        accent_text_rgb=(0.14, 0.29, 0.49),
        divider_rgb=(0.45, 0.52, 0.62),
        flow_node_fill_rgb=(0.16, 0.35, 0.62),
        flow_node_border_rgb=(0.12, 0.26, 0.48),
        active_flow_fill_rgb=(0.86, 0.42, 0.10),
        active_flow_border_rgb=(0.62, 0.26, 0.04),
        chip_fill_rgb=(0.34, 0.38, 0.44),
        action_banner_rgb=(0.20, 0.54, 0.16),
        takeaway_pill_rgb=(0.72, 0.20, 0.16),
        trend_up_rgb=(0.78, 0.18, 0.16),
        trend_down_rgb=(0.14, 0.54, 0.20),
        segment_palette=_LIGHT_SEGMENTS,
    ),
}


def get_theme(name: str) -> ThemePreset:
    """Resolve a built-in theme preset by name."""
    if name not in THEMES:
        available = ", ".join(sorted(THEMES))
        raise ValueError(f"Unknown theme '{name}'. Available themes: {available}")
    return THEMES[name]


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
