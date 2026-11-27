"""Chart renderers (native Keynote charts + progressive/waterfall vector charts)."""

from __future__ import annotations

import math
from typing import Any

from creator_studio_doc_format.core import (
    RGBA,
    AlignmentType,
    AreaChart,
    BarChart,
    BezierPath,
    BodyStrokeProperties,
    CanvasObject,
    CharacterProperties,
    Chart,
    ChartCategoryAxis,
    ChartColor,
    ChartData,
    ChartDataRow,
    ChartDataSource,
    ChartDataValue,
    ChartLegend,
    ChartSeries,
    ChartValueAxis,
    Color,
    ColumnChart,
    ColumnHeader,
    Constituent,
    DonutChart,
    Fill,
    Geometry,
    Label,
    LayoutProperties,
    Line,
    LineChart,
    LineEnd,
    OverallProperties,
    Paragraph,
    ParagraphProperties,
    Pattern,
    PieChart,
    PlotDirection,
    Position,
    Rect,
    Row,
    ScatterChart,
    SeriesValueLabelPosition,
    Shape,
    Size,
    SlideObject,
    StackedBarChart,
    StackedColumnChart,
    Stroke,
    Text,
    TextRun,
    VerticalAlignmentType,
    VisualProperties,
)
from creator_studio_doc_format.core import Path as ShapePath

from keyflow.layouts.types import BoxRect, PlacedChart, _text_units
from keyflow.objects.helpers import (
    _UNIT_SPACE,
    _make_open_line_shape,
    _make_solid_card,
    _make_textbox,
    _readable_text_rgb,
    _rgba,
    _rgba_int,
    _rounded_rect_path,
)
from keyflow.objects.registry import register_object_renderer
from keyflow.themes import ThemePreset, contrast_ratio, hex_to_rgb_float
from keyflow.tokens import CHART_Y_LABEL_MAX_W_PT, CHART_Y_LABEL_MIN_W_PT


def _ellipse_unit_path() -> str:
    return "M 0.5,0 A 0.5,0.5 0 1 1 0.4999,0 Z"


_CHART_MODEL_MAP: dict[str, tuple[str, Any]] = {
    "column": ("column", ColumnChart),
    "bar": ("bar", BarChart),
    "pie": ("pie", PieChart),
    "donut": ("donut", DonutChart),
    "line": ("line", LineChart),
    "area": ("area", AreaChart),
    "stacked_column": ("stacked_column", StackedColumnChart),
    "stacked_bar": ("stacked_bar", StackedBarChart),
    "scatter": ("scatter", ScatterChart),
}


def _format_chart_num(val: float) -> str:
    if abs(val - round(val)) < 1e-4:
        return str(int(round(val)))
    if abs(val) >= 100:
        return f"{val:.1f}".rstrip("0").rstrip(".")
    return f"{val:.2f}".rstrip("0").rstrip(".")


def _make_bezier_shape(
    ident: str,
    rect: BoxRect,
    bezier_d: str,
    *,
    fill_rgba: RGBA | None = None,
    stroke: Stroke | None = None,
    opacity: float = 1.0,
) -> SlideObject:
    sh = Shape(
        identifier=ident,
        geometry=Geometry(
            position=Position(x=rect.x, y=rect.y),
            size=Size(width=max(2.0, rect.w), height=max(2.0, rect.h)),
        ),
        path=ShapePath(bezier=BezierPath(path=bezier_d, space=_UNIT_SPACE)),
        fill=Fill(color=Color(rgba=fill_rgba)) if fill_rgba is not None else None,
        stroke=stroke if stroke is not None else Stroke(empty=True),
        opacity=opacity,
    )
    return SlideObject(object=CanvasObject(shape=sh))


