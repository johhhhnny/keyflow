"""Story-model epistemic alignment, source grounding, and metric-scope checks."""

from __future__ import annotations

from keyflow.audit.report import AuditFinding
from keyflow.schema import DeckSpec

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


