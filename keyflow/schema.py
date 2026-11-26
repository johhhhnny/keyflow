"""Cognitive storyboard DSL models and mode-aware structural validator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Literal, Sequence

from keyflow.themes import THEMES, is_valid_hex_color

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
ChartType = Literal["column", "bar", "pie", "donut", "line", "area", "stacked_column", "stacked_bar", "scatter"]
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
    notes: str = ""
    subtitle: str | None = None


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
    palette: dict[str, Any] | None = None
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


def _parse_nodes_and_edges(raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]]) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    nodes: list[NodeSpec] = []
    for n_raw in raw_nodes:
        children = [
            ChildNodeSpec(
                id=str(c["id"]),
                label=str(c["label"]),
                sublabel=str(c["sublabel"]) if c.get("sublabel") else None,
                badge=str(c["badge"]) if c.get("badge") else None,
                metric=str(c["metric"]) if c.get("metric") else None,
                variant=c.get("variant", "primary"),
                note=str(c.get("note", "")),
                evidence_refs=[str(r) for r in c.get("evidence_refs", [])],
            )
            for c in n_raw.get("children", [])
        ]
        nodes.append(
            NodeSpec(
                id=str(n_raw["id"]),
                label=str(n_raw["label"]),
                sublabel=str(n_raw["sublabel"]) if n_raw.get("sublabel") else None,
                badge=str(n_raw["badge"]) if n_raw.get("badge") else None,
                metric=str(n_raw["metric"]) if n_raw.get("metric") else None,
                kind=n_raw.get("kind", "card"),
                variant=n_raw.get("variant", "primary"),
                children=children,
                child_layout=n_raw.get("child_layout", "row"),
                caption_position=n_raw.get("caption_position", "bottom"),
                note=str(n_raw.get("note", "")),
                evidence_refs=[str(r) for r in n_raw.get("evidence_refs", [])],
            )
        )

    edges = [
        EdgeSpec(
            id=str(e["id"]),
            from_id=str(e["from"]),
            to_id=str(e["to"]),
            label=str(e["label"]) if e.get("label") else None,
            style=e.get("style", "solid"),
        )
        for e in raw_edges
    ]
    return nodes, edges


def parse_deck(raw: dict[str, Any]) -> DeckSpec:
    """Parse a raw JSON dictionary into typed DeckSpec dataclasses."""
    if not isinstance(raw, dict):
        raise ValueError("Deck payload must be a JSON object.")

    pinned_flow: PinnedFlowSpec | None = None
    if raw.get("pinned_flow"):
        pf_raw = raw["pinned_flow"]
        pf_nodes, pf_edges = _parse_nodes_and_edges(pf_raw.get("nodes", []), pf_raw.get("edges", []))
        pf_groups = [
            PinnedFlowGroupSpec(
                id=str(g["id"]),
                label=str(g["label"]),
                node_ids=[str(nid) for nid in g.get("node_ids", [])],
            )
            for g in pf_raw.get("groups", [])
        ]
        pinned_flow = PinnedFlowSpec(nodes=pf_nodes, edges=pf_edges, groups=pf_groups)

    story_model: StoryModelSpec | None = None
    if raw.get("story_model"):
        sm_raw = raw["story_model"]
        claims = [
            StoryClaimSpec(
                id=str(cl["id"]),
                type=cl["type"],
                claim=str(cl["claim"]),
                source_quote=str(cl["source_quote"]) if cl.get("source_quote") is not None else None,
                source_id=str(cl["source_id"]) if cl.get("source_id") is not None else None,
                metric_scope=str(cl["metric_scope"]) if cl.get("metric_scope") is not None else None,
                confidence=cl.get("confidence"),
            )
            for cl in sm_raw.get("claims", [])
        ]
        story_model = StoryModelSpec(
            core_question=str(sm_raw["core_question"]) if sm_raw.get("core_question") is not None else None,
            claims=claims,
        )

    scenes: list[SceneSpec] = []
    for s_raw in raw.get("scenes", []):
        nodes, edges = _parse_nodes_and_edges(s_raw.get("nodes", []), s_raw.get("edges", []))

        prop_bar: ProportionBarSpec | None = None
        if s_raw.get("proportion_bar"):
            pb = s_raw["proportion_bar"]
            prop_bar = ProportionBarSpec(
                items=[
                    ProportionItemSpec(
                        id=str(it["id"]),
                        label=str(it["label"]),
                        value=float(it["value"]),
                        display_value=str(it["display_value"]) if it.get("display_value") else None,
                        note=str(it.get("note", "")),
                        evidence_refs=[str(r) for r in it.get("evidence_refs", [])],
                    )
                    for it in pb.get("items", [])
                ],
                axis_min=float(pb.get("axis_min", 0.0)),
                axis_max=float(pb.get("axis_max", 100.0)),
                axis_step=float(pb.get("axis_step", 10.0)),
                unit=str(pb.get("unit", "%")),
                show_summary_list=bool(pb.get("show_summary_list", True)),
                summary_title=str(pb.get("summary_title", "")),
            )

        matrix: ComparisonMatrixSpec | None = None
        if s_raw.get("matrix"):
            mx = s_raw["matrix"]
            matrix = ComparisonMatrixSpec(
                formula=str(mx["formula"]) if mx.get("formula") else None,
                columns=[
                    MatrixColumnSpec(
                        id=str(col["id"]),
                        caption=str(col["caption"]),
                        headers=[str(h) for h in col.get("headers", [])],
                        rows=[
                            MatrixRowSpec(
                                chip=str(r["chip"]),
                                values=[str(v) for v in r.get("values", [])],
                                trend=r.get("trend"),
                            )
                            for r in col.get("rows", [])
                        ],
                        action_banner=str(col["action_banner"]) if col.get("action_banner") else None,
                        action_subtext=str(col["action_subtext"]) if col.get("action_subtext") else None,
                        takeaway=str(col["takeaway"]) if col.get("takeaway") else None,
                        is_baseline=bool(col.get("is_baseline", False)),
                        note=str(col.get("note", "")),
                        evidence_refs=[str(r) for r in col.get("evidence_refs", [])],
                    )
                    for col in mx.get("columns", [])
                ],
            )

        frames: list[FrameSpec] = []
        for f_raw in s_raw.get("frames") or []:
            raw_obj_states = f_raw.get("object_states") or {}
            obj_states: dict[str, dict[str, Any]] = {}
            for k, v in raw_obj_states.items():
                if not isinstance(v, dict):
                    continue
                parsed_state: dict[str, Any] = {}
                for sk, sv in v.items():
                    key = str(sk)
                    if isinstance(sv, list):
                        parsed_state[key] = [str(x) for x in sv]
                    elif isinstance(sv, str):
                        parsed_state[key] = sv
                    else:
                        parsed_state[key] = int(sv)
                obj_states[str(k)] = parsed_state
            frames.append(
                FrameSpec(
                    visible_nodes=[str(x) for x in f_raw.get("visible_nodes", [])],
                    expanded_nodes=[str(x) for x in f_raw.get("expanded_nodes", [])],
                    visible_edges=f_raw.get("visible_edges", "auto"),
                    focus_nodes=(
                        [str(x) for x in f_raw["focus_nodes"]]
                        if f_raw.get("focus_nodes") is not None
                        else None
                    ),
                    visible_items=(
                        [str(x) for x in f_raw["visible_items"]]
                        if f_raw.get("visible_items") is not None
                        else None
                    ),
                    visible_columns=(
                        [str(x) for x in f_raw["visible_columns"]]
                        if f_raw.get("visible_columns") is not None
                        else None
                    ),
                    visible_objects=(
                        [str(x) for x in f_raw["visible_objects"]]
                        if f_raw.get("visible_objects") is not None
                        else None
                    ),
                    focus_objects=(
                        [str(x) for x in f_raw["focus_objects"]]
                        if f_raw.get("focus_objects") is not None
                        else None
                    ),
                    object_states=obj_states,
                    show_annotations=bool(f_raw.get("show_annotations", True)),
                    notes=str(f_raw.get("notes", "")),
                    subtitle=f_raw.get("subtitle"),
                )
            )

        grid: GridSpec | None = None
        if s_raw.get("grid"):
            g_raw = s_raw["grid"]
            grid = GridSpec(
                columns=int(g_raw.get("columns", 12)),
                rows=int(g_raw["rows"]) if g_raw.get("rows") is not None else None,
                gap=float(g_raw.get("gap", 28.0)),
            )

        regions: list[RegionSpec] = [
            RegionSpec(
                id=str(r["id"]),
                col=int(r.get("col", 1)),
                row=int(r.get("row", 1)),
                col_span=int(r.get("col_span", 12)),
                row_span=int(r.get("row_span", 1)),
                arrange=r.get("arrange", "stack"),
                gap=float(r.get("gap", 20.0)),
                padding=float(r.get("padding", 0.0)),
                title=str(r["title"]) if r.get("title") else None,
                frame=bool(r.get("frame", False)),
            )
            for r in s_raw.get("regions", [])
        ]

        objects: list[CanvasObjectSpec] = []
        for obj_raw in s_raw.get("objects", []):
            chart_spec: ChartSpec | None = None
            if obj_raw.get("chart"):
                ch_raw = obj_raw["chart"]
                chart_spec = ChartSpec(
                    chart_type=ch_raw["chart_type"],
                    categories=[str(c) for c in ch_raw.get("categories", [])],
                    series=[
                        ChartSeriesSpec(
                            name=str(sr["name"]),
                            values=[float(v) for v in sr.get("values", [])],
                            color_hex=str(sr["color_hex"]) if sr.get("color_hex") else None,
                        )
                        for sr in ch_raw.get("series", [])
                    ],
                    title=str(ch_raw["title"]) if ch_raw.get("title") else None,
                    unit=str(ch_raw["unit"]) if ch_raw.get("unit") else None,
                    show_legend=ch_raw.get("show_legend"),
                    show_value_labels=bool(ch_raw.get("show_value_labels", True)),
                    axis_min=float(ch_raw["axis_min"]) if ch_raw.get("axis_min") is not None else None,
                    axis_max=float(ch_raw["axis_max"]) if ch_raw.get("axis_max") is not None else None,
                    reveal=ch_raw.get("reveal", "whole"),
                    render_mode=ch_raw.get("render_mode", "auto"),
                )

            table_spec: TableSpec | None = None
            if obj_raw.get("table"):
                tb_raw = obj_raw["table"]
                table_spec = TableSpec(
                    headers=[str(h) for h in tb_raw.get("headers", [])],
                    rows=[[str(cell) for cell in row] for row in tb_raw.get("rows", [])],
                    title=str(tb_raw["title"]) if tb_raw.get("title") else None,
                    highlight_cols=[int(i) for i in tb_raw.get("highlight_cols", [])],
                    highlight_rows=[int(i) for i in tb_raw.get("highlight_rows", [])],
                    reveal=tb_raw.get("reveal", "whole"),
                )

            diagram_spec: DiagramSpec | None = None
            if obj_raw.get("diagram"):
                dg_raw = obj_raw["diagram"]
                dg_nodes, dg_edges = _parse_nodes_and_edges(
                    dg_raw.get("nodes", []),
                    dg_raw.get("edges", []),
                )
                diagram_spec = DiagramSpec(
                    diagram_layout=dg_raw.get("diagram_layout", "horizontal"),
                    nodes=dg_nodes,
                    edges=dg_edges,
                )

            objects.append(
                CanvasObjectSpec(
                    id=str(obj_raw["id"]),
                    kind=obj_raw["kind"],
                    region=str(obj_raw["region"]) if obj_raw.get("region") else None,
                    step=int(obj_raw.get("step", 1)),
                    variant=obj_raw.get("variant", "primary"),
                    note=str(obj_raw.get("note", "")),
                    evidence_refs=[str(r) for r in obj_raw.get("evidence_refs", [])],
                    weight=float(obj_raw.get("weight", 1.0)),
                    label=str(obj_raw["label"]) if obj_raw.get("label") else None,
                    sublabel=str(obj_raw["sublabel"]) if obj_raw.get("sublabel") else None,
                    badge=str(obj_raw["badge"]) if obj_raw.get("badge") else None,
                    metric=str(obj_raw["metric"]) if obj_raw.get("metric") else None,
                    text=str(obj_raw["text"]) if obj_raw.get("text") else None,
                    font_size=float(obj_raw["font_size"]) if obj_raw.get("font_size") is not None else None,
                    bold=obj_raw.get("bold"),
                    align=obj_raw.get("align", "center"),
                    fill_hex=str(obj_raw["fill_hex"]) if obj_raw.get("fill_hex") else None,
                    border_hex=str(obj_raw["border_hex"]) if obj_raw.get("border_hex") else None,
                    color_hex=str(obj_raw["color_hex"]) if obj_raw.get("color_hex") else None,
                    shape_type=obj_raw.get("shape_type", "rounded_rect"),
                    svg_path=str(obj_raw["svg_path"]) if obj_raw.get("svg_path") else None,
                    dashed=bool(obj_raw.get("dashed", False)),
                    chart=chart_spec,
                    table=table_spec,
                    diagram=diagram_spec,
                )
            )

        connectors = [
            EdgeSpec(
                id=str(e["id"]),
                from_id=str(e["from"]),
                to_id=str(e["to"]),
                label=str(e["label"]) if e.get("label") else None,
                style=e.get("style", "solid"),
            )
            for e in s_raw.get("connectors", [])
        ]

        default_pacing = "manual" if frames else "auto"
        inferred_layout = "canvas" if ("objects" in s_raw or "regions" in s_raw) else "horizontal_flow"
        scenes.append(
            SceneSpec(
                id=str(s_raw["id"]),
                title=str(s_raw["title"]),
                layout=s_raw.get("layout", inferred_layout),
                subtitle=s_raw.get("subtitle"),
                source_section=str(s_raw["source_section"]) if s_raw.get("source_section") else None,
                claim=str(s_raw["claim"]) if s_raw.get("claim") is not None else None,
                metric_scope=str(s_raw["metric_scope"]) if s_raw.get("metric_scope") is not None else None,
                evidence_refs=[str(r) for r in s_raw.get("evidence_refs", [])],
                pacing=s_raw.get("pacing", default_pacing),
                intro_note=str(s_raw.get("intro_note", "")),
                active_flow_node=str(s_raw["active_flow_node"]) if s_raw.get("active_flow_node") else None,
                show_pinned_flow=bool(s_raw.get("show_pinned_flow", True)),
                palette=dict(s_raw["palette"]) if isinstance(s_raw.get("palette"), dict) else None,
                grid=grid,
                regions=regions,
                objects=objects,
                connectors=connectors,
                nodes=nodes,
                edges=edges,
                proportion_bar=prop_bar,
                matrix=matrix,
                frames=frames,
            )
        )

    slide_size = raw.get("slide_size", {})
    return DeckSpec(
        title=str(raw.get("title", "Untitled Deck")),
        use_templates=bool(raw.get("use_templates", False)),
        theme=str(raw.get("theme", "slate_dark")),
        palette=dict(raw["palette"]) if isinstance(raw.get("palette"), dict) else None,
        slide_width=int(slide_size.get("width", 1920)),
        slide_height=int(slide_size.get("height", 1080)),
        pinned_flow=pinned_flow,
        story_model=story_model,
        scenes=scenes,
    )


def _check_label_density(
    target: str,
    label: str,
    sublabel: str | None,
    badge: str | None,
    metric: str | None,
    warnings: list[str],
) -> None:
    if "\n" in label or "•" in label:
        warnings.append(
            f"{target}: label contains line breaks or bullets; keep canvas cards single-phrase and move details to 'note'/'notes'."
        )
    elif len(label) > 18:
        warnings.append(
            f"{target}: label '{label}' exceeds 18 chars; consider tightening or splitting into 'sublabel'."
        )
    for field_name, val, limit in (
        ("sublabel", sublabel, 20),
        ("badge", badge, 16),
        ("metric", metric, 14),
    ):
        if val:
            if "\n" in val or "•" in val:
                warnings.append(f"{target}: {field_name} contains line breaks or bullets; keep it concise.")
            elif len(val) > limit:
                warnings.append(f"{target}: {field_name} '{val}' exceeds {limit} chars; tighten for readability.")


def compute_dag_layers(
    node_ids: Sequence[str],
    edge_pairs: Sequence[tuple[str, str]],
) -> tuple[dict[str, int], list[str]]:
    """Compute dependency layer depth via Kahn's topological sort, independent of input order.

    Returns ``(layers, cyclic_node_ids)`` where ``cyclic_node_ids`` lists any nodes
    participating in or blocked by directed cycles (sorted in input order).
    """
    unique_ids: list[str] = []
    seen_ids: set[str] = set()
    for nid in node_ids:
        if nid not in seen_ids:
            seen_ids.add(nid)
            unique_ids.append(nid)

    if not unique_ids:
        return {}, []

    children: dict[str, list[str]] = {nid: [] for nid in unique_ids}
    parents: dict[str, list[str]] = {nid: [] for nid in unique_ids}
    indegree: dict[str, int] = {nid: 0 for nid in unique_ids}
    seen_edges: set[tuple[str, str]] = set()

    for src, dst in edge_pairs:
        if src in seen_ids and dst in seen_ids and src != dst and (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            children[src].append(dst)
            parents[dst].append(src)
            indegree[dst] += 1

    queue: deque[str] = deque(nid for nid in unique_ids if indegree[nid] == 0)
    layers: dict[str, int] = {nid: 0 for nid in queue}

    while queue:
        u = queue.popleft()
        for v in children[u]:
            layers[v] = max(layers.get(v, 0), layers[u] + 1)
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)

    cyclic = [nid for nid in unique_ids if nid not in layers]
    if cyclic:
        max_layer = max(layers.values(), default=-1)
        for nid in cyclic:
            resolved_parents = [layers[p] for p in parents[nid] if p in layers]
            layers[nid] = (1 + max(resolved_parents)) if resolved_parents else (max_layer + 1)

    return layers, cyclic


def _as_float(val: Any) -> float | None:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    return float(val)


@lru_cache(maxsize=1)
def _schema_key_sets() -> dict[str, frozenset[str]]:
    """Extract allowed property sets directly from schemas/deck.schema.json to prevent validator drift."""
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "deck.schema.json"
    if not schema_path.exists():
        return {}
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    props = raw.get("properties", {})
    defs = raw.get("$defs", {})
    pf_props = props.get("pinned_flow", {}).get("properties", {})
    sm_props = props.get("story_model", {}).get("properties", {})
    sc_props = props.get("scenes", {}).get("items", {}).get("properties", {})
    node_props = defs.get("node", {}).get("properties", {})
    child_props = node_props.get("children", {}).get("items", {}).get("properties", {})
    edge_props = defs.get("edge", {}).get("properties", {})
    pb_props = sc_props.get("proportion_bar", {}).get("properties", {})
    pb_item_props = pb_props.get("items", {}).get("items", {}).get("properties", {})
    mx_props = sc_props.get("matrix", {}).get("properties", {})
    mx_col_props = mx_props.get("columns", {}).get("items", {}).get("properties", {})
    mx_row_props = mx_col_props.get("rows", {}).get("items", {}).get("properties", {})
    frame_props = sc_props.get("frames", {}).get("items", {}).get("properties", {})
    obj_props = sc_props.get("objects", {}).get("items", {}).get("properties", {})
    chart_props = obj_props.get("chart", {}).get("properties", {})
    table_props = obj_props.get("table", {}).get("properties", {})
    diagram_props = obj_props.get("diagram", {}).get("properties", {})
    return {
        "deck": frozenset(props),
        "palette": frozenset(defs.get("palette", {}).get("properties", {})),
        "slide_size": frozenset(props.get("slide_size", {}).get("properties", {})),
        "pinned_flow": frozenset(pf_props),
        "pf_node": frozenset(pf_props.get("nodes", {}).get("items", {}).get("properties", {})),
        "pf_edge": frozenset(pf_props.get("edges", {}).get("items", {}).get("properties", {})),
        "pf_group": frozenset(pf_props.get("groups", {}).get("items", {}).get("properties", {})),
        "story_model": frozenset(sm_props),
        "story_claim": frozenset(sm_props.get("claims", {}).get("items", {}).get("properties", {})),
        "scene": frozenset(sc_props),
        "grid": frozenset(sc_props.get("grid", {}).get("properties", {})),
        "region": frozenset(sc_props.get("regions", {}).get("items", {}).get("properties", {})),
        "canvas_object": frozenset(obj_props),
        "chart": frozenset(chart_props),
        "chart_series": frozenset(chart_props.get("series", {}).get("items", {}).get("properties", {})),
        "table": frozenset(table_props),
        "diagram": frozenset(diagram_props),
        "node": frozenset(node_props),
        "child": frozenset(child_props),
        "edge": frozenset(edge_props),
        "proportion_bar": frozenset(pb_props),
        "proportion_item": frozenset(pb_item_props),
        "matrix": frozenset(mx_props),
        "matrix_column": frozenset(mx_col_props),
        "matrix_row": frozenset(mx_row_props),
        "frame": frozenset(frame_props),
        "object_state": frozenset(
            frame_props.get("object_states", {}).get("additionalProperties", {}).get("properties", {})
        ),
    }


def _check_allowed_keys(
    obj: dict[str, Any],
    schema_key: str,
    path: str,
    errors: list[str],
) -> None:
    allowed = _schema_key_sets().get(schema_key)
    if not allowed:
        return
    unknown = sorted(set(obj) - allowed)
    for key in unknown:
        errors.append(f"{path}: unknown property '{key}'.")


def _check_evidence_refs(
    obj: dict[str, Any],
    claim_ids: set[str],
    path: str,
    errors: list[str],
) -> None:
    refs = obj.get("evidence_refs")
    if refs is None:
        return
    if not isinstance(refs, list):
        errors.append(f"{path}.evidence_refs must be a list of claim ids.")
        return
    for cid in refs:
        if not isinstance(cid, str) or cid not in claim_ids:
            errors.append(f"{path}: unknown evidence_ref '{cid}'.")


def _validate_palette(pal: Any, path: str, errors: list[str]) -> None:
    if not isinstance(pal, dict):
        errors.append(f"{path} must be an object.")
        return
    _check_allowed_keys(pal, "palette", path, errors)
    for k, v in pal.items():
        if k == "series_colors":
            if not isinstance(v, list) or not v:
                errors.append(f"{path}.series_colors must be a non-empty list of #RRGGBB hex colors.")
            else:
                for idx, item in enumerate(v):
                    if not isinstance(item, str) or not is_valid_hex_color(item):
                        errors.append(f"{path}.series_colors[{idx}]: invalid hex color '{item}' (expected #RRGGBB).")
        elif not isinstance(v, str) or not is_valid_hex_color(v):
            errors.append(f"{path}.{k}: invalid hex color '{v}' (expected #RRGGBB).")


def _validate_nodes_and_edges(
    nodes: Any,
    edges: Any,
    *,
    prefix: str,
    layout_kind: str,
    claim_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    valid_child_layouts = {"row", "column", "grid"}
    valid_variants = {"primary", "accent", "muted", "success", "warn"}
    node_map: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []

    if not isinstance(nodes, list):
        errors.append(f"{prefix}.nodes must be a list.")
        return node_map, set()

    for n_idx, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"{prefix}.nodes[{n_idx}]: must be an object.")
            continue
        _check_allowed_keys(n, "node", f"{prefix}.nodes[{n_idx}]", errors)
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"{prefix}.nodes[{n_idx}]: missing 'id'.")
            continue
        if nid in node_map:
            errors.append(f"{prefix}: duplicate node id '{nid}'.")
        else:
            node_order.append(nid)
        node_map[nid] = n
        _check_evidence_refs(n, claim_ids, f"{prefix}.nodes['{nid}']", errors)

        variant = n.get("variant", "primary")
        if variant not in valid_variants:
            errors.append(f"{prefix}.nodes['{nid}']: invalid variant '{variant}'.")

        raw_label = n.get("label")
        if not isinstance(raw_label, str) or not raw_label:
            errors.append(f"{prefix}.nodes[{n_idx}] ('{nid}'): missing 'label'.")
        else:
            _check_label_density(
                f"{prefix}.nodes['{nid}']",
                raw_label,
                n.get("sublabel") if isinstance(n.get("sublabel"), str) else None,
                n.get("badge") if isinstance(n.get("badge"), str) else None,
                n.get("metric") if isinstance(n.get("metric"), str) else None,
                warnings,
            )

        child_layout = n.get("child_layout", "row")
        if child_layout not in valid_child_layouts:
            errors.append(f"{prefix}.nodes['{nid}']: invalid child_layout '{child_layout}'.")

        children = n.get("children", [])
        if not isinstance(children, list):
            errors.append(f"{prefix}.nodes['{nid}'].children must be a list.")
            children = []
        if n.get("kind") == "group_dashed" and not children:
            errors.append(f"{prefix}.nodes['{nid}']: kind='group_dashed' requires non-empty 'children'.")
        if layout_kind in ("horizontal_flow", "horizontal") and len(children) >= 4 and child_layout == "row":
            warnings.append(
                f"{prefix}.nodes['{nid}']: {len(children)} children in horizontal 'row' may squeeze the flow; consider child_layout='grid'."
            )

        child_ids: set[str] = set()
        for c_idx, c in enumerate(children):
            if not isinstance(c, dict):
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: must be an object.")
                continue
            _check_allowed_keys(c, "child", f"{prefix}.nodes['{nid}'].children[{c_idx}]", errors)
            cid = c.get("id")
            if not isinstance(cid, str) or not cid:
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: missing 'id'.")
            elif cid in child_ids:
                errors.append(f"{prefix}.nodes['{nid}']: duplicate child id '{cid}'.")
            else:
                child_ids.add(cid)
            _check_evidence_refs(c, claim_ids, f"{prefix}.nodes['{nid}'].children['{cid}']", errors)

            cvar = c.get("variant", "primary")
            if cvar not in valid_variants:
                errors.append(f"{prefix}.nodes['{nid}'].children['{cid}']: invalid variant '{cvar}'.")

            clabel = c.get("label")
            if not isinstance(clabel, str) or not clabel:
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: missing 'label'.")
            else:
                _check_label_density(
                    f"{prefix}.nodes['{nid}'].children['{cid}']",
                    clabel,
                    c.get("sublabel") if isinstance(c.get("sublabel"), str) else None,
                    c.get("badge") if isinstance(c.get("badge"), str) else None,
                    c.get("metric") if isinstance(c.get("metric"), str) else None,
                    warnings,
                )

    edge_ids: set[str] = set()
    valid_edge_pairs: list[tuple[str, str]] = []
    if not isinstance(edges, list):
        errors.append(f"{prefix}.edges must be a list.")
    else:
        for e_idx, e in enumerate(edges):
            if not isinstance(e, dict):
                errors.append(f"{prefix}.edges[{e_idx}]: must be an object.")
                continue
            _check_allowed_keys(e, "edge", f"{prefix}.edges[{e_idx}]", errors)
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{prefix}.edges[{e_idx}]: missing 'id'.")
            elif eid in edge_ids:
                errors.append(f"{prefix}: duplicate edge id '{eid}'.")
            else:
                edge_ids.add(eid)
            src = e.get("from")
            dst = e.get("to")
            if src not in node_map:
                errors.append(f"{prefix}.edges['{eid}']: unknown 'from' node '{src}'.")
            if dst not in node_map:
                errors.append(f"{prefix}.edges['{eid}']: unknown 'to' node '{dst}'.")
            if isinstance(src, str) and isinstance(dst, str) and src in node_map and dst in node_map:
                if src == dst and layout_kind in ("flow_dag", "dag"):
                    errors.append(f"{prefix}.edges['{eid}']: self-loop '{src} -> {dst}' is not allowed in DAG.")
                valid_edge_pairs.append((src, dst))

    if layout_kind in ("flow_dag", "dag") and node_order and valid_edge_pairs:
        _, cyclic_nodes = compute_dag_layers(node_order, valid_edge_pairs)
        if cyclic_nodes:
            errors.append(
                f"{prefix}: DAG contains cyclic dependencies involving: {', '.join(cyclic_nodes)}."
            )

    return node_map, edge_ids


def _validate_canvas_scene(
    s: dict[str, Any],
    *,
    prefix: str,
    claim_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Validate grid, regions, freeform .keyx objects, and cross-object connectors."""
    grid_cols = 12
    grid_rows: int | None = None
    if s.get("grid") is not None:
        g = s["grid"]
        if not isinstance(g, dict):
            errors.append(f"{prefix}.grid must be an object.")
        else:
            _check_allowed_keys(g, "grid", f"{prefix}.grid", errors)
            cols_val = _as_float(g.get("columns", 12))
            if cols_val is None or cols_val < 1 or cols_val > 24:
                errors.append(f"{prefix}.grid.columns must be an integer in [1, 24].")
            else:
                grid_cols = int(cols_val)
            if g.get("rows") is not None:
                rows_val = _as_float(g["rows"])
                if rows_val is None or rows_val < 1 or rows_val > 12:
                    errors.append(f"{prefix}.grid.rows must be an integer in [1, 12].")
                else:
                    grid_rows = int(rows_val)
            if "gap" in g:
                gap_val = _as_float(g["gap"])
                if gap_val is None or gap_val < 0:
                    errors.append(f"{prefix}.grid.gap must be non-negative.")

    region_ids: set[str] = set()
    occupied_cells: dict[tuple[int, int], str] = {}
    valid_arranges = {"stack", "row", "grid"}
    if s.get("regions") is not None:
        regs = s["regions"]
        if not isinstance(regs, list):
            errors.append(f"{prefix}.regions must be a list.")
        else:
            for r_idx, reg in enumerate(regs):
                if not isinstance(reg, dict):
                    errors.append(f"{prefix}.regions[{r_idx}]: must be an object.")
                    continue
                _check_allowed_keys(reg, "region", f"{prefix}.regions[{r_idx}]", errors)
                rid = reg.get("id")
                if not isinstance(rid, str) or not rid:
                    errors.append(f"{prefix}.regions[{r_idx}]: missing 'id'.")
                    continue
                if rid in region_ids:
                    errors.append(f"{prefix}: duplicate region id '{rid}'.")
                else:
                    region_ids.add(rid)
                arrange = reg.get("arrange", "stack")
                if arrange not in valid_arranges:
                    errors.append(f"{prefix}.regions['{rid}']: invalid arrange '{arrange}'.")
                col = int(_as_float(reg.get("col", 1)) or 0)
                row = int(_as_float(reg.get("row", 1)) or 0)
                cspan = int(_as_float(reg.get("col_span", 12)) or 0)
                rspan = int(_as_float(reg.get("row_span", 1)) or 0)
                if col < 1 or cspan < 1 or col + cspan - 1 > grid_cols:
                    errors.append(
                        f"{prefix}.regions['{rid}']: col={col}, col_span={cspan} exceeds grid columns={grid_cols}."
                    )
                if row < 1 or rspan < 1 or (grid_rows is not None and row + rspan - 1 > grid_rows):
                    errors.append(
                        f"{prefix}.regions['{rid}']: row={row}, row_span={rspan} out of grid row bounds."
                    )
                for rr in range(max(1, row), max(1, row) + max(0, rspan)):
                    for cc in range(max(1, col), max(1, col) + max(0, cspan)):
                        prev = occupied_cells.get((rr, cc))
                        if prev and prev != rid:
                            errors.append(
                                f"{prefix}.regions['{rid}']: overlaps grid cell ({rr}, {cc}) with region '{prev}'."
                            )
                        else:
                            occupied_cells[(rr, cc)] = rid

    valid_kinds = {"chart", "table", "card", "textbox", "shape", "callout", "diagram"}
    valid_variants = {"primary", "accent", "muted", "success", "warn"}
    valid_chart_types = {"column", "bar", "pie", "donut", "line", "area", "stacked_column", "stacked_bar", "scatter"}
    valid_chart_reveals = {"whole", "by_series", "by_category"}
    valid_chart_render_modes = {"auto", "vector", "native"}
    valid_table_reveals = {"whole", "by_row", "by_column"}
    valid_shape_types = {"rounded_rect", "rect", "ellipse", "pill", "custom"}
    valid_diagram_layouts = {"horizontal", "vertical", "dag", "hub_spoke"}

    object_map: dict[str, dict[str, Any]] = {}
    raw_objects = s.get("objects")
    if raw_objects is None:
        errors.append(f"{prefix}: layout='canvas' requires an 'objects' list.")
        return set(), object_map
    if not isinstance(raw_objects, list):
        errors.append(f"{prefix}.objects must be a list.")
        return set(), object_map

    for o_idx, obj in enumerate(raw_objects):
        if not isinstance(obj, dict):
            errors.append(f"{prefix}.objects[{o_idx}]: must be an object.")
            continue
        _check_allowed_keys(obj, "canvas_object", f"{prefix}.objects[{o_idx}]", errors)
        oid = obj.get("id")
        if not isinstance(oid, str) or not oid:
            errors.append(f"{prefix}.objects[{o_idx}]: missing 'id'.")
            continue
        if oid in object_map:
            errors.append(f"{prefix}: duplicate object id '{oid}'.")
            continue
        object_map[oid] = obj
        _check_evidence_refs(obj, claim_ids, f"{prefix}.objects['{oid}']", errors)

        kind = obj.get("kind")
        if not isinstance(kind, str) or kind not in valid_kinds:
            errors.append(f"{prefix}.objects['{oid}']: invalid kind '{kind}'.")
            continue

        reg_ref = obj.get("region")
        if reg_ref is not None and region_ids and reg_ref not in region_ids:
            errors.append(f"{prefix}.objects['{oid}']: unknown region '{reg_ref}'.")

        variant = obj.get("variant", "primary")
        if variant not in valid_variants:
            errors.append(f"{prefix}.objects['{oid}']: invalid variant '{variant}'.")

        step_val = _as_float(obj.get("step", 1))
        if step_val is None or step_val < 0:
            errors.append(f"{prefix}.objects['{oid}']: 'step' must be a non-negative integer.")

        for hex_field in ("fill_hex", "border_hex", "color_hex"):
            if obj.get(hex_field) is not None and not is_valid_hex_color(str(obj[hex_field])):
                errors.append(f"{prefix}.objects['{oid}'].{hex_field}: invalid hex color '{obj[hex_field]}'.")

        if kind in ("card", "callout"):
            lbl = obj.get("label")
            if not isinstance(lbl, str) or not lbl:
                errors.append(f"{prefix}.objects['{oid}']: kind='{kind}' requires 'label'.")
            else:
                _check_label_density(
                    f"{prefix}.objects['{oid}']",
                    lbl,
                    obj.get("sublabel") if isinstance(obj.get("sublabel"), str) else None,
                    obj.get("badge") if isinstance(obj.get("badge"), str) else None,
                    obj.get("metric") if isinstance(obj.get("metric"), str) else None,
                    warnings,
                )
        elif kind == "textbox":
            if not isinstance(obj.get("text"), str) or not obj.get("text"):
                errors.append(f"{prefix}.objects['{oid}']: kind='textbox' requires non-empty 'text'.")
        elif kind == "shape":
            st = obj.get("shape_type", "rounded_rect")
            if st not in valid_shape_types:
                errors.append(f"{prefix}.objects['{oid}']: invalid shape_type '{st}'.")
            if st == "custom" and (not isinstance(obj.get("svg_path"), str) or not obj.get("svg_path")):
                errors.append(f"{prefix}.objects['{oid}']: shape_type='custom' requires 'svg_path'.")
        elif kind == "chart":
            ch = obj.get("chart")
            if not isinstance(ch, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='chart' requires 'chart' object.")
            else:
                _check_allowed_keys(ch, "chart", f"{prefix}.objects['{oid}'].chart", errors)
                ctype = ch.get("chart_type")
                if ctype not in valid_chart_types:
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid chart_type '{ctype}'.")
                crev = ch.get("reveal", "whole")
                if crev not in valid_chart_reveals:
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid reveal '{crev}'.")
                crm = ch.get("render_mode", "auto")
                if crm not in valid_chart_render_modes:
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid render_mode '{crm}'.")
                cats = ch.get("categories")
                series = ch.get("series")
                if not isinstance(cats, list) or not cats:
                    errors.append(f"{prefix}.objects['{oid}'].chart: 'categories' must be a non-empty list.")
                    cats = []
                if not isinstance(series, list) or not series:
                    errors.append(f"{prefix}.objects['{oid}'].chart: 'series' must be a non-empty list.")
                else:
                    for sr_idx, sr in enumerate(series):
                        if not isinstance(sr, dict):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: must be an object.")
                            continue
                        _check_allowed_keys(sr, "chart_series", f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]", errors)
                        if not isinstance(sr.get("name"), str) or not sr.get("name"):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: missing 'name'.")
                        vals = sr.get("values")
                        if not isinstance(vals, list) or (cats and len(vals) != len(cats)):
                            errors.append(
                                f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: 'values' length must match 'categories' ({len(cats)})."
                            )
                        elif any(_as_float(v) is None for v in vals):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: all values must be numeric.")
                        if sr.get("color_hex") is not None and not is_valid_hex_color(str(sr["color_hex"])):
                            errors.append(
                                f"{prefix}.objects['{oid}'].chart.series[{sr_idx}].color_hex: invalid hex '{sr['color_hex']}'."
                            )
        elif kind == "table":
            tb = obj.get("table")
            if not isinstance(tb, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='table' requires 'table' object.")
            else:
                _check_allowed_keys(tb, "table", f"{prefix}.objects['{oid}'].table", errors)
                trev = tb.get("reveal", "whole")
                if trev not in valid_table_reveals:
                    errors.append(f"{prefix}.objects['{oid}'].table: invalid reveal '{trev}'.")
                hdrs = tb.get("headers")
                trows = tb.get("rows")
                if not isinstance(hdrs, list) or not hdrs:
                    errors.append(f"{prefix}.objects['{oid}'].table: 'headers' must be a non-empty list.")
                    hdrs = []
                if not isinstance(trows, list) or not trows:
                    errors.append(f"{prefix}.objects['{oid}'].table: 'rows' must be a non-empty list.")
                else:
                    for r_idx, row in enumerate(trows):
                        if not isinstance(row, list) or (hdrs and len(row) != len(hdrs)):
                            errors.append(
                                f"{prefix}.objects['{oid}'].table.rows[{r_idx}]: column count must match headers ({len(hdrs)})."
                            )
        elif kind == "diagram":
            dg = obj.get("diagram")
            if not isinstance(dg, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='diagram' requires 'diagram' object.")
            else:
                _check_allowed_keys(dg, "diagram", f"{prefix}.objects['{oid}'].diagram", errors)
                dl = dg.get("diagram_layout", "horizontal")
                if dl not in valid_diagram_layouts:
                    errors.append(f"{prefix}.objects['{oid}'].diagram: invalid diagram_layout '{dl}'.")
                _validate_nodes_and_edges(
                    dg.get("nodes", []),
                    dg.get("edges", []),
                    prefix=f"{prefix}.objects['{oid}'].diagram",
                    layout_kind=dl,
                    claim_ids=claim_ids,
                    errors=errors,
                    warnings=warnings,
                )

    connectors = s.get("connectors", [])
    if not isinstance(connectors, list):
        errors.append(f"{prefix}.connectors must be a list.")
    else:
        conn_ids: set[str] = set()
        for e_idx, e in enumerate(connectors):
            if not isinstance(e, dict):
                errors.append(f"{prefix}.connectors[{e_idx}]: must be an object.")
                continue
            _check_allowed_keys(e, "edge", f"{prefix}.connectors[{e_idx}]", errors)
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{prefix}.connectors[{e_idx}]: missing 'id'.")
            elif eid in conn_ids:
                errors.append(f"{prefix}: duplicate connector id '{eid}'.")
            else:
                conn_ids.add(eid)
            if e.get("from") not in object_map:
                errors.append(f"{prefix}.connectors['{eid}']: unknown 'from' object '{e.get('from')}'.")
            if e.get("to") not in object_map:
                errors.append(f"{prefix}.connectors['{eid}']: unknown 'to' object '{e.get('to')}'.")

    return set(object_map), object_map


def validate_deck(
    raw: dict[str, Any],
    *,
    use_templates: bool | None = None,
) -> ValidationResult:
    """Validate structural integrity, references, mode switch, and visual density rules."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(raw, dict):
        return ValidationResult(valid=False, errors=["Top-level JSON must be an object."])

    _check_allowed_keys(raw, "deck", "deck", errors)

    if "use_templates" in raw and not isinstance(raw["use_templates"], bool):
        errors.append("Top-level 'use_templates' must be a boolean.")
    eff_use_templates = bool(raw.get("use_templates", False)) if use_templates is None else use_templates

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("Missing or invalid top-level 'title'.")

    theme = raw.get("theme", "slate_dark")
    if not isinstance(theme, str) or theme not in THEMES:
        errors.append(f"Unknown theme '{theme}'. Valid options: {', '.join(sorted(THEMES))}.")

    if raw.get("palette") is not None:
        if eff_use_templates:
            errors.append("Custom top-level 'palette' is forbidden when use_templates=true; set use_templates=false.")
        else:
            _validate_palette(raw["palette"], "deck.palette", errors)

    if raw.get("slide_size") is not None:
        ss = raw["slide_size"]
        if not isinstance(ss, dict):
            errors.append("'slide_size' must be an object.")
        else:
            _check_allowed_keys(ss, "slide_size", "slide_size", errors)
            for dim in ("width", "height"):
                if dim in ss and _as_float(ss[dim]) is None:
                    errors.append(f"slide_size.{dim} must be numeric.")

    claim_ids: set[str] = set()
    valid_claim_types = {"thesis", "fact", "relation", "inference", "counter_evidence", "conclusion", "example"}
    valid_confidence = {"high", "medium", "low"}
    if raw.get("story_model") is not None:
        sm = raw["story_model"]
        if not isinstance(sm, dict):
            errors.append("'story_model' must be an object.")
        else:
            _check_allowed_keys(sm, "story_model", "story_model", errors)
            if sm.get("core_question") is not None and not isinstance(sm.get("core_question"), str):
                errors.append("story_model.core_question must be a string.")
            claims = sm.get("claims")
            if not isinstance(claims, list) or not claims:
                errors.append("story_model.claims must be a non-empty list.")
            else:
                for cl_idx, cl in enumerate(claims):
                    if not isinstance(cl, dict):
                        errors.append(f"story_model.claims[{cl_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(cl, "story_claim", f"story_model.claims[{cl_idx}]", errors)
                    cid = cl.get("id")
                    if not isinstance(cid, str) or not cid:
                        errors.append(f"story_model.claims[{cl_idx}]: missing 'id'.")
                    elif cid in claim_ids:
                        errors.append(f"story_model: duplicate claim id '{cid}'.")
                    else:
                        claim_ids.add(cid)
                    ctype = cl.get("type")
                    if not isinstance(ctype, str) or ctype not in valid_claim_types:
                        errors.append(f"story_model.claims['{cid}']: invalid type '{ctype}'.")
                    ctext = cl.get("claim")
                    if not isinstance(ctext, str) or not ctext.strip():
                        errors.append(f"story_model.claims['{cid}']: missing 'claim'.")
                    conf = cl.get("confidence")
                    if conf is not None and (not isinstance(conf, str) or conf not in valid_confidence):
                        errors.append(f"story_model.claims['{cid}']: invalid confidence '{conf}'.")

    pf_node_ids: set[str] = set()
    if raw.get("pinned_flow") is not None:
        pf = raw["pinned_flow"]
        if not isinstance(pf, dict):
            errors.append("'pinned_flow' must be an object.")
        else:
            _check_allowed_keys(pf, "pinned_flow", "pinned_flow", errors)
            pf_nodes = pf.get("nodes", [])
            if not isinstance(pf_nodes, list) or not pf_nodes:
                errors.append("pinned_flow.nodes must be a non-empty list.")
            else:
                for idx, n in enumerate(pf_nodes):
                    if not isinstance(n, dict):
                        errors.append(f"pinned_flow.nodes[{idx}]: must be an object.")
                        continue
                    _check_allowed_keys(n, "pf_node", f"pinned_flow.nodes[{idx}]", errors)
                    nid = n.get("id")
                    if not isinstance(nid, str) or not nid:
                        errors.append(f"pinned_flow.nodes[{idx}]: missing 'id'.")
                    elif nid in pf_node_ids:
                        errors.append(f"pinned_flow: duplicate node id '{nid}'.")
                    else:
                        pf_node_ids.add(nid)
                    if not isinstance(n.get("label"), str) or not n.get("label"):
                        errors.append(f"pinned_flow.nodes[{idx}]: missing 'label'.")
                pf_edges = pf.get("edges", [])
                if not isinstance(pf_edges, list):
                    errors.append("pinned_flow.edges must be a list.")
                else:
                    for e_idx, e in enumerate(pf_edges):
                        if not isinstance(e, dict):
                            errors.append(f"pinned_flow.edges[{e_idx}]: must be an object.")
                            continue
                        _check_allowed_keys(e, "pf_edge", f"pinned_flow.edges[{e_idx}]", errors)
                        if e.get("from") not in pf_node_ids:
                            errors.append(f"pinned_flow.edges[{e_idx}]: unknown 'from' node '{e.get('from')}'.")
                        if e.get("to") not in pf_node_ids:
                            errors.append(f"pinned_flow.edges[{e_idx}]: unknown 'to' node '{e.get('to')}'.")
                pf_groups = pf.get("groups", [])
                if not isinstance(pf_groups, list):
                    errors.append("pinned_flow.groups must be a list.")
                else:
                    for g_idx, g in enumerate(pf_groups):
                        if not isinstance(g, dict):
                            errors.append(f"pinned_flow.groups[{g_idx}]: must be an object.")
                            continue
                        _check_allowed_keys(g, "pf_group", f"pinned_flow.groups[{g_idx}]", errors)
                        if not isinstance(g.get("label"), str) or not g.get("label"):
                            errors.append(f"pinned_flow.groups[{g_idx}]: missing 'label'.")
                        g_nids = g.get("node_ids", [])
                        if not isinstance(g_nids, list):
                            errors.append(f"pinned_flow.groups[{g_idx}]: 'node_ids' must be a list.")
                        else:
                            for nid in g_nids:
                                if nid not in pf_node_ids:
                                    errors.append(f"pinned_flow.groups[{g_idx}]: unknown node '{nid}'.")

    raw_scenes = raw.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        errors.append("'scenes' must be a non-empty list.")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    valid_layouts = {
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
    }
    valid_pacing = {"auto", "compact", "manual"}
    scene_ids: set[str] = set()

    for s_idx, s in enumerate(raw_scenes):
        prefix = f"scenes[{s_idx}]"
        if not isinstance(s, dict):
            errors.append(f"{prefix}: scene entry must be an object.")
            continue
        _check_allowed_keys(s, "scene", prefix, errors)
        _check_evidence_refs(s, claim_ids, prefix, errors)

        sid = s.get("id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"{prefix}: missing or invalid 'id'.")
        elif sid in scene_ids:
            errors.append(f"{prefix}: duplicate scene id '{sid}'.")
        else:
            scene_ids.add(sid)

        stitle = s.get("title")
        if not isinstance(stitle, str) or not stitle:
            errors.append(f"{prefix}: missing or invalid 'title'.")

        inferred_layout = "canvas" if ("objects" in s or "regions" in s) else "horizontal_flow"
        layout = s.get("layout", inferred_layout)
        if not isinstance(layout, str) or layout not in valid_layouts:
            errors.append(f"{prefix}: invalid layout '{layout}'.")

        has_freeform_fields = any(
            s.get(k) is not None for k in ("grid", "regions", "objects", "connectors", "palette")
        )
        if eff_use_templates and (layout == "canvas" or has_freeform_fields):
            errors.append(
                f"{prefix}: freeform 'canvas'/'regions'/'objects'/'palette' are forbidden when use_templates=true; set use_templates=false."
            )

        if s.get("palette") is not None and not eff_use_templates:
            _validate_palette(s["palette"], f"{prefix}.palette", errors)

        active_fn = s.get("active_flow_node")
        if active_fn is not None:
            if not isinstance(active_fn, str):
                errors.append(f"{prefix}: 'active_flow_node' must be a string.")
            elif active_fn:
                if not pf_node_ids:
                    errors.append(f"{prefix}: 'active_flow_node' set to '{active_fn}' without top-level 'pinned_flow'.")
                elif active_fn not in pf_node_ids:
                    errors.append(f"{prefix}: unknown active_flow_node '{active_fn}'.")

        has_frames = "frames" in s and s["frames"] is not None
        pacing = s.get("pacing", "manual" if has_frames else "auto")
        if not isinstance(pacing, str) or pacing not in valid_pacing:
            errors.append(f"{prefix}: invalid pacing '{pacing}'.")

        object_ids: set[str] = set()
        if layout == "canvas":
            object_ids, _ = _validate_canvas_scene(
                s,
                prefix=prefix,
                claim_ids=claim_ids,
                errors=errors,
                warnings=warnings,
            )

        nodes = s.get("nodes", [])
        edges = s.get("edges", [])
        node_map, edge_ids = _validate_nodes_and_edges(
            nodes,
            edges,
            prefix=prefix,
            layout_kind=str(layout),
            claim_ids=claim_ids,
            errors=errors,
            warnings=warnings,
        )

        if layout == "horizontal_flow" and isinstance(nodes, list) and len(nodes) > 5:
            warnings.append(
                f"{prefix}: {len(nodes)} top-level nodes in horizontal_flow may feel crowded; 3-5 pillars is recommended."
            )

        item_ids: set[str] = set()
        if layout == "proportion_bar":
            pb = s.get("proportion_bar")
            if not isinstance(pb, dict) or not isinstance(pb.get("items"), list) or not pb.get("items"):
                errors.append(f"{prefix}: layout='proportion_bar' requires 'proportion_bar.items' list.")
            else:
                _check_allowed_keys(pb, "proportion_bar", f"{prefix}.proportion_bar", errors)
                ax_min = _as_float(pb.get("axis_min", 0.0))
                ax_max = _as_float(pb.get("axis_max", 100.0))
                if ax_min is None or ax_max is None:
                    errors.append(f"{prefix}.proportion_bar: 'axis_min' and 'axis_max' must be numeric.")
                elif ax_max <= ax_min:
                    errors.append(f"{prefix}.proportion_bar: 'axis_max' must exceed 'axis_min'.")
                for it_idx, it in enumerate(pb.get("items", [])):
                    if not isinstance(it, dict):
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(it, "proportion_item", f"{prefix}.proportion_bar.items[{it_idx}]", errors)
                    iid = it.get("id")
                    if not isinstance(iid, str) or not iid:
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: missing 'id'.")
                    elif iid in item_ids:
                        errors.append(f"{prefix}.proportion_bar: duplicate item id '{iid}'.")
                    else:
                        item_ids.add(iid)
                    _check_evidence_refs(it, claim_ids, f"{prefix}.proportion_bar.items['{iid}']", errors)
                    if not isinstance(it.get("label"), str) or not it.get("label"):
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: missing 'label'.")
                    val = _as_float(it.get("value", 0))
                    if val is None or val < 0:
                        errors.append(f"{prefix}.proportion_bar.items['{iid}']: 'value' must be a non-negative number.")

        col_ids: set[str] = set()
        if layout == "comparison_matrix":
            mx = s.get("matrix")
            if not isinstance(mx, dict) or not isinstance(mx.get("columns"), list) or not mx.get("columns"):
                errors.append(f"{prefix}: layout='comparison_matrix' requires 'matrix.columns' list.")
            else:
                _check_allowed_keys(mx, "matrix", f"{prefix}.matrix", errors)
                for c_idx, col in enumerate(mx.get("columns", [])):
                    if not isinstance(col, dict):
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(col, "matrix_column", f"{prefix}.matrix.columns[{c_idx}]", errors)
                    cid = col.get("id")
                    if not isinstance(cid, str) or not cid:
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: missing 'id'.")
                    elif cid in col_ids:
                        errors.append(f"{prefix}.matrix: duplicate column id '{cid}'.")
                    else:
                        col_ids.add(cid)
                    _check_evidence_refs(col, claim_ids, f"{prefix}.matrix.columns['{cid}']", errors)
                    if not isinstance(col.get("caption"), str) or not col.get("caption"):
                        errors.append(f"{prefix}.matrix.columns['{cid}']: missing 'caption'.")
                    rows = col.get("rows")
                    if not isinstance(rows, list) or not rows:
                        errors.append(f"{prefix}.matrix.columns['{cid}']: must have at least one row.")
                    else:
                        for r_idx, row in enumerate(rows):
                            if not isinstance(row, dict):
                                errors.append(f"{prefix}.matrix.columns['{cid}'].rows[{r_idx}]: must be an object.")
                            else:
                                _check_allowed_keys(row, "matrix_row", f"{prefix}.matrix.columns['{cid}'].rows[{r_idx}]", errors)

        frames = s.get("frames")
        if frames is None:
            if pacing == "manual":
                errors.append(f"{prefix}: pacing='manual' requires a non-empty 'frames' list.")
            continue

        if not isinstance(frames, list) or not frames:
            errors.append(f"{prefix}: 'frames' must be a non-empty list when provided.")
            continue

        if isinstance(nodes, list) and len(nodes) >= 2 and len(frames) == 1 and pacing == "manual":
            warnings.append(
                f"{prefix}: {len(nodes)} nodes rendered in a single frame; consider splitting into progressive step-by-step frames or running `keyflow pace`."
            )

        for f_idx, f in enumerate(frames):
            if not isinstance(f, dict):
                errors.append(f"{prefix}.frames[{f_idx}]: frame entry must be an object.")
                continue
            _check_allowed_keys(f, "frame", f"{prefix}.frames[{f_idx}]", errors)
            vis = f.get("visible_nodes", [])
            exp = f.get("expanded_nodes", [])
            if not isinstance(vis, list):
                errors.append(f"{prefix}.frames[{f_idx}]: 'visible_nodes' must be a list.")
                vis = []
            if not isinstance(exp, list):
                errors.append(f"{prefix}.frames[{f_idx}]: 'expanded_nodes' must be a list.")
                exp = []

            for nid in vis:
                if not isinstance(nid, str) or nid not in node_map:
                    errors.append(f"{prefix}.frames[{f_idx}]: unknown visible node '{nid}'.")
            for nid in exp:
                if not isinstance(nid, str) or nid not in node_map:
                    errors.append(f"{prefix}.frames[{f_idx}]: unknown expanded node '{nid}'.")
                elif nid not in vis:
                    errors.append(f"{prefix}.frames[{f_idx}]: expanded node '{nid}' must also be in 'visible_nodes'.")
                elif not isinstance(node_map[nid].get("children"), list) or not node_map[nid].get("children"):
                    errors.append(f"{prefix}.frames[{f_idx}]: expanded node '{nid}' has no 'children' to unpack.")

            vis_edges = f.get("visible_edges", "auto")
            if vis_edges != "auto":
                if not isinstance(vis_edges, list):
                    errors.append(f"{prefix}.frames[{f_idx}]: 'visible_edges' must be 'auto' or a list of edge ids.")
                else:
                    for eid in vis_edges:
                        if not isinstance(eid, str) or eid not in edge_ids:
                            errors.append(f"{prefix}.frames[{f_idx}]: unknown visible edge '{eid}'.")

            for list_field, valid_pool in (
                ("focus_nodes", node_map),
                ("visible_items", item_ids),
                ("visible_columns", col_ids),
                ("visible_objects", object_ids),
                ("focus_objects", object_ids),
            ):
                field_val = f.get(list_field)
                if field_val is not None:
                    if not isinstance(field_val, list):
                        errors.append(f"{prefix}.frames[{f_idx}]: '{list_field}' must be a list.")
                    else:
                        for item_id in field_val:
                            if not isinstance(item_id, str) or item_id not in valid_pool:
                                errors.append(f"{prefix}.frames[{f_idx}]: unknown {list_field} id '{item_id}'.")

            obj_states = f.get("object_states")
            if obj_states is not None:
                if not isinstance(obj_states, dict):
                    errors.append(f"{prefix}.frames[{f_idx}]: 'object_states' must be an object.")
                else:
                    for oid, st_val in obj_states.items():
                        if oid not in object_ids:
                            errors.append(f"{prefix}.frames[{f_idx}].object_states: unknown object '{oid}'.")
                        elif not isinstance(st_val, dict):
                            errors.append(f"{prefix}.frames[{f_idx}].object_states['{oid}']: must be an object.")
                        else:
                            _check_allowed_keys(st_val, "object_state", f"{prefix}.frames[{f_idx}].object_states['{oid}']", errors)
                            for count_key in ("series_count", "category_count", "row_count", "col_count"):
                                if count_key in st_val:
                                    cval = st_val[count_key]
                                    if isinstance(cval, bool) or not isinstance(cval, int) or cval < 1:
                                        errors.append(
                                            f"{prefix}.frames[{f_idx}].object_states['{oid}'].{count_key}: must be an integer >= 1."
                                        )
                            for list_key in ("visible_nodes", "expanded_nodes", "focus_nodes"):
                                if list_key in st_val and (
                                    not isinstance(st_val[list_key], list)
                                    or not all(isinstance(x, str) for x in st_val[list_key])
                                ):
                                    errors.append(
                                        f"{prefix}.frames[{f_idx}].object_states['{oid}'].{list_key}: must be a list of strings."
                                    )
                            if "visible_edges" in st_val:
                                ve = st_val["visible_edges"]
                                if ve != "auto" and (
                                    not isinstance(ve, list) or not all(isinstance(x, str) for x in ve)
                                ):
                                    errors.append(
                                        f"{prefix}.frames[{f_idx}].object_states['{oid}'].visible_edges: must be 'auto' or list of strings."
                                    )

            if not f.get("notes"):
                warnings.append(
                    f"{prefix}.frames[{f_idx}]: empty 'notes'; put article explanations in presenter notes to keep the slide minimal."
                )

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
