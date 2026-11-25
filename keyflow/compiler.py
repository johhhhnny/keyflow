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
    Base64EncodedResource,
    BezierPath,
    CanvasObject,
    CharacterProperties,
    Color,
    Constituent,
    Fill,
    Geometry,
    ImageFill,
    KeynoteTheme,
    KeyxDocument,
    LayoutProperties,
    Line,
    LineEnd,
    Paragraph,
    ParagraphProperties,
    Pattern,
    Position,
    Presentation,
    Rect,
    Resource,
    Shape,
    Size,
    Slide,
    SlideBackground,
    SlideObject,
    Stroke,
    Technique,
    Text,
    Textbox,
    TextRun,
    VerticalAlignmentType,
)
from creator_studio_doc_format.core import Path as ShapePath
from creator_studio_doc_format.validation import validate_document

from keyflow.layout import (
    BoxRect,
    PlacedBox,
    PlacedComparisonMatrix,
    PlacedDivider,
    PlacedEdge,
    PlacedPinnedFlow,
    PlacedProportionBar,
    ResolvedFrame,
    resolve_scene,
)
from keyflow.pace import pace_deck
from keyflow.schema import DeckSpec, NodeVariant, parse_deck, validate_deck
from keyflow.themes import ThemePreset, get_theme, render_textured_bg_png_b64

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


def _build_slide_background(theme: ThemePreset) -> SlideBackground:
    png_b64 = render_textured_bg_png_b64(theme.bg_rgb, theme.bg_noise_amp)
    return SlideBackground(
        standard=Fill(
            image=ImageFill(
                resource=Resource(
                    base64_encoded=Base64EncodedResource(
                        string=png_b64,
                        filename=f"{theme.name}_bg.png",
                    )
                ),
                technique=Technique.SCALE_TO_FILL,
            )
        )
    )


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
            alignment=AlignmentType.CENTER,
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
    base_para = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=main_size,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(theme.text_rgb))),
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
                    character_fill=Fill(color=Color(rgba=_rgba(theme.text_rgb))),
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
    font_scale = max(0.74, scale)

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
    base_size = 29.0 if is_sub else 34.0
    main_size = round(base_size * font_scale, 1)
    para_props, text_obj = _card_text_payload(box, theme, main_size, font_scale)

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
        fill=Fill(color=Color(rgba=_fill_for_variant(theme, box.variant, is_sub))),
        stroke=_stroke_for_box(theme, box.variant, is_sub),
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
        contents.append(
            _make_textbox(
                f"{slide_prefix}_title",
                frame.title_rect,
                frame.title,
                font_name=theme.font_title,
                font_size=80.0,
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

    for d_idx, divider in enumerate(frame.dividers):
        contents.extend(_make_divider_objects(slide_prefix, d_idx, divider, theme))

    if frame.proportion_bar is not None:
        contents.extend(_make_proportion_bar_objects(slide_prefix, frame.proportion_bar, theme))

    if frame.comparison_matrix is not None:
        contents.extend(_make_comparison_matrix_objects(slide_prefix, frame.comparison_matrix, theme))

    caption_color = _rgba(theme.arrow_rgb)
    box_rects: dict[str, BoxRect] = {}
    for box in frame.boxes:
        objs, _ = _make_box_objects(
            slide_prefix,
            box,
            theme,
            scale=frame.scale,
            caption_color=caption_color,
        )
        contents.extend(objs)
        box_rects[box.id] = box.rect

    for edge in frame.edges:
        if edge.from_id in box_rects and edge.to_id in box_rects:
            contents.extend(_make_edge_objects(slide_prefix, edge, box_rects, theme, scale=frame.scale))

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
) -> Path:
    """Validate, pace if needed, lay out, and compile a KeyFlow deck specification into a .keyx file."""
    if isinstance(deck_or_raw, dict):
        validation = validate_deck(deck_or_raw)
        if not validation.valid:
            raise ValueError("Invalid storyboard:\n- " + "\n- ".join(validation.errors))
        materialized = pace_deck(deck_or_raw, overwrite_existing=False)
        deck = parse_deck(materialized)
    else:
        deck = deck_or_raw

    theme = get_theme(theme_override or deck.theme)
    bg = _build_slide_background(theme)

    slides: list[Slide] = []
    slide_counter = 1
    for scene in deck.scenes:
        resolved_frames = resolve_scene(
            scene,
            deck.slide_width,
            deck.slide_height,
            pinned_flow=deck.pinned_flow,
        )
        for frame in resolved_frames:
            slides.append(_render_slide(slide_counter, frame, theme, bg))
            slide_counter += 1

    doc = KeyxDocument(
        payload=Presentation(
            theme=KeynoteTheme(name="White", locale="en_US"),
            slide_size=Size(width=deck.slide_width, height=deck.slide_height),
            slides=slides,
        )
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

    applescript = f'''
tell application id "com.apple.Keynote"
    set doc to open POSIX file "{src}"
    export doc to POSIX file "{out}" as slide images with properties {{image format:PNG}}
    close doc saving no
end tell
'''
    proc = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "Make sure Apple Keynote is installed and allowed to run AppleScript."
        raise RuntimeError(f"Keynote PNG export failed: {detail}")
    return sorted(out.glob("*.png"))
