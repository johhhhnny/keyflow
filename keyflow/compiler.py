"""Compile a native-first DeckSpec / SlideSpec into a validated .keyx file."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from creator_studio_doc_format.core import (
    RGBA,
    AlignmentType,
    Anchor,
    AreaChart,
    BarChart,
    BaselineType,
    BezierPath,
    BodyStrokeProperties,
    BubbleChart,
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
    ConnectionLine,
    Constituent,
    ContactShadow,
    CurvedShadow,
    DonutChart,
    DropShadow,
    End,
    Fill,
    Flavor,
    Geometry,
    Gradient,
    Group,
    HeaderFooterStrokeProperties,
    Hyperlink,
    Image,
    ImageFill,
    IndirectResource,
    Insets,
    KeynoteTheme,
    KeyxDocument,
    Label,
    LayoutProperties,
    LineChart,
    LineEnd,
    LineSpacingKindType,
    LineSpacingType,
    LineType,
    Linear,
    ListLabelType,
    ListNumberLabel,
    ListProperties,
    ListStringLabel,
    Magnet,
    Mask,
    MixedChart,
    MixedSeriesType,
    NumberFormatTypeKind,
    OverallProperties,
    Paragraph,
    ParagraphProperties,
    Pattern,
    PieChart,
    PlotDirection,
    Position,
    Presentation,
    Preset,
    RadarChart,
    Radial,
    Rect,
    Reflection,
    Resource,
    Row,
    ScatterChart,
    Shadow,
    Shape,
    Size,
    Slide,
    SlideBackground,
    SlideObject,
    SlideTarget,
    StackedAreaChart,
    StackedBarChart,
    StackedColumnChart,
    Stop,
    StrikethroughType,
    Stroke,
    Table,
    Technique,
    Text,
    Textbox,
    TextRun,
    UnderlineType,
    VerticalAlignmentType,
    VisualProperties,
)
from creator_studio_doc_format.core import Line as StrokeLine
from creator_studio_doc_format.core import Path as ShapePath
from creator_studio_doc_format.validation import validate_document

from keyflow.spec import (
    AnchorSpec,
    ChartAxisSpec,
    ChartSpec,
    ColorValue,
    ConnectionSpec,
    DeckSpec,
    FillValue,
    GeometrySpec,
    GradientFillSpec,
    GroupSpec,
    ImageFillSpec,
    ImageSpec,
    LineEndStyle,
    MagnetSide,
    ParagraphSpec,
    ReflectionSpec,
    ShadowSpec,
    ShapeSpec,
    SlideSpec,
    StrokeSpec,
    TableCellSpec,
    TableSpec,
    TextboxSpec,
    TextSpec,
    TextStyleSpec,
    VisualObjectSpec,
    parse_color,
)


_UNIT_SPACE = Rect(position=Position(x=0, y=0), size=Size(width=1, height=1))

_DEFAULT_CHART_PALETTE = [
    "#3B82F6",
    "#10B981",
    "#F59E0B",
    "#EF4444",
    "#8B5CF6",
    "#06B6D4",
    "#EC4899",
    "#84CC16",
]


@dataclass
class ObjectBounds:
    """Resolved bounding box of a compiled visual object."""

    id: str | None
    type: str
    slide_index: int
    x: float
    y: float
    w: float
    h: float


@dataclass
class CompileResult:
    """Result of compiling a DeckSpec into a .keyx file."""

    keyx_path: Path
    slide_count: int
    object_count: int
    objects: list[ObjectBounds] = field(default_factory=list)
    geometry_notes: list[str] = field(default_factory=list)


class _ResourceCollector:
    """Collects local image files into KeyxDocument resources."""

    def __init__(self) -> None:
        self._by_src: dict[str, str] = {}
        self.resources: dict[str, bytes] = {}

    def register(self, src: str) -> Resource:
        resolved = str(Path(src).expanduser().resolve())
        if resolved in self._by_src:
            return Resource(indirect=IndirectResource(filename=self._by_src[resolved]))
        p = Path(resolved)
        if not p.exists():
            raise FileNotFoundError(f"Image resource not found: {src}")
        filename = f"asset_{len(self._by_src) + 1}_{p.name}"
        self._by_src[resolved] = filename
        self.resources[filename] = p.read_bytes()
        return Resource(indirect=IndirectResource(filename=filename))


# ---------------------------------------------------------------------------
# Color, Fill, Stroke, Shadow, Reflection helpers
# ---------------------------------------------------------------------------


def _to_rgba(value: ColorValue) -> RGBA:
    r, g, b, a = parse_color(value)
    return RGBA(red=r, green=g, blue=b, alpha=a)


def _to_color(value: ColorValue) -> Color:
    return Color(rgba=_to_rgba(value))


def _to_fill(value: FillValue, resources: _ResourceCollector) -> Fill | None:
    if value is None:
        return None
    if isinstance(value, GradientFillSpec):
        stops = [
            Stop(color=_to_color(s.color), fraction=s.position) for s in value.stops
        ]
        flavor = (
            Flavor(
                radial=Radial(
                    start_point=Position(x=50, y=50),
                    end_point=Position(x=100, y=50),
                    base_natural_size=Size(width=100, height=100),
                )
            )
            if value.type == "radial"
            else Flavor(linear=Linear(angle=value.angle))
        )
        return Fill(gradient=Gradient(stops=stops, flavor=flavor))
    if isinstance(value, ImageFillSpec):
        tech_map = {
            "scale_to_fill": Technique.SCALE_TO_FILL,
            "scale_to_fit": Technique.SCALE_TO_FIT,
            "stretch": Technique.STRETCH,
            "original_size": Technique.NATURAL_SIZE,
            "tile": Technique.TILE,
        }
        return Fill(
            image=ImageFill(
                resource=resources.register(value.src),
                technique=tech_map[value.scale],
            )
        )
    return Fill(color=_to_color(value))


def _to_stroke(spec: StrokeSpec | None) -> Stroke:
    if spec is None:
        return Stroke(empty=True)
    r, g, b, a = parse_color(spec.color)
    rgba = RGBA(red=r, green=g, blue=b, alpha=a * spec.opacity)
    pattern_map = {
        "solid": Pattern.SOLID,
        "dashed": Pattern.MEDIUM_DASH,
        "dotted": Pattern.ROUND_DASH,
    }
    return Stroke(
        line=StrokeLine(
            color=Color(rgba=rgba),
            width=spec.width,
            pattern=pattern_map[spec.style],
        )
    )


def _to_shadow(spec: ShadowSpec | None) -> Shadow | None:
    if spec is None:
        return None
    color = _to_color(spec.color)
    if spec.type == "contact":
        return Shadow(
            contactShadow=ContactShadow(
                opacity=spec.opacity,
                color=color,
                offset=spec.offset,
                radius=spec.radius,
            )
        )
    if spec.type == "curved":
        return Shadow(
            curvedShadow=CurvedShadow(
                angle=spec.angle,
                opacity=spec.opacity,
                color=color,
                offset=spec.offset,
                radius=spec.radius,
            )
        )
    return Shadow(
        dropShadow=DropShadow(
            angle=spec.angle,
            opacity=spec.opacity,
            color=color,
            offset=spec.offset,
            radius=spec.radius,
        )
    )


def _to_reflection(spec: ReflectionSpec | None) -> Reflection | None:
    if spec is None:
        return None
    return Reflection(opacity=spec.opacity)


def _to_geometry(spec: GeometrySpec) -> Geometry:
    return Geometry(
        position=Position(x=spec.x, y=spec.y),
        size=Size(width=spec.w, height=spec.h),
        angle=spec.angle,
        horizontal_flip=spec.flip_h,
        vertical_flip=spec.flip_v,
    )


# ---------------------------------------------------------------------------
# Shape Paths
# ---------------------------------------------------------------------------


def _polygon_path(sides: int, *, start_deg: float = -90.0) -> str:
    r = 0.5
    step = 2 * math.pi / sides
    start = math.radians(start_deg)
    pts = [
        (
            round(0.5 + r * math.cos(start + step * k), 4),
            round(0.5 + r * math.sin(start + step * k), 4),
        )
        for k in range(sides)
    ]
    head, *tail = pts
    return f"M {head[0]},{head[1]} " + " ".join(f"L {x},{y}" for x, y in tail) + " Z"


def _star_path(points: int, inner_ratio: float) -> str:
    outer, inner = 0.5, 0.5 * inner_ratio
    step = math.pi / points
    start = math.radians(-90.0)
    pts: list[tuple[float, float]] = []
    for k in range(points * 2):
        r = outer if k % 2 == 0 else inner
        pts.append(
            (
                round(0.5 + r * math.cos(start + step * k), 4),
                round(0.5 + r * math.sin(start + step * k), 4),
            )
        )
    head, *tail = pts
    return f"M {head[0]},{head[1]} " + " ".join(f"L {x},{y}" for x, y in tail) + " Z"


def _rounded_rect_path(radius: float) -> str:
    r = max(0.0, min(0.5, radius))
    if r == 0.0:
        return "M 0,0 H 1 V 1 H 0 Z"
    return (
        f"M {r},0 H {1 - r} A {r},{r} 0 0 1 1,{r} V {1 - r} "
        f"A {r},{r} 0 0 1 {1 - r},1 H {r} A {r},{r} 0 0 1 0,{1 - r} "
        f"V {r} A {r},{r} 0 0 1 {r},0 Z"
    )


def _shape_path(spec: ShapeSpec) -> ShapePath:
    if spec.shape == "custom":
        if not spec.path:
            raise ValueError("ShapeSpec with shape='custom' requires 'path'")
        space = (
            Rect(
                position=Position(x=0, y=0),
                size=Size(width=spec.path_space.w, height=spec.path_space.h),
            )
            if spec.path_space
            else _UNIT_SPACE
        )
        return ShapePath(bezier=BezierPath(path=spec.path, space=space))

    builtin: dict[str, str] = {
        "rect": "M 0,0 H 1 V 1 H 0 Z",
        "rounded_rect": _rounded_rect_path(spec.corner_radius),
        "pill": _rounded_rect_path(0.5),
        "oval": "M 0,0.5 A 0.5,0.5 0 1 1 1,0.5 A 0.5,0.5 0 1 1 0,0.5 Z",
        "triangle": "M 0.5,0 L 1,1 L 0,1 Z",
        "diamond": "M 0.5,0 L 1,0.5 L 0.5,1 L 0,0.5 Z",
        "pentagon": _polygon_path(5),
        "hexagon": _polygon_path(6),
        "octagon": _polygon_path(8, start_deg=-67.5),
        "star": _star_path(spec.star_points, spec.star_inner_ratio),
        "arrow": "M 0,0.28 H 0.62 V 0.05 L 1,0.5 L 0.62,0.95 V 0.72 H 0 Z",
    }
    d = builtin[spec.shape]
    return ShapePath(bezier=BezierPath(path=d, space=_UNIT_SPACE))


# ---------------------------------------------------------------------------
# Text & Typography
# ---------------------------------------------------------------------------


_ALIGNMENT_MAP = {
    "left": AlignmentType.LEFT,
    "center": AlignmentType.CENTER,
    "right": AlignmentType.RIGHT,
    "justified": AlignmentType.JUSTIFIED,
}

_VALIGN_MAP = {
    "top": VerticalAlignmentType.TOP,
    "center": VerticalAlignmentType.CENTER,
    "bottom": VerticalAlignmentType.BOTTOM,
}


def _to_hyperlink(url: str | None) -> Hyperlink | None:
    if not url:
        return None
    if url.startswith("slide:"):
        idx = int(url.split(":", 1)[1])
        return Hyperlink(slide_jump=SlideTarget(slide_index=idx))
    return Hyperlink(url=url)


def _to_char_props(style: TextStyleSpec) -> CharacterProperties:
    baseline_map = {
        "normal": BaselineType.DEFAULT,
        "superscript": BaselineType.SUPERSCRIPT,
        "subscript": BaselineType.SUBSCRIPT,
    }
    return CharacterProperties(
        font_name=style.font,
        font_size=style.size,
        character_fill=Fill(color=_to_color(style.color)),
        bold=style.bold,
        italic=style.italic,
        underline=UnderlineType.SINGLE if style.underline else UnderlineType.NONE,
        strikethrough=(
            StrikethroughType.SINGLE if style.strikethrough else StrikethroughType.NONE
        ),
        tracking=style.tracking,
        baseline=baseline_map[style.baseline],
    )


def _to_paragraph(p: ParagraphSpec, default_style: TextStyleSpec) -> Paragraph:
    p_base_style = p.style or default_style
    constituents: list[Constituent] = []
    for r in p.runs:
        run_style = r.style or p_base_style
        char_props = _to_char_props(run_style)
        if run_style.hyperlink:
            # Hyperlink is attached on TextRun
            constituents.append(
                Constituent(
                    run=TextRun(
                        string=r.text,
                        style=char_props,
                        hyperlink=_to_hyperlink(run_style.hyperlink),
                    )
                )
            )
        else:
            constituents.append(
                Constituent(run=TextRun(string=r.text, style=char_props))
            )

    list_props = None
    if p.list_style and p.list_style.type != "none":
        if p.list_style.type == "bullet":
            label_type = ListLabelType(string=ListStringLabel(string=p.list_style.bullet))
        else:
            num_map = {
                "decimal": NumberFormatTypeKind.DECIMAL,
                "upper_alpha": NumberFormatTypeKind.UPPER_ALPHA,
                "lower_alpha": NumberFormatTypeKind.LOWER_ALPHA,
                "upper_roman": NumberFormatTypeKind.UPPER_ROMAN,
                "lower_roman": NumberFormatTypeKind.LOWER_ROMAN,
            }
            label_type = ListLabelType(
                number=ListNumberLabel(type=num_map[p.list_style.number_format])
            )
        list_props = ListProperties(
            label_type=label_type,
            list_level=p.list_style.level,
        )

    para_props = ParagraphProperties(
        alignment=_ALIGNMENT_MAP[p.alignment] if p.alignment else None,
        line_spacing=(
            LineSpacingType(value=p.line_spacing, kind=LineSpacingKindType.RELATIVE)
            if p.line_spacing
            else None
        ),
        space_before=p.space_before or None,
        space_after=p.space_after or None,
        list_properties=list_props,
    )
    return Paragraph(contents=constituents, style=para_props)


def _to_text_and_props(spec: TextSpec) -> tuple[Text, ParagraphProperties]:
    default_para_props = ParagraphProperties(
        alignment=_ALIGNMENT_MAP[spec.alignment],
        line_spacing=LineSpacingType(
            value=spec.line_spacing, kind=LineSpacingKindType.RELATIVE
        ),
        character_properties=_to_char_props(spec.style),
    )
    if spec.paragraphs is not None:
        paragraphs = [_to_paragraph(p, spec.style) for p in spec.paragraphs]
        return Text(paragraphs=paragraphs), default_para_props

    raw = spec.string or ""
    lines = raw.split("\n")
    paragraphs = [
        Paragraph(
            contents=[
                Constituent(
                    run=TextRun(
                        string=line,
                        style=_to_char_props(spec.style),
                        hyperlink=_to_hyperlink(spec.style.hyperlink),
                    )
                )
            ]
        )
        for line in lines
    ]
    return Text(paragraphs=paragraphs), default_para_props


# ---------------------------------------------------------------------------
# Object Compilers
# ---------------------------------------------------------------------------


def _compile_textbox(spec: TextboxSpec, resources: _ResourceCollector) -> CanvasObject:
    text_obj, para_props = _to_text_and_props(spec.text)
    return CanvasObject(
        textbox=Textbox(
            identifier=spec.id,
            geometry=_to_geometry(spec.geometry),
            fill=_to_fill(spec.fill, resources),
            stroke=_to_stroke(spec.stroke),
            shadow=_to_shadow(spec.shadow),
            reflection=_to_reflection(spec.reflection),
            opacity=spec.opacity,
            layout_properties=LayoutProperties(
                padding=Insets(
                    top=spec.padding.top,
                    bottom=spec.padding.bottom,
                    left=spec.padding.left,
                    right=spec.padding.right,
                ),
                vertical_alignment=_VALIGN_MAP[spec.vertical_alignment],
                shrink_to_fit=spec.shrink_to_fit,
            ),
            paragraph_properties=para_props,
            text=text_obj,
        )
    )


def _compile_shape(spec: ShapeSpec, resources: _ResourceCollector) -> CanvasObject:
    text_obj = None
    para_props = None
    layout_props = None
    if spec.text is not None:
        text_obj, para_props = _to_text_and_props(spec.text)
        layout_props = LayoutProperties(
            vertical_alignment=_VALIGN_MAP[spec.vertical_alignment],
        )
    return CanvasObject(
        shape=Shape(
            identifier=spec.id,
            geometry=_to_geometry(spec.geometry),
            path=_shape_path(spec),
            fill=_to_fill(spec.fill, resources),
            stroke=_to_stroke(spec.stroke),
            shadow=_to_shadow(spec.shadow),
            reflection=_to_reflection(spec.reflection),
            opacity=spec.opacity,
            layout_properties=layout_props,
            paragraph_properties=para_props,
            text=text_obj,
            title_is_positioned_on_top=spec.title_on_top,
        )
    )


_LINE_END_MAP: dict[LineEndStyle, LineEnd] = {
    "none": LineEnd.NONE,
    "filled_arrow": LineEnd.FILLED_ARROW,
    "open_arrow": LineEnd.OPEN_ARROW,
    "filled_circle": LineEnd.FILLED_CIRCLE,
    "open_circle": LineEnd.OPEN_CIRCLE,
    "filled_diamond": LineEnd.FILLED_DIAMOND,
    "open_diamond": LineEnd.FILLED_DIAMOND,
    "filled_square": LineEnd.FILLED_SQUARE,
    "open_square": LineEnd.OPEN_SQUARE,
}


def _to_magnet(side: MagnetSide) -> Magnet:
    if side == "north":
        return Magnet(north=True)
    if side == "south":
        return Magnet(south=True)
    if side == "east":
        return Magnet(east=True)
    if side == "west":
        return Magnet(west=True)
    if side == "center":
        return Magnet(center=True)
    return Magnet(edge=True)


def _to_anchor(spec: AnchorSpec | None) -> Anchor | None:
    if spec is None:
        return None
    return Anchor(object_id=spec.object_id, magnet=_to_magnet(spec.magnet))


def _compile_connection(spec: ConnectionSpec) -> CanvasObject:
    x0, y0 = spec.from_point
    x1, y1 = spec.to_point
    if spec.line_type == "curved":
        if spec.control_point is not None:
            cx, cy = spec.control_point
        else:
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0 - max(30.0, abs(x1 - x0) * 0.15)
        lt = LineType(curved=Position(x=cx, y=cy))
    elif spec.line_type == "orthogonal":
        cx, cy = spec.control_point if spec.control_point is not None else ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        lt = LineType(corner=Position(x=cx, y=cy))
    else:
        lt = LineType(straight=True)

    return CanvasObject(
        connectionLine=ConnectionLine(
            identifier=spec.id,
            line_type=lt,
            tail=End(
                end_point=Position(x=spec.from_point[0], y=spec.from_point[1]),
                anchor=_to_anchor(spec.from_anchor),
                line_end=_LINE_END_MAP[spec.tail_end],
            ),
            head=End(
                end_point=Position(x=spec.to_point[0], y=spec.to_point[1]),
                anchor=_to_anchor(spec.to_anchor),
                line_end=_LINE_END_MAP[spec.head_end],
            ),
            stroke=_to_stroke(spec.stroke),
            shadow=_to_shadow(spec.shadow),
            opacity=spec.opacity,
        )
    )


def _compile_image(spec: ImageSpec, resources: _ResourceCollector) -> CanvasObject:
    geom = _to_geometry(spec.geometry)
    mask = None
    if spec.mask_shape:
        if spec.mask_shape == "custom":
            if not spec.mask_path:
                raise ValueError("ImageSpec with mask_shape='custom' requires 'mask_path'")
            d = spec.mask_path
        elif spec.mask_shape == "oval":
            d = "M 0,0.5 A 0.5,0.5 0 1 1 1,0.5 A 0.5,0.5 0 1 1 0,0.5 Z"
        elif spec.mask_shape == "rounded_rect":
            d = _rounded_rect_path(spec.mask_corner_radius)
        else:
            d = "M 0,0 H 1 V 1 H 0 Z"
        mask = Mask(
            geometry=geom,
            path=ShapePath(bezier=BezierPath(path=d, space=_UNIT_SPACE)),
        )

    return CanvasObject(
        image=Image(
            identifier=spec.id,
            geometry=geom,
            resource=resources.register(spec.src),
            mask=mask,
            stroke=_to_stroke(spec.stroke) if spec.stroke else None,
            shadow=_to_shadow(spec.shadow),
            reflection=_to_reflection(spec.reflection),
            opacity=spec.opacity,
        )
    )


def _compile_table(spec: TableSpec) -> CanvasObject:
    visual = VisualProperties(
        overall_properties=OverallProperties(
            has_alternating_rows=spec.alternating_rows,
            alternating_rows_fill=Fill(color=_to_color(spec.alternating_fill)),
        ),
        body_stroke_properties=BodyStrokeProperties(
            horizontal_stroke=_to_stroke(spec.grid_stroke),
            vertical_stroke=_to_stroke(spec.grid_stroke),
            horizontal_border_stroke=_to_stroke(spec.border_stroke),
            vertical_border_stroke=_to_stroke(spec.border_stroke),
        ),
        header_row_cell_properties=CellProperties(
            fill=Fill(color=_to_color(spec.header_fill)),
            vertical_alignment=VerticalAlignmentType.CENTER,
            padding=Insets(top=10, bottom=10, left=14, right=14),
        ),
        header_row_text_properties=ParagraphProperties(
            alignment=AlignmentType.LEFT,
            character_properties=_to_char_props(spec.header_text),
        ),
        header_row_stroke_properties=HeaderFooterStrokeProperties(
            separator_stroke=_to_stroke(spec.border_stroke),
            separator_visible=True,
        ),
        body_cell_properties=CellProperties(
            vertical_alignment=VerticalAlignmentType.CENTER,
            padding=Insets(top=10, bottom=10, left=14, right=14),
        ),
        body_text_properties=ParagraphProperties(
            character_properties=_to_char_props(spec.body_text),
        ),
    )

    col_headers = [
        ColumnHeader(
            column_identifier=f"col_{i}",
            title=col.title,
            column_width=col.width,
            text_properties=ParagraphProperties(
                alignment=_ALIGNMENT_MAP[col.alignment],
                character_properties=_to_char_props(spec.body_text),
            ),
        )
        for i, col in enumerate(spec.columns)
    ]

    compiled_rows: list[Row] = []
    if spec.header_rows > 0:
        header_cells = [
            Cell(value=col.title) for col in spec.columns
        ]
        compiled_rows.append(Row(cells=header_cells))

    for row_data in spec.rows:
        cells: list[Cell] = []
        for item in row_data:
            if isinstance(item, TableCellSpec):
                c_props = (
                    CellProperties(fill=Fill(color=_to_color(item.fill)))
                    if item.fill
                    else None
                )
                t_props = None
                if item.text_color is not None or item.bold is not None:
                    base = spec.body_text.model_copy()
                    if item.text_color is not None:
                        base.color = item.text_color
                    if item.bold is not None:
                        base.bold = item.bold
                    t_props = ParagraphProperties(character_properties=_to_char_props(base))
                cells.append(
                    Cell(
                        value=item.value,
                        cell_properties=c_props,
                        text_properties=t_props,
                    )
                )
            else:
                cells.append(Cell(value=item))
        compiled_rows.append(Row(cells=cells))

    return CanvasObject(
        table=Table(
            identifier=spec.id,
            geometry=_to_geometry(spec.geometry),
            number_of_columns=len(col_headers),
            number_of_rows=len(compiled_rows),
            column_headers=col_headers,
            rows=compiled_rows,
            header_rows=spec.header_rows,
            visual_properties=visual,
        )
    )


def _to_axis_style(axis: ChartAxisSpec) -> ParagraphProperties:
    return ParagraphProperties(
        character_properties=CharacterProperties(
            font_size=axis.label_size,
            character_fill=Fill(color=_to_color(axis.label_color)),
        )
    )


def _compile_chart(spec: ChartSpec) -> CanvasObject:
    palette = spec.colors or _DEFAULT_CHART_PALETTE
    chart_colors = [
        ChartColor(fill=Fill(color=_to_color(palette[i % len(palette)])))
        for i in range(max(len(spec.series), len(palette)))
    ]

    row_labels = [s.name for s in spec.series]
    col_labels = spec.categories or [
        str(i + 1) for i in range(max(len(s.values) for s in spec.series))
    ]
    data = ChartData(
        chart_data_source=ChartDataSource.CHART_DATA_GRID,
        column_labels=col_labels,
        row_labels=row_labels,
        rows=[
            ChartDataRow(values=[ChartDataValue(number=v) for v in s.values])
            for s in spec.series
        ],
    )

    series_objs: list[ChartSeries] = []
    for i, s in enumerate(spec.series):
        s_color = s.color or palette[i % len(palette)]
        mixed_type = None
        if spec.chart_type == "mixed":
            mt_map = {
                "column": MixedSeriesType.COLUMN,
                "line": MixedSeriesType.LINE,
                "area": MixedSeriesType.AREA,
            }
            mixed_type = mt_map[s.mixed_type or "column"]
        series_objs.append(
            ChartSeries(
                mixed_series_type=mixed_type,
                fill=Fill(color=_to_color(s_color)),
            )
        )

    title_label = (
        Label(
            text=Text(string=spec.title),
            paragraph_properties=ParagraphProperties(
                character_properties=CharacterProperties(
                    font_size=spec.title_size,
                    bold=True,
                    character_fill=Fill(color=_to_color(spec.title_color)),
                )
            ),
        )
        if spec.title
        else None
    )

    legend_obj = (
        ChartLegend(
            label_text_style=ParagraphProperties(
                character_properties=CharacterProperties(
                    font_size=spec.legend_size,
                    character_fill=Fill(color=_to_color(spec.legend_color)),
                )
            )
        )
        if spec.legend
        else None
    )

    cat_axis = ChartCategoryAxis(
        title=spec.category_axis.title,
        show_title=bool(spec.category_axis.title),
        title_text_style=_to_axis_style(spec.category_axis),
        show_gridlines=spec.category_axis.show_gridlines,
        show_labels=spec.category_axis.show_labels,
        label_text_style=_to_axis_style(spec.category_axis),
    )
    val_axis = ChartValueAxis(
        title=spec.value_axis.title,
        show_title=bool(spec.value_axis.title),
        title_text_style=_to_axis_style(spec.value_axis),
        show_gridlines=spec.value_axis.show_gridlines,
        show_labels=spec.value_axis.show_labels,
        label_text_style=_to_axis_style(spec.value_axis),
        minimum=spec.value_axis.min_value,
        maximum=spec.value_axis.max_value,
    )

    common_kwargs: dict[str, Any] = {
        "identifier": spec.id,
        "geometry": _to_geometry(spec.geometry),
        "title": title_label,
        "data": data,
        "show_legend": spec.legend,
        "legend": legend_obj,
        "series": series_objs,
        "chart_colors": chart_colors,
    }

    ct = spec.chart_type
    if ct == "pie":
        chart_model = Chart(pie=PieChart(**common_kwargs))
    elif ct == "donut":
        chart_model = Chart(donut=DonutChart(**common_kwargs))
    elif ct == "scatter":
        chart_model = Chart(
            scatter=ScatterChart(
                **common_kwargs,
                value_axis_x=val_axis,
                value_axis_y=val_axis,
            )
        )
    elif ct == "bubble":
        chart_model = Chart(
            bubble=BubbleChart(
                **common_kwargs,
                value_axis_x=val_axis,
                value_axis_y=val_axis,
            )
        )
    elif ct == "radar":
        chart_model = Chart(
            radar=RadarChart(
                **common_kwargs,
                category_axis=cat_axis,
                value_axis=val_axis,
            )
        )
    elif ct == "bar":
        chart_model = Chart(
            bar=BarChart(**common_kwargs, category_axis=cat_axis, value_axis=val_axis)
        )
    elif ct == "line":
        chart_model = Chart(
            line=LineChart(**common_kwargs, category_axis=cat_axis, value_axis=val_axis)
        )
    elif ct == "area":
        chart_model = Chart(
            area=AreaChart(**common_kwargs, category_axis=cat_axis, value_axis=val_axis)
        )
    elif ct == "stacked_bar":
        chart_model = Chart(
            stacked_bar=StackedBarChart(
                **common_kwargs, category_axis=cat_axis, value_axis=val_axis
            )
        )
    elif ct == "stacked_column":
        chart_model = Chart(
            stacked_column=StackedColumnChart(
                **common_kwargs, category_axis=cat_axis, value_axis=val_axis
            )
        )
    elif ct == "stacked_area":
        chart_model = Chart(
            stacked_area=StackedAreaChart(
                **common_kwargs, category_axis=cat_axis, value_axis=val_axis
            )
        )
    elif ct == "mixed":
        chart_model = Chart(
            mixed=MixedChart(
                **common_kwargs, category_axis=cat_axis, value_axis=val_axis
            )
        )
    else:
        chart_model = Chart(
            column=ColumnChart(
                **common_kwargs, category_axis=cat_axis, value_axis=val_axis
            )
        )

    return CanvasObject(chart=chart_model)


def _compile_object(
    spec: VisualObjectSpec,
    resources: _ResourceCollector,
    slide_index: int,
    bounds_out: list[ObjectBounds],
) -> CanvasObject:
    if isinstance(spec, GroupSpec):
        children = [
            _compile_object(child, resources, slide_index, bounds_out)
            for child in spec.children
        ]
        title_label = Label(text=Text(string=spec.title)) if spec.title else None
        return CanvasObject(
            group=Group(
                identifier=spec.id,
                title=title_label,
                children=children,
                opacity=spec.opacity,
            )
        )

    if isinstance(spec, TextboxSpec):
        obj = _compile_textbox(spec, resources)
        g = spec.geometry
        bounds_out.append(ObjectBounds(spec.id, "textbox", slide_index, g.x, g.y, g.w, g.h))
        return obj
    if isinstance(spec, ShapeSpec):
        obj = _compile_shape(spec, resources)
        g = spec.geometry
        bounds_out.append(ObjectBounds(spec.id, "shape", slide_index, g.x, g.y, g.w, g.h))
        return obj
    if isinstance(spec, ConnectionSpec):
        obj = _compile_connection(spec)
        x0, y0 = spec.from_point
        x1, y1 = spec.to_point
        bounds_out.append(
            ObjectBounds(
                spec.id,
                "connection",
                slide_index,
                min(x0, x1),
                min(y0, y1),
                abs(x1 - x0),
                abs(y1 - y0),
            )
        )
        return obj
    if isinstance(spec, ImageSpec):
        obj = _compile_image(spec, resources)
        g = spec.geometry
        bounds_out.append(ObjectBounds(spec.id, "image", slide_index, g.x, g.y, g.w, g.h))
        return obj
    if isinstance(spec, TableSpec):
        obj = _compile_table(spec)
        g = spec.geometry
        bounds_out.append(ObjectBounds(spec.id, "table", slide_index, g.x, g.y, g.w, g.h))
        return obj
    if isinstance(spec, ChartSpec):
        obj = _compile_chart(spec)
        g = spec.geometry
        bounds_out.append(ObjectBounds(spec.id, "chart", slide_index, g.x, g.y, g.w, g.h))
        return obj

    raise TypeError(f"Unsupported visual object spec: {type(spec).__name__}")


# ---------------------------------------------------------------------------
# Public Compile Entrypoint
# ---------------------------------------------------------------------------


def compile_deck(
    spec: DeckSpec | SlideSpec | dict[str, Any],
    output_path: str | Path,
) -> CompileResult:
    """Compile a DeckSpec, SlideSpec, or raw dict into a validated .keyx file."""
    if isinstance(spec, dict):
        if "slides" in spec:
            deck = DeckSpec.model_validate(spec)
        else:
            deck = DeckSpec(slides=[SlideSpec.model_validate(spec)])
    elif isinstance(spec, SlideSpec):
        deck = DeckSpec(slides=[spec])
    else:
        deck = spec

    resources = _ResourceCollector()
    all_bounds: list[ObjectBounds] = []
    compiled_slides: list[Slide] = []

    for idx, slide_spec in enumerate(deck.slides):
        bg_fill = _to_fill(slide_spec.background, resources)
        slide_bg = SlideBackground(standard=bg_fill) if bg_fill else None
        contents = [
            SlideObject(
                object=_compile_object(obj, resources, idx, all_bounds)
            )
            for obj in slide_spec.objects
        ]
        compiled_slides.append(
            Slide(
                background=slide_bg,
                contents=contents,
                note=Text(string=slide_spec.note) if slide_spec.note else None,
            )
        )

    doc = KeyxDocument(
        payload=Presentation(
            theme=KeynoteTheme(name=deck.theme, locale=deck.locale),
            slide_size=Size(width=deck.slide_size.w, height=deck.slide_size.h),
            slides=compiled_slides,
        ),
        resources=resources.resources,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out, pre_save_hooks=[validate_document])

    # Factual geometry telemetry (never blocking, purely observational)
    notes: list[str] = []
    cw, ch = deck.slide_size.w, deck.slide_size.h
    for b in all_bounds:
        label = b.id or f"{b.type}@slide{b.slide_index}"
        if b.x < 0 or b.y < 0 or b.x + b.w > cw or b.y + b.h > ch:
            notes.append(
                f"slide {b.slide_index}: {label} extends outside canvas "
                f"({b.x:.0f},{b.y:.0f} {b.w:.0f}x{b.h:.0f} vs {cw:.0f}x{ch:.0f})"
            )

    return CompileResult(
        keyx_path=out.resolve(),
        slide_count=len(compiled_slides),
        object_count=len(all_bounds),
        objects=all_bounds,
        geometry_notes=notes,
    )
