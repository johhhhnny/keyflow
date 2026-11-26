"""Table object renderer for KeyFlow freeform canvas slides."""

from __future__ import annotations

from creator_studio_doc_format.core import (
    AlignmentType,
    BodyStrokeProperties,
    CanvasObject,
    Cell,
    CellProperties,
    CharacterProperties,
    Color,
    ColumnHeader,
    Fill,
    Geometry,
    Line,
    OverallProperties,
    Paragraph,
    ParagraphProperties,
    Pattern,
    Position,
    Rect,
    Row,
    Size,
    SlideObject,
    Stroke,
    Table,
    TableColumnHeaderKind,
    TableColumnHeaderVisibilityState,
    TableRowKind,
    TableRowVisibilityState,
    Text,
    TextRun,
    VerticalAlignmentType,
    VisualProperties,
)

from keyflow.layouts.types import BoxRect, PlacedTable
from keyflow.objects.helpers import _make_textbox, _readable_text_rgb, _rgba
from keyflow.objects.registry import register_object_renderer
from keyflow.themes import ThemePreset


@register_object_renderer("table")
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

    hdr_text_rgb = _readable_text_rgb(theme.flow_node_fill_rgb, theme.title_rgb)
    header_text_props = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_title,
            font_size=20.0,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(hdr_text_rgb))),
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
    hl_text_rgb = _readable_text_rgb(theme.accent_fill_rgb, theme.accent_text_rgb)
    highlight_text_props = ParagraphProperties(
        alignment=AlignmentType.CENTER,
        character_properties=CharacterProperties(
            font_name=theme.font_body,
            font_size=18.0,
            bold=True,
            character_fill=Fill(color=Color(rgba=_rgba(hl_text_rgb))),
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


