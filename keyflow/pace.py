"""Stage 2 progressive pacing engine: expand full-state scene graphs into step-by-step frames."""

from __future__ import annotations

import copy
from typing import Any, Literal

from keyflow.schema import compute_dag_layers

DensityMode = Literal["standard", "compact"]


def _node_appear_note(node: dict[str, Any]) -> str:
    if node.get("note"):
        return str(node["note"])
    parts = [str(node["label"])]
    if node.get("metric"):
        parts.insert(0, str(node["metric"]))
    if node.get("sublabel"):
        parts.append(str(node["sublabel"]))
    return " · ".join(parts)


def _node_unpack_note(node: dict[str, Any]) -> str:
    children = node.get("children", [])
    child_notes = [str(c["note"]) for c in children if c.get("note")]
    if child_notes:
        return "；".join(child_notes)
    child_labels = "、".join(str(c["label"]) for c in children)
    base = f"展开 {node['label']}：{child_labels}"
    if node.get("note"):
        return f"{base}。{node['note']}"
    return base


def _pace_linear_flow(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Expand horizontal_flow or vertical_flow into title-first progressive reveal + unpack frames."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    frames: list[dict[str, Any]] = []

    if density == "standard":
        intro = scene.get("intro_note") or scene.get("subtitle") or f"主题总览：{scene['title']}"
        frames.append({"visible_nodes": [], "expanded_nodes": [], "notes": str(intro)})

    visible: list[str] = []
    expanded: list[str] = []
    for node in nodes:
        nid = str(node["id"])
        children = node.get("children", [])
        kind = node.get("kind", "card")
        visible.append(nid)

        if kind == "group_dashed" and children:
            expanded.append(nid)
            frames.append(
                {
                    "visible_nodes": list(visible),
                    "expanded_nodes": list(expanded),
                    "notes": _node_unpack_note(node),
                }
            )
            continue

        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": list(expanded),
                "notes": _node_appear_note(node),
            }
        )
        if children:
            expanded.append(nid)
            frames.append(
                {
                    "visible_nodes": list(visible),
                    "expanded_nodes": list(expanded),
                    "notes": _node_unpack_note(node),
                }
            )

    return frames or [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]


def _pace_flow_dag(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Expand a DAG scene layer-by-layer, revealing branches separately and unpacking groups inline."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    edges: list[dict[str, Any]] = scene.get("edges", [])
    if not nodes:
        return [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]

    node_ids = [str(n["id"]) for n in nodes]
    edge_pairs = [(str(e["from"]), str(e["to"])) for e in edges]
    depth, _ = compute_dag_layers(node_ids, edge_pairs)

    max_depth = max(depth.values(), default=0)
    frames: list[dict[str, Any]] = []
    visible: list[str] = []
    expanded: list[str] = []

    def _emit_node_step(node: dict[str, Any]) -> None:
        nid = str(node["id"])
        children = node.get("children", [])
        kind = node.get("kind", "card")
        visible.append(nid)
        if kind == "group_dashed" and children:
            expanded.append(nid)
            frames.append(
                {
                    "visible_nodes": list(visible),
                    "expanded_nodes": list(expanded),
                    "notes": _node_unpack_note(node),
                }
            )
            return
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": list(expanded),
                "notes": _node_appear_note(node),
            }
        )
        if children:
            expanded.append(nid)
            frames.append(
                {
                    "visible_nodes": list(visible),
                    "expanded_nodes": list(expanded),
                    "notes": _node_unpack_note(node),
                }
            )

    for d in range(max_depth + 1):
        layer_nodes = [n for n in nodes if depth[str(n["id"])] == d]
        if not layer_nodes:
            continue

        if len(layer_nodes) > 1 and d > 0 and density == "standard":
            for n in layer_nodes:
                _emit_node_step(n)
        else:
            # Group simple trunk nodes or compact layers together, while still unpacking groups cleanly
            pending_unpacks: list[dict[str, Any]] = []
            notes_parts: list[str] = []
            for n in layer_nodes:
                nid = str(n["id"])
                visible.append(nid)
                if n.get("kind") == "group_dashed" and n.get("children"):
                    expanded.append(nid)
                    notes_parts.append(_node_unpack_note(n))
                else:
                    notes_parts.append(_node_appear_note(n))
                    if n.get("children"):
                        pending_unpacks.append(n)

            frames.append(
                {
                    "visible_nodes": list(visible),
                    "expanded_nodes": list(expanded),
                    "notes": "；".join(notes_parts),
                }
            )
            for n in pending_unpacks:
                expanded.append(str(n["id"]))
                frames.append(
                    {
                        "visible_nodes": list(visible),
                        "expanded_nodes": list(expanded),
                        "notes": _node_unpack_note(n),
                    }
                )

    return frames


