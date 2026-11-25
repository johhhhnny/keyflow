"""Cognitive storyboard DSL models and mode-aware structural validator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from keyflow.themes import THEMES

LayoutMode = Literal[
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
]
NodeKind = Literal["card", "group_dashed"]
NodeVariant = Literal["primary", "accent", "muted", "success", "warn"]
ChildLayout = Literal["row", "column", "grid"]
CaptionPosition = Literal["bottom", "top", "inside"]
EdgeStyle = Literal["solid", "dashed"]
PacingMode = Literal["auto", "compact", "manual"]
TrendDirection = Literal["up", "down", "neutral"]


@dataclass(slots=True)
class ChildNodeSpec:
    """A compact sub-concept card nested inside an expanded group container."""

    id: str
    label: str
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    variant: NodeVariant = "primary"
    note: str = ""


@dataclass(slots=True)
class NodeSpec:
    """Top-level concept node in a scene, optionally expandable into a dashed group."""

    id: str
    label: str
    sublabel: str | None = None
    badge: str | None = None
    metric: str | None = None
    kind: NodeKind = "card"
    variant: NodeVariant = "primary"
    children: list[ChildNodeSpec] = field(default_factory=list)
    child_layout: ChildLayout = "row"
    caption_position: CaptionPosition = "bottom"
    note: str = ""


@dataclass(slots=True)
class EdgeSpec:
    """Directed relationship between two top-level nodes."""

    id: str
    from_id: str
    to_id: str
    label: str | None = None
    style: EdgeStyle = "solid"


@dataclass(slots=True)
class PinnedFlowGroupSpec:
    """A dashed legend container wrapping contiguous nodes inside the Deck pinned_flow ribbon."""

    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PinnedFlowSpec:
    """Deck-level persistent top navigation ribbon shared across scenes."""

    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    groups: list[PinnedFlowGroupSpec] = field(default_factory=list)


@dataclass(slots=True)
class ProportionItemSpec:
    """One quantitative segment in a proportion_bar scene."""

    id: str
    label: str
    value: float
    display_value: str | None = None
    note: str = ""


@dataclass(slots=True)
class ProportionBarSpec:
    """Segmented proportion scale primitive with optional left summary list."""

    items: list[ProportionItemSpec] = field(default_factory=list)
    axis_min: float = 0.0
    axis_max: float = 100.0
    axis_step: float = 10.0
    unit: str = "%"
    show_summary_list: bool = True
    summary_title: str = ""


@dataclass(slots=True)
class MatrixRowSpec:
    """One row inside a comparison_matrix column card."""

    chip: str
    values: list[str] = field(default_factory=list)
    trend: TrendDirection | None = None


@dataclass(slots=True)
class MatrixColumnSpec:
    """One dashed comparison column panel in a comparison_matrix scene."""

    id: str
    caption: str
    headers: list[str] = field(default_factory=list)
    rows: list[MatrixRowSpec] = field(default_factory=list)
    action_banner: str | None = None
    action_subtext: str | None = None
    takeaway: str | None = None
    is_baseline: bool = False
    note: str = ""


@dataclass(slots=True)
class ComparisonMatrixSpec:
    """Multi-column structured numeric comparison primitive."""

    formula: str | None = None
    columns: list[MatrixColumnSpec] = field(default_factory=list)


@dataclass(slots=True)
class FrameSpec:
    """One progressive visual frame within a scene."""

    visible_nodes: list[str] = field(default_factory=list)
    expanded_nodes: list[str] = field(default_factory=list)
    visible_edges: list[str] | Literal["auto"] = "auto"
    focus_nodes: list[str] | None = None
    visible_items: list[str] | None = None
    visible_columns: list[str] | None = None
    show_annotations: bool = True
    notes: str = ""
    subtitle: str | None = None


@dataclass(slots=True)
class SceneSpec:
    """One conceptual diagram sequence (rendered as 1..N progressive slides)."""

    id: str
    title: str
    layout: LayoutMode = "horizontal_flow"
    subtitle: str | None = None
    pacing: PacingMode = "auto"
    intro_note: str = ""
    active_flow_node: str | None = None
    show_pinned_flow: bool = True
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    proportion_bar: ProportionBarSpec | None = None
    matrix: ComparisonMatrixSpec | None = None
    frames: list[FrameSpec] = field(default_factory=list)


@dataclass(slots=True)
class DeckSpec:
    """Complete presentation specification compiled into a .keyx bundle."""

    title: str
    theme: str = "slate_dark"
    slide_width: int = 1920
    slide_height: int = 1080
    pinned_flow: PinnedFlowSpec | None = None
    scenes: list[SceneSpec] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    """Structured validation diagnostics for CLI, MCP, and LLM self-correction."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _parse_nodes_and_edges(raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]]) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    nodes: list[NodeSpec] = []
    for n_raw in raw_nodes:
        children = [
            ChildNodeSpec(
                id=str(c["id"]),
                label=str(c["label"]),
                sublabel=str(c["sublabel"]) if c.get("sublabel") else None,
                badge=str(c["badge"]) if c.get("badge") else None,
                metric=str(c["metric"]) if c.get("metric") else None,
                variant=c.get("variant", "primary"),
                note=str(c.get("note", "")),
            )
            for c in n_raw.get("children", [])
        ]
        nodes.append(
            NodeSpec(
                id=str(n_raw["id"]),
                label=str(n_raw["label"]),
                sublabel=str(n_raw["sublabel"]) if n_raw.get("sublabel") else None,
                badge=str(n_raw["badge"]) if n_raw.get("badge") else None,
                metric=str(n_raw["metric"]) if n_raw.get("metric") else None,
                kind=n_raw.get("kind", "card"),
                variant=n_raw.get("variant", "primary"),
                children=children,
                child_layout=n_raw.get("child_layout", "row"),
                caption_position=n_raw.get("caption_position", "bottom"),
                note=str(n_raw.get("note", "")),
            )
        )

    edges = [
        EdgeSpec(
            id=str(e["id"]),
            from_id=str(e["from"]),
            to_id=str(e["to"]),
            label=str(e["label"]) if e.get("label") else None,
            style=e.get("style", "solid"),
        )
        for e in raw_edges
    ]
    return nodes, edges


