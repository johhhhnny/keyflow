"""Freeform canvas layout solver and inline diagram/chart/table slot partitioning."""

from __future__ import annotations

import math
from typing import Any

from keyflow.layouts.flow import (
    _solve_flow_dag,
    _solve_horizontal_flow,
    _solve_hub_spoke,
    _solve_vertical_flow,
)
from keyflow.layouts.registry import get_layout_solver
from keyflow.layouts.types import (
    BoxRect,
    PlacedBox,
    PlacedChart,
    PlacedChartSeries,
    PlacedEdge,
    PlacedPinnedFlow,
    PlacedRegionFrame,
    PlacedShape,
    PlacedTable,
    PlacedTextbox,
    ResolvedFrame,
    _text_units,
)
from keyflow.schema import (
    CanvasObjectSpec,
    ChartSpec,
    DiagramLayout,
    FrameSpec,
    NodeSpec,
    RegionSpec,
    SceneSpec,
    TableSpec,
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
    solver = get_layout_solver(sub_layout)
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
                surface=node.surface,
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
                        surface=child.surface,
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
                        surface=obj.surface,
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

