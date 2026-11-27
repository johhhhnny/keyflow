"""Shared geometry, color, card, and line helpers for KeyFlow object renderers."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from creator_studio_doc_format.core import (
    RGBA,
    AlignmentType,
    AreaChart,
    BarChart,
    BezierPath,
    BodyStrokeProperties,
    CanvasObject,
    Cell,
    CellProperties,
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
    Flavor,
    Geometry,
    Gradient,
    KeynoteTheme,
    KeyxDocument,
    Label,
    LayoutProperties,
    Line,
    LineChart,
    LineEnd,
    Linear,
    OverallProperties,
    Paragraph,
    ParagraphProperties,
    Pattern,
    PieChart,
    PlotDirection,
    Position,
    Presentation,
    Preset,
    Rect,
    Row,
    ScatterChart,
    SeriesValueLabelPosition,
    Shape,
    Size,
    Slide,
    SlideBackground,
    SlideObject,
    StackedBarChart,
    StackedColumnChart,
    Stop,
    Stroke,
    Table,
    TableColumnHeaderKind,
    TableColumnHeaderVisibilityState,
    TableRowKind,
    TableRowVisibilityState,
    Text,
    Textbox,
    TextRun,
    VerticalAlignmentType,
    VisualProperties,
)
from creator_studio_doc_format.core import Path as ShapePath

from keyflow.layouts.types import (
    BoxRect,
    PlacedBox,
    _text_units,
)
from keyflow.schema import NodeVariant
from keyflow.themes import ThemePreset, contrast_ratio
from keyflow.tokens import LINE_HEIGHT_RATIO, MIN_READABLE_SCALE, MUTED_CARD_ALPHA

_BG_PRESET_ID = "keyflow_bg_fill"

_UNIT_SPACE = Rect(position=Position(x=0, y=0), size=Size(width=1, height=1))


def _rounded_rect_path(width: float, height: float, corner_px: float = 16.0) -> str:
    """Compute an SVG unit-space rounded rectangle path with uniform visual corner radius."""
    safe_w = max(width, 1.0)
    safe_h = max(height, 1.0)
    rx = min(0.45, corner_px / safe_w)
    ry = min(0.45, corner_px / safe_h)
    return (
        f"M {rx:.4f},0 H {1.0 - rx:.4f} "
        f"A {rx:.4f},{ry:.4f} 0 0 1 1,{ry:.4f} V {1.0 - ry:.4f} "
        f"A {rx:.4f},{ry:.4f} 0 0 1 {1.0 - rx:.4f},1 H {rx:.4f} "
        f"A {rx:.4f},{ry:.4f} 0 0 1 0,{1.0 - ry:.4f} V {ry:.4f} "
        f"A {rx:.4f},{ry:.4f} 0 0 1 {rx:.4f},0 Z"
    )


def _rgba(rgb: tuple[float, float, float], alpha: float = 1.0) -> RGBA:
    return RGBA(red=rgb[0], green=rgb[1], blue=rgb[2], alpha=alpha)


def _rgba_int(rgb: tuple[int, int, int], alpha: float = 1.0) -> RGBA:
    return RGBA(red=rgb[0] / 255.0, green=rgb[1] / 255.0, blue=rgb[2] / 255.0, alpha=alpha)


def _rgba4(rgba: tuple[float, float, float, float]) -> RGBA:
    return RGBA(red=rgba[0], green=rgba[1], blue=rgba[2], alpha=rgba[3])


def _fill_for_variant(theme: ThemePreset, variant: NodeVariant, is_subcard: bool) -> RGBA:
    if variant == "accent":
        return _rgba(theme.accent_fill_rgb)
    if variant == "success":
        return _rgba(theme.success_fill_rgb)
    if variant == "warn":
        return _rgba(theme.warn_fill_rgb)
    if variant == "muted":
        r, g, b = theme.card_fill_rgb
        return RGBA(red=r, green=g, blue=b, alpha=MUTED_CARD_ALPHA)
    return _rgba(theme.subcard_fill_rgb if is_subcard else theme.card_fill_rgb)


def _stroke_for_box(theme: ThemePreset, variant: NodeVariant, is_subcard: bool) -> Stroke:
    border_map = {
        "accent": (theme.accent_border_rgb, 2.5),
        "success": (theme.success_border_rgb, 2.0),
        "warn": (theme.warn_border_rgb, 2.0),
    }
    if variant in border_map:
        rgb, width = border_map[variant]
        return Stroke(line=Line(color=Color(rgba=_rgba(rgb)), width=width, pattern=Pattern.SOLID))
    if is_subcard:
        return Stroke(empty=True)
    return Stroke(
        line=Line(
            color=Color(rgba=_rgba(theme.card_border_rgb)),
            width=theme.elevation_border_width,
            pattern=Pattern.SOLID,
        )
    )


def _build_background_preset(theme: ThemePreset, ident: str = _BG_PRESET_ID) -> Preset:
    """Build a shared Fill preset (linear gradient or solid color) stored in presets.json."""
    if theme.bg_gradient_end_rgb is not None:
        props: dict[str, Any] = {
            "gradient": Gradient(
                stops=[
                    Stop(color=Color(rgba=_rgba_int(theme.bg_rgb)), fraction=0.0),
                    Stop(color=Color(rgba=_rgba_int(theme.bg_gradient_end_rgb)), fraction=1.0),
                ],
                flavor=Flavor(linear=Linear(angle=theme.bg_gradient_angle)),
            ).model_dump(mode="json")
        }
    else:
        props = {"color": {"rgba": _rgba_int(theme.bg_rgb).model_dump(mode="json")}}
    return Preset(identifier=ident, properties=props)


_ALIGN_MAP: dict[str, AlignmentType] = {
    "left": AlignmentType.LEFT,
    "center": AlignmentType.CENTER,
    "right": AlignmentType.RIGHT,
}


def _make_textbox(
    ident: str,
    rect: BoxRect,
    text: str,
    *,
    font_name: str,
    font_size: float,
    color: RGBA,
    bold: bool = True,
    opacity: float = 1.0,
    fill: Fill | None = None,
    alignment: AlignmentType = AlignmentType.CENTER,
) -> SlideObject:
    tb = Textbox(
        identifier=ident,
        geometry=Geometry(
            position=Position(x=rect.x, y=rect.y),
            size=Size(width=rect.w, height=rect.h),
        ),
        fill=fill,
        stroke=Stroke(empty=True),
        opacity=opacity,
        layout_properties=LayoutProperties(vertical_alignment=VerticalAlignmentType.CENTER),
        paragraph_properties=ParagraphProperties(
            alignment=alignment,
            character_properties=CharacterProperties(
                font_name=font_name,
                font_size=font_size,
                bold=bold,
                character_fill=Fill(color=Color(rgba=color)),
            ),
        ),
        text=Text(string=text),
    )
    return SlideObject(object=CanvasObject(textbox=tb))


def _clip_ray_to_box_edge(
    cx: float,
    cy: float,
    target_x: float,
    target_y: float,
    rect: BoxRect,
    outset: float,
) -> tuple[float, float]:
    """Return the point where a ray from (cx, cy) toward target exits rect plus outset."""
    dx = target_x - cx
    dy = target_y - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (cx, cy)
    ux = dx / dist
    uy = dy / dist
    hw = max(rect.w / 2.0, 1.0)
    hh = max(rect.h / 2.0, 1.0)
    tx = hw / abs(ux) if abs(ux) > 1e-9 else float("inf")
    ty = hh / abs(uy) if abs(uy) > 1e-9 else float("inf")
    step = min(tx, ty) + outset
    return (cx + ux * step, cy + uy * step)


def _endpoints_between_boxes(
    r_from: BoxRect,
    r_to: BoxRect,
    *,
    outset: float,
    curve_pass_through: tuple[float, float] | None = None,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Compute exact start and end coordinates clipped to box edges with outset."""
    if curve_pass_through is None:
        return (
            _clip_ray_to_box_edge(r_from.cx, r_from.cy, r_to.cx, r_to.cy, r_from, outset),
            _clip_ray_to_box_edge(r_to.cx, r_to.cy, r_from.cx, r_from.cy, r_to, outset),
        )
    # Solve quadratic Bezier control point so B(0.5) passes through curve_pass_through.
    qx = 2.0 * curve_pass_through[0] - 0.5 * (r_from.cx + r_to.cx)
    qy = 2.0 * curve_pass_through[1] - 0.5 * (r_from.cy + r_to.cy)
    return (
        _clip_ray_to_box_edge(r_from.cx, r_from.cy, qx, qy, r_from, outset),
        _clip_ray_to_box_edge(r_to.cx, r_to.cy, qx, qy, r_to, outset),
    )


