"""Final-bounds anchor-preserving layout solver for progressive Keynote scenes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from keyflow.schema import (
    CanvasObjectSpec,
    ChartSpec,
    ChildNodeSpec,
    ComparisonMatrixSpec,
    DeckSpec,
    DiagramLayout,
    EdgeSpec,
    EdgeStyle,
    FrameSpec,
    NodeSpec,
    NodeVariant,
    PinnedFlowSpec,
    ProportionBarSpec,
    RegionSpec,
    SceneSpec,
    SurfaceStyle,
    TableSpec,
    TextAlign,
    TrendDirection,
    compute_dag_layers,
)
from keyflow.tokens import (
    PINNED_FLOW_GAP_BELOW,
    SAFE_AREA_BOTTOM_MARGIN,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    SUBTITLE_MARGIN_X,
    TITLE_MARGIN_X,
)


@dataclass(frozen=True, slots=True)
class BoxRect:
    """Axis-aligned rectangle in slide points (origin top-left)."""

    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0


@dataclass(frozen=True, slots=True)
class PlacedBox:
    """A visual card or container placed on a slide."""

    id: str
    label: str
    rect: BoxRect
    kind: str  # "card" | "group_dashed" | "subcard" | "callout"
    variant: NodeVariant
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    opacity: float = 1.0
    caption: str | None = None
    caption_rect: BoxRect | None = None
    fill_hex: str | None = None
    border_hex: str | None = None
    color_hex: str | None = None
    font_scale: float | None = None
    surface: SurfaceStyle = "filled"
    align: TextAlign = "center"


@dataclass(frozen=True, slots=True)
class PlacedEdge:
    """A visual directed connector between two placed objects."""

    id: str
    from_id: str
    to_id: str
    tail_center: tuple[float, float]
    head_center: tuple[float, float]
    curve_control: tuple[float, float] | None = None
    label: str | None = None
    label_rect: BoxRect | None = None
    style: EdgeStyle = "solid"
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class PlacedDivider:
    """A vertical comparison divider line with an optional centered badge."""

    x: float
    y_top: float
    y_bottom: float
    label: str | None = None


@dataclass(frozen=True, slots=True)
class PlacedRibbonNode:
    id: str
    label: str
    rect: BoxRect
    is_active: bool = False


@dataclass(frozen=True, slots=True)
class PlacedRibbonGroup:
    id: str
    label: str
    rect: BoxRect
    legend_rect: BoxRect


@dataclass(frozen=True, slots=True)
class PlacedRibbonEdge:
    id: str
    from_id: str
    to_id: str
    tail_center: tuple[float, float]
    head_center: tuple[float, float]
    style: EdgeStyle = "solid"


@dataclass(frozen=True, slots=True)
class PlacedPinnedFlow:
    nodes: list[PlacedRibbonNode]
    groups: list[PlacedRibbonGroup]
    edges: list[PlacedRibbonEdge]
    is_centered: bool = False


@dataclass(frozen=True, slots=True)
class PlacedProportionItem:
    id: str
    label: str
    display_value: str
    color_index: int
    visible: bool
    seg_rect: BoxRect
    label_rect: BoxRect
    arrow_tail: tuple[float, float]
    arrow_head: tuple[float, float]
    chip_rect: BoxRect | None = None
    value_rect: BoxRect | None = None


@dataclass(frozen=True, slots=True)
class PlacedProportionBar:
    axis_start: tuple[float, float]
    axis_end: tuple[float, float]
    ticks: list[tuple[float, str]]
    bar_y: float
    bar_h: float
    items: list[PlacedProportionItem]
    summary_box: BoxRect | None = None
    summary_title: str = ""
    summary_caption_rect: BoxRect | None = None


@dataclass(frozen=True, slots=True)
class PlacedMatrixCell:
    rect: BoxRect
    text: str
    kind: str  # "header" | "chip" | "value" | "trend"
    trend: TrendDirection | None = None


@dataclass(frozen=True, slots=True)
class PlacedMatrixColumn:
    id: str
    box_rect: BoxRect
    caption: str
    caption_rect: BoxRect
    cells: list[PlacedMatrixCell]
    action_banner: str | None = None
    action_banner_rect: BoxRect | None = None
    action_subtext: str | None = None
    action_subtext_rect: BoxRect | None = None
    takeaway: str | None = None
    takeaway_rect: BoxRect | None = None


@dataclass(frozen=True, slots=True)
class PlacedComparisonMatrix:
    formula: str | None
    formula_rect: BoxRect | None
    columns: list[PlacedMatrixColumn]


@dataclass(frozen=True, slots=True)
class PlacedChartSeries:
    name: str
    values: list[float | None]
    color_hex: str | None = None
    active: bool = True
    full_values: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PlacedChart:
    id: str
    chart_type: str
    title: str | None
    rect: BoxRect
    categories: list[str]
    series: list[PlacedChartSeries]
    unit: str | None = None
    show_title: bool | None = None
    show_legend: bool = True
    show_value_labels: bool = True
    axis_min: float | None = None
    axis_max: float | None = None
    opacity: float = 1.0
    render_mode: str = "auto"
    use_vector: bool = False
    highlight_categories: tuple[str, ...] = ()
    estimate_from: int | None = None
    reference_lines: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class PlacedTable:
    id: str
    title: str | None
    rect: BoxRect
    headers: list[str]
    rows: list[list[str]]
    visible_rows: int
    visible_cols: int
    highlight_cols: tuple[int, ...] = ()
    highlight_rows: tuple[int, ...] = ()
    target_rows: tuple[int, ...] = ()
    cell_tones: tuple[tuple[str | None, ...], ...] = ()
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class PlacedTextbox:
    id: str
    text: str
    rect: BoxRect
    font_size: float = 28.0
    bold: bool = False
    align: str = "center"
    color_hex: str | None = None
    fill_hex: str | None = None
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class PlacedShape:
    id: str
    shape_type: str
    rect: BoxRect
    svg_path: str | None = None
    label: str | None = None
    fill_hex: str | None = None
    border_hex: str | None = None
    color_hex: str | None = None
    font_scale: float | None = None
    surface: SurfaceStyle = "filled"
    align: TextAlign = "center"
    dashed: bool = False
    variant: NodeVariant = "primary"
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class PlacedRegionFrame:
    id: str
    title: str | None
    rect: BoxRect
    title_rect: BoxRect | None = None


@dataclass(frozen=True, slots=True)
class ResolvedFrame:
    """Fully positioned visual elements for one slide frame."""

    scene_id: str
    frame_index: int
    title: str
    subtitle: str | None
    title_rect: BoxRect | None
    subtitle_rect: BoxRect | None
    scale: float = 1.0
    pinned_flow: PlacedPinnedFlow | None = None
    boxes: list[PlacedBox] = field(default_factory=list)
    edges: list[PlacedEdge] = field(default_factory=list)
    dividers: list[PlacedDivider] = field(default_factory=list)
    proportion_bar: PlacedProportionBar | None = None
    comparison_matrix: PlacedComparisonMatrix | None = None
    region_frames: list[PlacedRegionFrame] = field(default_factory=list)
    charts: list[PlacedChart] = field(default_factory=list)
    tables: list[PlacedTable] = field(default_factory=list)
    shapes: list[PlacedShape] = field(default_factory=list)
    textboxes: list[PlacedTextbox] = field(default_factory=list)
    palette: dict[str, object] | None = None
    notes: str = ""
    depth: int = 1


def _sequence_curve_control(
    r_from: BoxRect,
    r_to: BoxRect,
    from_idx: int,
    to_idx: int,
    scale: float,
) -> tuple[float, float] | None:
    """Compute quadratic Bezier control point for sequence_timeline forward-skip / backward-retry arcs."""
    span = to_idx - from_idx
    mx = (r_from.cx + r_to.cx) / 2.0
    if span > 1:
        arc_y = min(r_from.y, r_to.y) - (78.0 + 36.0 * (span - 2)) * max(0.75, scale)
        return (mx, arc_y)
    if span < 0:
        arc_y = max(r_from.y + r_from.h, r_to.y + r_to.h) + (82.0 + 36.0 * (abs(span) - 1)) * max(0.75, scale)
        return (mx, arc_y)
    return None


def _text_units(text: str) -> float:
    return sum(1.8 if ord(ch) > 127 else 1.0 for ch in text)


def _estimate_card_size(
    label: str,
    sublabel: str | None = None,
    badge: str | None = None,
    metric: str | None = None,
    *,
    min_w: float = 220.0,
    max_w: float = 360.0,
    base_h: float = 148.0,
) -> tuple[float, float]:
    """Estimate balanced card (width, height) accounting for micro-hierarchy elements."""
    units = _text_units(label)
    if sublabel:
        units = max(units, _text_units(sublabel) * 0.78)
    if badge:
        units = max(units, _text_units(badge) * 0.72)
    if metric:
        units = max(units, _text_units(metric) * 1.15)
    w = max(min_w, min(max_w, 96.0 + units * 19.0))

    h = base_h
    if sublabel:
        h += 18.0
    if badge:
        h += 24.0
    if metric:
        h += 48.0
    return w, h


def _node_always_expanded(node: NodeSpec, scene: SceneSpec) -> bool:
    if node.kind == "group_dashed":
        return True
    return any(node.id in f.expanded_nodes for f in scene.frames)


def _group_dimensions(
    node: NodeSpec,
    *,
    default_layout: str | None = None,
) -> tuple[float, float, list[tuple[ChildNodeSpec, BoxRect]]]:
    """Compute local (0,0)-based bounding size and child rects for an expanded group."""
    children = node.children
    k = len(children)
    if k == 0:
        w, h = _estimate_card_size(node.label, node.sublabel, node.badge, node.metric)
        return w, h, []

    eff_layout = default_layout or node.child_layout

    if eff_layout == "column":
        sizes = [
            _estimate_card_size(
                c.label, c.sublabel, c.badge, c.metric, min_w=240.0, max_w=360.0, base_h=94.0
            )
            for c in children
        ]
        sub_w = max(w for w, _ in sizes)
        gap = 18.0
        pad_x, pad_y = 28.0, 24.0
        total_w = sub_w + 2 * pad_x
        total_h = 2 * pad_y + sum(h for _, h in sizes) + max(0, k - 1) * gap
        rel_children: list[tuple[ChildNodeSpec, BoxRect]] = []
        cursor_y = pad_y
        for c, (_, sh) in zip(children, sizes):
            rel_children.append((c, BoxRect(pad_x, cursor_y, sub_w, sh)))
            cursor_y += sh + gap
        return total_w, total_h, rel_children

    if eff_layout == "grid":
        cols = 3 if k > 6 else 2
        rows = math.ceil(k / cols)
        sizes = [
            _estimate_card_size(
                c.label, c.sublabel, c.badge, c.metric, min_w=175.0, max_w=255.0, base_h=96.0
            )
            for c in children
        ]
        cell_w = max(w for w, _ in sizes)
        cell_h = max(h for _, h in sizes)
        gap_x, gap_y = 20.0, 18.0
        pad_x, pad_y = 24.0, 24.0
        total_w = 2 * pad_x + cols * cell_w + (cols - 1) * gap_x
        total_h = 2 * pad_y + rows * cell_h + (rows - 1) * gap_y
        rel_children = []
        for idx, c in enumerate(children):
            r, col = divmod(idx, cols)
            items_in_row = cols if r < rows - 1 else (k - r * cols)
            row_w = items_in_row * cell_w + (items_in_row - 1) * gap_x
            row_start_x = (total_w - row_w) / 2.0
            cx = row_start_x + col * (cell_w + gap_x)
            cy = pad_y + r * (cell_h + gap_y)
            rel_children.append((c, BoxRect(cx, cy, cell_w, cell_h)))
        return total_w, total_h, rel_children

    sizes = [
        _estimate_card_size(
            c.label, c.sublabel, c.badge, c.metric, min_w=185.0, max_w=275.0, base_h=112.0
        )
        for c in children
    ]
    sub_h = max(h for _, h in sizes)
    gap = 24.0
    pad_x, pad_y = 26.0, 30.0
    total_w = 2 * pad_x + sum(w for w, _ in sizes) + max(0, k - 1) * gap
    total_h = sub_h + 2 * pad_y
    rel_children = []
    cursor_x = pad_x
    for c, (sw, _) in zip(children, sizes):
        rel_children.append((c, BoxRect(cursor_x, pad_y, sw, sub_h)))
        cursor_x += sw + gap
    return total_w, total_h, rel_children


@dataclass(slots=True)
class _NodeGeometry:
    collapsed_rect: BoxRect
    expanded_rect: BoxRect
    child_rects: list[tuple[ChildNodeSpec, BoxRect]]
    caption_rect: BoxRect | None


@dataclass(slots=True)
class _LayoutOutcome:
    geos: dict[str, _NodeGeometry]
    scale: float
    dividers: list[PlacedDivider] = field(default_factory=list)


def _caption_rect_for(node: NodeSpec, group_rect: BoxRect, scale: float) -> BoxRect | None:
    if node.caption_position == "inside":
        return None
    cap_h = 54.0 * max(0.75, scale)
    cap_w = max(group_rect.w, 240.0 * scale)
    cap_x = group_rect.cx - cap_w / 2.0
    if node.caption_position == "top":
        return BoxRect(cap_x, group_rect.y - cap_h - 12.0 * scale, cap_w, cap_h)
    return BoxRect(cap_x, group_rect.y + group_rect.h + 14.0 * scale, cap_w, cap_h)


def _scale_children(
    expanded_rect: BoxRect,
    rel_children: list[tuple[ChildNodeSpec, BoxRect]],
    scale: float,
) -> list[tuple[ChildNodeSpec, BoxRect]]:
    return [
        (
            child,
            BoxRect(
                expanded_rect.x + crect.x * scale,
                expanded_rect.y + crect.y * scale,
                crect.w * scale,
                crect.h * scale,
            ),
        )
        for child, crect in rel_children
    ]


def _resolve_pinned_flow(
    pf: PinnedFlowSpec,
    active_node_id: str | None,
    canvas_w: float,
    canvas_h: float,
    *,
    centered: bool,
    docked_cy: float = 160.0,
) -> PlacedPinnedFlow:
    nodes = pf.nodes
    n = len(nodes)
    if n == 0:
        return PlacedPinnedFlow([], [], [], is_centered=centered)

    node_h = 104.0 if centered else 72.0
    gap = 92.0 if centered else 78.0
    widths = [
        _estimate_card_size(node.label, min_w=175.0 if not centered else 200.0, max_w=270.0, base_h=node_h)[0]
        for node in nodes
    ]
    raw_total_w = sum(widths) + max(0, n - 1) * gap
    usable_w = canvas_w - 150.0
    scale = min(1.0, usable_w / raw_total_w) if raw_total_w > 0 else 1.0

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (canvas_h * 0.50) if centered else docked_cy
    sh = node_h * max(0.84, scale)

    node_rects: dict[str, BoxRect] = {}
    placed_nodes: list[PlacedRibbonNode] = []
    for node, raw_w in zip(nodes, widths):
        sw = raw_w * scale
        rect = BoxRect(cursor_x, cy - sh / 2.0, sw, sh)
        node_rects[node.id] = rect
        placed_nodes.append(
            PlacedRibbonNode(
                id=node.id,
                label=node.label,
                rect=rect,
                is_active=(node.id == active_node_id),
            )
        )
        cursor_x += sw + gap * scale

    placed_groups: list[PlacedRibbonGroup] = []
    pad_x = 24.0 * scale
    pad_y = 24.0 * scale
    for grp in pf.groups:
        member_rects = [node_rects[nid] for nid in grp.node_ids if nid in node_rects]
        if not member_rects:
            continue
        x0 = min(r.x for r in member_rects) - pad_x
        y0 = min(r.y for r in member_rects) - pad_y
        x1 = max(r.x + r.w for r in member_rects) + pad_x
        y1 = max(r.y + r.h for r in member_rects) + pad_y
        g_rect = BoxRect(x0, y0, x1 - x0, y1 - y0)
        leg_w = min(g_rect.w - 30.0, max(130.0, _text_units(grp.label) * 16.0 + 30.0))
        leg_h = 34.0
        leg_rect = BoxRect(g_rect.cx - leg_w / 2.0, g_rect.y - leg_h / 2.0, leg_w, leg_h)
        placed_groups.append(
            PlacedRibbonGroup(id=grp.id, label=grp.label, rect=g_rect, legend_rect=leg_rect)
        )

    placed_edges: list[PlacedRibbonEdge] = []
    for edge in pf.edges:
        if edge.from_id in node_rects and edge.to_id in node_rects:
            rf = node_rects[edge.from_id]
            rt = node_rects[edge.to_id]
            placed_edges.append(
                PlacedRibbonEdge(
                    id=edge.id,
                    from_id=edge.from_id,
                    to_id=edge.to_id,
                    tail_center=(rf.cx, rf.cy),
                    head_center=(rt.cx, rt.cy),
                    style=edge.style,
                )
            )

    return PlacedPinnedFlow(
        nodes=placed_nodes,
        groups=placed_groups,
        edges=placed_edges,
        is_centered=centered,
    )


