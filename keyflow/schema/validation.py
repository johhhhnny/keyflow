"""Top-level storyboard validation entrypoint and node/pinned_flow validators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from keyflow.schema.models import ValidationResult
from keyflow.schema.references import (
    _as_float,
    _as_int,
    _check_allowed_keys,
    _check_evidence_refs,
    _check_label_density,
    _is_in,
    _schema_key_sets,
    _validate_palette,
    _validate_style_config,
    compute_dag_layers,
)
from keyflow.schema.canvas import _validate_canvas_scene
from keyflow.themes import THEMES, is_valid_hex_color, load_theme_file


def _validate_nodes_and_edges(
    nodes: Any,
    edges: Any,
    *,
    prefix: str,
    layout_kind: str,
    claim_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    valid_child_layouts = {"row", "column", "grid"}
    valid_variants = {"primary", "accent", "muted", "success", "warn"}
    valid_surfaces = {"filled", "ghost", "borderless", "accent_bar"}
    node_map: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []

    if not isinstance(nodes, list):
        errors.append(f"{prefix}.nodes must be a list.")
        return node_map, set()

    for n_idx, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"{prefix}.nodes[{n_idx}]: must be an object.")
            continue
        _check_allowed_keys(n, "node", f"{prefix}.nodes[{n_idx}]", errors)
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"{prefix}.nodes[{n_idx}]: missing 'id'.")
            continue
        if nid in node_map:
            errors.append(f"{prefix}: duplicate node id '{nid}'.")
        else:
            node_order.append(nid)
        node_map[nid] = n
        _check_evidence_refs(n, claim_ids, f"{prefix}.nodes['{nid}']", errors)

        variant = n.get("variant", "primary")
        if not _is_in(variant, valid_variants):
            errors.append(f"{prefix}.nodes['{nid}']: invalid variant '{variant}'.")
        surface = n.get("surface", "filled")
        if not _is_in(surface, valid_surfaces):
            errors.append(f"{prefix}.nodes['{nid}']: invalid surface '{surface}'.")

        raw_label = n.get("label")
        if not isinstance(raw_label, str) or not raw_label:
            errors.append(f"{prefix}.nodes[{n_idx}] ('{nid}'): missing 'label'.")
        else:
            _check_label_density(
                f"{prefix}.nodes['{nid}']",
                raw_label,
                n.get("sublabel") if isinstance(n.get("sublabel"), str) else None,
                n.get("badge") if isinstance(n.get("badge"), str) else None,
                n.get("metric") if isinstance(n.get("metric"), str) else None,
                warnings,
            )

        child_layout = n.get("child_layout", "row")
        if not _is_in(child_layout, valid_child_layouts):
            errors.append(f"{prefix}.nodes['{nid}']: invalid child_layout '{child_layout}'.")

        children = n.get("children", [])
        if not isinstance(children, list):
            errors.append(f"{prefix}.nodes['{nid}'].children must be a list.")
            children = []
        if n.get("kind") == "group_dashed" and not children:
            errors.append(f"{prefix}.nodes['{nid}']: kind='group_dashed' requires non-empty 'children'.")
        if layout_kind in ("horizontal_flow", "horizontal") and len(children) >= 4 and child_layout == "row":
            warnings.append(
                f"{prefix}.nodes['{nid}']: {len(children)} children in horizontal 'row' may squeeze the flow; consider child_layout='grid'."
            )

        child_ids: set[str] = set()
        for c_idx, c in enumerate(children):
            if not isinstance(c, dict):
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: must be an object.")
                continue
            _check_allowed_keys(c, "child", f"{prefix}.nodes['{nid}'].children[{c_idx}]", errors)
            cid = c.get("id")
            if not isinstance(cid, str) or not cid:
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: missing 'id'.")
            elif cid in child_ids:
                errors.append(f"{prefix}.nodes['{nid}']: duplicate child id '{cid}'.")
            else:
                child_ids.add(cid)
            _check_evidence_refs(c, claim_ids, f"{prefix}.nodes['{nid}'].children['{cid}']", errors)

            cvar = c.get("variant", "primary")
            if not _is_in(cvar, valid_variants):
                errors.append(f"{prefix}.nodes['{nid}'].children['{cid}']: invalid variant '{cvar}'.")
            csurf = c.get("surface", "filled")
            if not _is_in(csurf, valid_surfaces):
                errors.append(f"{prefix}.nodes['{nid}'].children['{cid}']: invalid surface '{csurf}'.")

            clabel = c.get("label")
            if not isinstance(clabel, str) or not clabel:
                errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: missing 'label'.")
            else:
                _check_label_density(
                    f"{prefix}.nodes['{nid}'].children['{cid}']",
                    clabel,
                    c.get("sublabel") if isinstance(c.get("sublabel"), str) else None,
                    c.get("badge") if isinstance(c.get("badge"), str) else None,
                    c.get("metric") if isinstance(c.get("metric"), str) else None,
                    warnings,
                )

    edge_ids: set[str] = set()
    valid_edge_pairs: list[tuple[str, str]] = []
    if not isinstance(edges, list):
        errors.append(f"{prefix}.edges must be a list.")
    else:
        for e_idx, e in enumerate(edges):
            if not isinstance(e, dict):
                errors.append(f"{prefix}.edges[{e_idx}]: must be an object.")
                continue
            _check_allowed_keys(e, "edge", f"{prefix}.edges[{e_idx}]", errors)
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{prefix}.edges[{e_idx}]: missing 'id'.")
            elif eid in edge_ids:
                errors.append(f"{prefix}: duplicate edge id '{eid}'.")
            else:
                edge_ids.add(eid)
            src = e.get("from")
            dst = e.get("to")
            if not _is_in(src, node_map):
                errors.append(f"{prefix}.edges['{eid}']: unknown 'from' node '{src}'.")
            if not _is_in(dst, node_map):
                errors.append(f"{prefix}.edges['{eid}']: unknown 'to' node '{dst}'.")
            if isinstance(src, str) and isinstance(dst, str) and src in node_map and dst in node_map:
                if src == dst and layout_kind in ("flow_dag", "dag"):
                    errors.append(f"{prefix}.edges['{eid}']: self-loop '{src} -> {dst}' is not allowed in DAG.")
                valid_edge_pairs.append((src, dst))

    if layout_kind in ("flow_dag", "dag") and node_order and valid_edge_pairs:
        _, cyclic_nodes = compute_dag_layers(node_order, valid_edge_pairs)
        if cyclic_nodes:
            errors.append(
                f"{prefix}: DAG contains cyclic dependencies involving: {', '.join(cyclic_nodes)}."
            )

    return node_map, edge_ids




def _validate_pinned_flow(pf: Any, prefix: str, errors: list[str]) -> set[str]:
    """Validate a deck-level or scene-level pinned_flow block and return its node IDs."""
    pf_node_ids: set[str] = set()
    if not isinstance(pf, dict):
        errors.append(f"'{prefix}' must be an object.")
        return pf_node_ids
    _check_allowed_keys(pf, "pinned_flow", prefix, errors)
    pf_nodes = pf.get("nodes", [])
    if not isinstance(pf_nodes, list) or not pf_nodes:
        errors.append(f"{prefix}.nodes must be a non-empty list.")
        return pf_node_ids
    for idx, n in enumerate(pf_nodes):
        if not isinstance(n, dict):
            errors.append(f"{prefix}.nodes[{idx}]: must be an object.")
            continue
        _check_allowed_keys(n, "pf_node", f"{prefix}.nodes[{idx}]", errors)
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"{prefix}.nodes[{idx}]: missing 'id'.")
        elif nid in pf_node_ids:
            errors.append(f"{prefix}: duplicate node id '{nid}'.")
        else:
            pf_node_ids.add(nid)
        if not isinstance(n.get("label"), str) or not n.get("label"):
            errors.append(f"{prefix}.nodes[{idx}]: missing 'label'.")
    pf_edges = pf.get("edges", [])
    if not isinstance(pf_edges, list):
        errors.append(f"{prefix}.edges must be a list.")
    else:
        for e_idx, e in enumerate(pf_edges):
            if not isinstance(e, dict):
                errors.append(f"{prefix}.edges[{e_idx}]: must be an object.")
                continue
            _check_allowed_keys(e, "pf_edge", f"{prefix}.edges[{e_idx}]", errors)
            if e.get("from") not in pf_node_ids:
                errors.append(f"{prefix}.edges[{e_idx}]: unknown 'from' node '{e.get('from')}'.")
            if e.get("to") not in pf_node_ids:
                errors.append(f"{prefix}.edges[{e_idx}]: unknown 'to' node '{e.get('to')}'.")
    pf_groups = pf.get("groups", [])
    if not isinstance(pf_groups, list):
        errors.append(f"{prefix}.groups must be a list.")
    else:
        for g_idx, g in enumerate(pf_groups):
            if not isinstance(g, dict):
                errors.append(f"{prefix}.groups[{g_idx}]: must be an object.")
                continue
            _check_allowed_keys(g, "pf_group", f"{prefix}.groups[{g_idx}]", errors)
            if not isinstance(g.get("label"), str) or not g.get("label"):
                errors.append(f"{prefix}.groups[{g_idx}]: missing 'label'.")
            g_nids = g.get("node_ids", [])
            if not isinstance(g_nids, list):
                errors.append(f"{prefix}.groups[{g_idx}]: 'node_ids' must be a list.")
            else:
                for nid in g_nids:
                    if nid not in pf_node_ids:
                        errors.append(f"{prefix}.groups[{g_idx}]: unknown node '{nid}'.")
    return pf_node_ids


def validate_deck(
    raw: dict[str, Any],
    *,
    use_templates: bool | None = None,
) -> ValidationResult:
    """Validate structural integrity, references, mode switch, and visual density rules."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(raw, dict):
        return ValidationResult(valid=False, errors=["Top-level JSON must be an object."])

    _check_allowed_keys(raw, "deck", "deck", errors)

    if "use_templates" in raw and not isinstance(raw["use_templates"], bool):
        errors.append("Top-level 'use_templates' must be a boolean.")
    eff_use_templates = bool(raw.get("use_templates", False)) if use_templates is None else use_templates

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("Missing or invalid top-level 'title'.")

    theme = raw.get("theme", "slate_dark")
    if not isinstance(theme, str):
        errors.append(f"Unknown theme '{theme}'. Valid options: {', '.join(sorted(THEMES))} (or .json file path).")
    elif theme not in THEMES:
        if theme.lower().endswith(".json") or Path(theme).exists():
            try:
                load_theme_file(theme)
            except Exception as exc:
                errors.append(f"Invalid theme file '{theme}': {exc}")
        else:
            errors.append(f"Unknown theme '{theme}'. Valid options: {', '.join(sorted(THEMES))} (or .json file path).")

    if raw.get("palette") is not None:
        if eff_use_templates:
            errors.append("Custom top-level 'palette' is forbidden when use_templates=true; set use_templates=false.")
        else:
            _validate_palette(raw["palette"], "deck.palette", errors)
    if raw.get("style_config") is not None:
        _validate_style_config(raw["style_config"], "deck.style_config", errors)

    if raw.get("slide_size") is not None:
        ss = raw["slide_size"]
        if not isinstance(ss, dict):
            errors.append("'slide_size' must be an object.")
        else:
            _check_allowed_keys(ss, "slide_size", "slide_size", errors)
            for dim in ("width", "height"):
                if dim in ss and _as_float(ss[dim]) is None:
                    errors.append(f"slide_size.{dim} must be numeric.")

    claim_ids: set[str] = set()
    valid_claim_types = {"thesis", "fact", "relation", "inference", "counter_evidence", "conclusion", "example"}
    valid_confidence = {"high", "medium", "low"}
    if raw.get("story_model") is not None:
        sm = raw["story_model"]
        if not isinstance(sm, dict):
            errors.append("'story_model' must be an object.")
        else:
            _check_allowed_keys(sm, "story_model", "story_model", errors)
            if sm.get("core_question") is not None and not isinstance(sm.get("core_question"), str):
                errors.append("story_model.core_question must be a string.")
            claims = sm.get("claims")
            if not isinstance(claims, list) or not claims:
                errors.append("story_model.claims must be a non-empty list.")
            else:
                for cl_idx, cl in enumerate(claims):
                    if not isinstance(cl, dict):
                        errors.append(f"story_model.claims[{cl_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(cl, "story_claim", f"story_model.claims[{cl_idx}]", errors)
                    cid = cl.get("id")
                    if not isinstance(cid, str) or not cid:
                        errors.append(f"story_model.claims[{cl_idx}]: missing 'id'.")
                    elif cid in claim_ids:
                        errors.append(f"story_model: duplicate claim id '{cid}'.")
                    else:
                        claim_ids.add(cid)
                    ctype = cl.get("type")
                    if not isinstance(ctype, str) or ctype not in valid_claim_types:
                        errors.append(f"story_model.claims['{cid}']: invalid type '{ctype}'.")
                    ctext = cl.get("claim")
                    if not isinstance(ctext, str) or not ctext.strip():
                        errors.append(f"story_model.claims['{cid}']: missing 'claim'.")
                    conf = cl.get("confidence")
                    if conf is not None and (not isinstance(conf, str) or conf not in valid_confidence):
                        errors.append(f"story_model.claims['{cid}']: invalid confidence '{conf}'.")

    pf_node_ids: set[str] = set()
    if raw.get("pinned_flow") is not None:
        pf_node_ids = _validate_pinned_flow(raw["pinned_flow"], "pinned_flow", errors)

    raw_scenes = raw.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        errors.append("'scenes' must be a non-empty list.")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    valid_layouts = {
        "canvas",
        "horizontal_flow",
        "vertical_flow",
        "comparison",
        "hub_spoke",
        "flow_dag",
        "architecture_evolution",
        "sequence_timeline",
        "metrics_cards",
        "proportion_bar",
        "comparison_matrix",
    }
    valid_pacing = {"auto", "compact", "manual"}
    scene_ids: set[str] = set()

    for s_idx, s in enumerate(raw_scenes):
        prefix = f"scenes[{s_idx}]"
        if not isinstance(s, dict):
            errors.append(f"{prefix}: scene entry must be an object.")
            continue
        _check_allowed_keys(s, "scene", prefix, errors)
        _check_evidence_refs(s, claim_ids, prefix, errors)

        sid = s.get("id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"{prefix}: missing or invalid 'id'.")
        elif sid in scene_ids:
            errors.append(f"{prefix}: duplicate scene id '{sid}'.")
        else:
            scene_ids.add(sid)

        stitle = s.get("title")
        if not isinstance(stitle, str) or not stitle:
            errors.append(f"{prefix}: missing or invalid 'title'.")

        has_canvas_structure = any(
            s.get(k) is not None for k in ("grid", "regions", "objects", "connectors")
        )
        layout = s.get("layout")
        if layout is None:
            if has_canvas_structure:
                layout = "canvas"
            else:
                errors.append(f"{prefix}: missing 'layout'; choose a layout explicitly.")
        elif not isinstance(layout, str) or layout not in valid_layouts:
            errors.append(f"{prefix}: invalid layout '{layout}'.")

        has_freeform_fields = any(
            s.get(k) is not None for k in ("grid", "regions", "objects", "connectors", "palette")
        )
        if layout == "canvas" and (s.get("nodes") or s.get("edges")):
            errors.append(
                f"{prefix}: canvas scenes must declare visual primitives in 'objects'; "
                "move graph topology into an explicit kind='diagram' object."
            )
        elif layout != "canvas" and has_canvas_structure:
            errors.append(
                f"{prefix}: 'grid', 'regions', 'objects', and 'connectors' require layout='canvas'."
            )
        if eff_use_templates and (layout == "canvas" or has_freeform_fields):
            errors.append(
                f"{prefix}: freeform 'canvas'/'regions'/'objects'/'palette' are forbidden when use_templates=true; set use_templates=false."
            )

        if s.get("palette") is not None and not eff_use_templates:
            _validate_palette(s["palette"], f"{prefix}.palette", errors)
        if s.get("style_config") is not None:
            _validate_style_config(s["style_config"], f"{prefix}.style_config", errors)

        scene_pf_node_ids = pf_node_ids
        if s.get("pinned_flow") is not None:
            scene_pf_node_ids = _validate_pinned_flow(s["pinned_flow"], f"{prefix}.pinned_flow", errors)

        active_fn = s.get("active_flow_node")
        if active_fn is not None:
            if not isinstance(active_fn, str):
                errors.append(f"{prefix}: 'active_flow_node' must be a string.")
            elif active_fn:
                if not scene_pf_node_ids:
                    errors.append(f"{prefix}: 'active_flow_node' set to '{active_fn}' without 'pinned_flow'.")
                elif active_fn not in scene_pf_node_ids:
                    errors.append(f"{prefix}: unknown active_flow_node '{active_fn}'.")

        has_frames = "frames" in s and s["frames"] is not None
        pacing = s.get("pacing", "manual" if has_frames else "auto")
        if not isinstance(pacing, str) or pacing not in valid_pacing:
            errors.append(f"{prefix}: invalid pacing '{pacing}'.")

        object_ids: set[str] = set()
        canvas_object_map: dict[str, dict[str, Any]] = {}
        if layout == "canvas":
            object_ids, canvas_object_map = _validate_canvas_scene(
                s,
                prefix=prefix,
                claim_ids=claim_ids,
                errors=errors,
                warnings=warnings,
            )

        nodes = s.get("nodes", [])
        edges = s.get("edges", [])
        node_map, edge_ids = _validate_nodes_and_edges(
            nodes,
            edges,
            prefix=prefix,
            layout_kind=str(layout),
            claim_ids=claim_ids,
            errors=errors,
            warnings=warnings,
        )

        if layout == "horizontal_flow" and isinstance(nodes, list) and len(nodes) > 5:
            warnings.append(
                f"{prefix}: {len(nodes)} top-level nodes in horizontal_flow may feel crowded; 3-5 pillars is recommended."
            )

        item_ids: set[str] = set()
        if layout == "proportion_bar":
            pb = s.get("proportion_bar")
            if not isinstance(pb, dict) or not isinstance(pb.get("items"), list) or not pb.get("items"):
                errors.append(f"{prefix}: layout='proportion_bar' requires 'proportion_bar.items' list.")
            else:
                _check_allowed_keys(pb, "proportion_bar", f"{prefix}.proportion_bar", errors)
                ax_min = _as_float(pb.get("axis_min", 0.0))
                ax_max = _as_float(pb.get("axis_max", 100.0))
                if ax_min is None or ax_max is None:
                    errors.append(f"{prefix}.proportion_bar: 'axis_min' and 'axis_max' must be numeric.")
                elif ax_max <= ax_min:
                    errors.append(f"{prefix}.proportion_bar: 'axis_max' must exceed 'axis_min'.")
                for it_idx, it in enumerate(pb.get("items", [])):
                    if not isinstance(it, dict):
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(it, "proportion_item", f"{prefix}.proportion_bar.items[{it_idx}]", errors)
                    iid = it.get("id")
                    if not isinstance(iid, str) or not iid:
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: missing 'id'.")
                    elif iid in item_ids:
                        errors.append(f"{prefix}.proportion_bar: duplicate item id '{iid}'.")
                    else:
                        item_ids.add(iid)
                    _check_evidence_refs(it, claim_ids, f"{prefix}.proportion_bar.items['{iid}']", errors)
                    if not isinstance(it.get("label"), str) or not it.get("label"):
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: missing 'label'.")
                    val = _as_float(it.get("value", 0))
                    if val is None or val < 0:
                        errors.append(f"{prefix}.proportion_bar.items['{iid}']: 'value' must be a non-negative number.")

        col_ids: set[str] = set()
        if layout == "comparison_matrix":
            mx = s.get("matrix")
            if not isinstance(mx, dict) or not isinstance(mx.get("columns"), list) or not mx.get("columns"):
                errors.append(f"{prefix}: layout='comparison_matrix' requires 'matrix.columns' list.")
            else:
                _check_allowed_keys(mx, "matrix", f"{prefix}.matrix", errors)
                for c_idx, col in enumerate(mx.get("columns", [])):
                    if not isinstance(col, dict):
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: must be an object.")
                        continue
                    _check_allowed_keys(col, "matrix_column", f"{prefix}.matrix.columns[{c_idx}]", errors)
                    cid = col.get("id")
                    if not isinstance(cid, str) or not cid:
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: missing 'id'.")
                    elif cid in col_ids:
                        errors.append(f"{prefix}.matrix: duplicate column id '{cid}'.")
                    else:
                        col_ids.add(cid)
                    _check_evidence_refs(col, claim_ids, f"{prefix}.matrix.columns['{cid}']", errors)
                    if not isinstance(col.get("caption"), str) or not col.get("caption"):
                        errors.append(f"{prefix}.matrix.columns['{cid}']: missing 'caption'.")
                    rows = col.get("rows")
                    if not isinstance(rows, list) or not rows:
                        errors.append(f"{prefix}.matrix.columns['{cid}']: must have at least one row.")
                    else:
                        for r_idx, row in enumerate(rows):
                            if not isinstance(row, dict):
                                errors.append(f"{prefix}.matrix.columns['{cid}'].rows[{r_idx}]: must be an object.")
                            else:
                                _check_allowed_keys(row, "matrix_row", f"{prefix}.matrix.columns['{cid}'].rows[{r_idx}]", errors)

        frames = s.get("frames")
        if frames is None:
            if pacing == "manual":
                errors.append(f"{prefix}: pacing='manual' requires a non-empty 'frames' list.")
            continue

        if not isinstance(frames, list) or not frames:
            errors.append(f"{prefix}: 'frames' must be a non-empty list when provided.")
            continue

        if isinstance(nodes, list) and len(nodes) >= 2 and len(frames) == 1 and pacing == "manual":
            warnings.append(
                f"{prefix}: {len(nodes)} nodes rendered in a single frame; consider splitting into progressive step-by-step frames or running `keyflow pace`."
            )

        for f_idx, f in enumerate(frames):
            if not isinstance(f, dict):
                errors.append(f"{prefix}.frames[{f_idx}]: frame entry must be an object.")
                continue
            _check_allowed_keys(f, "frame", f"{prefix}.frames[{f_idx}]", errors)
            if f.get("show_pinned_flow") is not None and not isinstance(f["show_pinned_flow"], bool):
                errors.append(f"{prefix}.frames[{f_idx}].show_pinned_flow: must be a boolean.")
            vis = f.get("visible_nodes", [])
            exp = f.get("expanded_nodes", [])
            if not isinstance(vis, list):
                errors.append(f"{prefix}.frames[{f_idx}]: 'visible_nodes' must be a list.")
                vis = []
            if not isinstance(exp, list):
                errors.append(f"{prefix}.frames[{f_idx}]: 'expanded_nodes' must be a list.")
                exp = []

            for nid in vis:
                if not isinstance(nid, str) or nid not in node_map:
                    errors.append(f"{prefix}.frames[{f_idx}]: unknown visible node '{nid}'.")
            for nid in exp:
                if not isinstance(nid, str) or nid not in node_map:
                    errors.append(f"{prefix}.frames[{f_idx}]: unknown expanded node '{nid}'.")
                elif nid not in vis:
                    errors.append(f"{prefix}.frames[{f_idx}]: expanded node '{nid}' must also be in 'visible_nodes'.")
                elif not isinstance(node_map[nid].get("children"), list) or not node_map[nid].get("children"):
                    errors.append(f"{prefix}.frames[{f_idx}]: expanded node '{nid}' has no 'children' to unpack.")

            vis_edges = f.get("visible_edges", "auto")
            if vis_edges != "auto":
                if not isinstance(vis_edges, list):
                    errors.append(f"{prefix}.frames[{f_idx}]: 'visible_edges' must be 'auto' or a list of edge ids.")
                else:
                    for eid in vis_edges:
                        if not isinstance(eid, str) or eid not in edge_ids:
                            errors.append(f"{prefix}.frames[{f_idx}]: unknown visible edge '{eid}'.")

            for list_field, valid_pool in (
                ("focus_nodes", node_map),
                ("visible_items", item_ids),
                ("visible_columns", col_ids),
                ("visible_objects", object_ids),
                ("focus_objects", object_ids),
            ):
                field_val = f.get(list_field)
                if field_val is not None:
                    if not isinstance(field_val, list):
                        errors.append(f"{prefix}.frames[{f_idx}]: '{list_field}' must be a list.")
                    else:
                        for item_id in field_val:
                            if not isinstance(item_id, str) or item_id not in valid_pool:
                                errors.append(f"{prefix}.frames[{f_idx}]: unknown {list_field} id '{item_id}'.")

            obj_states = f.get("object_states")
            if obj_states is not None:
                if not isinstance(obj_states, dict):
                    errors.append(f"{prefix}.frames[{f_idx}]: 'object_states' must be an object.")
                else:
                    for oid, st_val in obj_states.items():
                        if oid not in object_ids:
                            errors.append(f"{prefix}.frames[{f_idx}].object_states: unknown object '{oid}'.")
                        elif not isinstance(st_val, dict):
                            errors.append(f"{prefix}.frames[{f_idx}].object_states['{oid}']: must be an object.")
                        else:
                            _check_allowed_keys(st_val, "object_state", f"{prefix}.frames[{f_idx}].object_states['{oid}']", errors)
                            for count_key in ("series_count", "category_count", "row_count", "col_count"):
                                if count_key in st_val:
                                    cval = st_val[count_key]
                                    if isinstance(cval, bool) or not isinstance(cval, int) or cval < 1:
                                        errors.append(
                                            f"{prefix}.frames[{f_idx}].object_states['{oid}'].{count_key}: must be an integer >= 1."
                                        )
                            for list_key in ("visible_nodes", "expanded_nodes", "focus_nodes"):
                                if list_key in st_val and (
                                    not isinstance(st_val[list_key], list)
                                    or not all(isinstance(x, str) for x in st_val[list_key])
                                ):
                                    errors.append(
                                        f"{prefix}.frames[{f_idx}].object_states['{oid}'].{list_key}: must be a list of strings."
                                    )
                            if "visible_edges" in st_val:
                                ve = st_val["visible_edges"]
                                if ve != "auto" and (
                                    not isinstance(ve, list) or not all(isinstance(x, str) for x in ve)
                                ):
                                    errors.append(
                                        f"{prefix}.frames[{f_idx}].object_states['{oid}'].visible_edges: must be 'auto' or list of strings."
                                    )
                            c_obj = canvas_object_map.get(oid)
                            if c_obj and c_obj.get("kind") == "diagram" and isinstance(c_obj.get("diagram"), dict):
                                dg = c_obj["diagram"]
                                dg_nodes = {str(n.get("id")) for n in dg.get("nodes", []) if isinstance(n, dict) and n.get("id")}
                                dg_edges = {str(e.get("id")) for e in dg.get("edges", []) if isinstance(e, dict) and e.get("id")}
                                for list_key in ("visible_nodes", "expanded_nodes", "focus_nodes"):
                                    if isinstance(st_val.get(list_key), list):
                                        for ref_id in st_val[list_key]:
                                            if ref_id not in dg_nodes:
                                                errors.append(
                                                    f"{prefix}.frames[{f_idx}].object_states['{oid}'].{list_key}: unknown diagram node '{ref_id}'."
                                                )
                                if isinstance(st_val.get("visible_edges"), list):
                                    for ref_eid in st_val["visible_edges"]:
                                        if ref_eid not in dg_edges:
                                            errors.append(
                                                f"{prefix}.frames[{f_idx}].object_states['{oid}'].visible_edges: unknown diagram edge '{ref_eid}'."
                                            )

            if not f.get("notes"):
                warnings.append(
                    f"{prefix}.frames[{f_idx}]: empty 'notes'; put article explanations in presenter notes to keep the slide minimal."
                )

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