def _make_chart_header_and_legend(
    slide_prefix: str,
    chart: PlacedChart,
    theme: ThemePreset,
) -> tuple[list[SlideObject], float]:
    """Emit shared chart title Textbox and KeyFlow legend swatches/labels; return header height."""
    objs: list[SlideObject] = []
    top_offset = 0.0
    is_bar_like = chart.chart_type in ("column", "bar", "stacked_column", "stacked_bar", "waterfall")
    show_title = chart.show_title if chart.show_title is not None else (not is_bar_like)
    if chart.title and show_title:
        title_h = 48.0
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{chart.id}_title",
                BoxRect(chart.rect.x, chart.rect.y, chart.rect.w, title_h),
                chart.title,
                font_name=theme.font_title,
                font_size=30.0,
                color=_rgba(theme.title_rgb),
                bold=True,
                opacity=chart.opacity,
            )
        )
        top_offset = title_h + 6.0

    legend_h = 34.0 if chart.show_legend else 0.0
    palette = theme.segment_palette
    if chart.show_legend:
        legend_items: list[tuple[str, tuple[float, float, float], float]] = []
        if chart.chart_type in ("pie", "donut"):
            for i, cat in enumerate(chart.categories):
                cat_vis = any(
                    i < len(sr.values) and sr.values[i] is not None
                    for sr in chart.series
                )
                legend_items.append((cat, palette[i % len(palette)], 1.0 if cat_vis else 0.28))
        else:
            for s_idx, sr in enumerate(chart.series):
                s_rgb = hex_to_rgb_float(sr.color_hex) if sr.color_hex else palette[s_idx % len(palette)]
                legend_items.append((sr.name, s_rgb, 1.0 if sr.active else 0.28))

        swatch_sz = 14.0
        item_gap = 22.0
        item_widths = [swatch_sz + 8.0 + max(42.0, _text_units(lbl) * 10.5) for lbl, _, _ in legend_items]
        total_leg_w = sum(item_widths) + max(0, len(legend_items) - 1) * item_gap
        lx = chart.rect.x + max(12.0, (chart.rect.w - total_leg_w) / 2.0)
        ly = chart.rect.y + top_offset
        for l_idx, ((lbl, rgb, item_op), iw) in enumerate(zip(legend_items, item_widths)):
            eff_op = chart.opacity * item_op
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_{chart.id}_leg_sw_{l_idx}",
                    BoxRect(lx, ly + 8.0, swatch_sz, swatch_sz),
                    fill_rgb=_rgba(rgb),
                    stroke=Stroke(empty=True),
                    corner_px=3.0,
                    opacity=eff_op,
                )
            )
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_{chart.id}_leg_tx_{l_idx}",
                    BoxRect(lx + swatch_sz + 6.0, ly, iw - swatch_sz - 6.0, 30.0),
                    lbl,
                    font_name=theme.font_body,
                    font_size=16.0,
                    color=_rgba(theme.text_rgb),
                    bold=False,
                    opacity=eff_op,
                    alignment=AlignmentType.LEFT,
                )
            )
            lx += iw + item_gap

    return objs, top_offset + legend_h


