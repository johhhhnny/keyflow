"""Native .keyx compiler built on Apple's creator-studio-doc-format."""

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
from creator_studio_doc_format.validation import validate_document

from keyflow.exporter import export_slide_pngs  # noqa: F401 (backward-compat re-export)
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
from keyflow.schema import DeckSpec, NodeVariant, StyleConfigSpec, parse_deck, validate_deck
from keyflow.themes import ThemePreset, apply_palette_overrides, contrast_ratio, get_theme, hex_to_rgb_float
from keyflow.tokens import (
    CHART_Y_LABEL_MAX_W_PT,
    CHART_Y_LABEL_MIN_W_PT,
    DEFAULT_ARROW_WIDTH,
    DEFAULT_CARD_CORNER_PX,
    DEFAULT_SUBTITLE_SIZE,
    DEFAULT_TITLE_MAX_SIZE,
    DEFAULT_TITLE_MIN_SIZE,
    MUTED_CARD_ALPHA,
)

from keyflow.objects import OBJECT_RENDERERS
from keyflow.objects.charts import (  # noqa: F401
    _CHART_MODEL_MAP,
    _format_chart_num,
    _make_bezier_shape,
    _make_chart_header_and_legend,
    _make_chart_objects,
    _make_vector_chart_objects,
)
from keyflow.objects.helpers import (  # noqa: F401
    _ALIGN_MAP,
    _BG_PRESET_ID,
    _UNIT_SPACE,
    _build_background_preset,
    _card_text_payload,
    _clip_ray_to_box_edge,
    _endpoints_between_boxes,
    _fill_for_variant,
    _make_box_objects,
    _make_dashed_container,
    _make_open_line_shape,
    _make_solid_card,
    _make_textbox,
    _quad_bezier_extrema,
    _readable_text_rgb,
    _rgba,
    _rgba4,
    _rgba_int,
    _rounded_rect_path,
    _stroke_for_box,
)
from keyflow.objects.table import _make_table_objects  # noqa: F401

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
            tk_txt_rgb = _readable_text_rgb(theme.takeaway_pill_rgb, theme.text_rgb)
            objs.append(
                _make_solid_card(
                    f"{slide_prefix}_mx_tk_{col.id}",
                    col.takeaway_rect,
                    fill_rgb=_rgba(theme.takeaway_pill_rgb),
                    stroke=Stroke(empty=True),
                    text=col.takeaway,
                    font_name=theme.font_body,
                    font_size=22.0,
                    text_color=_rgba(tk_txt_rgb),
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
    arrow_base_width: float = DEFAULT_ARROW_WIDTH,
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
            width=round(arrow_base_width * max(0.78, scale), 1),
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


def _render_slide(
    slide_num: int,
    frame: ResolvedFrame,
    theme: ThemePreset,
    bg: SlideBackground,
    *,
    style_config: StyleConfigSpec | None = None,
) -> Slide:
    slide_prefix = f"s{slide_num}"
    contents: list[SlideObject] = []
    title_max = style_config.title_max_size if (style_config and style_config.title_max_size is not None) else DEFAULT_TITLE_MAX_SIZE
    sub_size = style_config.subtitle_size if (style_config and style_config.subtitle_size is not None) else DEFAULT_SUBTITLE_SIZE
    corner_px = (
        style_config.card_corner_px
        if (style_config and style_config.card_corner_px is not None)
        else (theme.card_corner_px if theme.card_corner_px is not None else DEFAULT_CARD_CORNER_PX)
    )
    arrow_w = style_config.arrow_width if (style_config and style_config.arrow_width is not None) else DEFAULT_ARROW_WIDTH

    if frame.pinned_flow is not None:
        contents.extend(_make_pinned_flow_objects(slide_prefix, frame.pinned_flow, theme))

    if frame.title_rect is not None:
        box_title_cap = min(title_max, frame.title_rect.h * 0.75)
        title_size = round(min(box_title_cap, max(min(DEFAULT_TITLE_MIN_SIZE, box_title_cap), (frame.title_rect.w - 80.0) / max(1.0, _text_units(frame.title) * 0.56))), 1)
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
                font_size=sub_size,
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
    layered_items: list[tuple[int, int, list[SlideObject]]] = []
    seq = 0
    for shape in frame.shapes:
        sh_obj = _make_shape_object(slide_prefix, shape, theme)
        if getattr(shape, "rotation", 0.0) and sh_obj.object.shape is not None:
            sh_obj.object.shape.geometry.angle = float(shape.rotation)
        layered_items.append((getattr(shape, "z_index", 0), seq, [sh_obj]))
        seq += 1
        connector_rects[shape.id] = shape.rect

    for chart in frame.charts:
        layered_items.append((getattr(chart, "z_index", 0), seq, _make_chart_objects(slide_prefix, chart, theme)))
        seq += 1
        connector_rects[chart.id] = chart.rect

    for table in frame.tables:
        layered_items.append((getattr(table, "z_index", 0), seq, _make_table_objects(slide_prefix, table, theme)))
        seq += 1
        connector_rects[table.id] = table.rect

    for tb in frame.textboxes:
        t_color = _rgba(hex_to_rgb_float(tb.color_hex)) if tb.color_hex else _rgba(theme.text_rgb)
        t_fill = Fill(color=Color(rgba=_rgba(hex_to_rgb_float(tb.fill_hex)))) if tb.fill_hex else None
        tb_obj = _make_textbox(
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
        if getattr(tb, "rotation", 0.0) and tb_obj.object.textbox is not None:
            tb_obj.object.textbox.geometry.angle = float(tb.rotation)
        layered_items.append((getattr(tb, "z_index", 0), seq, [tb_obj]))
        seq += 1
        connector_rects[tb.id] = tb.rect

    caption_color = _rgba(theme.arrow_rgb)
    for box in frame.boxes:
        objs, _ = _make_box_objects(
            slide_prefix,
            box,
            theme,
            scale=frame.scale,
            caption_color=caption_color,
            corner_base_px=corner_px,
        )
        if getattr(box, "rotation", 0.0):
            for s_obj in objs:
                if s_obj.object.shape is not None:
                    s_obj.object.shape.geometry.angle = float(box.rotation)
                elif s_obj.object.textbox is not None:
                    s_obj.object.textbox.geometry.angle = float(box.rotation)
        layered_items.append((getattr(box, "z_index", 0), seq, objs))
        seq += 1
        connector_rects[box.id] = box.rect

    layered_items.sort(key=lambda item: (item[0], item[1]))
    for _, _, item_objs in layered_items:
        contents.extend(item_objs)

    for edge in frame.edges:
        if edge.from_id in connector_rects and edge.to_id in connector_rects:
            contents.extend(
                _make_edge_objects(
                    slide_prefix,
                    edge,
                    connector_rects,
                    theme,
                    scale=frame.scale,
                    arrow_base_width=arrow_w,
                )
            )

    return Slide(
        background=bg,
        contents=contents,
        depth=frame.depth,
        note=Text(string=frame.notes) if frame.notes else None,
    )


def _merge_style_config(
    deck_sc: StyleConfigSpec | None,
    scene_sc: StyleConfigSpec | None,
) -> StyleConfigSpec | None:
    if deck_sc is None and scene_sc is None:
        return None
    return StyleConfigSpec(
        title_max_size=(
            scene_sc.title_max_size if (scene_sc and scene_sc.title_max_size is not None)
            else (deck_sc.title_max_size if deck_sc else None)
        ),
        subtitle_size=(
            scene_sc.subtitle_size if (scene_sc and scene_sc.subtitle_size is not None)
            else (deck_sc.subtitle_size if deck_sc else None)
        ),
        card_corner_px=(
            scene_sc.card_corner_px if (scene_sc and scene_sc.card_corner_px is not None)
            else (deck_sc.card_corner_px if deck_sc else None)
        ),
        arrow_width=(
            scene_sc.arrow_width if (scene_sc and scene_sc.arrow_width is not None)
            else (deck_sc.arrow_width if deck_sc else None)
        ),
    )


def _apply_slide_overrides(slides: list[Slide], overrides: Mapping[str, Any]) -> None:
    """Apply per-object patch overrides (keyed by object identifier) without modifying compiler code."""
    for slide in slides:
        for item in slide.contents:
            target = item.object.shape or item.object.textbox or item.object.table or item.object.chart
            if target is None or not getattr(target, "identifier", None):
                continue
            patch = overrides.get(target.identifier)
            if not isinstance(patch, Mapping):
                continue
            geom = getattr(target, "geometry", None)
            if geom is not None:
                if "x" in patch:
                    geom.position.x = float(patch["x"])
                if "y" in patch:
                    geom.position.y = float(patch["y"])
                if "w" in patch:
                    geom.size.width = max(10.0, float(patch["w"]))
                if "h" in patch:
                    geom.size.height = max(10.0, float(patch["h"]))
                if "dx" in patch:
                    geom.position.x += float(patch["dx"])
                if "dy" in patch:
                    geom.position.y += float(patch["dy"])
                if "dw" in patch:
                    geom.size.width = max(10.0, geom.size.width + float(patch["dw"]))
                if "dh" in patch:
                    geom.size.height = max(10.0, geom.size.height + float(patch["dh"]))
            if "opacity" in patch and hasattr(target, "opacity"):
                target.opacity = max(0.0, min(1.0, float(patch["opacity"])))
            if "font_size" in patch and (item.object.shape is not None or item.object.textbox is not None):
                fs = float(patch["font_size"])
                sh = item.object.shape or item.object.textbox
                if getattr(sh, "paragraph_properties", None) and sh.paragraph_properties.character_properties:
                    sh.paragraph_properties.character_properties.font_size = fs
                if getattr(sh, "text", None) and getattr(sh.text, "paragraphs", None):
                    for para in sh.text.paragraphs:
                        if para.style and para.style.character_properties:
                            para.style.character_properties.font_size = fs


def _render_cover_slide(
    deck: DeckSpec,
    theme: ThemePreset,
    bg: SlideBackground,
    *,
    style_config: StyleConfigSpec | None = None,
) -> Slide:
    """Render an editorial cover slide with generous whitespace, optional kicker, accent bar, and meta footer."""
    cover = deck.cover
    assert cover is not None
    w = float(deck.slide_width)
    h = float(deck.slide_height)
    is_center = cover.align == "center"
    para_align = AlignmentType.CENTER if is_center else AlignmentType.LEFT
    margin_x = 140.0
    content_w = w - 2.0 * margin_x if is_center else min(1320.0, w - 2.0 * margin_x)
    content_x = (w - content_w) / 2.0 if is_center else margin_x

    title_txt = (cover.title or deck.title).strip()
    subtitle_txt = (
        cover.subtitle.strip()
        if cover.subtitle
        else (deck.story_model.core_question.strip() if (deck.story_model and deck.story_model.core_question) else "")
    )
    kicker_txt = cover.kicker.strip() if cover.kicker else ""
    meta_txt = cover.meta.strip() if cover.meta else ""

    max_title_sz = float(style_config.title_max_size) if (style_config and style_config.title_max_size is not None) else 72.0
    title_sz = min(max_title_sz, 72.0) if len(title_txt) <= 22 else (60.0 if len(title_txt) <= 38 else 50.0)
    title_lines = max(1, int((len(title_txt) * title_sz * 0.72) // max(content_w, 400.0)) + 1)
    title_h = max(96.0, title_lines * title_sz * 1.24)

    block_y = round(h * 0.30, 1)
    contents: list[SlideObject] = []

    # Subtle decorative background geometric ring on the right for asymmetrical editorial balance
    if not is_center:
        ring_sz = round(h * 0.54, 1)
        contents.append(
            SlideObject(
                object=CanvasObject(
                    shape=Shape(
                        identifier="cover_deco_ring",
                        geometry=Geometry(
                            position=Position(x=w - ring_sz * 0.62, y=(h - ring_sz) / 2.0),
                            size=Size(width=ring_sz, height=ring_sz),
                        ),
                        path=ShapePath(bezier=BezierPath(path="M 0.5,0 A 0.5,0.5 0 1 1 0.4999,0 Z")),
                        fill=Fill(color=Color(rgba=_rgba(theme.accent_border_rgb, 0.05))),
                        stroke=Stroke(line=Line(color=Color(rgba=_rgba(theme.accent_border_rgb, 0.22)), width=1.5, pattern=Pattern.SOLID)),
                        opacity=1.0,
                    )
                )
            )
        )

    cur_y = block_y
    if kicker_txt:
        contents.append(
            _make_textbox(
                "cover_kicker",
                BoxRect(content_x, cur_y, content_w, 34.0),
                kicker_txt,
                font_name=theme.font_body,
                font_size=20.0,
                color=_rgba(theme.accent_text_rgb),
                bold=True,
                alignment=para_align,
            )
        )
        cur_y += 46.0

    title_y = cur_y
    contents.append(
        _make_textbox(
            "cover_title",
            BoxRect(content_x, cur_y, content_w, title_h),
            title_txt,
            font_name=theme.font_title,
            font_size=title_sz,
            color=_rgba(theme.title_rgb),
            bold=True,
            alignment=para_align,
        )
    )
    cur_y += title_h + 22.0

    if subtitle_txt:
        sub_h = 84.0 if len(subtitle_txt) > 45 else 48.0
        contents.append(
            _make_textbox(
                "cover_subtitle",
                BoxRect(content_x, cur_y, content_w, sub_h),
                subtitle_txt,
                font_name=theme.font_body,
                font_size=28.0,
                color=_rgba(theme.subtitle_rgb),
                bold=False,
                alignment=para_align,
            )
        )
        cur_y += sub_h + 12.0

    if cover.accent_bar:
        if is_center:
            bar_w = 120.0
            contents.append(
                _make_solid_card(
                    "cover_accent_bar",
                    BoxRect((w - bar_w) / 2.0, block_y - 24.0, bar_w, 5.0),
                    fill_rgb=_rgba(theme.accent_border_rgb),
                    stroke=Stroke(empty=True),
                    corner_px=2.5,
                )
            )
        else:
            bar_h = max(80.0, cur_y - block_y - 12.0)
            contents.append(
                _make_solid_card(
                    "cover_accent_bar",
                    BoxRect(content_x - 28.0, block_y + 4.0, 6.0, bar_h),
                    fill_rgb=_rgba(theme.accent_border_rgb),
                    stroke=Stroke(empty=True),
                    corner_px=3.0,
                )
            )

    if meta_txt:
        footer_y = h - 130.0
        contents.append(
            _make_open_line_shape(
                "cover_divider",
                (content_x, footer_y - 16.0),
                (content_x + min(content_w, 520.0), footer_y - 16.0),
                color=_rgba(theme.card_border_rgb, 0.5),
                width=1.2,
                pattern=Pattern.SOLID,
                head=LineEnd.NONE,
            )
        )
        contents.append(
            _make_textbox(
                "cover_meta",
                BoxRect(content_x, footer_y, content_w, 34.0),
                meta_txt,
                font_name=theme.font_body,
                font_size=18.0,
                color=_rgba(theme.sublabel_rgb),
                bold=False,
                alignment=para_align,
            )
        )

    return Slide(
        background=bg,
        contents=contents,
        depth=0,
        note=Text(string=subtitle_txt or title_txt),
    )


def compile_deck(
    deck_or_raw: DeckSpec | dict[str, Any],
    output_path: str | Path,
    *,
    theme_override: str | None = None,
    use_templates: bool | None = None,
    overrides: Mapping[str, Any] | str | Path | None = None,
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
    if deck.cover is not None and deck.cover.enabled:
        slides.append(_render_cover_slide(deck, base_theme, default_bg, style_config=deck.style_config))
        slide_counter = 2
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
        eff_style = _merge_style_config(deck.style_config, scene.style_config)
        for frame in resolved_frames:
            slides.append(_render_slide(slide_counter, frame, scene_theme, scene_bg, style_config=eff_style))
            slide_counter += 1

    if overrides is not None:
        if isinstance(overrides, (str, Path)):
            ov_path = Path(overrides)
            ov_map = json.loads(ov_path.read_text(encoding="utf-8"))
        else:
            ov_map = overrides
        if isinstance(ov_map, Mapping):
            _apply_slide_overrides(slides, ov_map)

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

