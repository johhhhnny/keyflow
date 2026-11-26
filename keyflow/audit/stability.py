"""Cross-frame Magic Move anchor stability and pinned_flow transition checks."""

from __future__ import annotations

from keyflow.audit.geometry import _max_point_delta, _max_rect_delta
from keyflow.audit.report import AuditFinding
from keyflow.layouts import PlacedPinnedFlow, ResolvedFrame
from keyflow.tokens import ANCHOR_JITTER_TOLERANCE_PT


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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
            if nn.rect.cy >= pn.rect.cy or nn.rect.h > pn.rect.h + ANCHOR_JITTER_TOLERANCE_PT:
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
            if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
            if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
            if axis_delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if f_delta > ANCHOR_JITTER_TOLERANCE_PT:
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
                if delta > ANCHOR_JITTER_TOLERANCE_PT:
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
            cur_ids = [n.id for n in cur.pinned_flow.nodes]
            nxt_ids = [n.id for n in nxt.pinned_flow.nodes]
            if cur_ids == nxt_ids:
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
            cur_ids = [n.id for n in cur.pinned_flow.nodes]
            nxt_ids = [n.id for n in nxt.pinned_flow.nodes]
            if cur_ids == nxt_ids:
                _check_pinned_flow_pair(
                    cur.pinned_flow,
                    nxt.pinned_flow,
                    slide_num=idx + 2,
                    scene_id=nxt.scene_id,
                    frame_index=nxt.frame_index,
                    findings=findings,
                )