def _make_vector_chart_objects(
    slide_prefix: str,
    chart: PlacedChart,
    theme: ThemePreset,
) -> list[SlideObject]:
    """Compile a PlacedChart purely from vector Shape + Textbox primitives for smooth Keynote Magic Move."""
    objs, header_h = _make_chart_header_and_legend(slide_prefix, chart, theme)
    palette = theme.segment_palette
    series_colors = [
        hex_to_rgb_float(sr.color_hex) if sr.color_hex else palette[s_idx % len(palette)]
        for s_idx, sr in enumerate(chart.series)
    ]

    if chart.chart_type in ("pie", "donut"):
        cx = chart.rect.x + chart.rect.w / 2.0
        plot_top = chart.rect.y + header_h + 10.0
        plot_h = max(100.0, (chart.rect.y + chart.rect.h) - plot_top - 10.0)
        r_outer = max(40.0, min(chart.rect.w, plot_h) * 0.42)
        r_inner = r_outer * 0.54 if chart.chart_type == "donut" else 0.0
        cy = plot_top + plot_h / 2.0
        sq = BoxRect(cx - r_outer, cy - r_outer, 2.0 * r_outer, 2.0 * r_outer)
        sr0 = chart.series[0] if chart.series else None
        if sr0 is None:
            return objs
        raw_full = sr0.full_values if sr0.full_values else [float(v or 0.0) for v in sr0.values]
        total = sum(max(0.0, float(v)) for v in raw_full)
        if total <= 1e-9:
            return objs
        ri_norm = r_inner / r_outer if r_outer > 0 else 0.0
        angle = -math.pi / 2.0
        for c_idx, cat in enumerate(chart.categories):
            fv = max(0.0, float(raw_full[c_idx])) if c_idx < len(raw_full) else 0.0
            frac = fv / total
            sweep = frac * 2.0 * math.pi
            a_end = angle + sweep
            vis_val = sr0.values[c_idx] if c_idx < len(sr0.values) else None
            if vis_val is not None and frac > 0.001:
                c_rgb = palette[c_idx % len(palette)]
                if frac >= 0.999:
                    d_path = _ellipse_unit_path()
                    if r_inner > 0:
                        # Donut ring using two arcs
                        d_path = (
                            f"M 0.5,0 A 0.5,0.5 0 1 1 0.4999,0 Z "
                            f"M 0.5,{0.5 - 0.5 * ri_norm:.4f} "
                            f"A {0.5 * ri_norm:.4f},{0.5 * ri_norm:.4f} 0 1 0 0.5001,{0.5 - 0.5 * ri_norm:.4f} Z"
                        )
                else:
                    ox0 = 0.5 + 0.5 * math.cos(angle)
                    oy0 = 0.5 + 0.5 * math.sin(angle)
                    ox1 = 0.5 + 0.5 * math.cos(a_end)
                    oy1 = 0.5 + 0.5 * math.sin(a_end)
                    large = 1 if sweep > math.pi else 0
                    if r_inner <= 0.0:
                        d_path = f"M 0.5,0.5 L {ox0:.4f},{oy0:.4f} A 0.5,0.5 0 {large} 1 {ox1:.4f},{oy1:.4f} Z"
                    else:
                        ir_u = 0.5 * ri_norm
                        ix0 = 0.5 + ir_u * math.cos(angle)
                        iy0 = 0.5 + ir_u * math.sin(angle)
                        ix1 = 0.5 + ir_u * math.cos(a_end)
                        iy1 = 0.5 + ir_u * math.sin(a_end)
                        d_path = (
                            f"M {ox0:.4f},{oy0:.4f} "
                            f"A 0.5,0.5 0 {large} 1 {ox1:.4f},{oy1:.4f} "
                            f"L {ix1:.4f},{iy1:.4f} "
                            f"A {ir_u:.4f},{ir_u:.4f} 0 {large} 0 {ix0:.4f},{iy0:.4f} Z"
                        )
                objs.append(
                    _make_bezier_shape(
                        f"{slide_prefix}_{chart.id}_wedge_{c_idx}",
                        sq,
                        d_path,
                        fill_rgba=_rgba(c_rgb),
                        stroke=Stroke(line=Line(color=Color(rgba=_rgba_int(theme.bg_rgb)), width=2.0, pattern=Pattern.SOLID)),
                        opacity=chart.opacity,
                    )
                )
                if chart.show_value_labels and frac >= 0.04:
                    mid_a = (angle + a_end) / 2.0
                    lbl_r = (r_outer + r_inner) / 2.0 if r_inner > 0 else r_outer * 0.65
                    lx = cx + lbl_r * math.cos(mid_a) - 36.0
                    ly = cy + lbl_r * math.sin(mid_a) - 14.0
                    txt_rgb = _readable_text_rgb(c_rgb, (1.0, 1.0, 1.0), min_ratio=3.5)
                    objs.append(
                        _make_textbox(
                            f"{slide_prefix}_{chart.id}_wlbl_{c_idx}",
                            BoxRect(lx, ly, 72.0, 28.0),
                            f"{_format_chart_num(float(vis_val))}",
                            font_name=theme.font_body,
                            font_size=20.0,
                            color=_rgba(txt_rgb),
                            bold=True,
                            opacity=chart.opacity,
                        )
                    )
            angle = a_end
        return objs

    ax_min = float(chart.axis_min if chart.axis_min is not None else 0.0)
    ax_max = float(chart.axis_max if chart.axis_max is not None else 1.0)
    if ax_max <= ax_min:
        ax_max = ax_min + 1.0
    ax_span = ax_max - ax_min
    tick_vals = [ax_min + ax_span * (i / 4.0) for i in range(5)]
    cat_count = max(1, len(chart.categories))

    if chart.unit:
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{chart.id}_unit",
                BoxRect(chart.rect.x + 8.0, chart.rect.y + header_h, chart.rect.w - 16.0, 22.0),
                f"单位：{chart.unit}",
                font_name=theme.font_body,
                font_size=16.0,
                color=_rgba(theme.subtitle_rgb),
                bold=False,
                opacity=chart.opacity,
                alignment=AlignmentType.RIGHT,
            )
        )

    is_horiz = chart.chart_type in ("bar", "stacked_bar")
    if is_horiz:
        cat_label_w = min(
            chart.rect.w * 0.40,
            max(108.0, max((_text_units(c) * 10.0 + 16.0 for c in chart.categories), default=108.0)),
        )
        inner_x = chart.rect.x + cat_label_w + 10.0
        inner_y = chart.rect.y + header_h + (24.0 if chart.unit else 8.0)
        inner_w = max(100.0, (chart.rect.x + chart.rect.w) - inner_x - 56.0)
        inner_h = max(80.0, (chart.rect.y + chart.rect.h) - inner_y - 36.0)

        for i, tv in enumerate(tick_vals):
            gx = inner_x + inner_w * (i / 4.0)
            is_zero_axis = i == 0
            objs.append(
                _make_open_line_shape(
                    f"{slide_prefix}_{chart.id}_grid_{i}",
                    (gx, inner_y),
                    (gx, inner_y + inner_h),
                    color=_rgba(theme.subtitle_rgb if is_zero_axis else theme.card_border_rgb, 0.85 if is_zero_axis else 0.35),
                    width=1.8 if is_zero_axis else 1.0,
                    pattern=Pattern.SOLID,
                    head=LineEnd.NONE,
                    opacity=chart.opacity,
                )
            )
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_{chart.id}_tick_{i}",
                    BoxRect(gx - 38.0, inner_y + inner_h + 6.0, 76.0, 24.0),
                    _format_chart_num(tv),
                    font_name=theme.font_body,
                    font_size=16.0,
                    color=_rgba(theme.subtitle_rgb),
                    bold=False,
                    opacity=chart.opacity,
                )
            )

        cat_slot_h = inner_h / cat_count
        cat_font = round(min(16.0, max(12.0, cat_slot_h * 0.32)), 1)
        for c_idx, cat in enumerate(chart.categories):
            cy = inner_y + c_idx * cat_slot_h
            cat_active = any(c_idx < len(sr.values) and sr.values[c_idx] is not None for sr in chart.series)
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_{chart.id}_cat_{c_idx}",
                    BoxRect(chart.rect.x + 2.0, cy, cat_label_w, cat_slot_h),
                    cat,
                    font_name=theme.font_body,
                    font_size=cat_font,
                    color=_rgba(theme.text_rgb),
                    bold=False,
                    opacity=chart.opacity * (1.0 if cat_active else 0.35),
                    alignment=AlignmentType.RIGHT,
                )
            )

        zero_x = max(inner_x, min(inner_x + inner_w, inner_x + ((0.0 - ax_min) / ax_span) * inner_w))
        if chart.chart_type == "bar":
            group_h = cat_slot_h * 0.72
            n_series = max(1, len(chart.series))
            inner_gap = min(6.0, group_h * 0.08) if n_series > 1 else 0.0
            bar_h = max(8.0, (group_h - inner_gap * (n_series - 1)) / n_series)
            val_font = round(min(30.0, max(19.0, bar_h * 0.62)), 1)
            for c_idx in range(cat_count):
                cy = inner_y + c_idx * cat_slot_h
                for s_idx, sr in enumerate(chart.series):
                    by = cy + (cat_slot_h - group_h) / 2.0 + s_idx * (bar_h + inner_gap)
                    s_rgb = series_colors[s_idx]
                    val = sr.values[c_idx] if c_idx < len(sr.values) else None
                    if val is None:
                        objs.append(
                            _make_solid_card(
                                f"{slide_prefix}_{chart.id}_b_{s_idx}_{c_idx}",
                                BoxRect(zero_x, by, 2.0, bar_h),
                                fill_rgb=_rgba(s_rgb),
                                stroke=Stroke(empty=True),
                                corner_px=0.0,
                                opacity=chart.opacity,
                            )
                        )
                        continue
                    vx = inner_x + ((float(val) - ax_min) / ax_span) * inner_w
                    if val >= 0:
                        bx = zero_x
                        bw = max(4.0, vx - zero_x)
                    else:
                        bx = vx
                        bw = max(4.0, zero_x - vx)
                    objs.append(
                        _make_solid_card(
                            f"{slide_prefix}_{chart.id}_b_{s_idx}_{c_idx}",
                            BoxRect(bx, by, bw, bar_h),
                            fill_rgb=_rgba(s_rgb),
                            stroke=Stroke(empty=True),
                            corner_px=0.0,
                            opacity=chart.opacity,
                        )
                    )
                    if chart.show_value_labels:
                        lx = (bx + bw + 6.0) if val >= 0 else max(inner_x, bx - 84.0)
                        align = AlignmentType.LEFT if val >= 0 else AlignmentType.RIGHT
                        objs.append(
                            _make_textbox(
                                f"{slide_prefix}_{chart.id}_vl_{s_idx}_{c_idx}",
                                BoxRect(lx, by - 4.0, 78.0, max(28.0, bar_h + 8.0)),
                                _format_chart_num(float(val)),
                                font_name=theme.font_body,
                                font_size=val_font,
                                color=_rgba(theme.text_rgb),
                                bold=True,
                                opacity=chart.opacity,
                                alignment=align,
                            )
                        )
        else:
            # stacked_bar
            bar_h = min(44.0, cat_slot_h * 0.62)
            for c_idx in range(cat_count):
                by = inner_y + c_idx * cat_slot_h + (cat_slot_h - bar_h) / 2.0
                pos_acc = 0.0
                neg_acc = 0.0
                for s_idx, sr in enumerate(chart.series):
                    val = sr.values[c_idx] if c_idx < len(sr.values) else None
                    if val is None:
                        continue
                    v = float(val)
                    base = pos_acc if v >= 0 else neg_acc
                    end = base + v
                    if v >= 0:
                        pos_acc = end
                    else:
                        neg_acc = end
                    x0 = inner_x + ((base - ax_min) / ax_span) * inner_w
                    x1 = inner_x + ((end - ax_min) / ax_span) * inner_w
                    bx = min(x0, x1)
                    bw = max(3.0, abs(x1 - x0))
                    s_rgb = series_colors[s_idx]
                    objs.append(
                        _make_solid_card(
                            f"{slide_prefix}_{chart.id}_sb_{s_idx}_{c_idx}",
                            BoxRect(bx, by, bw, bar_h),
                            fill_rgb=_rgba(s_rgb),
                            stroke=Stroke(empty=True),
                            corner_px=2.0,
                            opacity=chart.opacity,
                        )
                    )
                    if chart.show_value_labels and bw >= 34.0:
                        txt_rgb = _readable_text_rgb(s_rgb, (1.0, 1.0, 1.0), min_ratio=3.5)
                        objs.append(
                            _make_textbox(
                                f"{slide_prefix}_{chart.id}_svl_{s_idx}_{c_idx}",
                                BoxRect(bx + 2.0, by, bw - 4.0, bar_h),
                                _format_chart_num(v),
                                font_name=theme.font_body,
                                font_size=16.0,
                                color=_rgba(txt_rgb),
                                bold=True,
                                opacity=chart.opacity,
                            )
                        )
        return objs

    # Vertical charts: column, stacked_column, line, area, scatter
    max_tick_w = max(_text_units(_format_chart_num(tv)) * 9.5 for tv in tick_vals)
    y_label_w = max(CHART_Y_LABEL_MIN_W_PT, min(CHART_Y_LABEL_MAX_W_PT, max_tick_w + 14.0))
    raw_inner_x = chart.rect.x + y_label_w + 8.0
    base_y = chart.rect.y + header_h + (28.0 if chart.unit else 16.0)
    raw_inner_w = max(100.0, (chart.rect.x + chart.rect.w) - raw_inner_x - 16.0)
    inner_w = min(raw_inner_w, 820.0)
    inner_x = raw_inner_x + max(0.0, (raw_inner_w - inner_w) / 2.0)
    cat_label_h = 38.0
    raw_inner_h = max(80.0, (chart.rect.y + chart.rect.h) - base_y - cat_label_h - 6.0)
    inner_h = min(raw_inner_h, 430.0)
    inner_y = base_y + max(0.0, (raw_inner_h - inner_h) / 2.0)

    for i, tv in enumerate(tick_vals):
        gy = inner_y + inner_h - inner_h * (i / 4.0)
        is_zero_axis = abs(tv) < 1e-6 or (i == 0 and ax_min >= 0.0)
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_{chart.id}_grid_{i}",
                (inner_x, gy),
                (inner_x + inner_w, gy),
                color=_rgba(theme.subtitle_rgb if is_zero_axis else theme.card_border_rgb, 0.85 if is_zero_axis else 0.30),
                width=1.8 if is_zero_axis else 1.0,
                pattern=Pattern.SOLID,
                head=LineEnd.NONE,
                opacity=chart.opacity,
            )
        )
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{chart.id}_tick_{i}",
                BoxRect(inner_x - y_label_w - 6.0, gy - 12.0, y_label_w - 4.0, 24.0),
                _format_chart_num(tv),
                font_name=theme.font_body,
                font_size=16.0,
                color=_rgba(theme.subtitle_rgb),
                bold=False,
                opacity=chart.opacity,
                alignment=AlignmentType.RIGHT,
            )
        )

    cat_slot_w = inner_w / cat_count
    cat_font = round(min(15.5, max(11.5, cat_slot_w * 0.14)), 1)
    for c_idx, cat in enumerate(chart.categories):
        cx = inner_x + c_idx * cat_slot_w
        cat_active = any(c_idx < len(sr.values) and sr.values[c_idx] is not None for sr in chart.series)
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{chart.id}_cat_{c_idx}",
                BoxRect(cx + 2.0, inner_y + inner_h + 6.0, max(24.0, cat_slot_w - 4.0), cat_label_h - 4.0),
                cat,
                font_name=theme.font_body,
                font_size=cat_font,
                color=_rgba(theme.text_rgb),
                bold=False,
                opacity=chart.opacity * (1.0 if cat_active else 0.35),
            )
        )

    zero_y = max(inner_y, min(inner_y + inner_h, inner_y + inner_h - ((0.0 - ax_min) / ax_span) * inner_h))
    if ax_min < 0.0 < ax_max and all(abs(tv) >= 1e-6 for tv in tick_vals):
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_{chart.id}_zero_line",
                (inner_x, zero_y),
                (inner_x + inner_w, zero_y),
                color=_rgba(theme.subtitle_rgb, 0.85),
                width=1.8,
                pattern=Pattern.SOLID,
                head=LineEnd.NONE,
                opacity=chart.opacity,
            )
        )

    if chart.chart_type == "column":
        group_w = cat_slot_w * 0.68
        n_series = max(1, len(chart.series))
        inner_gap = min(8.0, group_w * 0.08) if n_series > 1 else 0.0
        bar_w = max(8.0, (group_w - inner_gap * (n_series - 1)) / n_series)
        val_font = round(min(34.0, max(20.0, bar_w * 0.48)), 1)
        for c_idx in range(cat_count):
            cx = inner_x + c_idx * cat_slot_w
            for s_idx, sr in enumerate(chart.series):
                bx = cx + (cat_slot_w - group_w) / 2.0 + s_idx * (bar_w + inner_gap)
                s_rgb = series_colors[s_idx]
                val = sr.values[c_idx] if c_idx < len(sr.values) else None
                if val is None:
                    objs.append(
                        _make_solid_card(
                            f"{slide_prefix}_{chart.id}_c_{s_idx}_{c_idx}",
                            BoxRect(bx, zero_y - 2.0, bar_w, 2.0),
                            fill_rgb=_rgba(s_rgb),
                            stroke=Stroke(empty=True),
                            corner_px=0.0,
                            opacity=chart.opacity,
                        )
                    )
                    continue
                vy = inner_y + inner_h - ((float(val) - ax_min) / ax_span) * inner_h
                if val >= 0:
                    by = vy
                    bh = max(4.0, zero_y - vy)
                else:
                    by = zero_y
                    bh = max(4.0, vy - zero_y)
                objs.append(
                    _make_solid_card(
                        f"{slide_prefix}_{chart.id}_c_{s_idx}_{c_idx}",
                        BoxRect(bx, by, bar_w, bh),
                        fill_rgb=_rgba(s_rgb),
                        stroke=Stroke(empty=True),
                        corner_px=0.0,
                        opacity=chart.opacity,
                    )
                )
                if chart.show_value_labels:
                    ly = max(inner_y - 44.0, by - 46.0) if val >= 0 else (by + bh + 4.0)
                    objs.append(
                        _make_textbox(
                            f"{slide_prefix}_{chart.id}_vl_{s_idx}_{c_idx}",
                            BoxRect(bx - 22.0, ly, bar_w + 44.0, 42.0),
                            _format_chart_num(float(val)),
                            font_name=theme.font_body,
                            font_size=val_font,
                            color=_rgba(theme.text_rgb),
                            bold=True,
                            opacity=chart.opacity,
                        )
                    )
    elif chart.chart_type == "stacked_column":
        bar_w = min(68.0, cat_slot_w * 0.58)
        for c_idx in range(cat_count):
            bx = inner_x + c_idx * cat_slot_w + (cat_slot_w - bar_w) / 2.0
            pos_acc = 0.0
            neg_acc = 0.0
            for s_idx, sr in enumerate(chart.series):
                val = sr.values[c_idx] if c_idx < len(sr.values) else None
                if val is None:
                    continue
                v = float(val)
                base = pos_acc if v >= 0 else neg_acc
                end = base + v
                if v >= 0:
                    pos_acc = end
                else:
                    neg_acc = end
                y0 = inner_y + inner_h - ((base - ax_min) / ax_span) * inner_h
                y1 = inner_y + inner_h - ((end - ax_min) / ax_span) * inner_h
                by = min(y0, y1)
                bh = max(3.0, abs(y1 - y0))
                s_rgb = series_colors[s_idx]
                objs.append(
                    _make_solid_card(
                        f"{slide_prefix}_{chart.id}_sc_{s_idx}_{c_idx}",
                        BoxRect(bx, by, bar_w, bh),
                        fill_rgb=_rgba(s_rgb),
                        stroke=Stroke(empty=True),
                        corner_px=2.0,
                        opacity=chart.opacity,
                    )
                )
                if chart.show_value_labels and bh >= 24.0:
                    txt_rgb = _readable_text_rgb(s_rgb, (1.0, 1.0, 1.0), min_ratio=3.5)
                    objs.append(
                        _make_textbox(
                            f"{slide_prefix}_{chart.id}_svl_{s_idx}_{c_idx}",
                            BoxRect(bx + 2.0, by, bar_w - 4.0, bh),
                            _format_chart_num(v),
                            font_name=theme.font_body,
                            font_size=16.0,
                            color=_rgba(txt_rgb),
                            bold=True,
                            opacity=chart.opacity,
                        )
                    )
    elif chart.chart_type == "waterfall":
        bar_w = min(74.0, cat_slot_w * 0.56)
        val_font = round(min(30.0, max(19.0, bar_w * 0.42)), 1)
        sr0 = chart.series[0] if chart.series else None
        full_vals = sr0.full_values if (sr0 and sr0.full_values) else ([v for v in sr0.values if v is not None] if sr0 else [])
        running = 0.0
        total_kw = ("总计", "合计", "期末", "total", "net", "ending")
        prev_end_xy: tuple[float, float] | None = None
        for c_idx in range(cat_count):
            if sr0 is None or c_idx >= len(sr0.values):
                continue
            vis_v = sr0.values[c_idx]
            raw_v = float(full_vals[c_idx]) if c_idx < len(full_vals) else (float(vis_v) if vis_v is not None else 0.0)
            cat_l = chart.categories[c_idx].lower()
            is_end_total = (c_idx == cat_count - 1) and abs(raw_v - running) <= max(1e-3, abs(running) * 1e-3)
            is_total = (c_idx == 0) or is_end_total or any(k in cat_l for k in total_kw)
            if is_total:
                start_v = 0.0
                end_v = raw_v
                running = end_v
                bar_rgb = series_colors[0] if c_idx == 0 else theme.accent_fill_rgb
                lbl_str = _format_chart_num(raw_v)
            else:
                start_v = running
                end_v = running + raw_v
                running = end_v
                pos_rgb = (0.22, 0.78, 0.56) if contrast_ratio(theme.text_rgb, (0.0, 0.0, 0.0)) > 7.0 else (0.14, 0.56, 0.36)
                neg_rgb = (0.90, 0.36, 0.34)
                bar_rgb = pos_rgb if raw_v >= 0 else neg_rgb
                lbl_str = f"+{_format_chart_num(raw_v)}" if raw_v > 0 else _format_chart_num(raw_v)

            bx = inner_x + c_idx * cat_slot_w + (cat_slot_w - bar_w) / 2.0
            if vis_v is None:
                prev_end_xy = None
                objs.append(
                    _make_solid_card(
                        f"{slide_prefix}_{chart.id}_wf_{c_idx}",
                        BoxRect(bx, zero_y - 2.0, bar_w, 2.0),
                        fill_rgb=_rgba(bar_rgb),
                        stroke=Stroke(empty=True),
                        corner_px=0.0,
                        opacity=chart.opacity,
                    )
                )
                continue
            y_start = inner_y + inner_h - ((start_v - ax_min) / ax_span) * inner_h
            y_end = inner_y + inner_h - ((end_v - ax_min) / ax_span) * inner_h
            by = min(y_start, y_end)
            bh = max(4.0, abs(y_end - y_start))

            if prev_end_xy is not None:
                bridge_y = y_end if is_total else y_start
                objs.append(
                    _make_open_line_shape(
                        f"{slide_prefix}_{chart.id}_wf_link_{c_idx}",
                        prev_end_xy,
                        (bx, bridge_y),
                        color=_rgba(theme.subtitle_rgb, 0.55),
                        width=1.2,
                        pattern=Pattern.MEDIUM_DASH,
                        head=LineEnd.NONE,
                        opacity=chart.opacity,
                    )
                )

            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_{chart.id}_wf_{c_idx}",
                    BoxRect(bx, by, bar_w, bh),
                    fill_rgb=_rgba(bar_rgb),
                    stroke=Stroke(empty=True),
                    corner_px=0.0,
                    opacity=chart.opacity,
                )
            )
            if chart.show_value_labels:
                upward = end_v >= start_v
                fits_below = (by + bh + 26.0) <= (inner_y + inner_h)
                if upward or not fits_below:
                    ly = max(inner_y - 22.0, by - 26.0)
                else:
                    ly = by + bh + 2.0
                objs.append(
                    _make_textbox(
                        f"{slide_prefix}_{chart.id}_wf_vl_{c_idx}",
                        BoxRect(bx - 16.0, ly, bar_w + 32.0, 24.0),
                        lbl_str,
                        font_name=theme.font_body,
                        font_size=val_font,
                        color=_rgba(theme.text_rgb),
                        bold=True,
                        opacity=chart.opacity,
                    )
                )
            prev_end_xy = (bx + bar_w, y_end)
    else:
        # line, area, scatter
        for s_idx, sr in enumerate(chart.series):
            s_rgb = series_colors[s_idx]
            pts: list[tuple[int, float, float, float]] = []
            for c_idx in range(cat_count):
                val = sr.values[c_idx] if c_idx < len(sr.values) else None
                if val is None:
                    continue
                px = inner_x + (c_idx + 0.5) * cat_slot_w
                py = inner_y + inner_h - ((float(val) - ax_min) / ax_span) * inner_h
                pts.append((c_idx, px, py, float(val)))

            if chart.chart_type in ("line", "area") and len(pts) >= 2:
                for p_i in range(len(pts) - 1):
                    c0, x0, y0, _ = pts[p_i]
                    c1, x1, y1, _ = pts[p_i + 1]
                    if chart.chart_type == "area":
                        bx = min(x0, x1)
                        bw = max(2.0, abs(x1 - x0))
                        by = min(y0, y1, zero_y)
                        bh = max(4.0, max(y0, y1, zero_y) - by)
                        u0y = (y0 - by) / bh
                        u1y = (y1 - by) / bh
                        uzy = (zero_y - by) / bh
                        d_area = f"M 0,{u0y:.4f} L 1,{u1y:.4f} L 1,{uzy:.4f} L 0,{uzy:.4f} Z"
                        objs.append(
                            _make_bezier_shape(
                                f"{slide_prefix}_{chart.id}_area_{s_idx}_{c0}",
                                BoxRect(bx, by, bw, bh),
                                d_area,
                                fill_rgba=_rgba(s_rgb, 0.22),
                                opacity=chart.opacity,
                            )
                        )
                    objs.append(
                        _make_open_line_shape(
                            f"{slide_prefix}_{chart.id}_seg_{s_idx}_{c0}",
                            (x0, y0),
                            (x1, y1),
                            color=_rgba(s_rgb),
                            width=3.5,
                            pattern=Pattern.SOLID,
                            head=LineEnd.NONE,
                            opacity=chart.opacity,
                        )
                    )

            dot_r = 6.0 if chart.chart_type != "scatter" else 8.0
            for c_idx, px, py, v in pts:
                objs.append(
                    _make_bezier_shape(
                        f"{slide_prefix}_{chart.id}_dot_{s_idx}_{c_idx}",
                        BoxRect(px - dot_r, py - dot_r, 2.0 * dot_r, 2.0 * dot_r),
                        _ellipse_unit_path(),
                        fill_rgba=_rgba(s_rgb),
                        stroke=Stroke(line=Line(color=Color(rgba=_rgba_int(theme.bg_rgb)), width=1.5, pattern=Pattern.SOLID)),
                        opacity=chart.opacity,
                    )
                )
                if chart.show_value_labels:
                    objs.append(
                        _make_textbox(
                            f"{slide_prefix}_{chart.id}_pvl_{s_idx}_{c_idx}",
                            BoxRect(px - 36.0, max(inner_y - 22.0, py - 28.0), 72.0, 22.0),
                            _format_chart_num(v),
                            font_name=theme.font_body,
                            font_size=14.0,
                            color=_rgba(theme.text_rgb),
                            bold=True,
                            opacity=chart.opacity,
                        )
                    )

    return objs