def _pace_hub_spoke(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Reveal central hub first, then attach surrounding spokes incrementally."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    if not nodes:
        return [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]

    hub = nodes[0]
    visible = [str(hub["id"])]
    frames: list[dict[str, Any]] = [
        {
            "visible_nodes": list(visible),
            "expanded_nodes": [],
            "notes": _node_appear_note(hub),
        }
    ]

    spokes = nodes[1:]
    step = 2 if (density == "compact" and len(spokes) >= 4) else 1
    for i in range(0, len(spokes), step):
        batch = spokes[i : i + step]
        visible.extend(str(n["id"]) for n in batch)
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": [],
                "notes": "；".join(_node_appear_note(n) for n in batch),
            }
        )
    return frames


def _pace_comparison(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Reveal comparison columns side-by-side incrementally so VS divider appears with contrast."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    if not nodes:
        return [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]

    if density == "compact" and len(nodes) == 2 and not any(n.get("children") for n in nodes):
        return [
            {
                "visible_nodes": [str(n["id"]) for n in nodes],
                "expanded_nodes": [],
                "notes": "；".join(_node_appear_note(n) for n in nodes),
            }
        ]

    visible: list[str] = []
    expanded: list[str] = []
    frames: list[dict[str, Any]] = []
    for n in nodes:
        nid = str(n["id"])
        visible.append(nid)
        if n.get("children"):
            expanded.append(nid)
            note = _node_unpack_note(n)
        else:
            note = _node_appear_note(n)
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": list(expanded),
                "notes": note,
            }
        )
    return frames


def _pace_sequence_timeline(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Step through sequence/state transitions edge-by-edge with active endpoint focus."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    edges: list[dict[str, Any]] = scene.get("edges", [])
    if not nodes:
        return [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]
    if not edges:
        return _pace_linear_flow(scene, density)

    node_map = {str(n["id"]): n for n in nodes}
    frames: list[dict[str, Any]] = []
    visible: list[str] = [str(nodes[0]["id"])]
    seen_edges: list[str] = []

    if density == "standard":
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": [],
                "visible_edges": [],
                "notes": _node_appear_note(nodes[0]),
            }
        )

    for edge in edges:
        eid = str(edge["id"])
        f_id, t_id = str(edge["from"]), str(edge["to"])
        if f_id not in visible:
            visible.append(f_id)
        if t_id not in visible:
            visible.append(t_id)
        seen_edges.append(eid)

        to_node = node_map.get(t_id, {})
        elabel = edge.get("label")
        step_note = _node_appear_note(to_node) if to_node else f"{f_id} -> {t_id}"
        if elabel:
            step_note = f"[{elabel}] {step_note}"

        frame: dict[str, Any] = {
            "visible_nodes": list(visible),
            "expanded_nodes": [],
            "visible_edges": list(seen_edges),
            "notes": step_note,
        }
        if density == "standard":
            frame["focus_nodes"] = [f_id, t_id]
        frames.append(frame)

    if density == "standard" and len(frames) > 1:
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": [],
                "visible_edges": list(seen_edges),
                "notes": scene.get("intro_note") or f"完整流转闭环：{scene['title']}",
            }
        )
    return frames