def _quad_bezier_extrema(p0: float, q: float, p1: float) -> list[float]:
    vals = [p0, p1]
    denom = p0 - 2.0 * q + p1
    if abs(denom) > 1e-9:
        t = (p0 - q) / denom
        if 0.0 < t < 1.0:
            mt = 1.0 - t
            vals.append(mt * mt * p0 + 2.0 * mt * t * q + t * t * p1)
    return vals


def _make_open_line_shape(
    ident: str,
    p0: tuple[float, float],
    p1: tuple[float, float],
    *,
    color: RGBA,
    width: float,
    pattern: Pattern,
    head: LineEnd = LineEnd.FILLED_ARROW,
    tail: LineEnd = LineEnd.NONE,
    opacity: float = 1.0,
    curve_pass_through: tuple[float, float] | None = None,
) -> SlideObject:
    """Create an open-path Shape line or quadratic Bezier curve so Keynote tracks it across slides."""
    x0, y0 = p0
    x1, y1 = p1
    if curve_pass_through is None:
        min_span = 20.0
        pad_x = max(0.0, (min_span - abs(x1 - x0)) / 2.0)
        pad_y = max(0.0, (min_span - abs(y1 - y0)) / 2.0)
        bx = min(x0, x1) - pad_x
        by = min(y0, y1) - pad_y
        bw = abs(x1 - x0) + 2.0 * pad_x
        bh = abs(y1 - y0) + 2.0 * pad_y
        ux0 = (x0 - bx) / bw
        uy0 = (y0 - by) / bh
        ux1 = (x1 - bx) / bw
        uy1 = (y1 - by) / bh
        d = f"M {ux0:.4f},{uy0:.4f} L {ux1:.4f},{uy1:.4f}"
    else:
        qx = 2.0 * curve_pass_through[0] - 0.5 * (x0 + x1)
        qy = 2.0 * curve_pass_through[1] - 0.5 * (y0 + y1)
        xs = _quad_bezier_extrema(x0, qx, x1)
        ys = _quad_bezier_extrema(y0, qy, y1)
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad_x = max(10.0, (20.0 - (max_x - min_x)) / 2.0)
        pad_y = max(10.0, (20.0 - (max_y - min_y)) / 2.0)
        bx = min_x - pad_x
        by = min_y - pad_y
        bw = (max_x - min_x) + 2.0 * pad_x
        bh = (max_y - min_y) + 2.0 * pad_y
        ux0 = (x0 - bx) / bw
        uy0 = (y0 - by) / bh
        uqx = (qx - bx) / bw
        uqy = (qy - by) / bh
        ux1 = (x1 - bx) / bw
        uy1 = (y1 - by) / bh
        d = f"M {ux0:.4f},{uy0:.4f} Q {uqx:.4f},{uqy:.4f} {ux1:.4f},{uy1:.4f}"

    sh = Shape(
        identifier=ident,
        geometry=Geometry(
            position=Position(x=bx, y=by),
            size=Size(width=bw, height=bh),
        ),
        path=ShapePath(bezier=BezierPath(path=d, space=_UNIT_SPACE)),
        tail=tail,
        head=head,
        fill=None,
        stroke=Stroke(line=Line(color=Color(rgba=color), width=width, pattern=pattern)),
        opacity=opacity,
    )
    return SlideObject(object=CanvasObject(shape=sh))


