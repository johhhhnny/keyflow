"""Cross-page visual consistency checks across scenes in a deck."""

from __future__ import annotations

from keyflow.audit.report import AuditFinding
from keyflow.layouts import ResolvedFrame
from keyflow.schema import DeckSpec


def _final_element_count(frame: ResolvedFrame) -> int:
    top_boxes = sum(1 for b in frame.boxes if b.kind in ("card", "callout"))
    return top_boxes + len(frame.charts) + len(frame.tables) + len(frame.shapes) + len(frame.textboxes)


def _audit_cross_page_consistency(
    deck: DeckSpec,
    scene_frames: list[tuple[str, int, list[ResolvedFrame]]],
    findings: list[AuditFinding],
) -> None:
    """Detect abrupt cross-scene density jumps, variant drift, and fragmented palettes."""
    if len(scene_frames) < 2:
        return

    # 1. Adjacent-scene density jump check
    prev_sid, _, prev_list = scene_frames[0]
    prev_count = _final_element_count(prev_list[-1]) if prev_list else 0
    for sid, first_slide, frames in scene_frames[1:]:
        cur_count = _final_element_count(frames[-1]) if frames else 0
        if prev_count == 1 and cur_count >= 7:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="cross_page_consistency",
                    slide_num=first_slide + max(0, len(frames) - 1),
                    scene_id=sid,
                    frame_index=max(0, len(frames) - 1),
                    message=(
                        f"Abrupt visual density jump from scene '{prev_sid}' ({prev_count} element) "
                        f"to '{sid}' ({cur_count} elements)."
                    ),
                    suggestion="Consider splitting dense scenes or adding an intermediate transition frame.",
                    suggested_action="balance_scene_density",
                )
            )
        prev_sid, prev_count = sid, cur_count

    # 2. Same-ID element variant continuity across scenes
    seen_variants: dict[str, tuple[str, str]] = {}
    for sid, first_slide, frames in scene_frames:
        if not frames:
            continue
        last_frame = frames[-1]
        for box in last_frame.boxes:
            if box.kind not in ("card", "callout") or "__" in box.id:
                continue
            prev = seen_variants.get(box.id)
            if prev is None:
                seen_variants[box.id] = (box.variant, sid)
            elif prev[0] != box.variant:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        category="cross_page_consistency",
                        slide_num=first_slide + len(frames) - 1,
                        scene_id=sid,
                        frame_index=len(frames) - 1,
                        target_id=box.id,
                        message=(
                            f"Object '{box.id}' changed variant from '{prev[0]}' (scene '{prev[1]}') "
                            f"to '{box.variant}' (scene '{sid}')."
                        ),
                        suggestion="Keep semantic variants consistent for recurring objects across scenes.",
                        suggested_action="align_recurring_variant",
                    )
                )

    # 3. Fragmented scene background overrides check
    if len(deck.scenes) >= 3:
        bg_override_count = sum(
            1 for sc in deck.scenes if sc.palette and "bg_hex" in sc.palette
        )
        if bg_override_count > len(deck.scenes) / 2.0:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="cross_page_consistency",
                    slide_num=1,
                    scene_id=deck.scenes[0].id,
                    frame_index=0,
                    message=(
                        f"{bg_override_count}/{len(deck.scenes)} scenes override 'palette.bg_hex', "
                        "which may fragment deck-wide visual continuity."
                    ),
                    suggestion="Use a single deck-level theme or palette and reserve bg_hex overrides for key chapter dividers.",
                    suggested_action="unify_deck_palette",
                )
            )

    # 4. Visual monotony checks: >= 3 consecutive identical layouts or 100% filled-card decks
    if len(deck.scenes) >= 3:
        streak = 1
        for i in range(1, len(deck.scenes)):
            cur_sc = deck.scenes[i]
            prev_sc = deck.scenes[i - 1]
            same_layout = cur_sc.layout == prev_sc.layout
            if same_layout and cur_sc.layout == "canvas":
                cur_sig = tuple(sorted(o.kind for o in cur_sc.objects))
                prev_sig = tuple(sorted(o.kind for o in prev_sc.objects))
                same_layout = cur_sig == prev_sig
            elif same_layout:
                cur_sig = (bool(cur_sc.nodes), bool(cur_sc.edges), cur_sc.show_pinned_flow, cur_sc.pinned_flow is not None)
                prev_sig = (bool(prev_sc.nodes), bool(prev_sc.edges), prev_sc.show_pinned_flow, prev_sc.pinned_flow is not None)
                same_layout = cur_sig == prev_sig
            if same_layout:
                streak += 1
                if streak == 3:
                    first_slide = scene_frames[i][1]
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            category="visual_monotony",
                            slide_num=first_slide,
                            scene_id=cur_sc.id,
                            frame_index=0,
                            message=f"3+ consecutive scenes share identical '{cur_sc.layout}' structure ending at '{cur_sc.id}'.",
                            suggestion="Vary visual rhythm using sequence_timeline, proportion_bar, comparison_matrix, charts, or borderless hero typography.",
                            suggested_action="diversify_scene_layouts",
                        )
                    )
            else:
                streak = 1

        total_cards = 0
        filled_cards = 0
        has_rich_visuals = False
        for _, _, frames in scene_frames:
            if not frames:
                continue
            lf = frames[-1]
            if lf.charts or lf.tables or lf.proportion_bar or lf.comparison_matrix or lf.edges:
                has_rich_visuals = True
            for b in lf.boxes:
                if b.kind in ("card", "callout") and "__" not in b.id:
                    total_cards += 1
                    if getattr(b, "surface", "filled") == "filled":
                        filled_cards += 1
        if total_cards >= 6 and filled_cards == total_cards and not has_rich_visuals:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="visual_monotony",
                    slide_num=1,
                    scene_id=deck.scenes[0].id,
                    frame_index=0,
                    message=f"All {total_cards} cards across {len(deck.scenes)} scenes use 'surface=filled' with no charts, diagrams, or borderless typography.",
                    suggestion="Use surface='borderless' for hero numbers/thesis statements, surface='ghost' for lightweight groups, or add nonlinear diagrams/charts.",
                    suggested_action="reduce_filled_card_monotony",
                )
            )