def _pace_metrics_cards(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Reveal KPI/metric highlight cards one-by-one (standard) or all together (compact)."""
    nodes: list[dict[str, Any]] = scene.get("nodes", [])
    if not nodes:
        return [{"visible_nodes": [], "expanded_nodes": [], "notes": str(scene.get("title", ""))}]

    if density == "compact":
        return [
            {
                "visible_nodes": [str(n["id"]) for n in nodes],
                "expanded_nodes": [],
                "notes": "；".join(_node_appear_note(n) for n in nodes),
            }
        ]

    visible: list[str] = []
    frames: list[dict[str, Any]] = []
    for n in nodes:
        visible.append(str(n["id"]))
        frames.append(
            {
                "visible_nodes": list(visible),
                "expanded_nodes": [],
                "notes": _node_appear_note(n),
            }
        )
    return frames


def _pace_proportion_bar(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Reveal summary + scale axis first, then progressively add proportion segments."""
    pb = scene.get("proportion_bar") or {}
    items: list[dict[str, Any]] = pb.get("items", [])
    if not items:
        return [{"visible_nodes": [], "notes": str(scene.get("title", ""))}]

    if density == "compact":
        return [
            {
                "visible_items": [],
                "notes": scene.get("intro_note") or f"{scene['title']}：先建立 0–100 刻度与分布列表。",
            },
            {
                "visible_items": [str(it["id"]) for it in items],
                "notes": "；".join(
                    str(it.get("note") or f"{it['label']} ({it.get('display_value') or it['value']})")
                    for it in items
                ),
            },
        ]

    frames: list[dict[str, Any]] = [
        {
            "visible_items": [],
            "notes": scene.get("intro_note") or f"{scene['title']}：先展示总体分布与刻度基线。",
        }
    ]
    visible_items: list[str] = []
    for it in items:
        visible_items.append(str(it["id"]))
        note = str(it.get("note") or f"{it['label']}：{it.get('display_value') or it['value']}")
        frames.append({"visible_items": list(visible_items), "notes": note})
    return frames


def _pace_comparison_matrix(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Reveal baseline column first, then sweep columns, then action/takeaway callout annotations."""
    mx = scene.get("matrix") or {}
    cols: list[dict[str, Any]] = mx.get("columns", [])
    if not cols:
        return [{"visible_nodes": [], "notes": str(scene.get("title", ""))}]

    # Order baseline column first if marked, preserving relative order otherwise
    ordered_cols = sorted(cols, key=lambda c: 0 if c.get("is_baseline") else 1)
    has_annotations = any(c.get("action_banner") or c.get("takeaway") for c in cols)

    if density == "compact":
        all_ids = [str(c["id"]) for c in cols]
        frames = [
            {
                "visible_columns": all_ids,
                "show_annotations": not has_annotations,
                "notes": scene.get("intro_note") or f"{scene['title']}：展示多组参数对照结果。",
            }
        ]
        if has_annotations:
            frames.append(
                {
                    "visible_columns": all_ids,
                    "show_annotations": True,
                    "notes": "；".join(
                        str(c.get("note") or f"{c['caption']}: {c.get('takeaway') or c.get('action_banner')}")
                        for c in cols
                        if c.get("action_banner") or c.get("takeaway")
                    ),
                }
            )
        return frames

    frames = []
    visible_cols: list[str] = []
    for col in ordered_cols:
        visible_cols.append(str(col["id"]))
        # Maintain natural left-to-right column order in visible_columns
        ordered_vis = [str(c["id"]) for c in cols if str(c["id"]) in visible_cols]
        frames.append(
            {
                "visible_columns": ordered_vis,
                "show_annotations": False,
                "notes": str(col.get("note") or f"{col['caption']} 参数分布结果。"),
            }
        )

    if has_annotations:
        all_ids = [str(c["id"]) for c in cols]
        frames.append(
            {
                "visible_columns": all_ids,
                "show_annotations": True,
                "notes": "；".join(
                    str(c.get("note") or f"{c['caption']}: {c.get('takeaway') or c.get('action_banner')}")
                    for c in cols
                    if c.get("action_banner") or c.get("takeaway")
                ),
            }
        )
    return frames


def _canvas_object_note(obj: dict[str, Any]) -> str:
    if obj.get("note"):
        return str(obj["note"])
    kind = obj.get("kind", "")
    if kind in ("card", "callout", "shape"):
        parts = [str(obj.get("label") or obj["id"])]
        if obj.get("metric"):
            parts.insert(0, str(obj["metric"]))
        if obj.get("sublabel"):
            parts.append(str(obj["sublabel"]))
        return " · ".join(parts)
    if kind == "chart":
        ch = obj.get("chart") or {}
        return str(ch.get("title") or obj["id"])
    if kind == "table":
        tb = obj.get("table") or {}
        return str(tb.get("title") or obj["id"])
    if kind == "textbox":
        return str(obj.get("text") or obj["id"])
    return str(obj["id"])


def _pace_canvas(scene: dict[str, Any], density: DensityMode) -> list[dict[str, Any]]:
    """Expand a freeform canvas scene deterministically by object step and chart/table reveal rules."""
    objects: list[dict[str, Any]] = scene.get("objects", [])
    if not objects:
        return [{"visible_objects": [], "notes": str(scene.get("intro_note") or scene.get("title", ""))}]

    if density == "compact":
        has_progressive_sub = any(
            (o.get("kind") == "chart" and (o.get("chart") or {}).get("reveal", "whole") != "whole")
            or (o.get("kind") == "table" and (o.get("table") or {}).get("reveal", "whole") != "whole")
            for o in objects
        )
        if not has_progressive_sub and len({int(o.get("step", 1)) for o in objects}) <= 1:
            return [
                {
                    "visible_objects": [str(o["id"]) for o in objects],
                    "notes": "；".join(_canvas_object_note(o) for o in objects),
                }
            ]

    frames: list[dict[str, Any]] = []
    step_values = sorted({int(o.get("step", 1)) for o in objects})
    if scene.get("intro_note") and density == "standard" and 0 not in step_values:
        frames.append({"visible_objects": [], "notes": str(scene["intro_note"])})

    visible: list[str] = []
    committed_states: dict[str, dict[str, int]] = {}

    for step_num in step_values:
        batch = [o for o in objects if int(o.get("step", 1)) == step_num]
        batch_ids = [str(o["id"]) for o in batch]
        visible.extend(batch_ids)

        # Check if any object in this step has sub-frame progressive reveal (chart/table)
        sub_stages: list[tuple[dict[str, dict[str, int]], str]] = []
        if density == "standard":
            for obj in batch:
                oid = str(obj["id"])
                kind = obj.get("kind")
                if kind == "chart":
                    ch = obj.get("chart") or {}
                    rev = ch.get("reveal", "whole")
                    if rev == "by_series" and len(ch.get("series", [])) > 1:
                        for k in range(1, len(ch["series"]) + 1):
                            sr_name = ch["series"][k - 1].get("name", f"Series {k}")
                            sub_stages.append(({oid: {"series_count": k}}, f"{_canvas_object_note(obj)}（{sr_name}）"))
                        committed_states[oid] = {"series_count": len(ch["series"])}
                    elif rev == "by_category" and len(ch.get("categories", [])) > 1:
                        for k in range(1, len(ch["categories"]) + 1):
                            cat_name = ch["categories"][k - 1]
                            sub_stages.append(({oid: {"category_count": k}}, f"{_canvas_object_note(obj)}（{cat_name}）"))
                        committed_states[oid] = {"category_count": len(ch["categories"])}
                elif kind == "table":
                    tb = obj.get("table") or {}
                    rev = tb.get("reveal", "whole")
                    if rev == "by_row" and len(tb.get("rows", [])) > 1:
                        for k in range(1, len(tb["rows"]) + 1):
                            sub_stages.append(({oid: {"row_count": k}}, f"{_canvas_object_note(obj)}（第 {k} 行）"))
                        committed_states[oid] = {"row_count": len(tb["rows"])}
                    elif rev == "by_column" and len(tb.get("headers", [])) > 1:
                        for k in range(1, len(tb["headers"]) + 1):
                            hdr = tb["headers"][k - 1]
                            sub_stages.append(({oid: {"col_count": k}}, f"{_canvas_object_note(obj)}（{hdr}）"))
                        committed_states[oid] = {"col_count": len(tb["headers"])}

        if not sub_stages:
            frame_obj: dict[str, Any] = {
                "visible_objects": list(visible),
                "notes": "；".join(_canvas_object_note(o) for o in batch),
            }
            if committed_states:
                frame_obj["object_states"] = copy.deepcopy(committed_states)
            if density == "standard" and len(step_values) > 1 and len(visible) > len(batch_ids):
                frame_obj["focus_objects"] = list(batch_ids)
            frames.append(frame_obj)
        else:
            # Emit progressive sub-stages for chart/table in this batch
            base_states = copy.deepcopy(committed_states)
            for oid in batch_ids:
                base_states.pop(oid, None)
            for idx, (delta_state, sub_note) in enumerate(sub_stages):
                merged = copy.deepcopy(base_states)
                for k_id, k_st in delta_state.items():
                    merged[k_id] = k_st
                # Keep previously finished sub-stages in this batch if multiple progressive objects share a step
                if idx == len(sub_stages) - 1:
                    for k_id, k_st in committed_states.items():
                        if k_id in batch_ids:
                            merged[k_id] = k_st
                frame_obj = {
                    "visible_objects": list(visible),
                    "notes": sub_note,
                }
                if merged:
                    frame_obj["object_states"] = merged
                if density == "standard" and len(step_values) > 1 and len(visible) > len(batch_ids):
                    frame_obj["focus_objects"] = list(batch_ids)
                frames.append(frame_obj)

    if density == "standard" and len(frames) > 1 and any("focus_objects" in f for f in frames):
        final_frame: dict[str, Any] = {
            "visible_objects": list(visible),
            "notes": str(scene.get("intro_note") or scene.get("claim") or f"全景汇总：{scene['title']}"),
        }
        if committed_states:
            final_frame["object_states"] = copy.deepcopy(committed_states)
        frames.append(final_frame)

    return frames


_PACERS = {
    "canvas": _pace_canvas,
    "horizontal_flow": _pace_linear_flow,
    "vertical_flow": _pace_linear_flow,
    "flow_dag": _pace_flow_dag,
    "hub_spoke": _pace_hub_spoke,
    "comparison": _pace_comparison,
    "architecture_evolution": _pace_comparison,
    "sequence_timeline": _pace_sequence_timeline,
    "metrics_cards": _pace_metrics_cards,
    "proportion_bar": _pace_proportion_bar,
    "comparison_matrix": _pace_comparison_matrix,
}


def expand_scene_frames(scene: dict[str, Any], *, density: DensityMode = "standard") -> list[dict[str, Any]]:
    """Deterministically expand a Stage 1 full-state scene dict into progressive frames."""
    inferred = "canvas" if ("objects" in scene or "regions" in scene) else "horizontal_flow"
    layout = str(scene.get("layout", inferred))
    pacer = _PACERS.get(layout, _pace_linear_flow)
    return pacer(scene, density)


def pace_deck(
    raw_deck: dict[str, Any],
    *,
    density: DensityMode | None = None,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    """Return a copy of raw_deck with progressive 'frames' materialized for auto-paced scenes."""
    deck = copy.deepcopy(raw_deck)
    for scene in deck.get("scenes", []):
        has_frames = bool(scene.get("frames"))
        scene_pacing = scene.get("pacing", "manual" if has_frames else "auto")
        if overwrite_existing or not has_frames or scene_pacing in ("auto", "compact"):
            if not overwrite_existing and has_frames and scene_pacing == "manual":
                continue
            eff_density: DensityMode = density or ("compact" if scene_pacing == "compact" else "standard")
            scene["frames"] = expand_scene_frames(scene, density=eff_density)
            scene["pacing"] = "manual"
    return deck