def _make_solid_card(
    ident: str,
    rect: BoxRect,
    *,
    fill_rgb: RGBA,
    stroke: Stroke,
    text: str = "",
    font_name: str = "PingFang SC",
    font_size: float = 24.0,
    text_color: RGBA | None = None,
    bold: bool = True,
    corner_px: float = 12.0,
    opacity: float = 1.0,
) -> SlideObject:
    sh = Shape(
        identifier=ident,
        geometry=Geometry(
            position=Position(x=rect.x, y=rect.y),
            size=Size(width=rect.w, height=rect.h),
        ),
        path=ShapePath(
            bezier=BezierPath(
                path=_rounded_rect_path(rect.w, rect.h, corner_px=corner_px),
                space=_UNIT_SPACE,
            )
        ),
        fill=Fill(color=Color(rgba=fill_rgb)),
        stroke=stroke,
        opacity=opacity,
        layout_properties=LayoutProperties(vertical_alignment=VerticalAlignmentType.CENTER),
        paragraph_properties=ParagraphProperties(
            alignment=AlignmentType.CENTER,
            character_properties=CharacterProperties(
                font_name=font_name,
                font_size=font_size,
                bold=bold,
                character_fill=Fill(color=Color(rgba=text_color or RGBA(red=1, green=1, blue=1))),
            ),
        ),
        text=Text(string=text) if text else None,
    )
    return SlideObject(object=CanvasObject(shape=sh))