def parse_deck(raw: dict[str, Any]) -> DeckSpec:
    """Parse a raw JSON dictionary into typed DeckSpec dataclasses."""
    if not isinstance(raw, dict):
        raise ValueError("Deck payload must be a JSON object.")

    pinned_flow: PinnedFlowSpec | None = None
    if raw.get("pinned_flow"):
        pf_raw = raw["pinned_flow"]
        pf_nodes, pf_edges = _parse_nodes_and_edges(pf_raw.get("nodes", []), pf_raw.get("edges", []))
        pf_groups = [
            PinnedFlowGroupSpec(
                id=str(g["id"]),
                label=str(g["label"]),
                node_ids=[str(nid) for nid in g.get("node_ids", [])],
            )
            for g in pf_raw.get("groups", [])
        ]
        pinned_flow = PinnedFlowSpec(nodes=pf_nodes, edges=pf_edges, groups=pf_groups)

    scenes: list[SceneSpec] = []
    for s_raw in raw.get("scenes", []):
        nodes, edges = _parse_nodes_and_edges(s_raw.get("nodes", []), s_raw.get("edges", []))

        prop_bar: ProportionBarSpec | None = None
        if s_raw.get("proportion_bar"):
            pb = s_raw["proportion_bar"]
            prop_bar = ProportionBarSpec(
                items=[
                    ProportionItemSpec(
                        id=str(it["id"]),
                        label=str(it["label"]),
                        value=float(it["value"]),
                        display_value=str(it["display_value"]) if it.get("display_value") else None,
                        note=str(it.get("note", "")),
                    )
                    for it in pb.get("items", [])
                ],
                axis_min=float(pb.get("axis_min", 0.0)),
                axis_max=float(pb.get("axis_max", 100.0)),
                axis_step=float(pb.get("axis_step", 10.0)),
                unit=str(pb.get("unit", "%")),
                show_summary_list=bool(pb.get("show_summary_list", True)),
                summary_title=str(pb.get("summary_title", "")),
            )

        matrix: ComparisonMatrixSpec | None = None
        if s_raw.get("matrix"):
            mx = s_raw["matrix"]
            matrix = ComparisonMatrixSpec(
                formula=str(mx["formula"]) if mx.get("formula") else None,
                columns=[
                    MatrixColumnSpec(
                        id=str(col["id"]),
                        caption=str(col["caption"]),
                        headers=[str(h) for h in col.get("headers", [])],
                        rows=[
                            MatrixRowSpec(
                                chip=str(r["chip"]),
                                values=[str(v) for v in r.get("values", [])],
                                trend=r.get("trend"),
                            )
                            for r in col.get("rows", [])
                        ],
                        action_banner=str(col["action_banner"]) if col.get("action_banner") else None,
                        action_subtext=str(col["action_subtext"]) if col.get("action_subtext") else None,
                        takeaway=str(col["takeaway"]) if col.get("takeaway") else None,
                        is_baseline=bool(col.get("is_baseline", False)),
                        note=str(col.get("note", "")),
                    )
                    for col in mx.get("columns", [])
                ],
            )

        frames: list[FrameSpec] = []
        for f_raw in s_raw.get("frames") or []:
            frames.append(
                FrameSpec(
                    visible_nodes=[str(x) for x in f_raw.get("visible_nodes", [])],
                    expanded_nodes=[str(x) for x in f_raw.get("expanded_nodes", [])],
                    visible_edges=f_raw.get("visible_edges", "auto"),
                    focus_nodes=(
                        [str(x) for x in f_raw["focus_nodes"]]
                        if f_raw.get("focus_nodes") is not None
                        else None
                    ),
                    visible_items=(
                        [str(x) for x in f_raw["visible_items"]]
                        if f_raw.get("visible_items") is not None
                        else None
                    ),
                    visible_columns=(
                        [str(x) for x in f_raw["visible_columns"]]
                        if f_raw.get("visible_columns") is not None
                        else None
                    ),
                    show_annotations=bool(f_raw.get("show_annotations", True)),
                    notes=str(f_raw.get("notes", "")),
                    subtitle=f_raw.get("subtitle"),
                )
            )

        default_pacing = "manual" if frames else "auto"
        scenes.append(
            SceneSpec(
                id=str(s_raw["id"]),
                title=str(s_raw["title"]),
                layout=s_raw.get("layout", "horizontal_flow"),
                subtitle=s_raw.get("subtitle"),
                pacing=s_raw.get("pacing", default_pacing),
                intro_note=str(s_raw.get("intro_note", "")),
                active_flow_node=str(s_raw["active_flow_node"]) if s_raw.get("active_flow_node") else None,
                show_pinned_flow=bool(s_raw.get("show_pinned_flow", True)),
                nodes=nodes,
                edges=edges,
                proportion_bar=prop_bar,
                matrix=matrix,
                frames=frames,
            )
        )

    slide_size = raw.get("slide_size", {})
    return DeckSpec(
        title=str(raw.get("title", "Untitled Deck")),
        theme=str(raw.get("theme", "slate_dark")),
        slide_width=int(slide_size.get("width", 1920)),
        slide_height=int(slide_size.get("height", 1080)),
        pinned_flow=pinned_flow,
        scenes=scenes,
    )


