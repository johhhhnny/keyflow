"""Preset node-flow and diagram layout solvers registered into LAYOUT_REGISTRY."""

from __future__ import annotations

import math

from keyflow.layouts.registry import register_layout
from keyflow.layouts.types import (
    BoxRect,
    PlacedDivider,
    _LayoutOutcome,
    _NodeGeometry,
    _caption_rect_for,
    _estimate_card_size,
    _group_dimensions,
    _node_always_expanded,
    _scale_children,
    _text_units,
)
from keyflow.schema import ChildNodeSpec, NodeSpec, SceneSpec, compute_dag_layers


@register_layout("horizontal_flow")
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


@register_layout("vertical_flow")
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


@register_layout("comparison")
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


@register_layout("architecture_evolution")
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


@register_layout("sequence_timeline")
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


@register_layout("metrics_cards")
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


@register_layout("hub_spoke")
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


@register_layout("flow_dag")
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


