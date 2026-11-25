"""Stage 2 progressive pacing engine: expand full-state scene graphs into step-by-step frames."""

from __future__ import annotations

import copy
from typing import Any, Literal

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

    order = {str(n["id"]): i for i, n in enumerate(nodes)}
    parents: dict[str, list[str]] = {str(n["id"]): [] for n in nodes}
    for e in edges:
        f_id, t_id = str(e["from"]), str(e["to"])
        if f_id in order and t_id in order and order[f_id] < order[t_id]:
            parents[t_id].append(f_id)

    depth: dict[str, int] = {}
    for n in nodes:
        nid = str(n["id"])
        depth[nid] = 0 if not parents[nid] else 1 + max(depth.get(p, 0) for p in parents[nid])

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


_PACERS = {
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
    layout = str(scene.get("layout", "horizontal_flow"))
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
