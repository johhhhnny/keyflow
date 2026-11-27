"""Cross-page visual consistency checks across scenes in a deck."""

from __future__ import annotations

from keyflow.audit.report import AuditFinding
from keyflow.layouts import ResolvedFrame
from keyflow.schema import DeckSpec


def _final_element_count(frame: ResolvedFrame) -> int:
    top_boxes = sum(1 for b in frame.boxes if b.kind in ("card", "callout"))
    return top_boxes + len(frame.charts) + len(frame.tables) + len(frame.shapes) + len(frame.textboxes)


def _audit_intent_form_alignment(
    deck: DeckSpec,
    scene_frames: list[tuple[str, int, list[ResolvedFrame]]],
    findings: list[AuditFinding],
) -> None:
    """Emit non-blocking critique hints only when a legacy string visual_intent diverges from its idiom."""
    for sc_idx, sc in enumerate(deck.scenes):
        intent = getattr(sc, "visual_intent", None)
        if not intent or isinstance(intent, dict):
            continue
        first_slide = scene_frames[sc_idx][1] if sc_idx < len(scene_frames) else 1
        chart_types = {o.chart.chart_type for o in sc.objects if o.kind == "chart" and o.chart is not None}
        diag_layouts = {o.diagram.diagram_layout for o in sc.objects if o.kind == "diagram" and o.diagram is not None}
        has_table = any(o.kind == "table" for o in sc.objects)
        has_hero_tb = any(o.kind == "textbox" and (o.font_size or 0.0) >= 60.0 for o in sc.objects)
        has_borderless_metric = any(o.kind in ("card", "callout") and o.surface == "borderless" and o.metric for o in sc.objects)

        mismatch_msg: str | None = None
        suggestion = ""
        if intent == "profit_bridge" and "waterfall" not in chart_types:
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='profit_bridge' without a 'waterfall' chart."
            suggestion = "Verify whether your chosen visual form expresses profit formation clearly, or switch to an open-ended visual_intent object."
        elif intent == "decay_trajectory" and not ({"line", "area"} & chart_types):
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='decay_trajectory' without a 'line' or 'area' chart."
            suggestion = "Verify whether your chosen visual form shows multi-period trajectory clearly, or switch to an open-ended visual_intent object."
        elif intent == "price_value_gap" and not (has_hero_tb or has_borderless_metric or sc.layout == "proportion_bar"):
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='price_value_gap' without hero typography or range scale."
            suggestion = "Consider hero typography (>=60pt), borderless metric, football_field, or proportion_bar if it sharpens the contrast."
        elif intent == "methodology_tradeoff" and sc.layout not in ("comparison_matrix", "comparison") and not has_table:
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='methodology_tradeoff' without a matrix, comparison, or table."
            suggestion = "Consider whether a comparison structure or custom spatial composition makes the trade-off easier to scan."
        elif intent == "tension_radiation" and sc.layout != "hub_spoke" and "hub_spoke" not in diag_layouts:
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='tension_radiation' without a hub_spoke topology."
            suggestion = "Verify whether your composition visually conveys opposing forces around the core thesis."
        elif intent == "nonlinear_loop" and sc.layout != "sequence_timeline" and "sequence" not in diag_layouts:
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='nonlinear_loop' without a sequence_timeline/sequence diagram."
            suggestion = "Verify whether your chosen visual form makes feedback/retry loops explicit."
        elif intent == "proportion_share" and sc.layout != "proportion_bar" and not ({"pie", "donut", "stacked_bar", "stacked_column", "progress_bars"} & chart_types):
            mismatch_msg = f"Scene '{sc.id}' declares legacy visual_intent='proportion_share' without a proportion_bar or share chart."
            suggestion = "Verify whether part-to-whole proportions are immediately visible."

        if mismatch_msg:
            findings.append(
                AuditFinding(
                    severity="warning",
                    tier="critique",
                    category="intent_form_alignment",
                    slide_num=first_slide,
                    scene_id=sc.id,
                    frame_index=0,
                    target_id=sc.id,
                    message=mismatch_msg,
                    suggestion=suggestion,
                    suggested_action="review_intent_visual_fit",
                )
            )


