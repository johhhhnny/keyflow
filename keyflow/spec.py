"""Native-first visual design specification for KeyFlow v0.4.

This module defines an unopinionated, 1:1 scene-graph DSL over Keynote's native
visual objects (Textbox, Shape, ConnectionLine, Image, Table, Chart, Group).
Agents author compositions, hierarchy, typography, color, and geometry directly
without rigid layout templates.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Color, Fill, Stroke, Effects
# ---------------------------------------------------------------------------


class RGBASpec(BaseModel):
    """RGBA color with channel values in [0.0, 1.0]."""

    r: float = Field(ge=0.0, le=1.0)
    g: float = Field(ge=0.0, le=1.0)
    b: float = Field(ge=0.0, le=1.0)
    a: float = Field(default=1.0, ge=0.0, le=1.0)


ColorValue = Union[str, RGBASpec]


def parse_color(value: ColorValue) -> tuple[float, float, float, float]:
    """Convert a hex string (#RGB, #RRGGBB, #RRGGBBAA) or RGBASpec to (r, g, b, a)."""
    if isinstance(value, RGBASpec):
        return (value.r, value.g, value.b, value.a)
    s = value.strip()
    if s.lower() == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if not s.startswith("#"):
        raise ValueError(f"Color string must start with '#', got {value!r}")
    hex_part = s[1:]
    if len(hex_part) == 3:
        r = int(hex_part[0] * 2, 16) / 255.0
        g = int(hex_part[1] * 2, 16) / 255.0
        b = int(hex_part[2] * 2, 16) / 255.0
        return (r, g, b, 1.0)
    if len(hex_part) == 6:
        r = int(hex_part[0:2], 16) / 255.0
        g = int(hex_part[2:4], 16) / 255.0
        b = int(hex_part[4:6], 16) / 255.0
        return (r, g, b, 1.0)
    if len(hex_part) == 8:
        r = int(hex_part[0:2], 16) / 255.0
        g = int(hex_part[2:4], 16) / 255.0
        b = int(hex_part[4:6], 16) / 255.0
        a = int(hex_part[6:8], 16) / 255.0
        return (r, g, b, a)
    raise ValueError(f"Unsupported hex color format: {value!r}")


class GradientStopSpec(BaseModel):
    """A color stop along a gradient [0.0, 1.0]."""

    color: ColorValue
    position: float = Field(ge=0.0, le=1.0)


class GradientFillSpec(BaseModel):
    """Linear or radial gradient fill."""

    type: Literal["linear", "radial"] = "linear"
    angle: float = 0.0
    stops: list[GradientStopSpec] = Field(min_length=2)


class ImageFillSpec(BaseModel):
    """Image fill inside a shape or background."""

    src: str
    scale: Literal["scale_to_fill", "scale_to_fit", "stretch", "original_size", "tile"] = (
        "scale_to_fill"
    )


FillValue = Union[ColorValue, GradientFillSpec, ImageFillSpec, None]


class StrokeSpec(BaseModel):
    """Outline stroke for shapes, textboxes, images, or connection lines."""

    color: ColorValue = "#FFFFFF"
    width: float = Field(default=1.5, gt=0.0)
    style: Literal["solid", "dashed", "dotted"] = "solid"
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ShadowSpec(BaseModel):
    """Drop, contact, or curved shadow effect."""

    type: Literal["drop", "contact", "curved"] = "drop"
    color: ColorValue = "#000000"
    angle: float = 270.0
    offset: float = 8.0
    radius: float = 16.0
    opacity: float = Field(default=0.35, ge=0.0, le=1.0)


class ReflectionSpec(BaseModel):
    """Floor reflection effect."""

    opacity: float = Field(default=0.3, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


class SizeSpec(BaseModel):
    """Canvas or object dimensions in points."""

    w: float = Field(gt=0.0)
    h: float = Field(gt=0.0)


class GeometrySpec(BaseModel):
    """Position, size, rotation, and flip on the slide canvas."""

    x: float
    y: float
    w: float = Field(gt=0.0)
    h: float = Field(gt=0.0)
    angle: float = 0.0
    flip_h: bool = False
    flip_v: bool = False


class InsetsSpec(BaseModel):
    """Inner padding in points."""

    top: float = 0.0
    bottom: float = 0.0
    left: float = 0.0
    right: float = 0.0


# ---------------------------------------------------------------------------
# Rich Text
# ---------------------------------------------------------------------------


class TextStyleSpec(BaseModel):
    """Character-level typography properties (supports '$token' references)."""

    font: str = "Helvetica Neue"
    size: Union[float, str] = 24.0
    color: ColorValue = "#FFFFFF"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    tracking: Union[float, str] = 0.0  # Fraction of em (e.g. 0.05 = subtle letter spacing)
    baseline: Literal["normal", "superscript", "subscript"] = "normal"
    hyperlink: str | None = None


class TextRunSpec(BaseModel):
    """A span of text with optional character style overrides."""

    text: str
    style: TextStyleSpec | None = None


class ListStyleSpec(BaseModel):
    """Paragraph list formatting."""

    type: Literal["none", "bullet", "number"] = "none"
    bullet: str = "•"
    number_format: Literal[
        "decimal", "upper_alpha", "lower_alpha", "upper_roman", "lower_roman"
    ] = "decimal"
    level: int = Field(default=0, ge=0, le=8)


class ParagraphSpec(BaseModel):
    """A single paragraph containing one or more styled runs."""

    runs: list[TextRunSpec]
    alignment: Literal["left", "center", "right", "justified"] | None = None
    line_spacing: float | None = None
    space_before: float = 0.0
    space_after: float = 0.0
    list_style: ListStyleSpec | None = None
    style: TextStyleSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_string_runs(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"runs": [{"text": data}]}
        if isinstance(data, dict) and isinstance(data.get("runs"), str):
            data = dict(data)
            data["runs"] = [{"text": data["runs"]}]
        return data


class TextSpec(BaseModel):
    """Rich text content: accepts a plain string, or structured paragraphs."""

    string: str | None = None
    paragraphs: list[ParagraphSpec] | None = None
    style: TextStyleSpec = Field(default_factory=TextStyleSpec)
    alignment: Literal["left", "center", "right", "justified"] = "left"
    line_spacing: float = Field(default=1.2, gt=0.0)

    @model_validator(mode="before")
    @classmethod
    def _coerce_plain_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"string": data}
        return data


# ---------------------------------------------------------------------------
# Semantic Identity & Composition Model (preserved for future multi-slide/motion)
# ---------------------------------------------------------------------------


class SemanticIdentity(BaseModel):
    """Why a visual object exists, what it expresses, and its role in the scene."""

    role: str  # e.g. "hero_visual", "core_thesis", "evidence_chart", "causal_link", "anchor_number"
    meaning: str  # Concise statement of what this object communicates
    hierarchy: Literal["primary", "secondary", "supporting", "ambient"] = "secondary"
    source_claim: str | None = None


class SemanticBriefSpec(BaseModel):
    """Stage 1 output: structured understanding of the source text."""

    core_thesis: str
    audience: str = "General / Decision Makers"
    goal: str = ""
    key_facts: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)  # causal, contrast, comparison, etc.
    visual_subject: str | None = None
    text_vs_visual: str | None = None