@register_object_renderer("chart")
def _make_chart_objects(slide_prefix: str, chart: PlacedChart, theme: ThemePreset) -> list[SlideObject]:
    """Compile a PlacedChart: pure Shape vector chart when progressive/vector, or native .keyx Chart."""
    if chart.use_vector:
        return _make_vector_chart_objects(slide_prefix, chart, theme)

    field_name, chart_cls = _CHART_MODEL_MAP[chart.chart_type]
    objs, header_h = _make_chart_header_and_legend(slide_prefix, chart, theme)
    is_circ = chart.chart_type in ("pie", "donut")
    left_pad = 135.0 if chart.chart_type in ("bar", "stacked_bar") else (72.0 if is_circ else 42.0)
    right_pad = 72.0 if is_circ else 12.0
    top_pad = 24.0 if is_circ else 0.0
    bottom_pad = 36.0 if is_circ else 10.0
    plot_x = chart.rect.x + left_pad
    plot_y = chart.rect.y + header_h + top_pad
    plot_w = max(120.0, chart.rect.w - left_pad - right_pad)
    plot_h = max(120.0, chart.rect.h - header_h - top_pad - bottom_pad)

    active_series = [sr for sr in chart.series if sr.active] or list(chart.series)
    cat_count = len(chart.categories)

    label_style = ParagraphProperties(
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=16.0,
            bold=False,
            character_fill=Fill(color=Color(rgba=_rgba(theme.subtitle_rgb))),
        )
    )
    value_label_style = ParagraphProperties(
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=15.0,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(theme.text_rgb))),
        )
    )

    palette = theme.segment_palette
    if chart.chart_type in ("pie", "donut"):
        sr0 = active_series[0]
        row_vals = [
            ChartDataValue(number=float(sr0.values[c_idx]))
            if (c_idx < len(sr0.values) and sr0.values[c_idx] is not None)
            else ChartDataValue(empty=True)
            for c_idx in range(cat_count)
        ]
        data = ChartData(
            chart_data_source=ChartDataSource.CHART_DATA_GRID,
            plot_direction=PlotDirection.COLUMNS_AS_SERIES,
            column_labels=list(chart.categories),
            row_labels=[sr0.name],
            rows=[ChartDataRow(values=row_vals)],
        )
        series_models = []
        for c_idx in range(max(1, cat_count)):
            c_rgb = palette[c_idx % len(palette)]
            in_rgb = (0.08, 0.10, 0.14) if contrast_ratio(c_rgb, (1.0, 1.0, 1.0)) < 2.8 else (1.0, 1.0, 1.0)
            in_style = ParagraphProperties(
                character_properties=CharacterProperties(
                    font_name=theme.font_body,
                    font_size=15.0,
                    bold=True,
                    character_fill=Fill(color=Color(rgba=_rgba(in_rgb))),
                )
            )
            series_models.append(
                ChartSeries(
                    series_index=c_idx,
                    show_value_labels=chart.show_value_labels,
                    value_label_position=SeriesValueLabelPosition.INSIDE,
                    value_label_text_style=in_style,
                    value_label_outside_text_style=value_label_style,
                    fill=Fill(color=Color(rgba=_rgba(c_rgb))),
                )
            )
    else:
        data_rows: list[ChartDataRow] = []
        for c_idx in range(cat_count):
            vals: list[ChartDataValue] = []
            for sr in active_series:
                v = sr.values[c_idx] if c_idx < len(sr.values) else None
                vals.append(ChartDataValue(number=float(v)) if v is not None else ChartDataValue(empty=True))
            data_rows.append(ChartDataRow(values=vals))

        data = ChartData(
            chart_data_source=ChartDataSource.CHART_DATA_GRID,
            plot_direction=PlotDirection.COLUMNS_AS_SERIES,
            column_labels=[sr.name for sr in active_series],
            row_labels=list(chart.categories),
            rows=data_rows,
        )

        series_models = []
        for s_idx, sr in enumerate(active_series):
            orig_idx = chart.series.index(sr)
            s_rgb = hex_to_rgb_float(sr.color_hex) if sr.color_hex else palette[orig_idx % len(palette)]
            s_fill = Fill(color=Color(rgba=_rgba(s_rgb)))
            s_stroke = (
                Stroke(line=Line(color=Color(rgba=_rgba(s_rgb)), width=3.5, pattern=Pattern.SOLID))
                if chart.chart_type in ("line", "area")
                else None
            )
            series_models.append(
                ChartSeries(
                    series_index=s_idx,
                    show_value_labels=chart.show_value_labels,
                    value_label_text_style=value_label_style,
                    value_label_outside_text_style=value_label_style,
                    fill=s_fill,
                    stroke=s_stroke,
                    symbol_fill=s_fill,
                )
            )

    kwargs: dict[str, Any] = {
        "identifier": f"{slide_prefix}_{chart.id}",
        "geometry": Geometry(
            position=Position(x=plot_x, y=plot_y),
            size=Size(width=plot_w, height=plot_h),
        ),
        "title": None,
        "data": data,
        "show_legend": False,
        "legend": None,
        "series": series_models,
    }

    if chart.chart_type in ("pie", "donut"):
        kwargs["chart_colors"] = [
            ChartColor(fill=Fill(color=Color(rgba=_rgba(palette[i % len(palette)]))))
            for i in range(max(1, cat_count))
        ]
    else:
        kwargs["category_axis"] = ChartCategoryAxis(
            label_text_style=label_style,
            show_axis=True,
        )
        val_axis_kwargs: dict[str, Any] = {
            "label_text_style": label_style,
            "show_axis": True,
            "show_major_gridlines": True,
        }
        if chart.unit:
            val_axis_kwargs["title"] = chart.unit
            val_axis_kwargs["show_title"] = True
            val_axis_kwargs["title_text_style"] = label_style
        if chart.axis_min is not None:
            val_axis_kwargs["min"] = ChartDataValue(number=float(chart.axis_min))
        if chart.axis_max is not None:
            val_axis_kwargs["max"] = ChartDataValue(number=float(chart.axis_max))
        kwargs["value_axis"] = ChartValueAxis(**val_axis_kwargs)

    inner_chart = chart_cls(**kwargs)
    objs.append(SlideObject(object=CanvasObject(chart=Chart(**{field_name: inner_chart}))))
    return objs


