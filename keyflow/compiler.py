"""Native .keyx compiler built on Apple's creator-studio-doc-format."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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
from creator_studio_doc_format.validation import validate_document

from keyflow.layout import (
    BoxRect,
    PlacedBox,
    PlacedChart,
    PlacedComparisonMatrix,
    PlacedDivider,
    PlacedEdge,
    PlacedPinnedFlow,
    PlacedProportionBar,
    PlacedRegionFrame,
    PlacedShape,
    PlacedTable,
    PlacedTextbox,
    ResolvedFrame,
    _text_units,
    resolve_scene,
)
from keyflow.pace import pace_deck
from keyflow.schema import DeckSpec, NodeVariant, parse_deck, validate_deck
from keyflow.themes import ThemePreset, apply_palette_overrides, get_theme, hex_to_rgb_float

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
        return RGBA(red=r, green=g, blue=b, alpha=0.72)
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
            width=1.5,
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


def _card_text_payload(
    box: PlacedBox,
    theme: ThemePreset,
    main_size: float,
    font_scale: float,
) -> tuple[ParagraphProperties, Text]:
    text_rgba = _rgba(hex_to_rgb_float(box.color_hex)) if box.color_hex else _rgba(theme.text_rgb)
    base_para = ParagraphProperties(
        alignment=AlignmentType.CENTER,
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
                    alignment=AlignmentType.CENTER,
                    space_after=4.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_title,
                        font_size=max(14.0, round(17.5 * font_scale, 1)),
                        bold=True,
                        character_fill=Fill(color=Color(rgba=_rgba(theme.badge_text_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.badge))],
            )
        )
    if box.metric:
        paragraphs.append(
            Paragraph(
                style=ParagraphProperties(
                    alignment=AlignmentType.CENTER,
                    space_after=6.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_title,
                        font_size=max(32.0, round(52.0 * font_scale, 1)),
                        bold=True,
                        character_fill=Fill(color=Color(rgba=_rgba(theme.metric_text_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.metric))],
            )
        )

    label_size = max(20.0, round(main_size * 0.86, 1)) if box.metric else main_size
    paragraphs.append(
        Paragraph(
            style=ParagraphProperties(
                alignment=AlignmentType.CENTER,
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
                    alignment=AlignmentType.CENTER,
                    space_before=4.0 * font_scale,
                    character_properties=CharacterProperties(
                        font_name=theme.font_body,
                        font_size=sub_size,
                        bold=False,
                        character_fill=Fill(color=Color(rgba=_rgba(theme.sublabel_rgb))),
                    ),
                ),
                contents=[Constituent(run=TextRun(string=box.sublabel))],
            )
        )

    return base_para, Text(paragraphs=paragraphs)


def _make_box_objects(
    slide_prefix: str,
    box: PlacedBox,
    theme: ThemePreset,
    *,
    scale: float,
    caption_color: RGBA,
) -> tuple[list[SlideObject], str]:
    """Create Shape (and optional external caption/badge Textbox) for a PlacedBox."""
    obj_id = f"{slide_prefix}_{box.id}"
    objs: list[SlideObject] = []
    eff_scale = box.font_scale if box.font_scale is not None else scale
    font_scale = max(0.68, eff_scale)

    if box.kind == "group_dashed":
        objs.append(
            _make_dashed_container(
                obj_id,
                box.rect,
                theme,
                corner_px=18.0 * font_scale,
                opacity=box.opacity,
            )
        )
        if box.badge:
            badge_rect = BoxRect(box.rect.x, box.rect.y - 42.0 * font_scale, box.rect.w, 34.0 * font_scale)
            objs.append(
                _make_textbox(
                    f"{obj_id}_badge",
                    badge_rect,
                    box.badge,
                    font_name=theme.font_title,
                    font_size=round(20.0 * font_scale, 1),
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
                    font_size=round(30.0 * font_scale, 1),
                    color=caption_color,
                    bold=True,
                    opacity=box.opacity,
                )
            )
        return objs, obj_id

    is_sub = box.kind == "subcard"
    base_size = 29.0 if is_sub else (30.0 if box.kind == "callout" else 34.0)
    main_size = round(base_size * font_scale, 1)
    if box.label:
        max_fit = max(18.0, (box.rect.w - 24.0) / max(1.0, _text_units(box.label) * 0.56))
        main_size = round(min(main_size, max_fit), 1)
    para_props, text_obj = _card_text_payload(box, theme, main_size, font_scale)
    fill_rgba = _rgba(hex_to_rgb_float(box.fill_hex)) if box.fill_hex else _fill_for_variant(theme, box.variant, is_sub)
    stroke = (
        Stroke(line=Line(color=Color(rgba=_rgba(hex_to_rgb_float(box.border_hex))), width=2.2, pattern=Pattern.SOLID))
        if box.border_hex
        else _stroke_for_box(theme, box.variant, is_sub)
    )

    sh = Shape(
        identifier=obj_id,
        geometry=Geometry(
            position=Position(x=box.rect.x, y=box.rect.y),
            size=Size(width=box.rect.w, height=box.rect.h),
        ),
        path=ShapePath(
            bezier=BezierPath(
                path=_rounded_rect_path(box.rect.w, box.rect.h, corner_px=15.0 * font_scale),
                space=_UNIT_SPACE,
            )
        ),
        fill=Fill(color=Color(rgba=fill_rgba)),
        stroke=stroke,
        opacity=box.opacity,
        layout_properties=LayoutProperties(vertical_alignment=VerticalAlignmentType.CENTER),
        paragraph_properties=para_props,
        text=text_obj,
    )
    objs.append(SlideObject(object=CanvasObject(shape=sh)))
    return objs, obj_id


def _make_pinned_flow_objects(
    slide_prefix: str,
    pf: PlacedPinnedFlow,
    theme: ThemePreset,
) -> list[SlideObject]:
    objs: list[SlideObject] = []
    bg_mask = Fill(color=Color(rgba=_rgba_int(theme.bg_rgb)))
    text_fg = _rgba(theme.text_rgb)
    caption_fg = _rgba(theme.arrow_rgb)

    for grp in pf.groups:
        objs.append(
            _make_dashed_container(
                f"{slide_prefix}_pf_grp_{grp.id}",
                grp.rect,
                theme,
                corner_px=16.0,
            )
        )
        objs.append(
            _make_textbox(
                f"{slide_prefix}_pf_leg_{grp.id}",
                grp.legend_rect,
                grp.label,
                font_name=theme.font_body,
                font_size=22.0 if not pf.is_centered else 25.0,
                color=caption_fg,
                bold=True,
                fill=bg_mask,
            )
        )

    node_rects: dict[str, BoxRect] = {}
    font_sz = 26.0 if pf.is_centered else 23.0
    for node in pf.nodes:
        nid = f"{slide_prefix}_pf_{node.id}"
        node_rects[node.id] = node.rect
        fill_rgb = theme.active_flow_fill_rgb if node.is_active else theme.flow_node_fill_rgb
        border_rgb = theme.active_flow_border_rgb if node.is_active else theme.flow_node_border_rgb
        objs.append(
            _make_solid_card(
                nid,
                node.rect,
                fill_rgb=_rgba(fill_rgb),
                stroke=Stroke(
                    line=Line(
                        color=Color(rgba=_rgba(border_rgb)),
                        width=2.0 if node.is_active else 1.5,
                        pattern=Pattern.SOLID,
                    )
                ),
                text=node.label,
                font_name=theme.font_body,
                font_size=font_sz,
                text_color=text_fg,
                corner_px=12.0,
            )
        )

    for edge in pf.edges:
        if edge.from_id not in node_rects or edge.to_id not in node_rects:
            continue
        pattern = Pattern.MEDIUM_DASH if edge.style == "dashed" else Pattern.SOLID
        p0, p1 = _endpoints_between_boxes(node_rects[edge.from_id], node_rects[edge.to_id], outset=10.0)
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_pf_e_{edge.id}",
                p0,
                p1,
                color=_rgba(theme.flow_node_border_rgb),
                width=3.5,
                pattern=pattern,
            )
        )

    return objs


def _make_proportion_bar_objects(
    slide_prefix: str,
    pb: PlacedProportionBar,
    theme: ThemePreset,
) -> list[SlideObject]:
    objs: list[SlideObject] = []
    fg = _rgba(theme.arrow_rgb)

    if pb.summary_box:
        objs.append(_make_dashed_container(f"{slide_prefix}_pb_box", pb.summary_box, theme, corner_px=18.0))
        if pb.summary_title and pb.summary_caption_rect:
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_pb_cap",
                    pb.summary_caption_rect,
                    pb.summary_title,
                    font_name=theme.font_body,
                    font_size=28.0,
                    color=fg,
                    bold=True,
                )
            )

    # Axis spine line & ticks
    objs.append(
        _make_open_line_shape(
            f"{slide_prefix}_pb_axis",
            pb.axis_start,
            pb.axis_end,
            color=fg,
            width=2.5,
            pattern=Pattern.SOLID,
        )
    )

    for t_idx, (tx, tlabel) in enumerate(pb.ticks):
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_pb_tick_{t_idx}",
                (tx, pb.bar_y - 4.0),
                (tx, pb.bar_y + pb.bar_h + 10.0),
                color=fg,
                width=2.0,
                pattern=Pattern.SOLID,
                head=LineEnd.NONE,
            )
        )
        objs.append(
            _make_textbox(
                f"{slide_prefix}_pb_tlab_{t_idx}",
                BoxRect(tx - 26.0, pb.bar_y + pb.bar_h + 16.0, 52.0, 34.0),
                tlabel,
                font_name=theme.font_title,
                font_size=21.0,
                color=fg,
                bold=False,
            )
        )

    palette = theme.segment_palette
    for item in pb.items:
        seg_rgb = palette[item.color_index % len(palette)]
        if item.chip_rect and item.value_rect:
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_pb_chip_{item.id}",
                    item.chip_rect,
                    fill_rgb=_rgba(theme.chip_fill_rgb),
                    stroke=Stroke(empty=True),
                    text=item.label.split(" (", 1)[0],
                    font_name=theme.font_body,
                    font_size=24.0,
                    text_color=_rgba(theme.text_rgb),
                    corner_px=4.0,
                )
            )
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_pb_val_{item.id}",
                    item.value_rect,
                    item.display_value,
                    font_name=theme.font_title,
                    font_size=25.0,
                    color=_rgba(theme.metric_text_rgb),
                    bold=True,
                )
            )

        if not item.visible:
            continue

        objs.append(
            _make_solid_card(
                f"{slide_prefix}_pb_seg_{item.id}",
                item.seg_rect,
                fill_rgb=_rgba(seg_rgb),
                stroke=Stroke(empty=True),
                corner_px=2.0,
            )
        )
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_pb_arr_{item.id}",
                item.arrow_tail,
                item.arrow_head,
                color=_rgba(seg_rgb),
                width=2.2,
                pattern=Pattern.SHORT_DASH,
            )
        )
        objs.append(
            _make_textbox(
                f"{slide_prefix}_pb_lab_{item.id}",
                item.label_rect,
                item.label,
                font_name=theme.font_body,
                font_size=23.0,
                color=_rgba(seg_rgb),
                bold=True,
            )
        )

    return objs


def _make_comparison_matrix_objects(
    slide_prefix: str,
    mx: PlacedComparisonMatrix,
    theme: ThemePreset,
) -> list[SlideObject]:
    objs: list[SlideObject] = []
    fg = _rgba(theme.arrow_rgb)

    if mx.formula and mx.formula_rect:
        objs.append(
            _make_textbox(
                f"{slide_prefix}_mx_formula",
                mx.formula_rect,
                mx.formula,
                font_name=theme.font_title,
                font_size=38.0,
                color=fg,
                bold=False,
            )
        )

    for col in mx.columns:
        objs.append(_make_dashed_container(f"{slide_prefix}_mx_col_{col.id}", col.box_rect, theme, corner_px=18.0))
        objs.append(
            _make_textbox(
                f"{slide_prefix}_mx_cap_{col.id}",
                col.caption_rect,
                col.caption,
                font_name=theme.font_title,
                font_size=26.0,
                color=fg,
                bold=True,
            )
        )

        if col.action_banner and col.action_banner_rect:
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_mx_act_{col.id}",
                    col.action_banner_rect,
                    fill_rgb=_rgba(theme.action_banner_rgb),
                    stroke=Stroke(empty=True),
                    text=col.action_banner,
                    font_name=theme.font_body,
                    font_size=23.0,
                    text_color=_rgba(theme.text_rgb),
                    corner_px=4.0,
                )
            )
        if col.action_subtext and col.action_subtext_rect:
            objs.append(
                _make_textbox(
                    f"{slide_prefix}_mx_sub_{col.id}",
                    col.action_subtext_rect,
                    col.action_subtext,
                    font_name=theme.font_body,
                    font_size=21.0,
                    color=fg,
                    bold=True,
                )
            )
        if col.takeaway and col.takeaway_rect:
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_mx_tk_{col.id}",
                    col.takeaway_rect,
                    fill_rgb=_rgba(theme.takeaway_pill_rgb),
                    stroke=Stroke(empty=True),
                    text=col.takeaway,
                    font_name=theme.font_body,
                    font_size=22.0,
                    text_color=_rgba(theme.text_rgb),
                    corner_px=6.0,
                )
            )

        for cell_idx, cell in enumerate(col.cells):
            cid = f"{slide_prefix}_mx_{col.id}_c{cell_idx}"
            if cell.kind == "chip":
                objs.append(
                    _make_solid_card(
                        cid,
                        cell.rect,
                        fill_rgb=_rgba(theme.chip_fill_rgb),
                        stroke=Stroke(empty=True),
                        text=cell.text,
                        font_name=theme.font_body,
                        font_size=21.0,
                        text_color=_rgba(theme.text_rgb),
                        corner_px=4.0,
                    )
                )
            elif cell.kind == "header":
                objs.append(
                    _make_textbox(
                        cid,
                        cell.rect,
                        cell.text,
                        font_name=theme.font_title,
                        font_size=19.0,
                        color=_rgba(theme.metric_text_rgb),
                        bold=True,
                    )
                )
            elif cell.kind == "trend":
                t_rgb = theme.trend_up_rgb if cell.trend == "up" else theme.trend_down_rgb
                objs.append(
                    _make_textbox(
                        cid,
                        cell.rect,
                        cell.text,
                        font_name=theme.font_title,
                        font_size=26.0,
                        color=_rgba(t_rgb),
                        bold=True,
                    )
                )
            else:
                objs.append(
                    _make_textbox(
                        cid,
                        cell.rect,
                        cell.text,
                        font_name=theme.font_title,
                        font_size=22.0,
                        color=fg,
                        bold=False,
                    )
                )

    return objs


def _make_edge_objects(
    slide_prefix: str,
    edge: PlacedEdge,
    box_rects: dict[str, BoxRect],
    theme: ThemePreset,
    *,
    scale: float,
) -> list[SlideObject]:
    pattern = Pattern.MEDIUM_DASH if edge.style == "dashed" else Pattern.SOLID
    outset = round(14.0 * max(0.75, scale), 1)
    p0, p1 = _endpoints_between_boxes(
        box_rects[edge.from_id],
        box_rects[edge.to_id],
        outset=outset,
        curve_pass_through=edge.curve_control,
    )
    objs: list[SlideObject] = [
        _make_open_line_shape(
            f"{slide_prefix}_edge_{edge.id}",
            p0,
            p1,
            color=_rgba(theme.arrow_rgb),
            width=round(4.5 * max(0.78, scale), 1),
            pattern=pattern,
            opacity=edge.opacity,
            curve_pass_through=edge.curve_control,
        )
    ]
    if edge.label and edge.label_rect:
        objs.append(
            _make_textbox(
                f"{slide_prefix}_edge_{edge.id}_label",
                edge.label_rect,
                edge.label,
                font_name=theme.font_body,
                font_size=round(21.0 * max(0.8, scale), 1),
                color=_rgba(theme.subtitle_rgb),
                bold=True,
                opacity=edge.opacity,
            )
        )
    return objs


def _make_divider_objects(
    slide_prefix: str,
    idx: int,
    divider: PlacedDivider,
    theme: ThemePreset,
) -> list[SlideObject]:
    mid_y = (divider.y_top + divider.y_bottom) / 2.0
    objs: list[SlideObject] = []
    if divider.label:
        gap = 34.0
        segments = [(divider.y_top, mid_y - gap), (mid_y + gap, divider.y_bottom)]
        badge_rect = BoxRect(divider.x - 40.0, mid_y - 26.0, 80.0, 52.0)
        objs.append(
            _make_textbox(
                f"{slide_prefix}_div_{idx}_vs",
                badge_rect,
                divider.label,
                font_name=theme.font_title,
                font_size=28.0,
                color=_rgba(theme.accent_text_rgb),
                bold=True,
            )
        )
    else:
        segments = [(divider.y_top, divider.y_bottom)]

    for seg_i, (y0, y1) in enumerate(segments):
        if y1 <= y0:
            continue
        objs.append(
            _make_open_line_shape(
                f"{slide_prefix}_div_{idx}_{seg_i}",
                (divider.x, y0),
                (divider.x, y1),
                color=_rgba(theme.divider_rgb),
                width=2.0,
                pattern=Pattern.MEDIUM_DASH,
                head=LineEnd.NONE,
                opacity=0.65,
            )
        )
    return objs


def _ellipse_unit_path() -> str:
    """Unit-space SVG ellipse path inside [0, 1] x [0, 1]."""
    return "M 0.5,0 A 0.5,0.5 0 1 1 0.4999,0 Z"


def _shape_path_for(shape: PlacedShape) -> str:
    if shape.shape_type == "custom" and shape.svg_path:
        return shape.svg_path
    if shape.shape_type == "ellipse":
        return _ellipse_unit_path()
    if shape.shape_type == "rect":
        return "M 0,0 H 1 V 1 H 0 Z"
    if shape.shape_type == "pill":
        return _rounded_rect_path(shape.rect.w, shape.rect.h, corner_px=min(shape.rect.w, shape.rect.h) / 2.0)
    return _rounded_rect_path(shape.rect.w, shape.rect.h, corner_px=16.0)


def _make_shape_object(slide_prefix: str, shape: PlacedShape, theme: ThemePreset) -> SlideObject:
    fill_rgba = (
        _rgba(hex_to_rgb_float(shape.fill_hex))
        if shape.fill_hex
        else _fill_for_variant(theme, shape.variant, is_subcard=False)
    )
    if shape.border_hex:
        stroke_rgb = _rgba(hex_to_rgb_float(shape.border_hex))
        stroke = Stroke(
            line=Line(
                color=Color(rgba=stroke_rgb),
                width=2.0,
                pattern=Pattern.MEDIUM_DASH if shape.dashed else Pattern.SOLID,
            )
        )
    elif shape.dashed:
        stroke = Stroke(
            line=Line(
                color=Color(rgba=_rgba(theme.group_border_rgb)),
                width=2.0,
                pattern=Pattern.MEDIUM_DASH,
            )
        )
    else:
        stroke = _stroke_for_box(theme, shape.variant, is_subcard=False)

    text_rgba = _rgba(hex_to_rgb_float(shape.color_hex)) if shape.color_hex else _rgba(theme.text_rgb)
    sh = Shape(
        identifier=f"{slide_prefix}_{shape.id}",
        geometry=Geometry(
            position=Position(x=shape.rect.x, y=shape.rect.y),
            size=Size(width=shape.rect.w, height=shape.rect.h),
        ),
        path=ShapePath(bezier=BezierPath(path=_shape_path_for(shape), space=_UNIT_SPACE)),
        fill=Fill(color=Color(rgba=fill_rgba)),
        stroke=stroke,
        opacity=shape.opacity,
        layout_properties=LayoutProperties(vertical_alignment=VerticalAlignmentType.CENTER),
        paragraph_properties=ParagraphProperties(
            alignment=AlignmentType.CENTER,
            character_properties=CharacterProperties(
                font_name=theme.font_body,
                font_size=28.0,
                bold=True,
                character_fill=Fill(color=Color(rgba=text_rgba)),
            ),
        ),
        text=Text(string=shape.label) if shape.label else None,
    )
    return SlideObject(object=CanvasObject(shape=sh))


def _make_region_frame_objects(
    slide_prefix: str,
    rf: PlacedRegionFrame,
    theme: ThemePreset,
) -> list[SlideObject]:
    objs: list[SlideObject] = [
        _make_dashed_container(
            f"{slide_prefix}_reg_{rf.id}",
            rf.rect,
            theme,
            corner_px=18.0,
        )
    ]
    if rf.title and rf.title_rect:
        objs.append(
            _make_textbox(
                f"{slide_prefix}_reg_{rf.id}_title",
                rf.title_rect,
                rf.title,
                font_name=theme.font_title,
                font_size=22.0,
                color=_rgba(theme.badge_text_rgb),
                bold=True,
                alignment=AlignmentType.LEFT,
            )
        )
    return objs


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


def _make_chart_objects(slide_prefix: str, chart: PlacedChart, theme: ThemePreset) -> list[SlideObject]:
    """Compile a PlacedChart into a native editable .keyx Chart (plus internal title Textbox)."""
    field_name, chart_cls = _CHART_MODEL_MAP[chart.chart_type]
    objs: list[SlideObject] = []
    top_offset = 0.0
    if chart.title:
        title_h = 40.0
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{chart.id}_title",
                BoxRect(chart.rect.x, chart.rect.y, chart.rect.w, title_h),
                chart.title,
                font_name=theme.font_title,
                font_size=24.0,
                color=_rgba(theme.title_rgb),
                bold=True,
                opacity=chart.opacity,
            )
        )
        top_offset = title_h + 6.0

    legend_h = 34.0 if chart.show_legend else 0.0
    left_pad = 135.0 if chart.chart_type in ("bar", "stacked_bar") else (20.0 if chart.chart_type in ("pie", "donut") else 42.0)
    plot_x = chart.rect.x + left_pad
    plot_y = chart.rect.y + top_offset + legend_h
    plot_w = max(120.0, chart.rect.w - left_pad - 12.0)
    plot_h = max(120.0, chart.rect.h - top_offset - legend_h - 10.0)

    cat_count = len(chart.categories)
    data_rows: list[ChartDataRow] = []
    for c_idx in range(cat_count):
        vals: list[ChartDataValue] = []
        for sr in chart.series:
            v = sr.values[c_idx] if c_idx < len(sr.values) else None
            vals.append(ChartDataValue(number=float(v)) if v is not None else ChartDataValue(empty=True))
        data_rows.append(ChartDataRow(values=vals))

    data = ChartData(
        chart_data_source=ChartDataSource.CHART_DATA_GRID,
        plot_direction=PlotDirection.COLUMNS_AS_SERIES,
        column_labels=[sr.name for sr in chart.series],
        row_labels=list(chart.categories),
        rows=data_rows,
    )

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
    legend_style = ParagraphProperties(
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=16.0,
            bold=False,
            character_fill=Fill(color=Color(rgba=_rgba(theme.text_rgb))),
        )
    )

    palette = theme.segment_palette
    if chart.show_legend:
        legend_items: list[tuple[str, tuple[float, float, float]]] = []
        if chart.chart_type in ("pie", "donut"):
            for i, cat in enumerate(chart.categories):
                legend_items.append((cat, palette[i % len(palette)]))
        else:
            for s_idx, sr in enumerate(chart.series):
                s_rgb = hex_to_rgb_float(sr.color_hex) if sr.color_hex else palette[s_idx % len(palette)]
                legend_items.append((sr.name, s_rgb))

        swatch_sz = 14.0
        item_gap = 22.0
        item_widths = [swatch_sz + 8.0 + max(42.0, _text_units(lbl) * 10.5) for lbl, _ in legend_items]
        total_leg_w = sum(item_widths) + max(0, len(legend_items) - 1) * item_gap
        lx = chart.rect.x + max(12.0, (chart.rect.w - total_leg_w) / 2.0)
        ly = chart.rect.y + top_offset
        for l_idx, ((lbl, rgb), iw) in enumerate(zip(legend_items, item_widths)):
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_{chart.id}_leg_sw_{l_idx}",
                    BoxRect(lx, ly + 8.0, swatch_sz, swatch_sz),
                    fill_rgb=_rgba(rgb),
                    stroke=Stroke(empty=True),
                    corner_px=3.0,
                    opacity=chart.opacity,
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
                    opacity=chart.opacity,
                    alignment=AlignmentType.LEFT,
                )
            )
            lx += iw + item_gap

    series_models: list[ChartSeries] = []
    for s_idx, sr in enumerate(chart.series):
        s_rgb = hex_to_rgb_float(sr.color_hex) if sr.color_hex else palette[s_idx % len(palette)]
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


def _make_table_objects(slide_prefix: str, table: PlacedTable, theme: ThemePreset) -> list[SlideObject]:
    """Compile a PlacedTable into a native editable .keyx Table object (with optional title Textbox)."""
    objs: list[SlideObject] = []
    table_rect = table.rect
    if table.title:
        title_h = 44.0
        objs.append(
            _make_textbox(
                f"{slide_prefix}_{table.id}_title",
                BoxRect(table.rect.x, table.rect.y, table.rect.w, title_h),
                table.title,
                font_name=theme.font_title,
                font_size=24.0,
                color=_rgba(theme.title_rgb),
                bold=True,
                opacity=table.opacity,
            )
        )
        table_rect = BoxRect(table.rect.x, table.rect.y + title_h + 6.0, table.rect.w, max(80.0, table.rect.h - title_h - 6.0))

    n_cols = max(1, len(table.headers))
    n_rows = 1 + len(table.rows)
    col_w = round(table_rect.w / n_cols, 2)
    row_h = round(table_rect.h / n_rows, 2)

    grid_line = Stroke(line=Line(color=Color(rgba=_rgba(theme.card_border_rgb, 0.55)), width=1.0, pattern=Pattern.SOLID))
    header_fill = Fill(color=Color(rgba=_rgba(theme.flow_node_fill_rgb)))
    body_fill = Fill(color=Color(rgba=_rgba(theme.card_fill_rgb)))
    highlight_fill = Fill(color=Color(rgba=_rgba(theme.accent_fill_rgb)))

    header_text_props = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_title,
            font_size=20.0,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(theme.title_rgb))),
        ),
    )
    body_text_props = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=18.0,
            bold=False,
            character_fill=Fill(color=Color(rgba=_rgba(theme.text_rgb))),
        ),
    )
    highlight_text_props = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=18.0,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(theme.accent_text_rgb))),
        ),
    )

    col_headers = [
        ColumnHeader(
            title=hdr if c_idx < table.visible_cols else "",
            column_width=col_w,
            visibility_state=TableColumnHeaderVisibilityState.VISIBLE,
            kind=TableColumnHeaderKind(body=True),
        )
        for c_idx, hdr in enumerate(table.headers)
    ]

    content_rows: list[Row] = [
        Row(
            row_index=0,
            row_height=row_h,
            visibility_state=TableRowVisibilityState.VISIBLE,
            kind=TableRowKind(body=True),
            cells=[
                Cell(
                    value=hdr if c_idx < table.visible_cols else "",
                    column_index=c_idx,
                    cell_properties=CellProperties(
                        fill=highlight_fill if c_idx in table.highlight_cols else header_fill,
                        vertical_alignment=VerticalAlignmentType.CENTER,
                    ),
                    text_properties=header_text_props,
                )
                for c_idx, hdr in enumerate(table.headers)
            ],
        )
    ]

    for r_idx, raw_row in enumerate(table.rows):
        row_visible = r_idx < table.visible_rows
        is_hl_row = r_idx in table.highlight_rows
        cells: list[Cell] = []
        for c_idx in range(n_cols):
            val = raw_row[c_idx] if (row_visible and c_idx < table.visible_cols and c_idx < len(raw_row)) else ""
            is_hl = is_hl_row or (c_idx in table.highlight_cols)
            cells.append(
                Cell(
                    value=val,
                    column_index=c_idx,
                    cell_properties=CellProperties(
                        fill=highlight_fill if is_hl else body_fill,
                        vertical_alignment=VerticalAlignmentType.CENTER,
                    ),
                    text_properties=highlight_text_props if is_hl else body_text_props,
                )
            )
        content_rows.append(
            Row(
                row_index=r_idx + 1,
                row_height=row_h,
                visibility_state=TableRowVisibilityState.VISIBLE,
                kind=TableRowKind(body=True),
                cells=cells,
            )
        )

    tbl = Table(
        identifier=f"{slide_prefix}_{table.id}",
        geometry=Geometry(
            position=Position(x=table_rect.x, y=table_rect.y),
            size=Size(width=table_rect.w, height=table_rect.h),
        ),
        number_of_columns=n_cols,
        number_of_rows=n_rows,
        number_of_header_rows=1,
        default_column_width=col_w,
        default_row_height=row_h,
        visual_properties=VisualProperties(
            overall_properties=OverallProperties(has_alternating_rows=False, auto_resize=False),
            header_row_cell_properties=CellProperties(fill=header_fill, vertical_alignment=VerticalAlignmentType.CENTER),
            header_row_text_properties=header_text_props,
            body_cell_properties=CellProperties(fill=body_fill, vertical_alignment=VerticalAlignmentType.CENTER),
            body_text_properties=body_text_props,
            body_stroke_properties=BodyStrokeProperties(
                horizontal_stroke=grid_line,
                vertical_stroke=grid_line,
                horizontal_border_stroke=grid_line,
                vertical_border_stroke=grid_line,
                border_strokes_visible=True,
                horizontal_strokes_visible=True,
                vertical_strokes_visible=True,
            ),
        ),
        column_headers=col_headers,
        content=content_rows,
    )
    objs.append(SlideObject(object=CanvasObject(table=tbl)))
    return objs


def _render_slide(
    slide_num: int,
    frame: ResolvedFrame,
    theme: ThemePreset,
    bg: SlideBackground,
) -> Slide:
    slide_prefix = f"s{slide_num}"
    contents: list[SlideObject] = []

    if frame.pinned_flow is not None:
        contents.extend(_make_pinned_flow_objects(slide_prefix, frame.pinned_flow, theme))

    if frame.title_rect is not None:
        title_size = round(min(78.0, max(44.0, (frame.title_rect.w - 40.0) / max(1.0, _text_units(frame.title) * 0.56))), 1)
        contents.append(
            _make_textbox(
                f"{slide_prefix}_title",
                frame.title_rect,
                frame.title,
                font_name=theme.font_title,
                font_size=title_size,
                color=_rgba(theme.title_rgb),
                bold=True,
            )
        )

    if frame.subtitle and frame.subtitle_rect:
        contents.append(
            _make_textbox(
                f"{slide_prefix}_subtitle",
                frame.subtitle_rect,
                frame.subtitle,
                font_name=theme.font_body,
                font_size=28.0,
                color=_rgba(theme.subtitle_rgb),
                bold=False,
            )
        )

    for rf in frame.region_frames:
        contents.extend(_make_region_frame_objects(slide_prefix, rf, theme))

    for d_idx, divider in enumerate(frame.dividers):
        contents.extend(_make_divider_objects(slide_prefix, d_idx, divider, theme))

    if frame.proportion_bar is not None:
        contents.extend(_make_proportion_bar_objects(slide_prefix, frame.proportion_bar, theme))

    if frame.comparison_matrix is not None:
        contents.extend(_make_comparison_matrix_objects(slide_prefix, frame.comparison_matrix, theme))

    connector_rects: dict[str, BoxRect] = {}
    for shape in frame.shapes:
        contents.append(_make_shape_object(slide_prefix, shape, theme))
        connector_rects[shape.id] = shape.rect

    for chart in frame.charts:
        contents.extend(_make_chart_objects(slide_prefix, chart, theme))
        connector_rects[chart.id] = chart.rect

    for table in frame.tables:
        contents.extend(_make_table_objects(slide_prefix, table, theme))
        connector_rects[table.id] = table.rect

    for tb in frame.textboxes:
        t_color = _rgba(hex_to_rgb_float(tb.color_hex)) if tb.color_hex else _rgba(theme.text_rgb)
        t_fill = Fill(color=Color(rgba=_rgba(hex_to_rgb_float(tb.fill_hex)))) if tb.fill_hex else None
        contents.append(
            _make_textbox(
                f"{slide_prefix}_{tb.id}",
                tb.rect,
                tb.text,
                font_name=theme.font_body,
                font_size=tb.font_size,
                color=t_color,
                bold=tb.bold,
                opacity=tb.opacity,
                fill=t_fill,
                alignment=_ALIGN_MAP.get(tb.align, AlignmentType.CENTER),
            )
        )
        connector_rects[tb.id] = tb.rect

    caption_color = _rgba(theme.arrow_rgb)
    for box in frame.boxes:
        objs, _ = _make_box_objects(
            slide_prefix,
            box,
            theme,
            scale=frame.scale,
            caption_color=caption_color,
        )
        contents.extend(objs)
        connector_rects[box.id] = box.rect

    for edge in frame.edges:
        if edge.from_id in connector_rects and edge.to_id in connector_rects:
            contents.extend(_make_edge_objects(slide_prefix, edge, connector_rects, theme, scale=frame.scale))

    return Slide(
        background=bg,
        contents=contents,
        depth=frame.depth,
        note=Text(string=frame.notes) if frame.notes else None,
    )


def compile_deck(
    deck_or_raw: DeckSpec | dict[str, Any],
    output_path: str | Path,
    *,
    theme_override: str | None = None,
    use_templates: bool | None = None,
) -> Path:
    """Validate, pace if needed, lay out, and compile a KeyFlow deck specification into a .keyx file."""
    if isinstance(deck_or_raw, dict):
        validation = validate_deck(deck_or_raw, use_templates=use_templates)
        if not validation.valid:
            raise ValueError("Invalid storyboard:\n- " + "\n- ".join(validation.errors))
        materialized = pace_deck(deck_or_raw, overwrite_existing=False)
        deck = parse_deck(materialized)
    else:
        deck = deck_or_raw

    base_theme = apply_palette_overrides(get_theme(theme_override or deck.theme), deck.palette)
    presets: list[Preset] = [_build_background_preset(base_theme, _BG_PRESET_ID)]
    seen_preset_ids: set[str] = {_BG_PRESET_ID}
    default_bg = SlideBackground(standard=Fill(preset_identifier=_BG_PRESET_ID))

    slides: list[Slide] = []
    slide_counter = 1
    for scene in deck.scenes:
        scene_theme = apply_palette_overrides(base_theme, scene.palette)
        if scene.palette and any(k in scene.palette for k in ("bg_hex", "bg_gradient_end_hex")):
            bg_id = f"{_BG_PRESET_ID}_{scene.id}"
            if bg_id not in seen_preset_ids:
                presets.append(_build_background_preset(scene_theme, bg_id))
                seen_preset_ids.add(bg_id)
            scene_bg = SlideBackground(standard=Fill(preset_identifier=bg_id))
        else:
            scene_bg = default_bg

        resolved_frames = resolve_scene(
            scene,
            deck.slide_width,
            deck.slide_height,
            pinned_flow=deck.pinned_flow,
        )
        for frame in resolved_frames:
            slides.append(_render_slide(slide_counter, frame, scene_theme, scene_bg))
            slide_counter += 1

    doc = KeyxDocument(
        payload=Presentation(
            theme=KeynoteTheme(name="White", locale="en_US"),
            slide_size=Size(width=deck.slide_width, height=deck.slide_height),
            slides=slides,
        ),
        presets=presets,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out, pre_save_hooks=[validate_document])
    return out


def export_slide_pngs(keyx_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Optional macOS Keynote helper: export a .keyx file as PNG slide previews."""
    if sys.platform != "darwin" or shutil.which("osascript") is None:
        raise RuntimeError(
            "PNG preview export requires macOS with Apple Keynote ('osascript' is unavailable here). "
            "Your .keyx presentation can still be compiled cleanly on any OS."
        )

    src = Path(keyx_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Keynote file not found: {src}")

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    applescript = """
on run argv
    set srcPath to POSIX file (item 1 of argv)
    set outPath to POSIX file (item 2 of argv)
    tell application id "com.apple.Keynote"
        set doc to open srcPath
        export doc to outPath as slide images with properties {image format:PNG}
        close doc saving no
    end tell
end run
"""
    proc = subprocess.run(
        ["osascript", "-e", applescript, str(src), str(out)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "Make sure Apple Keynote is installed and allowed to run AppleScript."
        raise RuntimeError(f"Keynote PNG export failed: {detail}")
    return sorted(out.glob("*.png"))
