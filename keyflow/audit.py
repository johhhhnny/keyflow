"""Two-tier visual self-check engine for KeyFlow storyboards and compiled PNGs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from keyflow.layout import BoxRect, PlacedBox, ResolvedFrame, resolve_scene
from keyflow.pace import pace_deck
from keyflow.schema import DeckSpec, parse_deck, validate_deck

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "slide_num": self.slide_num,
            "scene_id": self.scene_id,
            "frame_index": self.frame_index,
            "message": self.message,
            "suggestion": self.suggestion,
        }


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
            )
        )


def _audit_frame(
    frame: ResolvedFrame,
    *,
    slide_num: int,
    slide_w: int,
    slide_h: int,
    findings: list[AuditFinding],
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
                        )
                    )


def _audit_scene_anchor_stability(
    scene_frames: list[ResolvedFrame],
    start_slide_num: int,
    findings: list[AuditFinding],
) -> None:
    """Verify persistent elements never shift coordinates across consecutive frames in a scene."""
    for f_idx in range(len(scene_frames) - 1):
        cur = scene_frames[f_idx]
        nxt = scene_frames[f_idx + 1]
        cur_map = {b.id: b for b in cur.boxes}
        for nb in nxt.boxes:
            pb = cur_map.get(nb.id)
            if pb is None or pb.kind != nb.kind:
                continue
            delta = max(
                abs(pb.rect.x - nb.rect.x),
                abs(pb.rect.y - nb.rect.y),
                abs(pb.rect.w - nb.rect.w),
                abs(pb.rect.h - nb.rect.h),
            )
            if delta > 0.5:
                findings.append(
                    AuditFinding(
                        severity="error",
                        category="anchor_jitter",
                        slide_num=start_slide_num + f_idx + 1,
                        scene_id=cur.scene_id,
                        frame_index=f_idx + 1,
                        message=f"Box '{nb.id}' shifted by {delta:.1f}pt between frames {f_idx} and {f_idx + 1}.",
                        suggestion="Check layout solver final-bounds anchoring for this scene layout.",
                    )
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


def audit_deck(
    deck_or_raw: DeckSpec | dict[str, Any],
    *,
    strict: bool = False,
) -> AuditReport:
    """Run Tier 1 deterministic geometry, stability, and readability audit on a deck."""
    if isinstance(deck_or_raw, dict):
        validation = validate_deck(deck_or_raw)
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
                )
                for err in validation.errors
            ]
            return AuditReport(slide_count=0, errors=findings, review_slides=[])
        materialized = pace_deck(deck_or_raw, overwrite_existing=False)
        deck = parse_deck(materialized)
    else:
        deck = deck_or_raw

    all_findings: list[AuditFinding] = []
    scene_ranges: list[tuple[str, int, int]] = []
    slide_num = 1
    min_scale = 1.0

    for scene in deck.scenes:
        resolved = resolve_scene(
            scene,
            deck.slide_width,
            deck.slide_height,
            pinned_flow=deck.pinned_flow,
        )
        scene_ranges.append((scene.id, slide_num, len(resolved)))
        for frame in resolved:
            min_scale = min(min_scale, frame.scale)
            _audit_frame(
                frame,
                slide_num=slide_num,
                slide_w=deck.slide_width,
                slide_h=deck.slide_height,
                findings=all_findings,
            )
            slide_num += 1
        _audit_scene_anchor_stability(resolved, scene_ranges[-1][1], all_findings)

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