class CompositionSpec(BaseModel):
    """Stage 2 & 3 output: visual concept, composition intent, and spatial strategy."""

    visual_concept: str
    central_tension: str | None = None
    expression_form: str = "custom"  # e.g. contrast, flow, data, hero_visual, editorial, diagram, custom
    focal_point: str | None = None
    reading_order: list[str] = Field(default_factory=list)  # ordered object IDs
    spatial_strategy: str | None = None
    color_rationale: str | None = None


# ---------------------------------------------------------------------------
# Native Visual Objects
# ---------------------------------------------------------------------------


ShapeKind = Literal[
    "rect",
    "rounded_rect",
    "oval",
    "triangle",
    "diamond",
    "pentagon",
    "hexagon",
    "octagon",
    "star",
    "arrow",
    "pill",
    "custom",
]


class TextboxSpec(BaseModel):
    """Native Keynote Textbox."""

    type: Literal["textbox"] = "textbox"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    geometry: GeometrySpec
    text: TextSpec
    fill: FillValue = None
    stroke: StrokeSpec | None = None
    shadow: ShadowSpec | None = None
    reflection: ReflectionSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    padding: InsetsSpec = Field(default_factory=InsetsSpec)
    vertical_alignment: Literal["top", "center", "bottom"] = "top"
    shrink_to_fit: bool = False