def _check_label_density(
    target: str,
    label: str,
    sublabel: str | None,
    badge: str | None,
    metric: str | None,
    warnings: list[str],
) -> None:
    if "\n" in label or "•" in label:
        warnings.append(
            f"{target}: label contains line breaks or bullets; keep canvas cards single-phrase and move details to 'note'/'notes'."
        )
    elif len(label) > 18:
        warnings.append(
            f"{target}: label '{label}' exceeds 18 chars; consider tightening or splitting into 'sublabel'."
        )
    for field_name, val, limit in (
        ("sublabel", sublabel, 20),
        ("badge", badge, 16),
        ("metric", metric, 14),
    ):
        if val:
            if "\n" in val or "•" in val:
                warnings.append(f"{target}: {field_name} contains line breaks or bullets; keep it concise.")
            elif len(val) > limit:
                warnings.append(f"{target}: {field_name} '{val}' exceeds {limit} chars; tighten for readability.")


def compute_dag_layers(
    node_ids: Sequence[str],
    edge_pairs: Sequence[tuple[str, str]],
) -> tuple[dict[str, int], list[str]]:
    """Compute dependency layer depth via Kahn's topological sort, independent of input order.

    Returns ``(layers, cyclic_node_ids)`` where ``cyclic_node_ids`` lists any nodes
    participating in or blocked by directed cycles (sorted in input order).
    """
    unique_ids: list[str] = []
    seen_ids: set[str] = set()
    for nid in node_ids:
        if nid not in seen_ids:
            seen_ids.add(nid)
            unique_ids.append(nid)

    if not unique_ids:
        return {}, []

    children: dict[str, list[str]] = {nid: [] for nid in unique_ids}
    parents: dict[str, list[str]] = {nid: [] for nid in unique_ids}
    indegree: dict[str, int] = {nid: 0 for nid in unique_ids}
    seen_edges: set[tuple[str, str]] = set()

    for src, dst in edge_pairs:
        if src in seen_ids and dst in seen_ids and src != dst and (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            children[src].append(dst)
            parents[dst].append(src)
            indegree[dst] += 1

    queue: deque[str] = deque(nid for nid in unique_ids if indegree[nid] == 0)
    layers: dict[str, int] = {nid: 0 for nid in queue}

    while queue:
        u = queue.popleft()
        for v in children[u]:
            layers[v] = max(layers.get(v, 0), layers[u] + 1)
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)

    cyclic = [nid for nid in unique_ids if nid not in layers]
    if cyclic:
        max_layer = max(layers.values(), default=-1)
        for nid in cyclic:
            resolved_parents = [layers[p] for p in parents[nid] if p in layers]
            layers[nid] = (1 + max(resolved_parents)) if resolved_parents else (max_layer + 1)

    return layers, cyclic


