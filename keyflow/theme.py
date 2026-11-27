"""Global theme configuration loader and token resolver for KeyFlow v0.4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from keyflow.spec import FillValue, ShadowSpec, SizeSpec

THEMES_DIR = Path(__file__).parent / "themes"


class ThemeColors(BaseModel):
    text_primary: str = "#FAFBFD"
    text_secondary: str = "#B8CBE8"
    text_muted: str = "#7A8FA8"
    accent_primary: str = "#FAC23D"
    accent_secondary: str = "#38BDF8"
    surface_1: str = "#141E33"
    surface_2: str = "#1B2845"
    border_subtle: str = "#2D426B"
    positive: str = "#3DC7A3"
    warning: str = "#F08F38"
    danger: str = "#EF4444"


class ThemeTypography(BaseModel):
    font_display: str = "PingFang SC"
    font_body: str = "PingFang SC"
    font_numeric: str = "Helvetica Neue"
    scale: dict[str, float] = Field(
        default_factory=lambda: {
            "hero": 48.0,
            "title": 36.0,
            "heading": 24.0,
            "body": 18.0,
            "caption": 14.0,
        }
    )
    tracking: dict[str, float] = Field(
        default_factory=lambda: {"kicker": 0.12, "display": 0.02, "body": 0.0}
    )
    line_spacing: float = 1.25
    min_font_size: float = 14.0


class ThemeSafeMargin(BaseModel):
    x: float = 80.0
    y: float = 60.0


class ThemeCanvas(BaseModel):
    default_size: SizeSpec = Field(default_factory=lambda: SizeSpec(w=1920.0, h=1080.0))
    safe_margin: ThemeSafeMargin = Field(default_factory=ThemeSafeMargin)
    spacing_unit: float = 8.0


class ThemeSurfaceDefaults(BaseModel):
    default_corner_radius: float = 0.1
    default_stroke_width: float = 1.5
    shadow: ShadowSpec = Field(default_factory=ShadowSpec)


class ThemeConnectors(BaseModel):
    primary_width: float = 3.0
    secondary_width: float = 1.5
    default_color: str = "#B8CBE8"


class ThemeCharts(BaseModel):
    palette: list[str] = Field(
        default_factory=lambda: ["#FAC23D", "#38BDF8", "#3DC7A3", "#F08F38", "#A78BFA", "#F472B6"]
    )
    title_color: str = "#FAFBFD"
    axis_label_color: str = "#B8CBE8"
    legend_color: str = "#B8CBE8"
    gridline_color: str = "#2D426B"


class ThemeConstraints(BaseModel):
    min_contrast_ratio: float = 4.5


class ThemeSpec(BaseModel):
    """Component-agnostic global theme configuration."""

    name: str
    description: str = ""
    mode: Literal["dark", "light"] = "dark"
    keynote_theme: str = "White"
    background: FillValue = "#0F172A"
    colors: ThemeColors = Field(default_factory=ThemeColors)
    typography: ThemeTypography = Field(default_factory=ThemeTypography)
    canvas: ThemeCanvas = Field(default_factory=ThemeCanvas)
    surface_defaults: ThemeSurfaceDefaults = Field(default_factory=ThemeSurfaceDefaults)
    connectors: ThemeConnectors = Field(default_factory=ThemeConnectors)
    charts: ThemeCharts = Field(default_factory=ThemeCharts)
    constraints: ThemeConstraints = Field(default_factory=ThemeConstraints)


def list_themes() -> list[str]:
    """List built-in theme names."""
    if not THEMES_DIR.exists():
        return []
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def load_theme(name_or_path: str | Path) -> ThemeSpec | None:
    """Load a built-in theme by name or a custom theme JSON file by path."""
    raw = str(name_or_path)
    p = Path(raw)
    if p.suffix == ".json" and p.exists():
        return ThemeSpec.model_validate(json.loads(p.read_text(encoding="utf-8")))
    builtin = THEMES_DIR / f"{raw}.json"
    if builtin.exists():
        return ThemeSpec.model_validate(json.loads(builtin.read_text(encoding="utf-8")))
    return None


def build_token_map(theme: ThemeSpec) -> dict[str, Any]:
    """Build lookup map for '$token' references."""
    tokens: dict[str, Any] = {}
    for k, v in theme.colors.model_dump().items():
        tokens[f"${k}"] = v
    tokens["$font_display"] = theme.typography.font_display
    tokens["$font_body"] = theme.typography.font_body
    tokens["$font_numeric"] = theme.typography.font_numeric
    for k, v in theme.typography.scale.items():
        tokens[f"${k}"] = v
    for k, v in theme.typography.tracking.items():
        tokens[f"$tracking_{k}"] = v
    return tokens


def resolve_tokens(data: Any, token_map: dict[str, Any]) -> Any:
    """Recursively resolve '$token' strings in a spec dictionary or list."""
    if isinstance(data, str):
        return token_map.get(data, data)
    if isinstance(data, list):
        return [resolve_tokens(item, token_map) for item in data]
    if isinstance(data, dict):
        return {k: resolve_tokens(v, token_map) for k, v in data.items()}
    return data
