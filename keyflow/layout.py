"""Backward-compatible facade re-exporting keyflow.layouts."""

from __future__ import annotations

from keyflow.layouts import *  # noqa: F401, F403
from keyflow.layouts import (  # noqa: F401
    _LAYOUT_SOLVERS,
    _caption_rect_for,
    _compute_chart_axis_bounds,
    _estimate_card_size,
    _group_dimensions,
    _LayoutOutcome,
    _node_always_expanded,
    _NodeGeometry,
    _partition_region_slots,
    _resolve_canvas_scene,
    _resolve_comparison_matrix,
    _resolve_inline_diagram,
    _resolve_pinned_flow,
    _resolve_proportion_bar,
    _scale_children,
    _solve_architecture_evolution,
    _solve_comparison,
    _solve_flow_dag,
    _solve_horizontal_flow,
    _solve_hub_spoke,
    _solve_metrics_cards,
    _solve_sequence_timeline,
    _solve_vertical_flow,
    _text_units,
)
