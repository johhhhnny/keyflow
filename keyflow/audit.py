"""Two-tier visual self-check engine for KeyFlow storyboards and compiled PNGs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from keyflow.layout import BoxRect, PlacedBox, ResolvedFrame, resolve_scene
from keyflow.pace import pace_deck
from keyflow.schema import DeckSpec, parse_deck, validate_deck
from keyflow.themes import (
    ThemePreset,
    apply_palette_overrides,
    contrast_ratio,
    get_theme,
    hex_to_rgb_float,
)

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """Single actionable geometry, stability, or readability finding on a slide."""

    severity: Severity
    category: str
    slide_num: int
    scene_id: str
    frame_index: int
    message: str
    suggestion: str
    target_id: str | None = None
    suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "category": self.category,
            "slide_num": self.slide_num,
            "scene_id": self.scene_id,
            "frame_index": self.frame_index,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        if self.target_id is not None:
            payload["target_id"] = self.target_id
        if self.suggested_action is not None:
            payload["suggested_action"] = self.suggested_action
        return payload


@dataclass(slots=True)
class AuditReport:
    """Visual self-check summary across every resolved slide of a deck."""

    slide_count: int
    errors: list[AuditFinding] = field(default_factory=list)
    warnings: list[AuditFinding] = field(default_factory=list)
    review_slides: list[int] = field(default_factory=list)
    min_scale: float = 1.0

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self, preview_paths: Sequence[Path | str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "passed": self.passed,
            "slide_count": self.slide_count,
            "min_scale": round(self.min_scale, 3),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [f.to_dict() for f in self.errors],
            "warnings": [f.to_dict() for f in self.warnings],
            "review_slides": list(self.review_slides),
        }
        if preview_paths is not None:
            paths = [str(p) for p in preview_paths]
            payload["review_pngs"] = [
                paths[idx - 1]
                for idx in self.review_slides
                if 1 <= idx <= len(paths)
            ]
        return payload


def _text_units(text: str) -> float:
    return sum(1.8 if ord(ch) > 127 else 1.0 for ch in text)


def _overlap_area(a: BoxRect, b: BoxRect, tol: float = 4.0) -> bool:
    ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return ox > tol and oy > tol


def _max_rect_delta(a: BoxRect, b: BoxRect) -> float:
    return max(abs(a.x - b.x), abs(a.y - b.y), abs(a.w - b.w), abs(a.h - b.h))


def _max_point_delta(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _check_rect_bounds(
    findings: list[AuditFinding],
    rect: BoxRect,
    label: str,
    *,
    slide_w: int,
    slide_h: int,
    slide_num: int,
    scene_id: str,
    frame_index: int,
    target_id: str | None = None,
    margin_x: float = 16.0,
    margin_y: float = 14.0,
) -> None:
    if rect.x < 0.0 or rect.y < 0.0 or rect.x + rect.w > slide_w or rect.y + rect.h > slide_h:
        findings.append(
            AuditFinding(
                severity="error",
                category="out_of_bounds",
                slide_num=slide_num,
                scene_id=scene_id,
                frame_index=frame_index,
                message=f"{label} extends outside canvas ({rect.x:.1f}, {rect.y:.1f}, {rect.w:.1f}x{rect.h:.1f}).",
                suggestion=f"Reduce node count, switch children to child_layout='grid', or split scene '{scene_id}'.",
                target_id=target_id,
                suggested_action="reduce_nodes_or_split_scene",
            )
        )
    elif (
        rect.x < margin_x
        or rect.y < margin_y
        or rect.x + rect.w > slide_w - margin_x
        or rect.y + rect.h > slide_h - margin_y
    ):
        findings.append(
            AuditFinding(
                severity="warning",
                category="out_of_bounds",
                slide_num=slide_num,
                scene_id=scene_id,
                frame_index=frame_index,
                message=f"{label} sits very close to canvas edge ({rect.x:.1f}, {rect.y:.1f}).",
                suggestion=f"Shorten labels or split scene '{scene_id}' for healthier breathing room.",
                target_id=target_id,
                suggested_action="shorten_label_or_split_scene",
            )
        )


def _audit_frame(
    frame: ResolvedFrame,
    *,
    slide_num: int,
    slide_w: int,
    slide_h: int,
    findings: list[AuditFinding],
    theme: ThemePreset | None = None,
) -> None:
    # 1. Scale check
    if frame.scale < 0.72:
        findings.append(
            AuditFinding(
                severity="warning",
                category="cramped_scale",
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                message=f"Scene '{frame.scene_id}' scaled down to {frame.scale:.2f}; typography may feel cramped.",
                suggestion="Limit each scene to <= 4-5 top-level nodes, use child_layout='grid', or split into two scenes.",
                target_id=frame.scene_id,
                suggested_action="use_grid_or_split_scene",
            )
        )

    # 2. Canvas bounds for title, subtitle, pinned_flow, boxes, labels, proportion_bar, matrix
    if frame.title_rect is not None:
        _check_rect_bounds(
            findings,
            frame.title_rect,
            "Title",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id="title",
        )
    if frame.subtitle and frame.subtitle_rect is not None:
        _check_rect_bounds(
            findings,
            frame.subtitle_rect,
            "Subtitle",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id="subtitle",
        )

    pf_bottom = 0.0
    if frame.pinned_flow is not None:
        for pn in frame.pinned_flow.nodes:
            pf_bottom = max(pf_bottom, pn.rect.y + pn.rect.h)
            _check_rect_bounds(
                findings,
                pn.rect,
                f"pinned_flow node '{pn.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=pn.id,
            )
        for pg in frame.pinned_flow.groups:
            pf_bottom = max(pf_bottom, pg.rect.y + pg.rect.h)
            _check_rect_bounds(
                findings,
                pg.rect,
                f"pinned_flow group '{pg.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=pg.id,
                margin_y=8.0,
            )
            _check_rect_bounds(
                findings,
                pg.legend_rect,
                f"pinned_flow legend '{pg.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=pg.id,
                margin_y=6.0,
            )

    solid_cards: list[PlacedBox] = []
    top_cards: list[PlacedBox] = []
    dashed_groups: list[PlacedBox] = []

    for box in frame.boxes:
        _check_rect_bounds(
            findings,
            box.rect,
            f"Box '{box.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=box.id,
        )
        if box.caption and box.caption_rect:
            _check_rect_bounds(
                findings,
                box.caption_rect,
                f"Group caption '{box.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=box.id,
            )

        if box.kind == "group_dashed":
            dashed_groups.append(box)
        else:
            solid_cards.append(box)
            if box.kind == "card":
                top_cards.append(box)
            # Estimate text wrap fit inside solid cards
            font_scale = max(0.74, frame.scale)
            base_size = 29.0 if box.kind == "subcard" else 34.0
            main_size = round(base_size * font_scale, 1)
            usable_w = max(box.rect.w - 28.0, 40.0)
            est_line_w = _text_units(box.label) * main_size * 0.56
            if est_line_w > usable_w * 2.25:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="text_overflow",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Card '{box.id}' label '{box.label}' may wrap excessively inside {box.rect.w:.0f}px width.",
                        suggestion=f"Shorten '{box.id}' label to 1-4 words (<= 12 CJK chars) and move details to 'note'.",
                        target_id=box.id,
                        suggested_action="shorten_label",
                    )
                )

    # 3. Pairwise overlap checks (excluding intentional parent group <-> own subcard nesting)
    for i, a in enumerate(solid_cards):
        for b in solid_cards[i + 1 :]:
            if _overlap_area(a.rect, b.rect):
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Cards '{a.id}' and '{b.id}' overlap.",
                        suggestion="Adjust node count/layout mode or report layout collision.",
                        target_id=f"{a.id},{b.id}",
                        suggested_action="adjust_layout_or_split_scene",
                    )
                )

    for i, ga in enumerate(dashed_groups):
        for gb in dashed_groups[i + 1 :]:
            if _overlap_area(ga.rect, gb.rect):
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Dashed groups '{ga.id}' and '{gb.id}' overlap.",
                        suggestion="Switch children to 'grid' or split modules across scenes.",
                        target_id=f"{ga.id},{gb.id}",
                        suggested_action="use_grid_children_or_split_scene",
                    )
                )
        for card in top_cards:
            if _overlap_area(ga.rect, card.rect):
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Dashed group '{ga.id}' overlaps top-level card '{card.id}'.",
                        suggestion="Reduce children density or split into separate scenes.",
                        target_id=ga.id,
                        suggested_action="reduce_children_or_split_scene",
                    )
                )

    # Edge label collisions against cards
    for edge in frame.edges:
        if not edge.label or edge.label_rect is None:
            continue
        _check_rect_bounds(
            findings,
            edge.label_rect,
            f"Edge label '{edge.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=edge.id,
        )
        for card in solid_cards:
            if _overlap_area(edge.label_rect, card.rect, tol=6.0):
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Edge '{edge.id}' label '{edge.label}' collides with card '{card.id}'.",
                        suggestion=f"Shorten edge '{edge.id}' label or omit redundant edge text.",
                        target_id=edge.id,
                        suggested_action="shorten_edge_label",
                    )
                )

    # Pinned top flow collision with scene header / content
    if frame.pinned_flow is not None and not frame.pinned_flow.is_centered and pf_bottom > 0.0:
        header_bottom = pf_bottom
        if frame.title_rect and frame.title_rect.y < header_bottom - 4.0:
            findings.append(
                AuditFinding(
                    severity="error",
                    category="overlap",
                    slide_num=slide_num,
                    scene_id=frame.scene_id,
                    frame_index=frame.frame_index,
                    message="Docked pinned_flow overlaps scene title area.",
                    suggestion="Reserve higher top offset when pinned_flow is active.",
                    target_id="title",
                    suggested_action="reserve_pinned_flow_margin",
                )
            )
        for box in frame.boxes:
            if box.rect.y < header_bottom - 4.0:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Docked pinned_flow overlaps box '{box.id}'.",
                        suggestion=f"Reduce vertical complexity in scene '{frame.scene_id}' so cards fit below pinned_flow.",
                        target_id=box.id,
                        suggested_action="reduce_scene_height",
                    )
                )

    # Proportion bar callouts & tiny segments
    if frame.proportion_bar is not None:
        pb = frame.proportion_bar
        vis_labels: list[tuple[str, BoxRect]] = []
        if pb.summary_box:
            _check_rect_bounds(
                findings,
                pb.summary_box,
                "proportion_bar summary_box",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id="proportion_bar.summary",
            )
        for item in pb.items:
            if not item.visible:
                continue
            _check_rect_bounds(
                findings,
                item.label_rect,
                f"proportion_bar callout '{item.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=item.id,
            )
            if item.seg_rect.w < 10.0:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="crowded_proportion",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Proportion segment '{item.id}' is very narrow ({item.seg_rect.w:.1f}px).",
                        suggestion="Merge tiny tail segments into an 'Other' bucket or narrow axis_min..axis_max range.",
                        target_id=item.id,
                        suggested_action="merge_small_segments",
                    )
                )
            for prev_id, prev_rect in vis_labels:
                if _overlap_area(prev_rect, item.label_rect, tol=2.0):
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            category="overlap",
                            slide_num=slide_num,
                            scene_id=frame.scene_id,
                            frame_index=frame.frame_index,
                            message=f"proportion_bar callouts '{prev_id}' and '{item.id}' overlap.",
                            suggestion="Shorten proportion item labels or merge adjacent tiny segments.",
                            target_id=f"{prev_id},{item.id}",
                            suggested_action="shorten_or_merge_labels",
                        )
                    )
            vis_labels.append((item.id, item.label_rect))

    # Comparison matrix column & formula checks
    if frame.comparison_matrix is not None:
        mx = frame.comparison_matrix
        if mx.formula_rect is not None:
            _check_rect_bounds(
                findings,
                mx.formula_rect,
                "comparison_matrix formula",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id="comparison_matrix.formula",
            )
        cols = mx.columns
        for idx, col in enumerate(cols):
            _check_rect_bounds(
                findings,
                col.box_rect,
                f"matrix column '{col.id}'",
                slide_w=slide_w,
                slide_h=slide_h,
                slide_num=slide_num,
                scene_id=frame.scene_id,
                frame_index=frame.frame_index,
                target_id=col.id,
            )
            if mx.formula_rect is not None and _overlap_area(mx.formula_rect, col.box_rect):
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"comparison_matrix formula overlaps column '{col.id}'.",
                        suggestion="Shorten formula text or reduce rows inside matrix columns.",
                        target_id=col.id,
                        suggested_action="shorten_formula_or_rows",
                    )
                )
            for other in cols[idx + 1 :]:
                if _overlap_area(col.box_rect, other.box_rect):
                    findings.append(
                        AuditFinding(
                            severity="error",
                            category="overlap",
                            slide_num=slide_num,
                            scene_id=frame.scene_id,
                            frame_index=frame.frame_index,
                            message=f"comparison_matrix columns '{col.id}' and '{other.id}' overlap.",
                            suggestion="Keep comparison_matrix to <= 3 columns with concise cell values.",
                            target_id=f"{col.id},{other.id}",
                            suggested_action="reduce_matrix_columns",
                        )
                    )

    # Freeform canvas objects: region frames, charts, tables, shapes, textboxes, contrast & collisions
    canvas_rects: list[tuple[str, BoxRect]] = [(b.id, b.rect) for b in top_cards]
    for ga in dashed_groups:
        canvas_rects.append((ga.id, ga.rect))

    for rf in frame.region_frames:
        _check_rect_bounds(
            findings,
            rf.rect,
            f"Region '{rf.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=rf.id,
        )

    for ch in frame.charts:
        _check_rect_bounds(
            findings,
            ch.rect,
            f"Chart '{ch.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=ch.id,
        )
        canvas_rects.append((ch.id, ch.rect))
        all_vals = [v for sr in ch.series for v in sr.values if v is not None]
        if ch.chart_type in ("pie", "donut"):
            if any(v < 0 for v in all_vals):
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="invalid_chart_data",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"{ch.chart_type} chart '{ch.id}' contains negative values.",
                        suggestion="Use non-negative values for pie/donut charts or switch to column/bar chart.",
                        target_id=ch.id,
                        suggested_action="fix_chart_values",
                    )
                )
            elif all_vals and sum(all_vals) <= 0:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="invalid_chart_data",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"{ch.chart_type} chart '{ch.id}' sums to zero.",
                        suggestion="Ensure at least one positive slice value.",
                        target_id=ch.id,
                        suggested_action="fix_chart_values",
                    )
                )
        if ch.chart_type in ("column", "stacked_column", "line", "area", "waterfall"):
            min_cat_w = max(56.0, len(ch.series) * 44.0 + 28.0) if ch.chart_type == "column" else 56.0
            if len(ch.categories) * min_cat_w > ch.rect.w:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="chart_crowded",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Chart '{ch.id}' has {len(ch.categories)} categories ({len(ch.series)} series) inside {ch.rect.w:.0f}px width.",
                        suggestion="Widen the chart region, group tail categories, or switch to horizontal bar chart.",
                        target_id=ch.id,
                        suggested_action="widen_chart_or_reduce_categories",
                    )
                )

    for tbl in frame.tables:
        _check_rect_bounds(
            findings,
            tbl.rect,
            f"Table '{tbl.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=tbl.id,
        )
        canvas_rects.append((tbl.id, tbl.rect))
        n_cols = max(1, len(tbl.headers))
        n_rows = 1 + len(tbl.rows)
        col_w = tbl.rect.w / n_cols
        row_h = tbl.rect.h / n_rows
        if col_w < 85.0 or row_h < 34.0:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="table_crowded",
                    slide_num=slide_num,
                    scene_id=frame.scene_id,
                    frame_index=frame.frame_index,
                    message=f"Table '{tbl.id}' cells are tight ({col_w:.0f}x{row_h:.0f}px).",
                    suggestion="Give the table a wider/taller region or reduce columns/rows.",
                    target_id=tbl.id,
                    suggested_action="reduce_table_density",
                )
            )

    for sh in frame.shapes:
        _check_rect_bounds(
            findings,
            sh.rect,
            f"Shape '{sh.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=sh.id,
        )
        canvas_rects.append((sh.id, sh.rect))
        if theme is not None and sh.label and (sh.fill_hex or sh.color_hex or frame.palette):
            fg = hex_to_rgb_float(sh.color_hex) if sh.color_hex else theme.text_rgb
            bg_rgb = hex_to_rgb_float(sh.fill_hex) if sh.fill_hex else theme.card_fill_rgb
            ratio = contrast_ratio(fg, bg_rgb)
            if ratio < 3.0:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="low_contrast",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Shape '{sh.id}' text contrast ratio {ratio:.2f} is below 3.0.",
                        suggestion="Adjust fill_hex or color_hex so text remains clearly legible.",
                        target_id=sh.id,
                        suggested_action="adjust_contrast",
                    )
                )

    for tb in frame.textboxes:
        _check_rect_bounds(
            findings,
            tb.rect,
            f"Textbox '{tb.id}'",
            slide_w=slide_w,
            slide_h=slide_h,
            slide_num=slide_num,
            scene_id=frame.scene_id,
            frame_index=frame.frame_index,
            target_id=tb.id,
        )
        canvas_rects.append((tb.id, tb.rect))
        est_w = _text_units(tb.text) * tb.font_size * 0.56
        lines = max(1.0, est_w / max(tb.rect.w - 16.0, 40.0))
        if lines * tb.font_size * 1.35 > tb.rect.h * 1.15:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="text_overflow",
                    slide_num=slide_num,
                    scene_id=frame.scene_id,
                    frame_index=frame.frame_index,
                    message=f"Textbox '{tb.id}' may overflow {tb.rect.w:.0f}x{tb.rect.h:.0f}px bounds.",
                    suggestion="Shorten text, lower font_size, or give this region more height.",
                    target_id=tb.id,
                    suggested_action="shorten_text_or_expand_region",
                )
            )
        if theme is not None and (tb.color_hex or tb.fill_hex or frame.palette):
            fg = hex_to_rgb_float(tb.color_hex) if tb.color_hex else theme.text_rgb
            bg_rgb = (
                hex_to_rgb_float(tb.fill_hex)
                if tb.fill_hex
                else (theme.bg_rgb[0] / 255.0, theme.bg_rgb[1] / 255.0, theme.bg_rgb[2] / 255.0)
            )
            ratio = contrast_ratio(fg, bg_rgb)
            if ratio < 3.0:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="low_contrast",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Textbox '{tb.id}' contrast ratio {ratio:.2f} is below 3.0.",
                        suggestion="Adjust color_hex/fill_hex or palette bg_hex for higher contrast.",
                        target_id=tb.id,
                        suggested_action="adjust_contrast",
                    )
                )

    if theme is not None:
        slide_bg = tuple(c / 255.0 for c in theme.bg_rgb)
        for box in top_cards:
            if box.fill_hex or box.color_hex or frame.palette:
                fg = hex_to_rgb_float(box.color_hex) if box.color_hex else theme.text_rgb
                bg_rgb = hex_to_rgb_float(box.fill_hex) if box.fill_hex else theme.card_fill_rgb
                if not box.fill_hex and box.variant == "muted":
                    # Muted cards use alpha=0.72 over the slide background.
                    a = 0.72
                    bg_rgb = (
                        bg_rgb[0] * a + slide_bg[0] * (1.0 - a),
                        bg_rgb[1] * a + slide_bg[1] * (1.0 - a),
                        bg_rgb[2] * a + slide_bg[2] * (1.0 - a),
                    )
                ratio = contrast_ratio(fg, bg_rgb)
                if ratio < 3.0:
                    findings.append(
                        AuditFinding(
                            severity="error",
                            category="low_contrast",
                            slide_num=slide_num,
                            scene_id=frame.scene_id,
                            frame_index=frame.frame_index,
                            message=f"Card '{box.id}' text contrast ratio {ratio:.2f} is below 3.0.",
                            suggestion="Adjust fill_hex or color_hex to meet >= 3.0 contrast.",
                            target_id=box.id,
                            suggested_action="adjust_contrast",
                        )
                    )
        for box in top_cards:
            if "__" in box.id and box.font_scale is not None and box.font_scale < 0.58:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="cramped_scale",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Inline diagram node '{box.id}' shrunk to scale {box.font_scale:.2f} (< 0.58).",
                        suggestion="Reduce nodes inside the inline diagram, shorten labels, or widen its region.",
                        target_id=box.id,
                        suggested_action="reduce_diagram_nodes_or_widen_region",
                    )
                )

    # Check collisions between heterogeneous freeform objects (e.g., chart vs card, table vs textbox)
    box_ids = {b.id for b in top_cards} | {g.id for g in dashed_groups}
    for i, (id_a, rect_a) in enumerate(canvas_rects):
        for id_b, rect_b in canvas_rects[i + 1 :]:
            if id_a in box_ids and id_b in box_ids:
                continue  # Already checked in box/group section above
            if _overlap_area(rect_a, rect_b):
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="overlap",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Canvas objects '{id_a}' and '{id_b}' overlap.",
                        suggestion="Assign objects to non-overlapping grid regions or let region arrange='stack'/'row'.",
                        target_id=f"{id_a},{id_b}",
                        suggested_action="adjust_regions_or_split_scene",
                    )
                )


def _emit_jitter(
    findings: list[AuditFinding],
    *,
    slide_num: int,
    scene_id: str,
    frame_index: int,
    target_id: str,
    message: str,
) -> None:
    findings.append(
        AuditFinding(
            severity="error",
            category="anchor_jitter",
            slide_num=slide_num,
            scene_id=scene_id,
            frame_index=frame_index,
            message=message,
            suggestion="Check layout solver final-bounds anchoring for this scene layout.",
            target_id=target_id,
            suggested_action="fix_layout_anchoring",
        )
    )


def _check_pinned_flow_pair(
    prev_pf: Any,
    next_pf: Any,
    *,
    slide_num: int,
    scene_id: str,
    frame_index: int,
    findings: list[AuditFinding],
) -> None:
    """Verify pinned_flow either stays anchored (same mode) or morphs smoothly between centered and docked."""
    prev_nodes = {n.id: n for n in prev_pf.nodes}
    next_nodes = {n.id: n for n in next_pf.nodes}
    prev_groups = {g.id: g for g in prev_pf.groups}
    next_groups = {g.id: g for g in next_pf.groups}
    prev_edges = {e.id: e for e in prev_pf.edges}
    next_edges = {e.id: e for e in next_pf.edges}

    if prev_pf.is_centered == next_pf.is_centered:
        for nid, nn in next_nodes.items():
            pn = prev_nodes.get(nid)
            if pn is not None:
                delta = _max_rect_delta(pn.rect, nn.rect)
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=scene_id,
                        frame_index=frame_index,
                        target_id=nid,
                        message=f"pinned_flow node '{nid}' shifted by {delta:.1f}pt across slides.",
                    )
        for gid, ng in next_groups.items():
            pg = prev_groups.get(gid)
            if pg is not None:
                delta = max(_max_rect_delta(pg.rect, ng.rect), _max_rect_delta(pg.legend_rect, ng.legend_rect))
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=scene_id,
                        frame_index=frame_index,
                        target_id=gid,
                        message=f"pinned_flow group '{gid}' shifted by {delta:.1f}pt across slides.",
                    )
        for eid, ne in next_edges.items():
            pe = prev_edges.get(eid)
            if pe is not None:
                delta = max(
                    _max_point_delta(pe.tail_center, ne.tail_center),
                    _max_point_delta(pe.head_center, ne.head_center),
                )
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=scene_id,
                        frame_index=frame_index,
                        target_id=eid,
                        message=f"pinned_flow edge '{eid}' shifted by {delta:.1f}pt across slides.",
                    )
        return

    # Intentional transition between centered macro overview and docked top ribbon:
    # every ribbon node must pair cleanly, and centered -> docked must move upward without growing taller.
    for nid, pn in prev_nodes.items():
        nn = next_nodes.get(nid)
        if nn is None:
            _emit_jitter(
                findings,
                slide_num=slide_num,
                scene_id=scene_id,
                frame_index=frame_index,
                target_id=nid,
                message=f"pinned_flow node '{nid}' disappeared during centered/docked transition.",
            )
            continue
        if prev_pf.is_centered and not next_pf.is_centered:
            if nn.rect.cy >= pn.rect.cy or nn.rect.h > pn.rect.h + 0.5:
                _emit_jitter(
                    findings,
                    slide_num=slide_num,
                    scene_id=scene_id,
                    frame_index=frame_index,
                    target_id=nid,
                    message=f"pinned_flow node '{nid}' failed to dock cleanly upward from centered state.",
                )
        elif not prev_pf.is_centered and next_pf.is_centered:
            if nn.rect.cy <= pn.rect.cy:
                _emit_jitter(
                    findings,
                    slide_num=slide_num,
                    scene_id=scene_id,
                    frame_index=frame_index,
                    target_id=nid,
                    message=f"pinned_flow node '{nid}' failed to expand cleanly downward to centered state.",
                )


def _audit_scene_anchor_stability(
    scene_frames: list[ResolvedFrame],
    start_slide_num: int,
    findings: list[AuditFinding],
) -> None:
    """Verify persistent elements (boxes, edges, dividers, charts, matrices, ribbon) stay anchored across frames."""
    for f_idx in range(len(scene_frames) - 1):
        cur = scene_frames[f_idx]
        nxt = scene_frames[f_idx + 1]
        slide_num = start_slide_num + f_idx + 1
        cur_map = {b.id: b for b in cur.boxes}
        nxt_map = {b.id: b for b in nxt.boxes}

        for nb in nxt.boxes:
            pb = cur_map.get(nb.id)
            if pb is None or pb.kind != nb.kind:
                continue
            delta = _max_rect_delta(pb.rect, nb.rect)
            if pb.caption_rect is not None and nb.caption_rect is not None:
                delta = max(delta, _max_rect_delta(pb.caption_rect, nb.caption_rect))
            if delta > 0.5:
                _emit_jitter(
                    findings,
                    slide_num=slide_num,
                    scene_id=cur.scene_id,
                    frame_index=f_idx + 1,
                    target_id=nb.id,
                    message=f"Box '{nb.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                )

        # Persistent edges/connectors whose endpoints did not collapse/expand across the frame step
        cur_edges = {e.id: e for e in cur.edges}
        cur_rects = {b.id: (b.kind, b.rect) for b in cur.boxes}
        nxt_rects = {b.id: (b.kind, b.rect) for b in nxt.boxes}
        for group_name, cur_items, nxt_items in (
            ("chart", cur.charts, nxt.charts),
            ("table", cur.tables, nxt.tables),
            ("shape", cur.shapes, nxt.shapes),
            ("textbox", cur.textboxes, nxt.textboxes),
        ):
            for it in cur_items:
                cur_rects[it.id] = (group_name, it.rect)
            for it in nxt_items:
                nxt_rects[it.id] = (group_name, it.rect)

        for ne in nxt.edges:
            pe = cur_edges.get(ne.id)
            if pe is None:
                continue
            pf_entry = cur_rects.get(pe.from_id)
            nf_entry = nxt_rects.get(ne.from_id)
            pt_entry = cur_rects.get(pe.to_id)
            nt_entry = nxt_rects.get(ne.to_id)
            if (
                pf_entry is None
                or nf_entry is None
                or pt_entry is None
                or nt_entry is None
                or pf_entry[0] != nf_entry[0]
                or pt_entry[0] != nt_entry[0]
            ):
                continue
            delta = max(
                _max_point_delta(pe.tail_center, ne.tail_center),
                _max_point_delta(pe.head_center, ne.head_center),
            )
            if pe.curve_control is not None and ne.curve_control is not None:
                delta = max(delta, _max_point_delta(pe.curve_control, ne.curve_control))
            if pe.label_rect is not None and ne.label_rect is not None:
                delta = max(delta, _max_rect_delta(pe.label_rect, ne.label_rect))
            if delta > 0.5:
                _emit_jitter(
                    findings,
                    slide_num=slide_num,
                    scene_id=cur.scene_id,
                    frame_index=f_idx + 1,
                    target_id=ne.id,
                    message=f"Edge '{ne.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                )

        # Freeform charts, tables, shapes, and textboxes anchor & axis stability
        for kind_label, cur_list, nxt_list in (
            ("Chart", cur.charts, nxt.charts),
            ("Table", cur.tables, nxt.tables),
            ("Shape", cur.shapes, nxt.shapes),
            ("Textbox", cur.textboxes, nxt.textboxes),
        ):
            c_by_id = {it.id: it for it in cur_list}
            for nit in nxt_list:
                cit = c_by_id.get(nit.id)
                if cit is None:
                    continue
                delta = _max_rect_delta(cit.rect, nit.rect)
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        target_id=nit.id,
                        message=f"{kind_label} '{nit.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                    )
                if kind_label == "Chart":
                    if cit.axis_min != nit.axis_min or cit.axis_max != nit.axis_max:  # type: ignore[attr-defined]
                        _emit_jitter(
                            findings,
                            slide_num=slide_num,
                            scene_id=cur.scene_id,
                            frame_index=f_idx + 1,
                            target_id=nit.id,
                            message=f"Chart '{nit.id}' value axis bounds changed between frames {f_idx} and {f_idx + 1}.",
                        )
                    if len(cit.series) != len(nit.series) or cit.categories != nit.categories:  # type: ignore[attr-defined]
                        _emit_jitter(
                            findings,
                            slide_num=slide_num,
                            scene_id=cur.scene_id,
                            frame_index=f_idx + 1,
                            target_id=nit.id,
                            message=f"Chart '{nit.id}' slot dimensions changed between frames {f_idx} and {f_idx + 1}.",
                        )
                    if cit.use_vector != nit.use_vector:  # type: ignore[attr-defined]
                        _emit_jitter(
                            findings,
                            slide_num=slide_num,
                            scene_id=cur.scene_id,
                            frame_index=f_idx + 1,
                            target_id=nit.id,
                            message=f"Chart '{nit.id}' render mode changed between frames {f_idx} and {f_idx + 1}.",
                        )

        # Dividers
        if len(cur.dividers) == len(nxt.dividers):
            for idx, (pd, nd) in enumerate(zip(cur.dividers, nxt.dividers)):
                if pd.label != nd.label:
                    continue
                delta = max(abs(pd.x - nd.x), abs(pd.y_top - nd.y_top), abs(pd.y_bottom - nd.y_bottom))
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        target_id=f"divider_{idx}",
                        message=f"Divider '{nd.label or idx}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                    )

        # Proportion bar items & axis
        if cur.proportion_bar is not None and nxt.proportion_bar is not None:
            cpb = cur.proportion_bar
            npb = nxt.proportion_bar
            axis_delta = max(
                _max_point_delta(cpb.axis_start, npb.axis_start),
                _max_point_delta(cpb.axis_end, npb.axis_end),
                abs(cpb.bar_y - npb.bar_y),
                abs(cpb.bar_h - npb.bar_h),
            )
            if axis_delta > 0.5:
                _emit_jitter(
                    findings,
                    slide_num=slide_num,
                    scene_id=cur.scene_id,
                    frame_index=f_idx + 1,
                    target_id="proportion_bar",
                    message=f"proportion_bar axis shifted by {axis_delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                )
            cur_items = {it.id: it for it in cpb.items if it.visible}
            for nit in npb.items:
                if not nit.visible:
                    continue
                cit = cur_items.get(nit.id)
                if cit is None:
                    continue
                delta = max(_max_rect_delta(cit.seg_rect, nit.seg_rect), _max_rect_delta(cit.label_rect, nit.label_rect))
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        target_id=nit.id,
                        message=f"proportion_bar item '{nit.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                    )

        # Comparison matrix columns & formula
        if cur.comparison_matrix is not None and nxt.comparison_matrix is not None:
            cmx = cur.comparison_matrix
            nmx = nxt.comparison_matrix
            if cmx.formula_rect is not None and nmx.formula_rect is not None:
                f_delta = _max_rect_delta(cmx.formula_rect, nmx.formula_rect)
                if f_delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        target_id="comparison_matrix.formula",
                        message=f"comparison_matrix formula shifted by {f_delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                    )
            cur_cols = {c.id: c for c in cmx.columns}
            for ncol in nmx.columns:
                ccol = cur_cols.get(ncol.id)
                if ccol is None:
                    continue
                delta = max(
                    _max_rect_delta(ccol.box_rect, ncol.box_rect),
                    _max_rect_delta(ccol.caption_rect, ncol.caption_rect),
                )
                if delta > 0.5:
                    _emit_jitter(
                        findings,
                        slide_num=slide_num,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        target_id=ncol.id,
                        message=f"matrix column '{ncol.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                    )

        # Pinned flow intra-scene stability
        if cur.pinned_flow is not None and nxt.pinned_flow is not None:
            _check_pinned_flow_pair(
                cur.pinned_flow,
                nxt.pinned_flow,
                slide_num=slide_num,
                scene_id=cur.scene_id,
                frame_index=f_idx + 1,
                findings=findings,
            )


def _audit_deck_pinned_flow_stability(
    all_frames: list[ResolvedFrame],
    findings: list[AuditFinding],
) -> None:
    """Verify deck-level pinned_flow transitions cleanly across consecutive slides across scene boundaries."""
    for idx in range(len(all_frames) - 1):
        cur = all_frames[idx]
        nxt = all_frames[idx + 1]
        if cur.scene_id == nxt.scene_id:
            continue
        if cur.pinned_flow is not None and nxt.pinned_flow is not None:
            _check_pinned_flow_pair(
                cur.pinned_flow,
                nxt.pinned_flow,
                slide_num=idx + 2,
                scene_id=nxt.scene_id,
                frame_index=nxt.frame_index,
                findings=findings,
            )


def select_review_slides(
    scene_frame_ranges: list[tuple[str, int, int]],
    findings: Sequence[AuditFinding],
) -> list[int]:
    """Select key slides (all flagged slides + slide 1 + final frame of each scene) for PNG visual review."""
    chosen: set[int] = set()
    for f in findings:
        chosen.add(f.slide_num)
    if scene_frame_ranges:
        chosen.add(1)
    for _, first_slide, count in scene_frame_ranges:
        if count >= 1:
            chosen.add(first_slide + count - 1)
    return sorted(chosen)


_FACTUAL_BADGES = ("FACT", "REPORTED", "VERIFIED", "DATA", "事实", "已证实")


def _badge_is_factual(badge: str | None) -> bool:
    if not badge:
        return False
    upper = badge.strip().upper()
    return any(upper.startswith(prefix) for prefix in _FACTUAL_BADGES)


def _audit_story_fidelity(
    deck: DeckSpec,
    scene_ranges: list[tuple[str, int, int]],
    findings: list[AuditFinding],
) -> None:
    """Verify Stage 0 story_model alignment: source quotes, epistemic tags, metric-scope purity, and zero dropped claims."""
    sm = deck.story_model
    if sm is None or not sm.claims:
        return

    claims_by_id = {c.id: c for c in sm.claims}
    referenced_ids: set[str] = set()

    for scene, (_, first_slide, _) in zip(deck.scenes, scene_ranges):
        scene_scopes: set[str] = set()
        if scene.metric_scope:
            scene_scopes.add(scene.metric_scope)

        def _inspect_refs(target_id: str, refs: Sequence[str], badge: str | None = None) -> None:
            for cid in refs:
                referenced_ids.add(cid)
                cl = claims_by_id.get(cid)
                if cl is None:
                    continue
                if cl.metric_scope:
                    scene_scopes.add(cl.metric_scope)
                if badge and _badge_is_factual(badge) and cl.type in ("inference", "thesis", "example"):
                    findings.append(
                        AuditFinding(
                            severity="error",
                            category="epistemic_mismatch",
                            slide_num=first_slide,
                            scene_id=scene.id,
                            frame_index=0,
                            message=f"Element '{target_id}' carries factual badge '{badge}' while referencing {cl.type} claim '{cid}'.",
                            suggestion=f"Change badge on '{target_id}' to '{cl.type.upper()}' or reference a verified 'fact' claim.",
                            target_id=target_id,
                            suggested_action="mark_as_inference_or_thesis",
                        )
                    )

        _inspect_refs(scene.id, scene.evidence_refs)
        for obj in scene.objects:
            _inspect_refs(obj.id, obj.evidence_refs, obj.badge)
            if obj.diagram is not None:
                for node in obj.diagram.nodes:
                    _inspect_refs(f"{obj.id}__{node.id}", node.evidence_refs, node.badge)
                    for child in node.children:
                        _inspect_refs(f"{obj.id}__{node.id}__{child.id}", child.evidence_refs, child.badge)
        for node in scene.nodes:
            _inspect_refs(node.id, node.evidence_refs, node.badge)
            for child in node.children:
                _inspect_refs(f"{node.id}__{child.id}", child.evidence_refs, child.badge)
        if scene.proportion_bar is not None:
            for item in scene.proportion_bar.items:
                _inspect_refs(item.id, item.evidence_refs)
        if scene.matrix is not None:
            for col in scene.matrix.columns:
                _inspect_refs(col.id, col.evidence_refs)

        if len(scene_scopes) > 1:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="scope_mixing",
                    slide_num=first_slide,
                    scene_id=scene.id,
                    frame_index=0,
                    message=f"Scene '{scene.id}' mixes multiple metric scopes: {', '.join(sorted(scene_scopes))}.",
                    suggestion=f"Split distinct denominators/metric_scopes across separate scenes instead of mixing them in '{scene.id}'.",
                    target_id=scene.id,
                    suggested_action="split_metric_scopes",
                )
            )

    for cl in sm.claims:
        if cl.type == "fact" and not cl.source_quote and not cl.source_id:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="unsourced_fact",
                    slide_num=1,
                    scene_id="",
                    frame_index=0,
                    message=f"Fact claim '{cl.id}' is missing 'source_quote' or 'source_id'.",
                    suggestion=f"Attach a verbatim 'source_quote' or 'source_id' to fact claim '{cl.id}'.",
                    target_id=cl.id,
                    suggested_action="add_source_quote",
                )
            )

    if referenced_ids:
        for cl in sm.claims:
            if cl.type in ("thesis", "counter_evidence") and cl.id not in referenced_ids:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="dropped_story_claim",
                        slide_num=1,
                        scene_id="",
                        frame_index=0,
                        message=f"Critical {cl.type} claim '{cl.id}' in story_model is not referenced by any scene.",
                        suggestion=f"Reference '{cl.id}' via 'evidence_refs' in a scene so Stage 0 key arguments are not dropped.",
                        target_id=cl.id,
                        suggested_action="reference_claim_in_scene",
                    )
                )


def audit_deck(
    deck_or_raw: DeckSpec | dict[str, Any],
    *,
    strict: bool = False,
    use_templates: bool | None = None,
) -> AuditReport:
    """Run Tier 1 deterministic geometry, stability, contrast, and readability audit on a deck."""
    if isinstance(deck_or_raw, dict):
        validation = validate_deck(deck_or_raw, use_templates=use_templates)
        if not validation.valid:
            findings = [
                AuditFinding(
                    severity="error",
                    category="schema_invalid",
                    slide_num=1,
                    scene_id="",
                    frame_index=0,
                    message=err,
                    suggestion="Fix schema validation errors reported by `keyflow validate` first.",
                    suggested_action="fix_schema",
                )
                for err in validation.errors
            ]
            return AuditReport(slide_count=0, errors=findings, review_slides=[])
        materialized = pace_deck(deck_or_raw, overwrite_existing=False)
        deck = parse_deck(materialized)
    else:
        deck = deck_or_raw

    base_theme = apply_palette_overrides(get_theme(deck.theme), deck.palette)
    all_findings: list[AuditFinding] = []
    all_frames: list[ResolvedFrame] = []
    scene_ranges: list[tuple[str, int, int]] = []
    slide_num = 1
    min_scale = 1.0

    for scene in deck.scenes:
        scene_theme = apply_palette_overrides(base_theme, scene.palette)
        resolved = resolve_scene(
            scene,
            deck.slide_width,
            deck.slide_height,
            pinned_flow=deck.pinned_flow,
        )
        scene_ranges.append((scene.id, slide_num, len(resolved)))
        all_frames.extend(resolved)
        for frame in resolved:
            min_scale = min(min_scale, frame.scale)
            _audit_frame(
                frame,
                slide_num=slide_num,
                slide_w=deck.slide_width,
                slide_h=deck.slide_height,
                findings=all_findings,
                theme=scene_theme,
            )
            slide_num += 1
        _audit_scene_anchor_stability(resolved, scene_ranges[-1][1], all_findings)

    _audit_deck_pinned_flow_stability(all_frames, all_findings)
    _audit_story_fidelity(deck, scene_ranges, all_findings)

    errors: list[AuditFinding] = []
    warnings: list[AuditFinding] = []
    for item in all_findings:
        if item.severity == "error" or strict:
            errors.append(item)
        else:
            warnings.append(item)

    review_slides = select_review_slides(scene_ranges, all_findings)
    return AuditReport(
        slide_count=slide_num - 1,
        errors=errors,
        warnings=warnings,
        review_slides=review_slides,
        min_scale=min_scale,
    )