class ShapeSpec(BaseModel):
    """Native Keynote Shape (primitive or custom Bezier path)."""

    type: Literal["shape"] = "shape"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    geometry: GeometrySpec
    shape: ShapeKind = "rect"
    corner_radius: float = Field(default=0.12, ge=0.0, le=0.5)
    star_points: int = Field(default=5, ge=3, le=32)
    star_inner_ratio: float = Field(default=0.4, gt=0.05, lt=1.0)
    path: str | None = None  # SVG path 'd' string when shape == 'custom'
    path_space: SizeSpec | None = None  # Defaults to unit square (1x1)
    fill: FillValue = "#3B82F6"
    stroke: StrokeSpec | None = None
    shadow: ShadowSpec | None = None
    reflection: ReflectionSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    text: TextSpec | None = None
    vertical_alignment: Literal["top", "center", "bottom"] = "center"
    title_on_top: bool = False


MagnetSide = Literal[
    "center",
    "north",
    "south",
    "east",
    "west",
    "north_east",
    "north_west",
    "south_east",
    "south_west",
]

LineEndStyle = Literal[
    "none",
    "filled_arrow",
    "open_arrow",
    "filled_circle",
    "open_circle",
    "filled_diamond",
    "open_diamond",
    "filled_square",
    "open_square",
]


class AnchorSpec(BaseModel):
    """Optional anchor attaching a connection endpoint to an object's magnet."""

    object_id: str
    magnet: MagnetSide = "center"


class ConnectionSpec(BaseModel):
    """Native Keynote ConnectionLine (straight, curved, or orthogonal connector)."""

    type: Literal["connection"] = "connection"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    line_type: Literal["straight", "curved", "orthogonal"] = "straight"
    from_point: tuple[float, float]
    to_point: tuple[float, float]
    control_point: tuple[float, float] | None = None
    from_anchor: AnchorSpec | None = None
    to_anchor: AnchorSpec | None = None
    tail_end: LineEndStyle = "none"
    head_end: LineEndStyle = "filled_arrow"
    stroke: StrokeSpec = Field(default_factory=StrokeSpec)
    shadow: ShadowSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ImageSpec(BaseModel):
    """Native Keynote Image with optional mask, frame stroke, shadow, and reflection."""

    type: Literal["image"] = "image"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    geometry: GeometrySpec
    src: str
    mask_shape: Literal["rect", "rounded_rect", "oval", "custom"] | None = None
    mask_corner_radius: float = Field(default=0.1, ge=0.0, le=0.5)
    mask_path: str | None = None
    stroke: StrokeSpec | None = None
    shadow: ShadowSpec | None = None
    reflection: ReflectionSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class TableColumnSpec(BaseModel):
    """Column definition for a native Keynote Table."""

    title: str = ""
    width: float = Field(default=240.0, gt=0.0)
    alignment: Literal["left", "center", "right", "justified"] = "left"


class TableCellSpec(BaseModel):
    """Cell value with optional fill or text color override."""

    value: Union[str, float, int]
    fill: ColorValue | None = None
    text_color: ColorValue | None = None
    bold: bool | None = None


