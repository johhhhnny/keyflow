"""Modular visual, anchor-stability, story-fidelity, and cross-page consistency audit engine."""

from __future__ import annotations

from typing import Any

from keyflow.audit.consistency import _audit_cross_page_consistency
from keyflow.audit.geometry import (
    _audit_frame,
    _audit_theme_aesthetics,
    _check_rect_bounds,
    _max_point_delta,
    _max_rect_delta,
    _overlap_area,
    _text_units,
)
from keyflow.audit.report import AuditFinding, AuditReport, Severity, select_review_slides
from keyflow.audit.stability import (
    _audit_deck_pinned_flow_stability,
    _audit_scene_anchor_stability,
    _check_pinned_flow_pair,
    _emit_jitter,
)
from keyflow.audit.story_fidelity import _audit_story_fidelity, _badge_is_factual
from keyflow.layouts import ResolvedFrame, resolve_scene
from keyflow.pace import pace_deck
from keyflow.schema import DeckSpec, parse_deck, validate_deck
from keyflow.themes import apply_palette_overrides, get_theme


def audit_deck(
    deck_or_raw: DeckSpec | dict[str, Any],
    *,
    strict: bool = False,
    use_templates: bool | None = None,
) -> AuditReport:
    """Run Tier 1 deterministic geometry, stability, contrast, and consistency audit on a deck."""
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
    _audit_theme_aesthetics(base_theme, scene_id=deck.scenes[0].id if deck.scenes else "", slide_num=1, findings=all_findings)
    all_frames: list[ResolvedFrame] = []
    scene_ranges: list[tuple[str, int, int]] = []
    scene_frames_meta: list[tuple[str, int, list[ResolvedFrame]]] = []
    slide_num = 1
    min_scale = 1.0

    for scene in deck.scenes:
        scene_theme = apply_palette_overrides(base_theme, scene.palette)
        if scene.palette:
            _audit_theme_aesthetics(scene_theme, scene_id=scene.id, slide_num=slide_num, findings=all_findings)
        resolved = resolve_scene(
            scene,
            deck.slide_width,
            deck.slide_height,
            pinned_flow=deck.pinned_flow,
        )
        first_slide = slide_num
        scene_ranges.append((scene.id, first_slide, len(resolved)))
        scene_frames_meta.append((scene.id, first_slide, resolved))
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
        _audit_scene_anchor_stability(resolved, first_slide, all_findings)

    _audit_deck_pinned_flow_stability(all_frames, all_findings)
    _audit_story_fidelity(deck, scene_ranges, all_findings)
    _audit_cross_page_consistency(deck, scene_frames_meta, all_findings)

    errors: list[AuditFinding] = []
    warnings: list[AuditFinding] = []
    for item in all_findings:
        if item.severity == "error" or (strict and item.tier != "critique"):
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


__all__ = [
    "Severity",
    "AuditFinding",
    "AuditReport",
    "select_review_slides",
    "audit_deck",
]
