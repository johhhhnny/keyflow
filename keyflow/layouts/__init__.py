"""Modular layout registry and scene geometry solvers for KeyFlow."""

from __future__ import annotations

from keyflow.layouts import flow as _flow  # noqa: F401 (registers built-in flow solvers)
from keyflow.layouts.canvas import (
    _compute_chart_axis_bounds,
    _partition_region_slots,
    _resolve_canvas_scene,
    _resolve_inline_diagram,
)
from keyflow.layouts.flow import (
    _solve_architecture_evolution,
    _solve_comparison,
    _solve_flow_dag,
    _solve_horizontal_flow,
    _solve_hub_spoke,
    _solve_metrics_cards,
    _solve_sequence_timeline,
    _solve_vertical_flow,
)
from keyflow.layouts.registry import LAYOUT_REGISTRY, get_layout_solver, register_layout
from keyflow.layouts.special import _resolve_comparison_matrix, _resolve_proportion_bar
from keyflow.layouts.types import (
    BoxRect,
    PlacedBox,
    PlacedChart,
    PlacedChartSeries,
    PlacedComparisonMatrix,
    PlacedDivider,
    PlacedEdge,
    PlacedMatrixCell,
    PlacedMatrixColumn,
    PlacedPinnedFlow,
    PlacedProportionBar,
    PlacedProportionItem,
    PlacedRegionFrame,
    PlacedRibbonEdge,
    PlacedRibbonGroup,
    PlacedRibbonNode,
    PlacedShape,
    PlacedTable,
    PlacedTextbox,
    ResolvedFrame,
    _caption_rect_for,
    _estimate_card_size,
    _group_dimensions,
    _LayoutOutcome,
    _node_always_expanded,
    _NodeGeometry,
    _resolve_pinned_flow,
    _scale_children,
    _text_units,
)
from keyflow.schema import FrameSpec, PinnedFlowSpec, SceneSpec
from keyflow.tokens import (
    PINNED_FLOW_GAP_BELOW,
    SAFE_AREA_BOTTOM_MARGIN,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    SUBTITLE_MARGIN_X,
    TITLE_MARGIN_X,
)

_LAYOUT_SOLVERS = LAYOUT_REGISTRY


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
        ribbon_title_rect = BoxRect(TITLE_MARGIN_X, 36.0, canvas_w - 2 * TITLE_MARGIN_X, 74.0)
        ribbon_subtitle_rect = BoxRect(SUBTITLE_MARGIN_X, 112.0, canvas_w - 2 * SUBTITLE_MARGIN_X, 42.0) if has_any_subtitle else None
        has_groups = bool(effective_pf and effective_pf.groups)
        docked_cy = (206.0 if has_any_subtitle else 164.0) + (42.0 if has_groups else 0.0)

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

    solver = get_layout_solver(scene.layout)
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
                        surface=node.surface,
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
                            surface=child.surface,
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
                        surface=node.surface,
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


__all__ = [
    "LAYOUT_REGISTRY",
    "register_layout",
    "get_layout_solver",
    "BoxRect",
    "PlacedBox",
    "PlacedEdge",
    "PlacedDivider",
    "PlacedRibbonNode",
    "PlacedRibbonGroup",
    "PlacedRibbonEdge",
    "PlacedPinnedFlow",
    "PlacedProportionItem",
    "PlacedProportionBar",
    "PlacedMatrixCell",
    "PlacedMatrixColumn",
    "PlacedComparisonMatrix",
    "PlacedChartSeries",
    "PlacedChart",
    "PlacedTable",
    "PlacedTextbox",
    "PlacedShape",
    "PlacedRegionFrame",
    "ResolvedFrame",
    "resolve_scene",
]