def _make_dashed_container(
    ident: str,
    rect: BoxRect,
    theme: ThemePreset,
    *,
    corner_px: float = 18.0,
    opacity: float = 1.0,
) -> SlideObject:
    sh = Shape(
        identifier=ident,
        geometry=Geometry(
            position=Position(x=rect.x, y=rect.y),
            size=Size(width=rect.w, height=rect.h),
        ),
        path=ShapePath(
            bezier=BezierPath(
                path=_rounded_rect_path(rect.w, rect.h, corner_px=corner_px),
                space=_UNIT_SPACE,
            )
        ),
        fill=Fill(color=Color(rgba=_rgba4(theme.group_fill_rgba))),
        stroke=Stroke(
            line=Line(
                color=Color(rgba=_rgba(theme.group_border_rgb)),
                width=2.0,
                pattern=Pattern.MEDIUM_DASH,
            )
        ),
        opacity=opacity,
    )
    return SlideObject(object=CanvasObject(shape=sh))


def _readable_text_rgb(
    bg_rgb: tuple[float, float, float],
    preferred_rgb: tuple[float, float, float],
    *,
    min_ratio: float = 3.5,
) -> tuple[float, float, float]:
    """Return *preferred_rgb* if contrast against *bg_rgb* is sufficient, else dark/light fallback."""
    if contrast_ratio(preferred_rgb, bg_rgb) >= min_ratio:
        return preferred_rgb
    dark = (0.06, 0.08, 0.12)
    light = (0.98, 0.99, 1.0)
    return dark if contrast_ratio(dark, bg_rgb) >= contrast_ratio(light, bg_rgb) else light


