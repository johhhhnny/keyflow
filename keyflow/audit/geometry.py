"""Per-frame geometry, bounds, overlap, contrast, and text-overflow checks."""

from __future__ import annotations

from keyflow.audit.report import AuditFinding
from keyflow.layouts import BoxRect, PlacedBox, ResolvedFrame
from keyflow.themes import ThemePreset, contrast_ratio, hex_to_rgb_float
from keyflow.tokens import (
    CHART_BAR_SLOT_STEP_PT,
    CHART_GROUP_PAD_PT,
    CHART_MIN_CATEGORY_WIDTH_PT,
    MIN_CONTRAST_RATIO,
    MIN_READABLE_SCALE,
    MUTED_CARD_ALPHA,
    OVERLAP_TOLERANCE_PT,
)


def _text_units(text: str) -> float:
    return sum(1.8 if ord(ch) > 127 else 1.0 for ch in text)


def _overlap_area(a: BoxRect, b: BoxRect, tol: float = OVERLAP_TOLERANCE_PT) -> bool:
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
    if frame.scale < MIN_READABLE_SCALE:
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
        pf_top = min(
            [n.rect.y for n in frame.pinned_flow.nodes]
            + [g.rect.y for g in frame.pinned_flow.groups]
            + [g.legend_rect.y for g in frame.pinned_flow.groups]
        )
        title_bottom = 0.0
        if frame.title_rect is not None:
            title_bottom = max(title_bottom, frame.title_rect.y + frame.title_rect.h)
        if frame.subtitle and frame.subtitle_rect is not None:
            title_bottom = max(title_bottom, frame.subtitle_rect.y + frame.subtitle_rect.h)
        if title_bottom > pf_top + 4.0:
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
            min_cat_w = (
                max(CHART_MIN_CATEGORY_WIDTH_PT, len(ch.series) * CHART_BAR_SLOT_STEP_PT + CHART_GROUP_PAD_PT)
                if ch.chart_type == "column"
                else CHART_MIN_CATEGORY_WIDTH_PT
            )
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
            if ratio < MIN_CONTRAST_RATIO:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="low_contrast",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Shape '{sh.id}' text contrast ratio {ratio:.2f} is below {MIN_CONTRAST_RATIO:.1f}.",
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
            if ratio < MIN_CONTRAST_RATIO:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="low_contrast",
                        slide_num=slide_num,
                        scene_id=frame.scene_id,
                        frame_index=frame.frame_index,
                        message=f"Textbox '{tb.id}' contrast ratio {ratio:.2f} is below {MIN_CONTRAST_RATIO:.1f}.",
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
                    # Muted cards use MUTED_CARD_ALPHA over the slide background.
                    a = MUTED_CARD_ALPHA
                    bg_rgb = (
                        bg_rgb[0] * a + slide_bg[0] * (1.0 - a),
                        bg_rgb[1] * a + slide_bg[1] * (1.0 - a),
                        bg_rgb[2] * a + slide_bg[2] * (1.0 - a),
                    )
                ratio = contrast_ratio(fg, bg_rgb)
                if ratio < MIN_CONTRAST_RATIO:
                    findings.append(
                        AuditFinding(
                            severity="error",
                            category="low_contrast",
                            slide_num=slide_num,
                            scene_id=frame.scene_id,
                            frame_index=frame.frame_index,
                            message=f"Card '{box.id}' text contrast ratio {ratio:.2f} is below {MIN_CONTRAST_RATIO:.1f}.",
                            suggestion=f"Adjust fill_hex or color_hex to meet >= {MIN_CONTRAST_RATIO:.1f} contrast.",
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


