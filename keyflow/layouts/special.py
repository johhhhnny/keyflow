"""Dedicated data-visualization layout solvers (proportion_bar, comparison_matrix)."""

from __future__ import annotations

from keyflow.layouts.types import (
    BoxRect,
    PlacedComparisonMatrix,
    PlacedMatrixCell,
    PlacedMatrixColumn,
    PlacedProportionBar,
    PlacedProportionItem,
    _text_units,
)
from keyflow.schema import ComparisonMatrixSpec, ProportionBarSpec


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