def _audit_cross_page_consistency(
    deck: DeckSpec,
    scene_frames: list[tuple[str, int, list[ResolvedFrame]]],
    findings: list[AuditFinding],
) -> None:
    """Detect abrupt cross-scene density jumps, variant drift, visual monotony, and card text bloat."""
    _audit_intent_form_alignment(deck, scene_frames, findings)
    # 0. Card & Callout text-layer bloat check (per-object)
    for sc_idx, sc in enumerate(deck.scenes):
        if sc.layout != "canvas":
            continue
        first_slide = scene_frames[sc_idx][1] if sc_idx < len(scene_frames) else 1
        for obj in sc.objects:
            if (
                obj.kind == "card"
                and obj.surface != "borderless"
                and not obj.metric
                and obj.badge
                and obj.label
                and obj.sublabel
            ):
                findings.append(
                    AuditFinding(
                        severity="warning",
                        tier="critique",
                        category="card_text_bloat",
                        slide_num=first_slide,
                        scene_id=sc.id,
                        frame_index=0,
                        target_id=obj.id,
                        message=f"Card '{obj.id}' packs 3 text layers (badge + label + sublabel) without a metric or unpack structure.",
                        suggestion="Keep plain cards to 1 line ('label') and move explanatory 'sublabel' text into 'note' (Presenter Notes).",
                        suggested_action="move_sublabel_to_note",
                    )
                )
            elif (
                obj.kind == "callout"
                and obj.surface != "borderless"
                and not obj.metric
                and obj.badge
                and obj.label
                and obj.sublabel
                and len(obj.sublabel.strip()) > 28
            ):
                findings.append(
                    AuditFinding(
                        severity="warning",
                        tier="critique",
                        category="callout_text_bloat",
                        slide_num=first_slide,
                        scene_id=sc.id,
                        frame_index=0,
                        target_id=obj.id,
                        message=f"Callout '{obj.id}' packs 3 text layers with long sublabel prose ({len(obj.sublabel.strip())} chars).",
                        suggestion="Move explanatory context into 'note' and keep 'sublabel' concise.",
                        suggested_action="move_sublabel_to_note",
                    )
                )

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
                            tier="critique",
                            category="visual_monotony",
                            slide_num=first_slide,
                            scene_id=cur_sc.id,
                            frame_index=0,
                            message=f"3+ consecutive scenes share identical '{cur_sc.layout}' structure ending at '{cur_sc.id}'.",
                            suggestion="Review whether identical structure aids horizontal comparison (keep it intentionally if so); otherwise vary composition to reflect narrative shift.",
                            suggested_action="review_rhythm_necessity",
                        )
                    )
            else:
                streak = 1

        # Per-scene / contiguous-run check so 1 chart cannot mask 15 filled-card slides
        monotone_card_total = 0
        monotone_scene_ids: list[str] = []
        monotone_first_slide = 1
        for sc_id, first_slide, frames in scene_frames:
            if not frames:
                continue
            lf = frames[-1]
            scene_has_rich = bool(lf.charts or lf.tables or lf.proportion_bar or lf.comparison_matrix or lf.edges)
            scene_cards = [b for b in lf.boxes if b.kind in ("card", "callout") and "__" not in b.id]
            scene_filled = sum(1 for b in scene_cards if getattr(b, "surface", "filled") == "filled")
            if scene_cards and scene_filled == len(scene_cards) and not scene_has_rich:
                if not monotone_scene_ids:
                    monotone_first_slide = first_slide
                monotone_card_total += scene_filled
                monotone_scene_ids.append(sc_id)
            else:
                if len(monotone_scene_ids) >= 3 and monotone_card_total >= 6:
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            tier="critique",
                            category="visual_monotony",
                            slide_num=monotone_first_slide,
                            scene_id=monotone_scene_ids[0],
                            frame_index=0,
                            message=(
                                f"All {monotone_card_total} cards across {len(monotone_scene_ids)} consecutive scenes "
                                f"({', '.join(monotone_scene_ids)}) use 'surface=filled' with no charts, diagrams, or borderless typography."
                            ),
                            suggestion="Consider whether borderless typography, accent_bar cards, ghost frames, or diagrams would clarify hierarchy better than uniform filled boxes.",
                            suggested_action="review_surface_variety",
                        )
                    )
                monotone_card_total = 0
                monotone_scene_ids = []
        if len(monotone_scene_ids) >= 3 and monotone_card_total >= 6:
            findings.append(
                AuditFinding(
                    severity="warning",
                    category="visual_monotony",
                    slide_num=monotone_first_slide,
                    scene_id=monotone_scene_ids[0],
                    frame_index=0,
                    message=(
                        f"All {monotone_card_total} cards across {len(monotone_scene_ids)} consecutive scenes "
                        f"({', '.join(monotone_scene_ids)}) use 'surface=filled' with no charts, diagrams, or borderless typography."
                    ),
                    suggestion="Use surface='borderless' for hero numbers/thesis statements, surface='ghost' for lightweight groups, or add nonlinear diagrams/charts.",
                    suggested_action="reduce_filled_card_monotony",
                )
            )

        # Deck-level visual idiom diversity check (>=4 scenes with canvas relying solely on basic cards/column/table)
        if len(deck.scenes) >= 4 and any(sc.layout == "canvas" for sc in deck.scenes):
            idioms: set[str] = set()
            for sc in deck.scenes:
                if sc.layout != "canvas":
                    idioms.add(f"layout:{sc.layout}")
                for o in sc.objects:
                    if o.kind == "chart" and o.chart is not None:
                        idioms.add(f"chart:{o.chart.chart_type}")
                    elif o.kind == "diagram" and o.diagram is not None:
                        idioms.add(f"diagram:{o.diagram.diagram_layout}")
                    elif o.kind == "textbox" and (o.font_size or 0.0) >= 60.0:
                        idioms.add("hero_textbox")
                    elif o.kind == "table":
                        idioms.add("table")
                    elif o.kind in ("card", "callout"):
                        idioms.add(f"{o.kind}:{o.surface}")
            rich_idioms = {
                "chart:waterfall",
                "chart:line",
                "chart:area",
                "chart:pie",
                "chart:donut",
                "chart:scatter",
                "chart:stacked_column",
                "chart:stacked_bar",
                "hero_textbox",
                "layout:proportion_bar",
                "layout:comparison_matrix",
                "layout:hub_spoke",
                "layout:sequence_timeline",
                "layout:architecture_evolution",
                "layout:flow_dag",
            }
            if len(idioms) <= 2 and not (idioms & rich_idioms):
                findings.append(
                    AuditFinding(
                        severity="warning",
                        tier="critique",
                        category="visual_monotony",
                        slide_num=1,
                        scene_id=deck.scenes[0].id,
                        frame_index=0,
                        message=f"Deck has {len(deck.scenes)} scenes but uses only {len(idioms)} basic visual idioms ({', '.join(sorted(idioms))}).",
                        suggestion="Diagnostic note: verify whether this uniform visual vocabulary is intentional for consistent comparison, or if richer visual metaphors would help.",
                        suggested_action="review_visual_idiom_range",
                    )
                )