def _as_float(val: Any) -> float | None:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    return float(val)


def validate_deck(raw: dict[str, Any]) -> ValidationResult:
    """Validate structural integrity, references, and visual density rules."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(raw, dict):
        return ValidationResult(valid=False, errors=["Top-level JSON must be an object."])

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("Missing or invalid top-level 'title'.")

    theme = raw.get("theme", "slate_dark")
    if not isinstance(theme, str) or theme not in THEMES:
        errors.append(f"Unknown theme '{theme}'. Valid options: {', '.join(sorted(THEMES))}.")

    pf_node_ids: set[str] = set()
    if raw.get("pinned_flow") is not None:
        pf = raw["pinned_flow"]
        if not isinstance(pf, dict):
            errors.append("'pinned_flow' must be an object.")
        else:
            pf_nodes = pf.get("nodes", [])
            if not isinstance(pf_nodes, list) or not pf_nodes:
                errors.append("pinned_flow.nodes must be a non-empty list.")
            else:
                for idx, n in enumerate(pf_nodes):
                    if not isinstance(n, dict):
                        errors.append(f"pinned_flow.nodes[{idx}]: must be an object.")
                        continue
                    nid = n.get("id")
                    if not isinstance(nid, str) or not nid:
                        errors.append(f"pinned_flow.nodes[{idx}]: missing 'id'.")
                    elif nid in pf_node_ids:
                        errors.append(f"pinned_flow: duplicate node id '{nid}'.")
                    else:
                        pf_node_ids.add(nid)
                    if not isinstance(n.get("label"), str) or not n.get("label"):
                        errors.append(f"pinned_flow.nodes[{idx}]: missing 'label'.")
                pf_edges = pf.get("edges", [])
                if not isinstance(pf_edges, list):
                    errors.append("pinned_flow.edges must be a list.")
                else:
                    for e_idx, e in enumerate(pf_edges):
                        if not isinstance(e, dict):
                            errors.append(f"pinned_flow.edges[{e_idx}]: must be an object.")
                            continue
                        if e.get("from") not in pf_node_ids:
                            errors.append(f"pinned_flow.edges[{e_idx}]: unknown 'from' node '{e.get('from')}'.")
                        if e.get("to") not in pf_node_ids:
                            errors.append(f"pinned_flow.edges[{e_idx}]: unknown 'to' node '{e.get('to')}'.")
                pf_groups = pf.get("groups", [])
                if not isinstance(pf_groups, list):
                    errors.append("pinned_flow.groups must be a list.")
                else:
                    for g_idx, g in enumerate(pf_groups):
                        if not isinstance(g, dict):
                            errors.append(f"pinned_flow.groups[{g_idx}]: must be an object.")
                            continue
                        if not isinstance(g.get("label"), str) or not g.get("label"):
                            errors.append(f"pinned_flow.groups[{g_idx}]: missing 'label'.")
                        g_nids = g.get("node_ids", [])
                        if not isinstance(g_nids, list):
                            errors.append(f"pinned_flow.groups[{g_idx}]: 'node_ids' must be a list.")
                        else:
                            for nid in g_nids:
                                if nid not in pf_node_ids:
                                    errors.append(f"pinned_flow.groups[{g_idx}]: unknown node '{nid}'.")

    raw_scenes = raw.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        errors.append("'scenes' must be a non-empty list.")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    valid_layouts = {
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
    valid_child_layouts = {"row", "column", "grid"}
    valid_pacing = {"auto", "compact", "manual"}
    valid_variants = {"primary", "accent", "muted", "success", "warn"}
    scene_ids: set[str] = set()

    for s_idx, s in enumerate(raw_scenes):
        prefix = f"scenes[{s_idx}]"
        if not isinstance(s, dict):
            errors.append(f"{prefix}: scene entry must be an object.")
            continue

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

        layout = s.get("layout", "horizontal_flow")
        if not isinstance(layout, str) or layout not in valid_layouts:
            errors.append(f"{prefix}: invalid layout '{layout}'.")

        active_fn = s.get("active_flow_node")
        if active_fn is not None:
            if not isinstance(active_fn, str):
                errors.append(f"{prefix}: 'active_flow_node' must be a string.")
            elif active_fn:
                if not pf_node_ids:
                    errors.append(f"{prefix}: 'active_flow_node' set to '{active_fn}' without top-level 'pinned_flow'.")
                elif active_fn not in pf_node_ids:
                    errors.append(f"{prefix}: unknown active_flow_node '{active_fn}'.")

        has_frames = "frames" in s and s["frames"] is not None
        pacing = s.get("pacing", "manual" if has_frames else "auto")
        if not isinstance(pacing, str) or pacing not in valid_pacing:
            errors.append(f"{prefix}: invalid pacing '{pacing}'.")

        nodes = s.get("nodes", [])
        if not isinstance(nodes, list):
            errors.append(f"{prefix}.nodes must be a list.")
            continue

        node_map: dict[str, dict[str, Any]] = {}
        node_order: list[str] = []
        for n_idx, n in enumerate(nodes):
            if not isinstance(n, dict):
                errors.append(f"{prefix}.nodes[{n_idx}]: must be an object.")
                continue
            nid = n.get("id")
            if not isinstance(nid, str) or not nid:
                errors.append(f"{prefix}.nodes[{n_idx}]: missing 'id'.")
                continue
            if nid in node_map:
                errors.append(f"{prefix}: duplicate node id '{nid}'.")
            else:
                node_order.append(nid)
            node_map[nid] = n

            variant = n.get("variant", "primary")
            if variant not in valid_variants:
                errors.append(f"{prefix}.nodes['{nid}']: invalid variant '{variant}'.")

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
            if child_layout not in valid_child_layouts:
                errors.append(f"{prefix}.nodes['{nid}']: invalid child_layout '{child_layout}'.")

            children = n.get("children", [])
            if not isinstance(children, list):
                errors.append(f"{prefix}.nodes['{nid}'].children must be a list.")
                children = []
            if n.get("kind") == "group_dashed" and not children:
                errors.append(f"{prefix}.nodes['{nid}']: kind='group_dashed' requires non-empty 'children'.")
            if layout == "horizontal_flow" and len(children) >= 4 and child_layout == "row":
                warnings.append(
                    f"{prefix}.nodes['{nid}']: {len(children)} children in horizontal 'row' may squeeze the flow; consider child_layout='grid'."
                )

            child_ids: set[str] = set()
            for c_idx, c in enumerate(children):
                if not isinstance(c, dict):
                    errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: must be an object.")
                    continue
                cid = c.get("id")
                if not isinstance(cid, str) or not cid:
                    errors.append(f"{prefix}.nodes['{nid}'].children[{c_idx}]: missing 'id'.")
                elif cid in child_ids:
                    errors.append(f"{prefix}.nodes['{nid}']: duplicate child id '{cid}'.")
                else:
                    child_ids.add(cid)

                cvar = c.get("variant", "primary")
                if cvar not in valid_variants:
                    errors.append(f"{prefix}.nodes['{nid}'].children['{cid}']: invalid variant '{cvar}'.")

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

        if layout == "horizontal_flow" and len(nodes) > 5:
            warnings.append(
                f"{prefix}: {len(nodes)} top-level nodes in horizontal_flow may feel crowded; 3-5 pillars is recommended."
            )

        edges = s.get("edges", [])
        edge_ids: set[str] = set()
        valid_edge_pairs: list[tuple[str, str]] = []
        if not isinstance(edges, list):
            errors.append(f"{prefix}.edges must be a list.")
        else:
            for e_idx, e in enumerate(edges):
                if not isinstance(e, dict):
                    errors.append(f"{prefix}.edges[{e_idx}]: must be an object.")
                    continue
                eid = e.get("id")
                if not isinstance(eid, str) or not eid:
                    errors.append(f"{prefix}.edges[{e_idx}]: missing 'id'.")
                elif eid in edge_ids:
                    errors.append(f"{prefix}: duplicate edge id '{eid}'.")
                else:
                    edge_ids.add(eid)
                src = e.get("from")
                dst = e.get("to")
                if src not in node_map:
                    errors.append(f"{prefix}.edges['{eid}']: unknown 'from' node '{src}'.")
                if dst not in node_map:
                    errors.append(f"{prefix}.edges['{eid}']: unknown 'to' node '{dst}'.")
                if isinstance(src, str) and isinstance(dst, str) and src in node_map and dst in node_map:
                    if src == dst and layout == "flow_dag":
                        errors.append(f"{prefix}.edges['{eid}']: self-loop '{src} -> {dst}' is not allowed in flow_dag.")
                    valid_edge_pairs.append((src, dst))

        if layout == "flow_dag" and node_order and valid_edge_pairs:
            _, cyclic_nodes = compute_dag_layers(node_order, valid_edge_pairs)
            if cyclic_nodes:
                errors.append(
                    f"{prefix}: flow_dag contains cyclic dependencies involving: {', '.join(cyclic_nodes)}."
                )

        item_ids: set[str] = set()
        if layout == "proportion_bar":
            pb = s.get("proportion_bar")
            if not isinstance(pb, dict) or not isinstance(pb.get("items"), list) or not pb.get("items"):
                errors.append(f"{prefix}: layout='proportion_bar' requires 'proportion_bar.items' list.")
            else:
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
                    iid = it.get("id")
                    if not isinstance(iid, str) or not iid:
                        errors.append(f"{prefix}.proportion_bar.items[{it_idx}]: missing 'id'.")
                    elif iid in item_ids:
                        errors.append(f"{prefix}.proportion_bar: duplicate item id '{iid}'.")
                    else:
                        item_ids.add(iid)
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
                for c_idx, col in enumerate(mx.get("columns", [])):
                    if not isinstance(col, dict):
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: must be an object.")
                        continue
                    cid = col.get("id")
                    if not isinstance(cid, str) or not cid:
                        errors.append(f"{prefix}.matrix.columns[{c_idx}]: missing 'id'.")
                    elif cid in col_ids:
                        errors.append(f"{prefix}.matrix: duplicate column id '{cid}'.")
                    else:
                        col_ids.add(cid)
                    if not isinstance(col.get("caption"), str) or not col.get("caption"):
                        errors.append(f"{prefix}.matrix.columns['{cid}']: missing 'caption'.")
                    rows = col.get("rows")
                    if not isinstance(rows, list) or not rows:
                        errors.append(f"{prefix}.matrix.columns['{cid}']: must have at least one row.")
                    else:
                        for r_idx, row in enumerate(rows):
                            if not isinstance(row, dict):
                                errors.append(f"{prefix}.matrix.columns['{cid}'].rows[{r_idx}]: must be an object.")

        frames = s.get("frames")
        if frames is None:
            if pacing == "manual":
                errors.append(f"{prefix}: pacing='manual' requires a non-empty 'frames' list.")
            continue

        if not isinstance(frames, list) or not frames:
            errors.append(f"{prefix}: 'frames' must be a non-empty list when provided.")
            continue

        if len(nodes) >= 2 and len(frames) == 1 and pacing == "manual":
            warnings.append(
                f"{prefix}: {len(nodes)} nodes rendered in a single frame; consider splitting into progressive step-by-step frames or running `keyflow pace`."
            )

        for f_idx, f in enumerate(frames):
            if not isinstance(f, dict):
                errors.append(f"{prefix}.frames[{f_idx}]: frame entry must be an object.")
                continue
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
            ):
                field_val = f.get(list_field)
                if field_val is not None:
                    if not isinstance(field_val, list):
                        errors.append(f"{prefix}.frames[{f_idx}]: '{list_field}' must be a list.")
                    else:
                        for item_id in field_val:
                            if not isinstance(item_id, str) or item_id not in valid_pool:
                                errors.append(f"{prefix}.frames[{f_idx}]: unknown {list_field} id '{item_id}'.")

            if not f.get("notes"):
                warnings.append(
                    f"{prefix}.frames[{f_idx}]: empty 'notes'; put article explanations in presenter notes to keep the slide minimal."
                )

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