def _card_text_payload(
    box: PlacedBox,
    theme: ThemePreset,
    main_size: float,
    font_scale: float,
    *,
    bg_rgb: tuple[float, float, float] | None = None,
) -> tuple[ParagraphProperties, Text]:
    if box.color_hex:
        main_rgb = hex_to_rgb_float(box.color_hex)
    elif bg_rgb is not None:
        main_rgb = _readable_text_rgb(bg_rgb, theme.text_rgb)
    elif surface == "accent_bar":
        fill_rgba = _rgba(hex_to_rgb_float(box.fill_hex)) if box.fill_hex else _fill_for_variant(theme, box.variant, is_sub)
        fill_obj = Fill(color=Color(rgba=RGBA(red=fill_rgba.red, green=fill_rgba.green, blue=fill_rgba.blue, alpha=0.65)))
        bg_rgb = (fill_rgba.red, fill_rgba.green, fill_rgba.blue)
        stroke = Stroke(empty=True)
    else:
        main_rgb = theme.text_rgb
    text_rgba = _rgba(main_rgb)
    badge_rgb = _readable_text_rgb(bg_rgb, theme.badge_text_rgb) if bg_rgb is not None else theme.badge_text_rgb
    metric_rgb = _readable_text_rgb(bg_rgb, theme.metric_text_rgb) if bg_rgb is not None else theme.metric_text_rgb
    sublabel_rgb = _readable_text_rgb(bg_rgb, theme.sublabel_rgb) if bg_rgb is not None else theme.sublabel_rgb

    para_align = _ALIGN_MAP.get(getattr(box, "align", "center"), AlignmentType.CENTER)
    base_para = ParagraphProperties(
        alignment=para_align,
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=main_size,
            bold=True,
            character_fill=Fill(color=Color(rgba=text_rgba)),
        ),
    )
    if not box.badge and not box.metric and not box.sublabel:
        return base_para, Text(string=box.label)

    paragraphs: list[Paragraph] = []
    if box.badge:
        paragraphs.append(
            Paragraph(
                style=ParagraphProperties(
                    alignment=para_align,
                    space_after=4.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_title,
                        font_size=max(14.0, round(17.5 * font_scale, 1)),
                        bold=True,
                        character_fill=Fill(color=Color(rgba=_rgba(badge_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.badge))],
            )
        )
    if box.metric:
        paragraphs.append(
            Paragraph(
                style=ParagraphProperties(
                    alignment=para_align,
                    space_after=6.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_title,
                        font_size=max(32.0, round(52.0 * font_scale, 1)),
                        bold=True,
                        character_fill=Fill(color=Color(rgba=_rgba(metric_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.metric))],
            )
        )

    label_size = max(20.0, round(main_size * 0.86, 1)) if box.metric else main_size
    paragraphs.append(
        Paragraph(
            style=ParagraphProperties(
                alignment=para_align,
                character_properties=CharacterProperties(
                    font_name=theme.font_body,
                    font_size=label_size,
                    bold=True,
                    character_fill=Fill(color=Color(rgba=text_rgba)),
                ),
            ),
            contents=[Constituent(run=TextRun(string=box.label))],
        )
    )

    if box.sublabel:
        sub_size = max(15.0, round(main_size * 0.64, 1))
        paragraphs.append(
            Paragraph(
                style=ParagraphProperties(
                    alignment=para_align,
                    space_before=4.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_body,
                        font_size=sub_size,
                        bold=False,
                        character_fill=Fill(color=Color(rgba=_rgba(sublabel_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.sublabel))],
            )
        )

    return base_para, Text(paragraphs=paragraphs)


def _step_down_font(
    ladder: tuple[float, ...],
    text: str,
    text_w: float,
    eff_scale: float,
    *,
    max_lines: int = 1,
) -> float:
    """Pick the largest modular font size from ladder that fits cleanly without decimal drift."""
    start_idx = 0
    if eff_scale < 0.76 and len(ladder) > 2:
        start_idx = 2
    elif eff_scale < 0.88 and len(ladder) > 1:
        start_idx = 1
    units = _text_units(text)
    for sz in ladder[start_idx:]:
        est_lines = max(1, math.ceil(units * sz * 0.62 / max(40.0, text_w)))
        if est_lines <= max_lines:
            return sz
    return ladder[-1]


def compute_box_text_layout(
    box: PlacedBox,
    *,
    scale: float,
) -> list[tuple[str, str, str, float, bool, BoxRect]]:
    """Compute exact (suffix, text, role, font_size, bold, rect) using modular scale & discrete step-down."""
    eff_scale = max(MIN_READABLE_SCALE, box.font_scale if box.font_scale is not None else scale)
    is_sub = box.kind == "subcard"
    surface = getattr(box, "surface", "filled")
    pad_x = 18.0 if surface == "accent_bar" else 14.0
    text_w = max(40.0, box.rect.w - 2 * pad_x)
    text_x = box.rect.x + pad_x

    label_ladder = (24.0, 19.0, 15.0) if is_sub else (30.0, 24.0, 19.0)
    main_size = _step_down_font(label_ladder, box.label, text_w, eff_scale) if box.label else label_ladder[0]

    gap_sm = 4.0 if eff_scale >= 0.85 else 3.0
    gap_md = 6.0 if eff_scale >= 0.85 else 4.0

    line_specs: list[tuple[str, str, str, float, bool, float, float]] = []
    if box.badge:
        bsz = 15.0
        bh = round(bsz * LINE_HEIGHT_RATIO, 1)
        line_specs.append(("badge", box.badge, "title", bsz, True, bh, gap_sm))
    if box.metric:
        msz = 48.0 if eff_scale >= 0.85 else 38.0
        mh = round(msz * 1.25, 1)
        line_specs.append(("metric", box.metric, "title", msz, True, mh, gap_md))
    if box.label:
        lsz = main_size
        n_lines = max(1, math.ceil(_text_units(box.label) * lsz * 0.62 / text_w))
        lh = round(lsz * LINE_HEIGHT_RATIO * n_lines, 1)
        line_specs.append(("caption", box.label, "body", lsz, True, lh, 0.0))
    if box.sublabel:
        ssz = 15.0 if (is_sub or eff_scale < 0.85) else 19.0
        n_lines = max(1, math.ceil(_text_units(box.sublabel) * ssz * 0.62 / text_w))
        sh_h = round(ssz * LINE_HEIGHT_RATIO * n_lines, 1)
        if line_specs:
            prev = line_specs[-1]
            line_specs[-1] = (*prev[:6], gap_sm)
        line_specs.append(("sublabel", box.sublabel, "body", ssz, False, sh_h, 0.0))

    total_h = sum(spec[5] + spec[6] for spec in line_specs)
    cursor_y = box.rect.y + max(6.0, (box.rect.h - total_h) / 2.0)
    resolved: list[tuple[str, str, str, float, bool, BoxRect]] = []
    for suffix, tb_txt, role, tb_sz, tb_bold, tb_h, gap_after in line_specs:
        resolved.append((suffix, tb_txt, role, tb_sz, tb_bold, BoxRect(text_x, cursor_y, text_w, tb_h)))
        cursor_y += tb_h + gap_after
    return resolved


def _make_box_objects(
    slide_prefix: str,
    box: PlacedBox,
    theme: ThemePreset,
    *,
    scale: float,
    caption_color: RGBA,
    corner_base_px: float = 8.0,
) -> tuple[list[SlideObject], str]:
    """Create Shape (and optional external caption/badge Textbox) for a PlacedBox."""
    obj_id = f"{slide_prefix}_{box.id}"
    objs: list[SlideObject] = []
    eff_scale = max(MIN_READABLE_SCALE, box.font_scale if box.font_scale is not None else scale)

    if box.kind == "group_dashed":
        objs.append(
            _make_dashed_container(
                obj_id,
                box.rect,
                theme,
                corner_px=max(12.0, corner_base_px + 4.0),
                opacity=box.opacity,
            )
        )
        if box.badge:
            badge_rect = BoxRect(box.rect.x, box.rect.y - 42.0 * eff_scale, box.rect.w, 34.0 * eff_scale)
            objs.append(
                _make_textbox(
                    f"{obj_id}_badge",
                    badge_rect,
                    box.badge,
                    font_name=theme.font_title,
                    font_size=19.0 if eff_scale >= 0.85 else 15.0,
                    color=_rgba(theme.badge_text_rgb),
                    bold=True,
                    opacity=box.opacity,
                )
            )
        if box.caption and box.caption_rect:
            objs.append(
                _make_textbox(
                    f"{obj_id}_caption",
                    box.caption_rect,
                    box.caption,
                    font_name=theme.font_body,
                    font_size=30.0 if eff_scale >= 0.85 else 24.0,
                    color=caption_color,
                    bold=True,
                    opacity=box.opacity,
                )
            )
        return objs, obj_id

    is_sub = box.kind == "subcard"
    surface = getattr(box, "surface", "filled")
    canvas_bg_rgb = (theme.bg_rgb[0] / 255.0, theme.bg_rgb[1] / 255.0, theme.bg_rgb[2] / 255.0)
    if surface == "borderless":
        fill_obj: Fill | None = None
        bg_rgb = canvas_bg_rgb
        stroke = Stroke(empty=True)
    elif surface == "ghost":
        fill_obj = None
        bg_rgb = canvas_bg_rgb
        if box.border_hex:
            stroke = Stroke(line=Line(color=Color(rgba=_rgba(hex_to_rgb_float(box.border_hex))), width=theme.elevation_border_width, pattern=Pattern.SOLID))
        else:
            base_stroke = _stroke_for_box(theme, box.variant, is_sub)
            stroke = Stroke(line=Line(color=base_stroke.line.color, width=theme.elevation_border_width, pattern=Pattern.SOLID)) if base_stroke.line else base_stroke
    elif surface == "accent_bar":
        fill_rgba = _rgba(hex_to_rgb_float(box.fill_hex)) if box.fill_hex else _fill_for_variant(theme, box.variant, is_sub)
        fill_obj = Fill(color=Color(rgba=RGBA(red=fill_rgba.red, green=fill_rgba.green, blue=fill_rgba.blue, alpha=0.65)))
        bg_rgb = (fill_rgba.red, fill_rgba.green, fill_rgba.blue)
        stroke = Stroke(empty=True)
    else:
        fill_rgba = _rgba(hex_to_rgb_float(box.fill_hex)) if box.fill_hex else _fill_for_variant(theme, box.variant, is_sub)
        fill_obj = Fill(color=Color(rgba=fill_rgba))
        bg_rgb = (fill_rgba.red, fill_rgba.green, fill_rgba.blue)
        stroke = (
            Stroke(line=Line(color=Color(rgba=_rgba(hex_to_rgb_float(box.border_hex))), width=2.2, pattern=Pattern.SOLID))
            if box.border_hex
            else _stroke_for_box(theme, box.variant, is_sub)
        )

    if surface != "borderless":
        sh = Shape(
            identifier=obj_id,
            geometry=Geometry(
                position=Position(x=box.rect.x, y=box.rect.y),
                size=Size(width=box.rect.w, height=box.rect.h),
            ),
            path=ShapePath(
                bezier=BezierPath(
                    path=_rounded_rect_path(box.rect.w, box.rect.h, corner_px=corner_base_px),
                    space=_UNIT_SPACE,
                )
            ),
            fill=fill_obj,
            stroke=stroke,
            opacity=box.opacity,
        )
        objs.append(SlideObject(object=CanvasObject(shape=sh)))
        if surface == "accent_bar":
            bar_color_map = {
                "accent": theme.accent_border_rgb,
                "success": theme.success_border_rgb,
                "warn": theme.warn_border_rgb,
            }
            bar_rgb = hex_to_rgb_float(box.border_hex) if box.border_hex else bar_color_map.get(box.variant, theme.accent_border_rgb)
            objs.append(
                _make_solid_card(
                    f"{obj_id}_bar",
                    BoxRect(box.rect.x, box.rect.y, 4.5, box.rect.h),
                    fill_rgb=_rgba(bar_rgb),
                    stroke=Stroke(empty=True),
                    corner_px=2.0,
                    opacity=box.opacity,
                )
            )

    # Emit one independent Textbox per line (badge, metric, caption/label, sublabel)
    # so cards can be paced line-by-line and match group_dashed _badge/_caption IDs in Magic Move.
    main_rgb = hex_to_rgb_float(box.color_hex) if box.color_hex else _readable_text_rgb(bg_rgb, theme.text_rgb)
    badge_rgb = _readable_text_rgb(bg_rgb, theme.badge_text_rgb)
    metric_rgb = _readable_text_rgb(bg_rgb, theme.metric_text_rgb)
    sub_rgb = _readable_text_rgb(bg_rgb, theme.sublabel_rgb)
    para_align = _ALIGN_MAP.get(getattr(box, "align", "center"), AlignmentType.CENTER)

    role_color_map = {
        "badge": badge_rgb,
        "metric": metric_rgb,
        "caption": main_rgb,
        "sublabel": sub_rgb,
    }
    for suffix, tb_txt, role, tb_sz, tb_bold, tb_rect in compute_box_text_layout(box, scale=scale):
        tb_font = theme.font_title if role == "title" else theme.font_body
        tb_rgb = role_color_map[suffix]
        objs.append(
            _make_textbox(
                f"{obj_id}_{suffix}",
                tb_rect,
                tb_txt,
                font_name=tb_font,
                font_size=tb_sz,
                color=_rgba(tb_rgb),
                bold=tb_bold,
                opacity=box.opacity,
                alignment=para_align,
            )
        )

    return objs, obj_id


