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
    TableSpec,
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
    show_legend: bool = True
    show_value_labels: bool = True
    axis_min: float | None = None
    axis_max: float | None = None
    opacity: float = 1.0
    render_mode: str = "auto"
    use_vector: bool = False


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


def _solve_horizontal_flow(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    nodes = scene.nodes
    n = len(nodes)
    if n == 0:
        return _LayoutOutcome({}, 1.0)

    arrow_gap = 170.0
    slots: list[tuple[NodeSpec, float, float, float, float, list[tuple[ChildNodeSpec, BoxRect]]]] = []

    for node in nodes:
        cw, ch = _estimate_card_size(node.label, node.sublabel, node.badge, node.metric)
        if _node_always_expanded(node, scene) and node.children:
            gw, gh, rel_children = _group_dimensions(node)
        else:
            gw, gh, rel_children = cw, ch, []
        slots.append((node, cw, ch, gw, gh, rel_children))

    raw_total_w = sum(max(cw, gw) for _, cw, _, gw, _, _ in slots) + max(0, n - 1) * arrow_gap
    usable_w = canvas_w - 130.0
    scale = min(1.0, usable_w / raw_total_w) if raw_total_w > 0 else 1.0

    max_h = max(max(ch, gh) for _, _, ch, _, gh, _ in slots) * scale
    usable_h = (area_bottom - area_top) - 90.0
    if max_h > usable_h and max_h > 0:
        scale *= usable_h / max_h

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (area_top + area_bottom) / 2.0 - 20.0

    result: dict[str, _NodeGeometry] = {}
    for node, cw, ch, gw, gh, rel_children in slots:
        slot_w = max(cw, gw) * scale
        scw, sch = cw * scale, ch * scale
        sgw, sgh = gw * scale, gh * scale

        collapsed_rect = BoxRect(cursor_x, cy - sch / 2.0, scw, sch)
        expanded_rect = BoxRect(cursor_x, cy - sgh / 2.0, sgw, sgh)
        result[node.id] = _NodeGeometry(
            collapsed_rect=collapsed_rect,
            expanded_rect=expanded_rect,
            child_rects=_scale_children(expanded_rect, rel_children, scale),
            caption_rect=_caption_rect_for(node, expanded_rect, scale),
        )
        cursor_x += slot_w + arrow_gap * scale

    return _LayoutOutcome(result, scale)


def _solve_vertical_flow(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    nodes = scene.nodes
    n = len(nodes)
    if n == 0:
        return _LayoutOutcome({}, 1.0)

    arrow_gap = 82.0
    slots: list[tuple[NodeSpec, float, float, float, float, list[tuple[ChildNodeSpec, BoxRect]]]] = []

    for node in nodes:
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=280.0, max_w=460.0, base_h=112.0
        )
        if _node_always_expanded(node, scene) and node.children:
            gw, gh, rel_children = _group_dimensions(node)
        else:
            gw, gh, rel_children = cw, ch, []
        slots.append((node, cw, ch, gw, gh, rel_children))

    raw_total_h = sum(max(ch, gh) for _, _, ch, _, gh, _ in slots) + max(0, n - 1) * arrow_gap
    usable_h = (area_bottom - area_top) - 40.0
    scale = min(1.0, usable_h / raw_total_h) if raw_total_h > 0 else 1.0

    scaled_total_h = raw_total_h * scale
    cursor_y = area_top + max(0.0, (usable_h - scaled_total_h) / 2.0)
    cx = canvas_w / 2.0

    result: dict[str, _NodeGeometry] = {}
    for node, cw, ch, gw, gh, rel_children in slots:
        slot_h = max(ch, gh) * scale
        scw, sch = cw * scale, ch * scale
        sgw, sgh = gw * scale, gh * scale

        collapsed_rect = BoxRect(cx - scw / 2.0, cursor_y, scw, sch)
        expanded_rect = BoxRect(cx - sgw / 2.0, cursor_y, sgw, sgh)
        result[node.id] = _NodeGeometry(
            collapsed_rect=collapsed_rect,
            expanded_rect=expanded_rect,
            child_rects=_scale_children(expanded_rect, rel_children, scale),
            caption_rect=_caption_rect_for(node, expanded_rect, scale),
        )
        cursor_y += slot_h + arrow_gap * scale

    return _LayoutOutcome(result, scale)


def _solve_comparison(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Side-by-side column cards or dashed groups with a centered comparison divider."""
    nodes = scene.nodes
    n = len(nodes)
    if n == 0:
        return _LayoutOutcome({}, 1.0)

    col_gap = 150.0
    slots: list[tuple[NodeSpec, float, float, float, float, list[tuple[ChildNodeSpec, BoxRect]]]] = []

    for node in nodes:
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=300.0, max_w=460.0, base_h=170.0
        )
        if (_node_always_expanded(node, scene) or node.children) and node.children:
            col_layout = node.child_layout if node.child_layout != "row" or len(node.children) <= 2 else "column"
            gw, gh, rel_children = _group_dimensions(node, default_layout=col_layout)
        else:
            gw, gh, rel_children = cw, ch, []
        slots.append((node, cw, ch, gw, gh, rel_children))

    raw_total_w = sum(max(cw, gw) for _, cw, _, gw, _, _ in slots) + max(0, n - 1) * col_gap
    usable_w = canvas_w - 160.0
    scale = min(1.0, usable_w / raw_total_w) if raw_total_w > 0 else 1.0

    max_h = max(max(ch, gh) for _, _, ch, _, gh, _ in slots) * scale
    usable_h = (area_bottom - area_top) - 80.0
    if max_h > usable_h and max_h > 0:
        scale *= usable_h / max_h

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (area_top + area_bottom) / 2.0 - 20.0

    result: dict[str, _NodeGeometry] = {}
    col_bounds: list[tuple[float, float]] = []
    for node, cw, ch, gw, gh, rel_children in slots:
        slot_w = max(cw, gw) * scale
        scw, sch = cw * scale, ch * scale
        sgw, sgh = gw * scale, gh * scale

        collapsed_rect = BoxRect(cursor_x + (slot_w - scw) / 2.0, cy - sch / 2.0, scw, sch)
        expanded_rect = BoxRect(cursor_x + (slot_w - sgw) / 2.0, cy - sgh / 2.0, sgw, sgh)
        result[node.id] = _NodeGeometry(
            collapsed_rect=collapsed_rect,
            expanded_rect=expanded_rect,
            child_rects=_scale_children(expanded_rect, rel_children, scale),
            caption_rect=_caption_rect_for(node, expanded_rect, scale),
        )
        col_bounds.append((cursor_x, cursor_x + slot_w))
        cursor_x += slot_w + col_gap * scale

    dividers: list[PlacedDivider] = []
    if n >= 2:
        div_half_h = max(165.0, max_h * 0.68)
        for i in range(n - 1):
            mid_x = (col_bounds[i][1] + col_bounds[i + 1][0]) / 2.0
            dividers.append(
                PlacedDivider(
                    x=mid_x,
                    y_top=cy - div_half_h,
                    y_bottom=cy + div_half_h,
                    label="VS" if n == 2 else None,
                )
            )

    return _LayoutOutcome(result, scale, dividers=dividers)


def _solve_architecture_evolution(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Multi-era stacked architecture columns connected by left-to-right evolution arrows."""
    nodes = scene.nodes
    n = len(nodes)
    if n == 0:
        return _LayoutOutcome({}, 1.0)

    stage_gap = 185.0
    slots: list[tuple[NodeSpec, float, float, float, float, list[tuple[ChildNodeSpec, BoxRect]]]] = []

    for node in nodes:
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=300.0, max_w=460.0, base_h=170.0
        )
        if node.children:
            eff_layout = node.child_layout if node.child_layout in ("column", "grid") else "column"
            gw, gh, rel_children = _group_dimensions(node, default_layout=eff_layout)
        else:
            gw, gh, rel_children = cw, ch, []
        slots.append((node, cw, ch, gw, gh, rel_children))

    raw_total_w = sum(max(cw, gw) for _, cw, _, gw, _, _ in slots) + max(0, n - 1) * stage_gap
    usable_w = canvas_w - 150.0
    scale = min(1.0, usable_w / raw_total_w) if raw_total_w > 0 else 1.0

    max_h = max(max(ch, gh) for _, _, ch, _, gh, _ in slots) * scale
    usable_h = (area_bottom - area_top) - 90.0
    if max_h > usable_h and max_h > 0:
        scale *= usable_h / max_h

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (area_top + area_bottom) / 2.0 - 20.0

    result: dict[str, _NodeGeometry] = {}
    for node, cw, ch, gw, gh, rel_children in slots:
        slot_w = max(cw, gw) * scale
        scw, sch = cw * scale, ch * scale
        sgw, sgh = gw * scale, gh * scale

        collapsed_rect = BoxRect(cursor_x + (slot_w - scw) / 2.0, cy - sch / 2.0, scw, sch)
        expanded_rect = BoxRect(cursor_x + (slot_w - sgw) / 2.0, cy - sgh / 2.0, sgw, sgh)
        result[node.id] = _NodeGeometry(
            collapsed_rect=collapsed_rect,
            expanded_rect=expanded_rect,
            child_rects=_scale_children(expanded_rect, rel_children, scale),
            caption_rect=_caption_rect_for(node, expanded_rect, scale),
        )
        cursor_x += slot_w + stage_gap * scale

    return _LayoutOutcome(result, scale)


def _solve_sequence_timeline(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Horizontal state/actor rail reserving top and bottom bands for curved forward/feedback transitions."""
    nodes = scene.nodes
    n = len(nodes)
    if n == 0:
        return _LayoutOutcome({}, 1.0)

    arrow_gap = 155.0
    slots: list[tuple[NodeSpec, float, float]] = []
    for node in nodes:
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=210.0, max_w=320.0, base_h=136.0
        )
        slots.append((node, cw, ch))

    raw_total_w = sum(cw for _, cw, _ in slots) + max(0, n - 1) * arrow_gap
    usable_w = canvas_w - 150.0
    scale = min(1.0, usable_w / raw_total_w) if raw_total_w > 0 else 1.0

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (area_top + area_bottom) / 2.0

    result: dict[str, _NodeGeometry] = {}
    for node, cw, ch in slots:
        scw, sch = cw * scale, ch * scale
        rect = BoxRect(cursor_x, cy - sch / 2.0, scw, sch)
        result[node.id] = _NodeGeometry(rect, rect, [], None)
        cursor_x += scw + arrow_gap * scale

    return _LayoutOutcome(result, scale)


def _solve_metrics_cards(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Spacious KPI / highlight card grid (1-4 in a row, 5-6 in a 3x2 grid)."""
    nodes = scene.nodes
    k = len(nodes)
    if k == 0:
        return _LayoutOutcome({}, 1.0)

    cols = k if k <= 4 else 3
    rows = math.ceil(k / cols)
    # Single-card hero mode ("one big number / core thesis") gets centerpiece proportions
    card_min_w = 520.0 if k == 1 else 270.0
    card_max_w = 780.0 if k == 1 else 400.0
    card_base_h = 280.0 if k == 1 else 210.0
    sizes = [
        _estimate_card_size(
            n.label,
            n.sublabel,
            n.badge,
            n.metric,
            min_w=card_min_w,
            max_w=card_max_w,
            base_h=card_base_h,
        )
        for n in nodes
    ]
    cell_w = max(w for w, _ in sizes)
    cell_h = max(h for _, h in sizes)
    gap_x = 44.0
    gap_y = 36.0

    raw_w = cols * cell_w + max(0, cols - 1) * gap_x
    raw_h = rows * cell_h + max(0, rows - 1) * gap_y
    usable_w = canvas_w - 160.0
    usable_h = (area_bottom - area_top) - 40.0
    scale = min(1.0, usable_w / raw_w if raw_w > 0 else 1.0, usable_h / raw_h if raw_h > 0 else 1.0)

    sc_w, sc_h = cell_w * scale, cell_h * scale
    sg_x, sg_y = gap_x * scale, gap_y * scale
    total_h = rows * sc_h + max(0, rows - 1) * sg_y
    start_y = area_top + max(0.0, (usable_h - total_h) / 2.0)

    result: dict[str, _NodeGeometry] = {}
    for idx, node in enumerate(nodes):
        r, col = divmod(idx, cols)
        items_in_row = cols if r < rows - 1 else (k - r * cols)
        row_w = items_in_row * sc_w + max(0, items_in_row - 1) * sg_x
        row_start_x = (canvas_w - row_w) / 2.0
        rect = BoxRect(row_start_x + col * (sc_w + sg_x), start_y + r * (sc_h + sg_y), sc_w, sc_h)
        result[node.id] = _NodeGeometry(rect, rect, [], None)

    return _LayoutOutcome(result, scale)


def _solve_hub_spoke(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Place first node at center and distribute remaining nodes radially around it."""
    nodes = scene.nodes
    if not nodes:
        return _LayoutOutcome({}, 1.0)

    cx = canvas_w / 2.0
    cy = (area_top + area_bottom) / 2.0
    hub = nodes[0]
    hub_w, hub_h = _estimate_card_size(
        hub.label, hub.sublabel, hub.badge, hub.metric, min_w=260.0, max_w=360.0, base_h=150.0
    )
    result: dict[str, _NodeGeometry] = {}

    hub_rect = BoxRect(cx - hub_w / 2.0, cy - hub_h / 2.0, hub_w, hub_h)
    result[hub.id] = _NodeGeometry(hub_rect, hub_rect, [], None)

    spokes = nodes[1:]
    if not spokes:
        return _LayoutOutcome(result, 1.0)

    rx = min(560.0, (canvas_w - 440.0) / 2.0)
    ry = min(255.0, (area_bottom - area_top - 180.0) / 2.0)
    for idx, node in enumerate(spokes):
        angle = -math.pi / 2.0 + (2.0 * math.pi * idx) / len(spokes)
        sx = cx + rx * math.cos(angle)
        sy = cy + ry * math.sin(angle)
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=210.0, max_w=320.0, base_h=122.0
        )
        rect = BoxRect(sx - cw / 2.0, sy - ch / 2.0, cw, ch)
        result[node.id] = _NodeGeometry(rect, rect, [], None)

    return _LayoutOutcome(result, 1.0)


def _solve_flow_dag(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> _LayoutOutcome:
    """Layered left-to-right DAG layout supporting branches, parallel lanes, and merges."""
    nodes = scene.nodes
    if not nodes:
        return _LayoutOutcome({}, 1.0)

    layer_of, _ = compute_dag_layers(
        [n.id for n in nodes],
        [(e.from_id, e.to_id) for e in scene.edges],
    )

    num_layers = max(layer_of.values(), default=0) + 1
    layers: list[list[NodeSpec]] = [[] for _ in range(num_layers)]
    for node in nodes:
        layers[layer_of[node.id]].append(node)

    node_dims: dict[str, tuple[float, float, float, float, list[tuple[ChildNodeSpec, BoxRect]]]] = {}
    for node in nodes:
        cw, ch = _estimate_card_size(
            node.label, node.sublabel, node.badge, node.metric, min_w=205.0, max_w=310.0, base_h=132.0
        )
        if _node_always_expanded(node, scene) and node.children:
            gw, gh, rel_children = _group_dimensions(node)
        else:
            gw, gh, rel_children = cw, ch, []
        node_dims[node.id] = (cw, ch, gw, gh, rel_children)

    col_gap = 135.0
    row_gap = 120.0
    layer_widths = [
        max(max(node_dims[n.id][0], node_dims[n.id][2]) for n in layer) if layer else 0.0
        for layer in layers
    ]
    layer_heights: list[float] = []
    for layer in layers:
        if not layer:
            layer_heights.append(0.0)
            continue
        extra_caps = sum(
            62.0 if (_node_always_expanded(n, scene) and n.children and n.caption_position != "inside") else 0.0
            for n in layer
        )
        h_sum = (
            sum(max(node_dims[n.id][1], node_dims[n.id][3]) for n in layer)
            + max(0, len(layer) - 1) * row_gap
            + extra_caps
        )
        layer_heights.append(h_sum)

    raw_total_w = sum(layer_widths) + max(0, num_layers - 1) * col_gap
    raw_max_h = max(layer_heights, default=0.0)

    usable_w = canvas_w - 130.0
    usable_h = (area_bottom - area_top) - 40.0
    scale_w = usable_w / raw_total_w if raw_total_w > 0 else 1.0
    scale_h = usable_h / raw_max_h if raw_max_h > 0 else 1.0
    scale = min(1.0, scale_w, scale_h)

    scaled_total_w = raw_total_w * scale
    cursor_x = (canvas_w - scaled_total_w) / 2.0
    cy = (area_top + area_bottom) / 2.0 - 10.0

    result: dict[str, _NodeGeometry] = {}
    for layer, raw_lw, raw_lh in zip(layers, layer_widths, layer_heights):
        lw = raw_lw * scale
        lh = raw_lh * scale
        cursor_y = cy - lh / 2.0
        for node in layer:
            cw, ch, gw, gh, rel_children = node_dims[node.id]
            scw, sch = cw * scale, ch * scale
            sgw, sgh = gw * scale, gh * scale
            slot_h = max(sch, sgh)
            x_center = cursor_x + lw / 2.0

            collapsed_rect = BoxRect(x_center - scw / 2.0, cursor_y + (slot_h - sch) / 2.0, scw, sch)
            expanded_rect = BoxRect(x_center - sgw / 2.0, cursor_y + (slot_h - sgh) / 2.0, sgw, sgh)
            cap_rect = _caption_rect_for(node, expanded_rect, scale)

            result[node.id] = _NodeGeometry(
                collapsed_rect=collapsed_rect,
                expanded_rect=expanded_rect,
                child_rects=_scale_children(expanded_rect, rel_children, scale),
                caption_rect=cap_rect,
            )
            extra = (
                62.0 * scale
                if (_node_always_expanded(node, scene) and node.children and node.caption_position != "inside")
                else 0.0
            )
            cursor_y += slot_h + row_gap * scale + extra
        cursor_x += lw + col_gap * scale

    return _LayoutOutcome(result, scale)


def _resolve_proportion_bar(
    pb: ProportionBarSpec,
    visible_item_ids: set[str] | None,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> PlacedProportionBar:
    items = pb.items
    span = max(pb.axis_max - pb.axis_min, 1e-6)
    cy = (area_top + area_bottom) / 2.0

    summary_box: BoxRect | None = None
    summary_caption_rect: BoxRect | None = None
    chip_rects: dict[str, tuple[BoxRect, BoxRect]] = {}

    if pb.show_summary_list:
        row_h = 54.0
        row_gap = 24.0
        pad_y = 32.0
        box_w = 390.0
        box_h = 2 * pad_y + len(items) * row_h + max(0, len(items) - 1) * row_gap
        max_h = area_bottom - area_top - 100.0
        list_scale = min(1.0, max_h / box_h) if box_h > max_h else 1.0
        s_row_h = row_h * list_scale
        s_row_gap = row_gap * list_scale
        s_pad_y = pad_y * list_scale
        s_box_h = box_h * list_scale
        box_x = 120.0
        box_y = cy - s_box_h / 2.0 - 14.0
        summary_box = BoxRect(box_x, box_y, box_w, s_box_h)
        if pb.summary_title:
            summary_caption_rect = BoxRect(box_x, box_y + s_box_h + 18.0, box_w, 50.0)

        for idx, it in enumerate(items):
            ry = box_y + s_pad_y + idx * (s_row_h + s_row_gap)
            c_rect = BoxRect(box_x + 48.0, ry, 178.0, s_row_h)
            v_rect = BoxRect(box_x + 245.0, ry, 105.0, s_row_h)
            chip_rects[it.id] = (c_rect, v_rect)

        axis_x0 = 610.0
        axis_x1 = canvas_w - 205.0
    else:
        axis_x0 = 180.0
        axis_x1 = canvas_w - 215.0

    axis_w = axis_x1 - axis_x0
    bar_h = 18.0
    bar_y = cy + 68.0
    axis_y = bar_y + bar_h / 2.0

    # Generate scale ticks
    ticks: list[tuple[float, str]] = []
    if pb.axis_step > 0:
        cur = pb.axis_min
        while cur <= pb.axis_max + 1e-6:
            frac = (cur - pb.axis_min) / span
            tx = axis_x0 + frac * axis_w
            label = f"{int(cur)}" if abs(cur - round(cur)) < 1e-6 else f"{cur:g}"
            ticks.append((tx, label))
            cur += pb.axis_step

    placed_items: list[PlacedProportionItem] = []
    cursor_val = pb.axis_min
    tier_right: list[float] = [-1e9, -1e9, -1e9]

    for idx, it in enumerate(items):
        is_vis = visible_item_ids is None or it.id in visible_item_ids
        seg_start_val = cursor_val
        cursor_val = min(pb.axis_max, cursor_val + it.value)
        seg_x = axis_x0 + ((seg_start_val - pb.axis_min) / span) * axis_w
        seg_w = max(8.0, ((cursor_val - seg_start_val) / span) * axis_w)
        seg_rect = BoxRect(seg_x, bar_y, seg_w, bar_h)

        disp = it.display_value or f"{it.value:g}{pb.unit}"
        full_label = f"{it.label} ({disp})"
        label_w = max(130.0, _text_units(full_label) * 14.5 + 18.0)
        label_h = 40.0
        seg_mid_x = seg_x + seg_w / 2.0
        label_cx = min(canvas_w - 36.0 - label_w / 2.0, seg_mid_x)
        label_left = label_cx - label_w / 2.0

        chosen_tier = 2
        for t in range(3):
            if label_left >= tier_right[t] + 12.0:
                chosen_tier = t
                break

        label_y = bar_y - (168.0 + chosen_tier * 52.0)
        label_rect = BoxRect(label_left, label_y, label_w, label_h)
        tier_right[chosen_tier] = max(tier_right[chosen_tier], label_rect.x + label_rect.w)

        c_rect, v_rect = chip_rects.get(it.id, (None, None))
        placed_items.append(
            PlacedProportionItem(
                id=it.id,
                label=full_label,
                display_value=disp,
                color_index=idx,
                visible=is_vis,
                seg_rect=seg_rect,
                label_rect=label_rect,
                arrow_tail=(seg_mid_x, bar_y - 4.0),
                arrow_head=(label_cx, label_y + label_h + 6.0),
                chip_rect=c_rect,
                value_rect=v_rect,
            )
        )

    return PlacedProportionBar(
        axis_start=(axis_x0 - 16.0, axis_y),
        axis_end=(axis_x1 + 78.0, axis_y),
        ticks=ticks,
        bar_y=bar_y,
        bar_h=bar_h,
        items=placed_items,
        summary_box=summary_box,
        summary_title=pb.summary_title,
        summary_caption_rect=summary_caption_rect,
    )


def _resolve_comparison_matrix(
    mx: ComparisonMatrixSpec,
    visible_col_ids: set[str] | None,
    show_annotations: bool,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
) -> PlacedComparisonMatrix:
    cols = mx.columns
    n = len(cols)

    formula_rect: BoxRect | None = None
    cols_top = area_top + 20.0
    if mx.formula:
        formula_rect = BoxRect(260.0, area_top + 12.0, canvas_w - 520.0, 96.0)
        cols_top = area_top + 122.0

    has_any_action = any(c.action_banner or c.action_subtext for c in cols)
    has_any_takeaway = any(c.takeaway for c in cols)
    top_anno_pad = (110.0 if has_any_action else 0.0) + (62.0 if has_any_takeaway else 0.0)

    col_gap = 46.0
    usable_w = canvas_w - 140.0
    col_w = min(530.0, (usable_w - max(0, n - 1) * col_gap) / max(n, 1))
    total_w = n * col_w + max(0, n - 1) * col_gap
    start_x = (canvas_w - total_w) / 2.0

    max_rows = max((len(c.rows) for c in cols), default=1)
    avail_box_h = area_bottom - (cols_top + top_anno_pad) - 72.0
    header_h = 44.0
    pad_y = 22.0
    row_gap = 14.0
    row_h = min(48.0, max(34.0, (avail_box_h - 2 * pad_y - header_h - max(0, max_rows) * row_gap) / max(max_rows, 1)))

    placed_cols: list[PlacedMatrixColumn] = []
    for c_idx, col in enumerate(cols):
        if visible_col_ids is not None and col.id not in visible_col_ids:
            continue
        cx = start_x + c_idx * (col_w + col_gap)
        box_h = 2 * pad_y + header_h + len(col.rows) * (row_h + row_gap)
        box_y = cols_top + top_anno_pad
        box_rect = BoxRect(cx, box_y, col_w, box_h)
        cap_rect = BoxRect(cx, box_y + box_h + 14.0, col_w, 46.0)

        # Horizontal column split inside the card: [chip] + [proportional value cols] + [trend arrow]
        chip_w = min(136.0, col_w * 0.25)
        trend_w = 32.0 if any(r.trend for r in col.rows) else 0.0
        val_count = max(len(col.headers), max((len(r.values) for r in col.rows), default=1))
        inner_left = cx + 20.0
        inner_right = cx + col_w - 18.0 - trend_w
        vals_x0 = inner_left + chip_w + 10.0
        vals_total_w = max(120.0, inner_right - vals_x0)

        col_weights: list[float] = []
        for vi in range(val_count):
            h_units = _text_units(col.headers[vi]) if vi < len(col.headers) else 2.0
            v_units = max((_text_units(r.values[vi]) if vi < len(r.values) else 2.0) for r in col.rows)
            col_weights.append(max(2.6, h_units, v_units))
        weight_sum = sum(col_weights) or 1.0
        val_widths = [vals_total_w * (w / weight_sum) for w in col_weights]
        val_starts: list[float] = []
        vx = vals_x0
        for vw in val_widths:
            val_starts.append(vx)
            vx += vw

        cells: list[PlacedMatrixCell] = []
        hy = box_y + pad_y
        for h_idx, h_text in enumerate(col.headers):
            cells.append(
                PlacedMatrixCell(
                    rect=BoxRect(val_starts[h_idx], hy, val_widths[h_idx], header_h),
                    text=h_text,
                    kind="header",
                )
            )

        for r_idx, row in enumerate(col.rows):
            ry = hy + header_h + 8.0 + r_idx * (row_h + row_gap)
            cells.append(
                PlacedMatrixCell(
                    rect=BoxRect(inner_left, ry, chip_w, row_h),
                    text=row.chip,
                    kind="chip",
                )
            )
            for v_idx, val in enumerate(row.values):
                cells.append(
                    PlacedMatrixCell(
                        rect=BoxRect(val_starts[v_idx], ry, val_widths[v_idx], row_h),
                        text=val,
                        kind="value",
                    )
                )
            if row.trend in ("up", "down"):
                arrow_ch = "↑" if row.trend == "up" else "↓"
                cells.append(
                    PlacedMatrixCell(
                        rect=BoxRect(inner_right + 2.0, ry, trend_w, row_h),
                        text=arrow_ch,
                        kind="trend",
                        trend=row.trend,
                    )
                )

        ab_rect = None
        as_rect = None
        tk_rect = None
        if show_annotations:
            if col.action_banner:
                ab_rect = BoxRect(cx + 28.0, box_y - 62.0, col_w - 56.0, 44.0)
            if col.action_subtext:
                as_rect = BoxRect(cx + 12.0, box_y - 110.0, col_w - 24.0, 38.0)
            if col.takeaway:
                tk_w = min(col_w - 80.0, max(150.0, _text_units(col.takeaway) * 18.0 + 36.0))
                tk_rect = BoxRect(box_rect.cx - tk_w / 2.0, box_y - 162.0, tk_w, 42.0)

        placed_cols.append(
            PlacedMatrixColumn(
                id=col.id,
                box_rect=box_rect,
                caption=col.caption,
                caption_rect=cap_rect,
                cells=cells,
                action_banner=col.action_banner if show_annotations else None,
                action_banner_rect=ab_rect,
                action_subtext=col.action_subtext if show_annotations else None,
                action_subtext_rect=as_rect,
                takeaway=col.takeaway if show_annotations else None,
                takeaway_rect=tk_rect,
            )
        )

    return PlacedComparisonMatrix(
        formula=mx.formula,
        formula_rect=formula_rect,
        columns=placed_cols,
    )


def _compute_chart_axis_bounds(chart: ChartSpec) -> tuple[float | None, float | None]:
    """Compute locked (axis_min, axis_max) across all series so progressive frames never jump scale."""
    if chart.chart_type in ("pie", "donut"):
        return chart.axis_min, chart.axis_max

    if chart.chart_type == "waterfall":
        vals = list(chart.series[0].values) if chart.series else []
        running = 0.0
        levels: list[float] = [0.0]
        total_kw = ("总计", "合计", "期末", "total", "net", "ending")
        for idx, v in enumerate(vals):
            cat_l = chart.categories[idx].lower() if idx < len(chart.categories) else ""
            is_end_total = idx == len(vals) - 1 and abs(v - running) <= max(1e-3, abs(running) * 1e-3)
            if idx == 0 or is_end_total or any(k in cat_l for k in total_kw):
                running = float(v)
            else:
                running += float(v)
            levels.append(running)
        raw_min = min([0.0, *levels])
        raw_max = max([1.0, *levels])
    elif chart.chart_type in ("stacked_column", "stacked_bar"):
        cat_count = len(chart.categories)
        pos_sums = [0.0] * cat_count
        neg_sums = [0.0] * cat_count
        for sr in chart.series:
            for idx, v in enumerate(sr.values[:cat_count]):
                if v >= 0:
                    pos_sums[idx] += v
                else:
                    neg_sums[idx] += v
        raw_min = min([0.0, *neg_sums])
        raw_max = max([1.0, *pos_sums])
    else:
        vals = [v for sr in chart.series for v in sr.values]
        raw_min = min([0.0, *vals]) if vals else 0.0
        raw_max = max([1.0, *vals]) if vals else 1.0

    span = max(1e-6, raw_max - raw_min)
    if chart.axis_min is not None:
        ax_min = chart.axis_min
    else:
        ax_min = (raw_min - span * 0.14) if raw_min < 0 else raw_min
    if chart.axis_max is not None:
        ax_max = chart.axis_max
    else:
        ax_max = raw_max + span * 0.12
    return ax_min, ax_max


def _partition_region_slots(
    inner: BoxRect,
    objects: list[CanvasObjectSpec],
    arrange: str,
    gap: float,
) -> list[tuple[CanvasObjectSpec, BoxRect]]:
    """Allocate exact non-overlapping sub-rectangles inside a region for its assigned objects."""
    k = len(objects)
    if k == 0:
        return []
    if k == 1:
        obj = objects[0]
        if obj.kind == "callout":
            h = min(inner.h, max(120.0, inner.h * 0.65))
            return [(obj, BoxRect(inner.x, inner.cy - h / 2.0, inner.w, h))]
        return [(obj, inner)]

    if arrange == "row":
        total_w = max(40.0, inner.w - max(0, k - 1) * gap)
        w_sum = sum(max(0.1, o.weight) for o in objects)
        cursor_x = inner.x
        out: list[tuple[CanvasObjectSpec, BoxRect]] = []
        for o in objects:
            ow = total_w * (max(0.1, o.weight) / w_sum)
            out.append((o, BoxRect(cursor_x, inner.y, ow, inner.h)))
            cursor_x += ow + gap
        return out

    if arrange == "grid":
        cols = 2 if k <= 4 else math.ceil(math.sqrt(k))
        rows = math.ceil(k / cols)
        cell_w = max(40.0, (inner.w - max(0, cols - 1) * gap) / cols)
        cell_h = max(40.0, (inner.h - max(0, rows - 1) * gap) / rows)
        out = []
        for idx, o in enumerate(objects):
            r_idx, c_idx = divmod(idx, cols)
            out.append(
                (
                    o,
                    BoxRect(
                        inner.x + c_idx * (cell_w + gap),
                        inner.y + r_idx * (cell_h + gap),
                        cell_w,
                        cell_h,
                    ),
                )
            )
        return out

    # Default: vertical "stack"
    total_h = max(40.0, inner.h - max(0, k - 1) * gap)
    w_sum = sum(max(0.1, o.weight) for o in objects)
    cursor_y = inner.y
    out = []
    for o in objects:
        oh = total_h * (max(0.1, o.weight) / w_sum)
        out.append((o, BoxRect(inner.x, cursor_y, inner.w, oh)))
        cursor_y += oh + gap
    return out


def _resolve_inline_diagram(
    obj: CanvasObjectSpec,
    slot: BoxRect,
    opacity: float,
    state: dict[str, Any] | None = None,
) -> tuple[list[PlacedBox], list[PlacedEdge]]:
    """Solve an inline diagram object inside its region slot, locking coordinates across progressive frames."""
    dg = obj.diagram
    if dg is None or not dg.nodes:
        return [], []
    layout_map: dict[DiagramLayout, str] = {
        "horizontal": "horizontal_flow",
        "vertical": "vertical_flow",
        "dag": "flow_dag",
        "hub_spoke": "hub_spoke",
    }
    sub_layout = layout_map[dg.diagram_layout]
    dummy_scene = SceneSpec(
        id=obj.id,
        title="",
        layout=sub_layout,  # type: ignore[arg-type]
        nodes=dg.nodes,
        edges=dg.edges,
        frames=[
            FrameSpec(
                visible_nodes=[n.id for n in dg.nodes],
                expanded_nodes=[n.id for n in dg.nodes if n.children],
            )
        ],
    )
    solver = _LAYOUT_SOLVERS[sub_layout]
    outcome = solver(dummy_scene, slot.w, 0.0, slot.h)

    st = state or {}
    all_node_ids = {n.id for n in dg.nodes}
    vis_nodes = set(st["visible_nodes"]) if "visible_nodes" in st else all_node_ids
    exp_nodes = (
        set(st["expanded_nodes"])
        if "expanded_nodes" in st
        else {n.id for n in dg.nodes if n.children}
    )
    focus_nodes = set(st["focus_nodes"]) if "focus_nodes" in st else None
    vis_edges_spec = st.get("visible_edges", "auto")

    placed_boxes: list[PlacedBox] = []
    anchor_rects: dict[str, BoxRect] = {}
    for node in dg.nodes:
        if node.id not in vis_nodes:
            continue
        geo = outcome.geos[node.id]
        is_exp = bool(node.children) and (node.id in exp_nodes)
        base_rect = geo.expanded_rect if is_exp else geo.collapsed_rect
        shifted = BoxRect(slot.x + base_rect.x, slot.y + base_rect.y, base_rect.w, base_rect.h)
        full_id = f"{obj.id}__{node.id}"
        anchor_rects[node.id] = shifted
        n_op = opacity * (1.0 if (focus_nodes is None or node.id in focus_nodes) else 0.42)
        cap_rect = (
            BoxRect(
                slot.x + geo.caption_rect.x,
                slot.y + geo.caption_rect.y,
                geo.caption_rect.w,
                geo.caption_rect.h,
            )
            if geo.caption_rect is not None
            else None
        )
        placed_boxes.append(
            PlacedBox(
                id=full_id,
                label=node.label,
                sublabel=node.sublabel,
                badge=node.badge,
                metric=node.metric,
                rect=shifted,
                kind="group_dashed" if is_exp else "card",
                variant=node.variant,
                opacity=n_op,
                caption=node.label if (is_exp and node.caption_position != "inside") else None,
                caption_rect=cap_rect,
                font_scale=outcome.scale,
            )
        )
        if is_exp:
            for child, crect in geo.child_rects:
                placed_boxes.append(
                    PlacedBox(
                        id=f"{full_id}__{child.id}",
                        label=child.label,
                        sublabel=child.sublabel,
                        badge=child.badge,
                        metric=child.metric,
                        rect=BoxRect(slot.x + crect.x, slot.y + crect.y, crect.w, crect.h),
                        kind="subcard",
                        variant=child.variant,
                        opacity=n_op,
                        font_scale=outcome.scale,
                    )
                )

    placed_edges: list[PlacedEdge] = []
    for edge in dg.edges:
        if edge.from_id not in anchor_rects or edge.to_id not in anchor_rects:
            continue
        if isinstance(vis_edges_spec, list) and edge.id not in vis_edges_spec:
            continue
        rf = anchor_rects[edge.from_id]
        rt = anchor_rects[edge.to_id]
        e_op = opacity
        if focus_nodes is not None and (edge.from_id not in focus_nodes or edge.to_id not in focus_nodes):
            e_op *= 0.42
        lrect: BoxRect | None = None
        if edge.label:
            mx = (rf.cx + rt.cx) / 2.0
            my = (rf.cy + rt.cy) / 2.0 - 20.0
            lw = max(84.0, _text_units(edge.label) * 14.0)
            lrect = BoxRect(mx - lw / 2.0, my - 16.0, lw, 30.0)
        placed_edges.append(
            PlacedEdge(
                id=f"{obj.id}__{edge.id}",
                from_id=f"{obj.id}__{edge.from_id}",
                to_id=f"{obj.id}__{edge.to_id}",
                tail_center=(rf.cx, rf.cy),
                head_center=(rt.cx, rt.cy),
                label=edge.label,
                label_rect=lrect,
                style=edge.style,
                opacity=e_op,
            )
        )
    return placed_boxes, placed_edges


def _resolve_canvas_scene(
    scene: SceneSpec,
    canvas_w: float,
    area_top: float,
    area_bottom: float,
    *,
    title_rect: BoxRect | None,
    subtitle_rect: BoxRect | None,
    placed_ribbon: PlacedPinnedFlow | None,
    ribbon_title_rect: BoxRect | None = None,
    ribbon_subtitle_rect: BoxRect | None = None,
) -> list[ResolvedFrame]:
    """Resolve a freeform region/grid canvas scene with anchor-locked object coordinates."""
    safe_x = 80.0
    safe_w = max(200.0, canvas_w - 160.0)
    safe_y = area_top
    safe_h = max(160.0, area_bottom - area_top)

    regions = scene.regions or [RegionSpec(id="main", col=1, row=1, col_span=12, row_span=1, arrange="stack")]
    grid_cols = scene.grid.columns if scene.grid else 12
    grid_rows = (
        scene.grid.rows
        if (scene.grid and scene.grid.rows is not None)
        else max((r.row + r.row_span - 1 for r in regions), default=1)
    )
    grid_gap = scene.grid.gap if scene.grid else 28.0
    cell_w = max(20.0, (safe_w - max(0, grid_cols - 1) * grid_gap) / grid_cols)
    cell_h = max(20.0, (safe_h - max(0, grid_rows - 1) * grid_gap) / grid_rows)

    region_outer: dict[str, BoxRect] = {}
    region_inner: dict[str, BoxRect] = {}
    region_frames: list[PlacedRegionFrame] = []
    for reg in regions:
        rx = safe_x + (reg.col - 1) * (cell_w + grid_gap)
        ry = safe_y + (reg.row - 1) * (cell_h + grid_gap)
        rw = reg.col_span * cell_w + max(0, reg.col_span - 1) * grid_gap
        rh = reg.row_span * cell_h + max(0, reg.row_span - 1) * grid_gap
        outer = BoxRect(rx, ry, rw, rh)
        region_outer[reg.id] = outer

        pad = reg.padding if reg.padding > 0 else (18.0 if reg.frame or reg.title else 0.0)
        title_h = 44.0 if reg.title else 0.0
        inner = BoxRect(
            rx + pad,
            ry + pad + title_h,
            max(40.0, rw - 2 * pad),
            max(40.0, rh - 2 * pad - title_h),
        )
        region_inner[reg.id] = inner
        if reg.frame or reg.title:
            t_rect = BoxRect(rx + pad, ry + max(6.0, pad * 0.5), max(80.0, rw - 2 * pad), 36.0) if reg.title else None
            region_frames.append(PlacedRegionFrame(id=reg.id, title=reg.title, rect=outer, title_rect=t_rect))

    default_reg_id = regions[0].id
    objs_by_region: dict[str, list[CanvasObjectSpec]] = {r.id: [] for r in regions}
    for obj in scene.objects:
        target_reg = obj.region if (obj.region and obj.region in objs_by_region) else default_reg_id
        objs_by_region[target_reg].append(obj)

    obj_rects: dict[str, BoxRect] = {}
    for reg in regions:
        slots = _partition_region_slots(
            region_inner[reg.id],
            objs_by_region[reg.id],
            reg.arrange,
            reg.gap,
        )
        for obj, rect in slots:
            obj_rects[obj.id] = rect

    chart_bounds: dict[str, tuple[float | None, float | None]] = {}
    for obj in scene.objects:
        if obj.kind == "chart" and obj.chart is not None:
            chart_bounds[obj.id] = _compute_chart_axis_bounds(obj.chart)

    frames_to_render = scene.frames or [
        FrameSpec(visible_objects=[o.id for o in scene.objects], notes=scene.intro_note)
    ]

    resolved_frames: list[ResolvedFrame] = []
    for f_idx, frame in enumerate(frames_to_render):
        vis_ids = (
            set(frame.visible_objects)
            if frame.visible_objects is not None
            else {o.id for o in scene.objects}
        )
        focus_ids = set(frame.focus_objects) if frame.focus_objects is not None else None

        placed_boxes: list[PlacedBox] = []
        placed_edges: list[PlacedEdge] = []
        placed_charts: list[PlacedChart] = []
        placed_tables: list[PlacedTable] = []
        placed_shapes: list[PlacedShape] = []
        placed_textboxes: list[PlacedTextbox] = []
        connector_rects: dict[str, BoxRect] = {}
        active_regions: set[str] = set()

        for obj in scene.objects:
            if obj.id not in vis_ids:
                continue
            target_reg = obj.region if (obj.region and obj.region in objs_by_region) else default_reg_id
            active_regions.add(target_reg)
            rect = obj_rects[obj.id]
            opacity = 1.0 if (focus_ids is None or obj.id in focus_ids) else 0.42
            state = frame.object_states.get(obj.id, {})
            connector_rects[obj.id] = rect

            if obj.kind in ("card", "callout"):
                placed_boxes.append(
                    PlacedBox(
                        id=obj.id,
                        label=obj.label or obj.id,
                        sublabel=obj.sublabel,
                        badge=obj.badge,
                        metric=obj.metric,
                        rect=rect,
                        kind="callout" if obj.kind == "callout" else "card",
                        variant=obj.variant if obj.kind == "card" else ("accent" if obj.variant == "primary" else obj.variant),
                        opacity=opacity,
                        fill_hex=obj.fill_hex,
                        border_hex=obj.border_hex,
                        color_hex=obj.color_hex,
                    )
                )
            elif obj.kind == "textbox":
                placed_textboxes.append(
                    PlacedTextbox(
                        id=obj.id,
                        text=obj.text or "",
                        rect=rect,
                        font_size=obj.font_size or 28.0,
                        bold=bool(obj.bold) if obj.bold is not None else False,
                        align=obj.align,
                        color_hex=obj.color_hex,
                        fill_hex=obj.fill_hex,
                        opacity=opacity,
                    )
                )
            elif obj.kind == "shape":
                placed_shapes.append(
                    PlacedShape(
                        id=obj.id,
                        shape_type=obj.shape_type,
                        svg_path=obj.svg_path,
                        label=obj.label,
                        rect=rect,
                        fill_hex=obj.fill_hex,
                        border_hex=obj.border_hex,
                        color_hex=obj.color_hex,
                        dashed=obj.dashed,
                        variant=obj.variant,
                        opacity=opacity,
                    )
                )
            elif obj.kind == "chart" and obj.chart is not None:
                ch = obj.chart
                ax_min, ax_max = chart_bounds[obj.id]
                sr_limit = max(1, int(state.get("series_count", len(ch.series))))
                cat_limit = max(1, int(state.get("category_count", len(ch.categories))))
                placed_series = [
                    PlacedChartSeries(
                        name=sr.name,
                        values=[
                            (v if (s_idx < sr_limit and c_idx < cat_limit) else None)
                            for c_idx, v in enumerate(sr.values)
                        ],
                        color_hex=sr.color_hex,
                        active=(s_idx < sr_limit),
                        full_values=list(sr.values),
                    )
                    for s_idx, sr in enumerate(ch.series)
                ]
                use_vector = (
                    (ch.chart_type == "waterfall")
                    or (ch.render_mode == "vector")
                    or (ch.render_mode == "auto" and ch.reveal != "whole")
                )
                show_leg = (
                    ch.show_legend
                    if ch.show_legend is not None
                    else (ch.chart_type != "waterfall" and (len(ch.series) > 1 or ch.chart_type in ("pie", "donut")))
                )
                placed_charts.append(
                    PlacedChart(
                        id=obj.id,
                        chart_type=ch.chart_type,
                        title=ch.title,
                        rect=rect,
                        categories=list(ch.categories),
                        series=placed_series,
                        unit=ch.unit,
                        show_legend=show_leg,
                        show_value_labels=ch.show_value_labels,
                        axis_min=ax_min,
                        axis_max=ax_max,
                        opacity=opacity,
                        render_mode=ch.render_mode,
                        use_vector=use_vector,
                    )
                )
            elif obj.kind == "table" and obj.table is not None:
                tb = obj.table
                vis_rows = min(len(tb.rows), max(1, state.get("row_count", len(tb.rows))))
                vis_cols = min(len(tb.headers), max(1, state.get("col_count", len(tb.headers))))
                placed_tables.append(
                    PlacedTable(
                        id=obj.id,
                        title=tb.title,
                        rect=rect,
                        headers=list(tb.headers),
                        rows=[list(r) for r in tb.rows],
                        visible_rows=vis_rows,
                        visible_cols=vis_cols,
                        highlight_cols=tuple(tb.highlight_cols),
                        highlight_rows=tuple(tb.highlight_rows),
                        opacity=opacity,
                    )
                )
            elif obj.kind == "diagram":
                d_boxes, d_edges = _resolve_inline_diagram(obj, rect, opacity, state)
                placed_boxes.extend(d_boxes)
                placed_edges.extend(d_edges)

        for conn in scene.connectors:
            if conn.from_id not in connector_rects or conn.to_id not in connector_rects:
                continue
            rf = connector_rects[conn.from_id]
            rt = connector_rects[conn.to_id]
            c_op = (
                1.0
                if (focus_ids is None or (conn.from_id in focus_ids and conn.to_id in focus_ids))
                else 0.42
            )
            lrect: BoxRect | None = None
            if conn.label:
                mx = (rf.cx + rt.cx) / 2.0
                my = (rf.cy + rt.cy) / 2.0 - 20.0
                lw = max(84.0, _text_units(conn.label) * 14.0)
                lrect = BoxRect(mx - lw / 2.0, my - 16.0, lw, 30.0)
            placed_edges.append(
                PlacedEdge(
                    id=conn.id,
                    from_id=conn.from_id,
                    to_id=conn.to_id,
                    tail_center=(rf.cx, rf.cy),
                    head_center=(rt.cx, rt.cy),
                    label=conn.label,
                    label_rect=lrect,
                    style=conn.style,
                    opacity=c_op,
                )
            )

        f_uses_ribbon = bool(
            placed_ribbon is not None
            and (frame.show_pinned_flow if frame.show_pinned_flow is not None else scene.show_pinned_flow)
        )
        f_ribbon = placed_ribbon if f_uses_ribbon else None
        f_title_rect = (ribbon_title_rect if ribbon_title_rect is not None else title_rect) if f_uses_ribbon else title_rect
        f_sub_base = (ribbon_subtitle_rect if ribbon_subtitle_rect is not None else subtitle_rect) if f_uses_ribbon else subtitle_rect

        resolved_frames.append(
            ResolvedFrame(
                scene_id=scene.id,
                frame_index=f_idx,
                title=scene.title,
                subtitle=frame.subtitle if frame.subtitle is not None else scene.subtitle,
                title_rect=f_title_rect,
                subtitle_rect=f_sub_base if (frame.subtitle or scene.subtitle) else None,
                pinned_flow=f_ribbon,
                boxes=placed_boxes,
                edges=placed_edges,
                region_frames=[rf for rf in region_frames if rf.id in active_regions],
                charts=placed_charts,
                tables=placed_tables,
                shapes=placed_shapes,
                textboxes=placed_textboxes,
                palette=scene.palette,
                notes=frame.notes,
                depth=1 if f_idx == 0 else 2,
            )
        )

    return resolved_frames


_LAYOUT_SOLVERS = {
    "horizontal_flow": _solve_horizontal_flow,
    "vertical_flow": _solve_vertical_flow,
    "comparison": _solve_comparison,
    "hub_spoke": _solve_hub_spoke,
    "flow_dag": _solve_flow_dag,
    "architecture_evolution": _solve_architecture_evolution,
    "sequence_timeline": _solve_sequence_timeline,
    "metrics_cards": _solve_metrics_cards,
}


def resolve_scene(
    scene: SceneSpec,
    canvas_w: int = SLIDE_WIDTH,
    canvas_h: int = SLIDE_HEIGHT,
    *,
    pinned_flow: PinnedFlowSpec | None = None,
) -> list[ResolvedFrame]:
    """Compute anchor-preserved geometry for every progressive frame in a scene."""
    effective_pf = scene.pinned_flow if scene.pinned_flow is not None else pinned_flow

    def _frame_uses_ribbon(fr: FrameSpec) -> bool:
        if not effective_pf:
            return False
        return fr.show_pinned_flow if fr.show_pinned_flow is not None else scene.show_pinned_flow

    any_ribbon = (
        any(_frame_uses_ribbon(f) for f in scene.frames)
        if scene.frames
        else bool(effective_pf and scene.show_pinned_flow)
    )
    is_macro_only = (
        any_ribbon
        and not scene.nodes
        and not scene.objects
        and scene.proportion_bar is None
        and scene.matrix is None
    )

    has_any_subtitle = bool(scene.subtitle or any(f.subtitle for f in scene.frames))
    title_rect = BoxRect(TITLE_MARGIN_X, 86.0, canvas_w - 2 * TITLE_MARGIN_X, 112.0)
    subtitle_rect = BoxRect(SUBTITLE_MARGIN_X, 198.0, canvas_w - 2 * SUBTITLE_MARGIN_X, 50.0) if has_any_subtitle else None

    if is_macro_only:
        ribbon_title_rect = BoxRect(TITLE_MARGIN_X, 72.0, canvas_w - 2 * TITLE_MARGIN_X, 92.0)
        ribbon_subtitle_rect = BoxRect(SUBTITLE_MARGIN_X, 168.0, canvas_w - 2 * SUBTITLE_MARGIN_X, 44.0) if has_any_subtitle else None
        docked_cy = 160.0
    else:
        # Title & optional subtitle sit ABOVE the docked ribbon so the slide headline stays the top anchor.
        ribbon_title_rect = BoxRect(TITLE_MARGIN_X, 44.0, canvas_w - 2 * TITLE_MARGIN_X, 56.0)
        ribbon_subtitle_rect = BoxRect(SUBTITLE_MARGIN_X, 102.0, canvas_w - 2 * SUBTITLE_MARGIN_X, 38.0) if has_any_subtitle else None
        has_groups = bool(effective_pf and effective_pf.groups)
        docked_cy = (198.0 if has_any_subtitle else 156.0) + (42.0 if has_groups else 0.0)

    placed_ribbon = (
        _resolve_pinned_flow(
            effective_pf,
            scene.active_flow_node,
            float(canvas_w),
            float(canvas_h),
            centered=is_macro_only,
            docked_cy=docked_cy,
        )
        if any_ribbon and effective_pf is not None
        else None
    )

    if is_macro_only:
        area_top = 224.0 if has_any_subtitle else 184.0
    elif any_ribbon and placed_ribbon is not None:
        pf_bottom = max(
            [n.rect.y + n.rect.h for n in placed_ribbon.nodes]
            + [g.rect.y + g.rect.h for g in placed_ribbon.groups],
            default=docked_cy + 36.0,
        )
        area_top = pf_bottom + PINNED_FLOW_GAP_BELOW
    else:
        area_top = 262.0 if has_any_subtitle else 225.0

    area_bottom = float(canvas_h) - SAFE_AREA_BOTTOM_MARGIN

    def _frame_header(fr: FrameSpec) -> tuple[PlacedPinnedFlow | None, BoxRect | None, BoxRect | None]:
        if _frame_uses_ribbon(fr):
            sub_r = ribbon_subtitle_rect if (fr.subtitle or scene.subtitle) else None
            return placed_ribbon, ribbon_title_rect, sub_r
        sub_r = subtitle_rect if (fr.subtitle or scene.subtitle) else None
        return None, title_rect, sub_r

    if scene.layout == "canvas":
        return _resolve_canvas_scene(
            scene,
            float(canvas_w),
            area_top,
            area_bottom,
            title_rect=title_rect,
            subtitle_rect=subtitle_rect,
            placed_ribbon=placed_ribbon,
            ribbon_title_rect=ribbon_title_rect,
            ribbon_subtitle_rect=ribbon_subtitle_rect,
        )

    # Dedicated data visualization layouts
    if scene.layout == "proportion_bar" and scene.proportion_bar is not None:
        resolved: list[ResolvedFrame] = []
        for f_idx, frame in enumerate(scene.frames):
            vis_items = set(frame.visible_items) if frame.visible_items is not None else None
            pb_placed = _resolve_proportion_bar(
                scene.proportion_bar, vis_items, float(canvas_w), area_top, area_bottom
            )
            f_ribbon, f_title_r, f_sub_r = _frame_header(frame)
            resolved.append(
                ResolvedFrame(
                    scene_id=scene.id,
                    frame_index=f_idx,
                    title=scene.title,
                    subtitle=frame.subtitle if frame.subtitle is not None else scene.subtitle,
                    title_rect=f_title_r,
                    subtitle_rect=f_sub_r,
                    pinned_flow=f_ribbon,
                    proportion_bar=pb_placed,
                    notes=frame.notes,
                    depth=1 if f_idx == 0 else 2,
                )
            )
        return resolved

    if scene.layout == "comparison_matrix" and scene.matrix is not None:
        resolved = []
        for f_idx, frame in enumerate(scene.frames):
            vis_cols = set(frame.visible_columns) if frame.visible_columns is not None else None
            mx_placed = _resolve_comparison_matrix(
                scene.matrix,
                vis_cols,
                frame.show_annotations,
                float(canvas_w),
                area_top,
                area_bottom,
            )
            f_ribbon, f_title_r, f_sub_r = _frame_header(frame)
            resolved.append(
                ResolvedFrame(
                    scene_id=scene.id,
                    frame_index=f_idx,
                    title=scene.title,
                    subtitle=frame.subtitle if frame.subtitle is not None else scene.subtitle,
                    title_rect=f_title_r,
                    subtitle_rect=f_sub_r,
                    pinned_flow=f_ribbon,
                    comparison_matrix=mx_placed,
                    notes=frame.notes,
                    depth=1 if f_idx == 0 else 2,
                )
            )
        return resolved

    solver = _LAYOUT_SOLVERS[scene.layout]
    outcome = solver(scene, float(canvas_w), area_top, area_bottom)
    node_geos = outcome.geos
    node_order = {n.id: i for i, n in enumerate(scene.nodes)}

    resolved_frames: list[ResolvedFrame] = []
    for f_idx, frame in enumerate(scene.frames):
        visible_set = set(frame.visible_nodes)
        expanded_set = set(frame.expanded_nodes)
        focus_set = set(frame.focus_nodes) if frame.focus_nodes is not None else None

        placed_boxes: list[PlacedBox] = []
        active_anchor_rects: dict[str, BoxRect] = {}

        for node in scene.nodes:
            if node.id not in visible_set:
                continue
            geo = node_geos[node.id]
            opacity = 1.0 if (focus_set is None or node.id in focus_set) else 0.42
            is_expanded = (node.id in expanded_set or node.kind == "group_dashed") and bool(node.children)

            if is_expanded:
                active_anchor_rects[node.id] = geo.expanded_rect
                placed_boxes.append(
                    PlacedBox(
                        id=node.id,
                        label=node.label,
                        sublabel=node.sublabel,
                        badge=node.badge,
                        metric=node.metric,
                        rect=geo.expanded_rect,
                        kind="group_dashed",
                        variant=node.variant,
                        opacity=opacity,
                        caption=node.label if node.caption_position != "inside" else None,
                        caption_rect=geo.caption_rect,
                    )
                )
                for child, crect in geo.child_rects:
                    placed_boxes.append(
                        PlacedBox(
                            id=f"{node.id}__{child.id}",
                            label=child.label,
                            sublabel=child.sublabel,
                            badge=child.badge,
                            metric=child.metric,
                            rect=crect,
                            kind="subcard",
                            variant=child.variant,
                            opacity=opacity,
                        )
                    )
            else:
                active_anchor_rects[node.id] = geo.collapsed_rect
                placed_boxes.append(
                    PlacedBox(
                        id=node.id,
                        label=node.label,
                        sublabel=node.sublabel,
                        badge=node.badge,
                        metric=node.metric,
                        rect=geo.collapsed_rect,
                        kind="card",
                        variant=node.variant,
                        opacity=opacity,
                    )
                )

        if frame.visible_edges == "auto":
            edge_ids = [
                e.id
                for e in scene.edges
                if e.from_id in active_anchor_rects and e.to_id in active_anchor_rects
            ]
        else:
            edge_ids = list(frame.visible_edges)

        edge_id_set = set(edge_ids)
        placed_edges: list[PlacedEdge] = []
        for edge in scene.edges:
            if edge.id not in edge_id_set:
                continue
            if edge.from_id not in active_anchor_rects or edge.to_id not in active_anchor_rects:
                continue
            r_from = active_anchor_rects[edge.from_id]
            r_to = active_anchor_rects[edge.to_id]
            e_opacity = (
                1.0
                if (focus_set is None or (edge.from_id in focus_set and edge.to_id in focus_set))
                else 0.42
            )

            curve_control: tuple[float, float] | None = None
            from_i = node_order.get(edge.from_id, 0)
            to_i = node_order.get(edge.to_id, 0)
            if scene.layout == "sequence_timeline" and edge.from_id != edge.to_id:
                span = to_i - from_i
                mx = (r_from.cx + r_to.cx) / 2.0
                if span > 1:
                    arc_y = min(r_from.y, r_to.y) - (78.0 + 36.0 * (span - 2)) * max(0.75, outcome.scale)
                    curve_control = (mx, arc_y)
                elif span < 0:
                    arc_y = max(r_from.y + r_from.h, r_to.y + r_to.h) + (82.0 + 36.0 * (abs(span) - 1)) * max(0.75, outcome.scale)
                    curve_control = (mx, arc_y)

            label_rect: BoxRect | None = None
            if edge.label:
                if curve_control is not None:
                    mx = curve_control[0]
                    is_upper = curve_control[1] < r_from.cy
                    my = curve_control[1] + (-20.0 if is_upper else 22.0) * max(0.8, outcome.scale)
                else:
                    if r_to.x > r_from.x + r_from.w:
                        mx = (r_from.x + r_from.w + r_to.x) / 2.0
                    elif r_from.x > r_to.x + r_to.w:
                        mx = (r_to.x + r_to.w + r_from.x) / 2.0
                    else:
                        mx = (r_from.cx + r_to.cx) / 2.0
                    my = (r_from.cy + r_to.cy) / 2.0 - 24.0 * max(0.8, outcome.scale)
                lw = max(96.0, _text_units(edge.label) * 15.0) * max(0.8, outcome.scale)
                label_rect = BoxRect(mx - lw / 2.0, my - 18.0, lw, 34.0)

            placed_edges.append(
                PlacedEdge(
                    id=edge.id,
                    from_id=edge.from_id,
                    to_id=edge.to_id,
                    tail_center=(r_from.cx, r_from.cy),
                    head_center=(r_to.cx, r_to.cy),
                    curve_control=curve_control,
                    label=edge.label,
                    label_rect=label_rect,
                    style=edge.style,
                    opacity=e_opacity,
                )
            )

        frame_dividers = outcome.dividers if len(active_anchor_rects) >= 2 else []
        f_ribbon, f_title_r, f_sub_r = _frame_header(frame)

        resolved_frames.append(
            ResolvedFrame(
                scene_id=scene.id,
                frame_index=f_idx,
                title=scene.title,
                subtitle=frame.subtitle if frame.subtitle is not None else scene.subtitle,
                title_rect=f_title_r,
                subtitle_rect=f_sub_r,
                scale=outcome.scale,
                pinned_flow=f_ribbon,
                boxes=placed_boxes,
                edges=placed_edges,
                dividers=frame_dividers,
                notes=frame.notes,
                depth=1 if f_idx == 0 else 2,
            )
        )

    return resolved_frames