class TableSpec(BaseModel):
    """Native Keynote Table."""

    type: Literal["table"] = "table"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    geometry: GeometrySpec
    columns: list[TableColumnSpec] = Field(min_length=1)
    rows: list[list[Union[TableCellSpec, str, float, int]]] = Field(default_factory=list)
    header_rows: int = Field(default=1, ge=0)
    alternating_rows: bool = False
    alternating_fill: ColorValue = "#F3F4F6"
    header_fill: ColorValue = "#1E293B"
    header_text: TextStyleSpec = Field(
        default_factory=lambda: TextStyleSpec(size=24.0, color="#FFFFFF", bold=True)
    )
    body_text: TextStyleSpec = Field(
        default_factory=lambda: TextStyleSpec(size=22.0, color="#1E293B")
    )
    grid_stroke: StrokeSpec | None = Field(
        default_factory=lambda: StrokeSpec(color="#CBD5E1", width=0.5)
    )
    border_stroke: StrokeSpec | None = Field(
        default_factory=lambda: StrokeSpec(color="#94A3B8", width=1.0)
    )


ChartKind = Literal[
    "bar",
    "column",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "bubble",
    "radar",
    "stacked_bar",
    "stacked_column",
    "stacked_area",
    "mixed",
]


class ChartSeriesSpec(BaseModel):
    """One data series in a native Keynote Chart."""

    name: str
    values: list[float]
    color: ColorValue | None = None
    mixed_type: Literal["column", "line", "area"] | None = None


class ChartAxisSpec(BaseModel):
    """Axis configuration for a native Keynote Chart."""

    title: str | None = None
    show_gridlines: bool = True
    show_labels: bool = True
    label_color: ColorValue = "#CBD5E1"
    label_size: float = 20.0
    min_value: float | None = None
    max_value: float | None = None


class ChartSpec(BaseModel):
    """Native Keynote Chart."""

    type: Literal["chart"] = "chart"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    geometry: GeometrySpec
    chart_type: ChartKind = "column"
    title: str | None = None
    title_color: ColorValue = "#FFFFFF"
    title_size: float = 32.0
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeriesSpec] = Field(min_length=1)
    legend: bool = True
    legend_color: ColorValue = "#CBD5E1"
    legend_size: float = 20.0
    category_axis: ChartAxisSpec = Field(default_factory=ChartAxisSpec)
    value_axis: ChartAxisSpec = Field(default_factory=ChartAxisSpec)
    colors: list[ColorValue] | None = None


class GroupSpec(BaseModel):
    """Hierarchical group of native visual objects."""

    type: Literal["group"] = "group"
    id: str | None = None
    semantic: SemanticIdentity | None = None
    title: str | None = None
    children: list["VisualObjectSpec"] = Field(default_factory=list)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


VisualObjectSpec = Annotated[
    Union[
        TextboxSpec,
        ShapeSpec,
        ConnectionSpec,
        ImageSpec,
        TableSpec,
        ChartSpec,
        GroupSpec,
    ],
    Field(discriminator="type"),
]

GroupSpec.model_rebuild()


# ---------------------------------------------------------------------------
# Slide & Deck
# ---------------------------------------------------------------------------


class SlideSpec(BaseModel):
    """One designed slide: semantic brief, composition model, background, objects, and note."""

    id: str | None = None
    brief: SemanticBriefSpec | None = None
    composition: CompositionSpec | None = None
    background: FillValue = None
    objects: list[VisualObjectSpec] = Field(default_factory=list)
    note: str | None = None


class DeckSpec(BaseModel):
    """A complete presentation design specification."""

    slide_size: SizeSpec = Field(default_factory=lambda: SizeSpec(w=1920.0, h=1080.0))
    theme: str = "midnight_indigo"
    locale: str = "en_US"
    slides: list[SlideSpec] = Field(min_length=1)
