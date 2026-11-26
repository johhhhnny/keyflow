"""Cognitive storyboard DSL models and mode-aware structural validator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Literal, Sequence

from keyflow.themes import THEMES, is_valid_hex_color, load_theme_file

LayoutMode = Literal[
    "canvas",
    "horizontal_flow",
    "vertical_flow",
    "comparison",
    "hub_spoke",
    "flow_dag",
    "architecture_evolution",
    "sequence_timeline",
    "metrics_cards",
    "proportion_bar",
    "comparison_matrix",
]
NodeKind = Literal["card", "group_dashed"]
NodeVariant = Literal["primary", "accent", "muted", "success", "warn"]
ChildLayout = Literal["row", "column", "grid"]
CaptionPosition = Literal["bottom", "top", "inside"]
EdgeStyle = Literal["solid", "dashed"]
PacingMode = Literal["auto", "compact", "manual"]
TrendDirection = Literal["up", "down", "neutral"]
EvidenceType = Literal["thesis", "fact", "relation", "inference", "counter_evidence", "conclusion", "example"]
ConfidenceLevel = Literal["high", "medium", "low"]
RegionArrange = Literal["stack", "row", "grid"]
CanvasObjectKind = Literal["chart", "table", "card", "textbox", "shape", "callout", "diagram"]
ChartType = Literal["column", "bar", "pie", "donut", "line", "area", "stacked_column", "stacked_bar", "scatter", "waterfall"]
ChartReveal = Literal["whole", "by_series", "by_category"]
ChartRenderMode = Literal["auto", "vector", "native"]
TableReveal = Literal["whole", "by_row", "by_column"]
ShapeType = Literal["rounded_rect", "rect", "ellipse", "pill", "custom"]
DiagramLayout = Literal["horizontal", "vertical", "dag", "hub_spoke"]
TextAlign = Literal["left", "center", "right"]


@dataclass(slots=True)
class StoryClaimSpec:
    """One atomic epistemic claim/evidence entry linking slides back to the source article."""

    id: str
    type: EvidenceType
    claim: str
    source_quote: str | None = None
    source_id: str | None = None
    metric_scope: str | None = None
    confidence: ConfidenceLevel | None = None


@dataclass(slots=True)
class StoryModelSpec:
    """Structured Stage 0 story spine carried alongside Stage 1 scenes for fidelity verification."""

    core_question: str | None = None
    claims: list[StoryClaimSpec] = field(default_factory=list)


@dataclass(slots=True)
class ChildNodeSpec:
    """A compact sub-concept card nested inside an expanded group container."""

    id: str
    label: str
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    variant: NodeVariant = "primary"
    note: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NodeSpec:
    """Top-level concept node in a scene, optionally expandable into a dashed group."""

    id: str
    label: str
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    kind: NodeKind = "card"
    variant: NodeVariant = "primary"
    children: list[ChildNodeSpec] = field(default_factory=list)
    child_layout: ChildLayout = "row"
    caption_position: CaptionPosition = "bottom"
    note: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EdgeSpec:
    """Directed relationship between two top-level nodes."""

    id: str
    from_id: str
    to_id: str
    label: str | None = None
    style: EdgeStyle = "solid"


@dataclass(slots=True)
class PinnedFlowGroupSpec:
    """A dashed legend container wrapping contiguous nodes inside the Deck pinned_flow ribbon."""

    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PinnedFlowSpec:
    """Deck-level persistent top navigation ribbon shared across scenes."""

    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    groups: list[PinnedFlowGroupSpec] = field(default_factory=list)


@dataclass(slots=True)
class ProportionItemSpec:
    """One quantitative segment in a proportion_bar scene."""

    id: str
    label: str
    value: float
    display_value: str | None = None
    note: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProportionBarSpec:
    """Segmented proportion scale primitive with optional left summary list."""

    items: list[ProportionItemSpec] = field(default_factory=list)
    axis_min: float = 0.0
    axis_max: float = 100.0
    axis_step: float = 10.0
    unit: str = "%"
    show_summary_list: bool = True
    summary_title: str = ""


@dataclass(slots=True)
class MatrixRowSpec:
    """One row inside a comparison_matrix column card."""

    chip: str
    values: list[str] = field(default_factory=list)
    trend: TrendDirection | None = None


@dataclass(slots=True)
class MatrixColumnSpec:
    """One dashed comparison column panel in a comparison_matrix scene."""

    id: str
    caption: str
    headers: list[str] = field(default_factory=list)
    rows: list[MatrixRowSpec] = field(default_factory=list)
    action_banner: str | None = None
    action_subtext: str | None = None
    takeaway: str | None = None
    is_baseline: bool = False
    note: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ComparisonMatrixSpec:
    """Multi-column structured numeric comparison primitive."""

    formula: str | None = None
    columns: list[MatrixColumnSpec] = field(default_factory=list)


@dataclass(slots=True)
class GridSpec:
    """12-column (or custom) grid specification for a freeform canvas scene."""

    columns: int = 12
    rows: int | None = None
    gap: float = 28.0


@dataclass(slots=True)
class RegionSpec:
    """One named grid region inside a freeform canvas scene."""

    id: str
    col: int = 1
    row: int = 1
    col_span: int = 12
    row_span: int = 1
    arrange: RegionArrange = "stack"
    gap: float = 20.0
    padding: float = 0.0
    title: str | None = None
    frame: bool = False


@dataclass(slots=True)
class ChartSeriesSpec:
    """One data series inside a native .keyx Chart primitive."""

    name: str
    values: list[float] = field(default_factory=list)
    color_hex: str | None = None


@dataclass(slots=True)
class ChartSpec:
    """Native .keyx Chart specification."""

    chart_type: ChartType
    categories: list[str] = field(default_factory=list)
    series: list[ChartSeriesSpec] = field(default_factory=list)
    title: str | None = None
    unit: str | None = None
    show_legend: bool | None = None
    show_value_labels: bool = True
    axis_min: float | None = None
    axis_max: float | None = None
    reveal: ChartReveal = "whole"
    render_mode: ChartRenderMode = "auto"


@dataclass(slots=True)
class TableSpec:
    """Native .keyx Table specification."""

    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    title: str | None = None
    highlight_cols: list[int] = field(default_factory=list)
    highlight_rows: list[int] = field(default_factory=list)
    reveal: TableReveal = "whole"


@dataclass(slots=True)
class DiagramSpec:
    """Inline node-and-edge diagram placed inside a canvas region."""

    diagram_layout: DiagramLayout = "horizontal"
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)


@dataclass(slots=True)
class CanvasObjectSpec:
    """One freeform visual object aligned to native .keyx primitives."""

    id: str
    kind: CanvasObjectKind
    region: str | None = None
    step: int = 1
    variant: NodeVariant = "primary"
    note: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    weight: float = 1.0
    label: str | None = None
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    text: str | None = None
    font_size: float | None = None
    bold: bool | None = None
    align: TextAlign = "center"
    fill_hex: str | None = None
    border_hex: str | None = None
    color_hex: str | None = None
    shape_type: ShapeType = "rounded_rect"
    svg_path: str | None = None
    dashed: bool = False
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    diagram: DiagramSpec | None = None


@dataclass(slots=True)
class FrameSpec:
    """One progressive visual frame within a scene."""

    visible_nodes: list[str] = field(default_factory=list)
    expanded_nodes: list[str] = field(default_factory=list)
    visible_edges: list[str] | Literal["auto"] = "auto"
    focus_nodes: list[str] | None = None
    visible_items: list[str] | None = None
    visible_columns: list[str] | None = None
    visible_objects: list[str] | None = None
    focus_objects: list[str] | None = None
    object_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    show_annotations: bool = True
    show_pinned_flow: bool | None = None
    notes: str = ""
    subtitle: str | None = None


@dataclass(slots=True)
class StyleConfigSpec:
    """Optional per-deck or per-scene visual tuning overrides without modifying compiler code."""

    title_max_size: float | None = None
    subtitle_size: float | None = None
    card_corner_px: float | None = None
    arrow_width: float | None = None


@dataclass(slots=True)
class SceneSpec:
    """One conceptual diagram or freeform canvas sequence (rendered as 1..N progressive slides)."""

    id: str
    title: str
    layout: LayoutMode = "horizontal_flow"
    subtitle: str | None = None
    source_section: str | None = None
    claim: str | None = None
    metric_scope: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    pacing: PacingMode = "auto"
    intro_note: str = ""
    active_flow_node: str | None = None
    show_pinned_flow: bool = True
    pinned_flow: PinnedFlowSpec | None = None
    palette: dict[str, Any] | None = None
    style_config: StyleConfigSpec | None = None
    grid: GridSpec | None = None
    regions: list[RegionSpec] = field(default_factory=list)
    objects: list[CanvasObjectSpec] = field(default_factory=list)
    connectors: list[EdgeSpec] = field(default_factory=list)
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    proportion_bar: ProportionBarSpec | None = None
    matrix: ComparisonMatrixSpec | None = None
    frames: list[FrameSpec] = field(default_factory=list)


@dataclass(slots=True)
class DeckSpec:
    """Complete presentation specification compiled into a .keyx bundle."""

    title: str
    use_templates: bool = False
    theme: str = "slate_dark"
    palette: dict[str, Any] | None = None
    slide_width: int = 1920
    slide_height: int = 1080
    pinned_flow: PinnedFlowSpec | None = None
    story_model: StoryModelSpec | None = None
    style_config: StyleConfigSpec | None = None
    scenes: list[SceneSpec] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    """Structured validation diagnostics for CLI, MCP, and LLM self-correction."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


