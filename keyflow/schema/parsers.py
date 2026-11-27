"""Stage 1 / Stage 2 JSON parsers into typed KeyFlow dataclasses."""

from __future__ import annotations

from typing import Any

from keyflow.schema.models import (
    CanvasObjectSpec,
    ChartSeriesSpec,
    ChartSpec,
    ChildNodeSpec,
    ComparisonMatrixSpec,
    DeckSpec,
    DiagramSpec,
    EdgeSpec,
    FrameSpec,
    GridSpec,
    MatrixColumnSpec,
    MatrixRowSpec,
    NodeSpec,
    PinnedFlowGroupSpec,
    PinnedFlowSpec,
    ProportionBarSpec,
    ProportionItemSpec,
    RegionSpec,
    SceneSpec,
    StoryClaimSpec,
    StoryModelSpec,
    StyleConfigSpec,
    TableSpec,
)


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
                surface=c.get("surface", "filled"),
                note=str(c.get("note", "")),
                evidence_refs=[str(r) for r in c.get("evidence_refs", [])],
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
                surface=n_raw.get("surface", "filled"),
                children=children,
                child_layout=n_raw.get("child_layout", "row"),
                caption_position=n_raw.get("caption_position", "bottom"),
                note=str(n_raw.get("note", "")),
                evidence_refs=[str(r) for r in n_raw.get("evidence_refs", [])],
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


def _parse_style_config(raw: Any) -> StyleConfigSpec | None:
    if not isinstance(raw, dict):
        return None
    return StyleConfigSpec(
        title_max_size=float(raw["title_max_size"]) if raw.get("title_max_size") is not None else None,
        subtitle_size=float(raw["subtitle_size"]) if raw.get("subtitle_size") is not None else None,
        card_corner_px=float(raw["card_corner_px"]) if raw.get("card_corner_px") is not None else None,
        arrow_width=float(raw["arrow_width"]) if raw.get("arrow_width") is not None else None,
    )


def _parse_pinned_flow(pf_raw: dict[str, Any]) -> PinnedFlowSpec:
    pf_nodes, pf_edges = _parse_nodes_and_edges(pf_raw.get("nodes", []), pf_raw.get("edges", []))
    pf_groups = [
        PinnedFlowGroupSpec(
            id=str(g["id"]),
            label=str(g["label"]),
            node_ids=[str(nid) for nid in g.get("node_ids", [])],
        )
        for g in pf_raw.get("groups", [])
    ]
    return PinnedFlowSpec(nodes=pf_nodes, edges=pf_edges, groups=pf_groups)


def parse_deck(raw: dict[str, Any]) -> DeckSpec:
    """Parse a raw JSON dictionary into typed DeckSpec dataclasses."""
    if not isinstance(raw, dict):
        raise ValueError("Deck payload must be a JSON object.")

    pinned_flow: PinnedFlowSpec | None = None
    if raw.get("pinned_flow"):
        pinned_flow = _parse_pinned_flow(raw["pinned_flow"])

    story_model: StoryModelSpec | None = None
    if raw.get("story_model"):
        sm_raw = raw["story_model"]
        claims = [
            StoryClaimSpec(
                id=str(cl["id"]),
                type=cl["type"],
                claim=str(cl["claim"]),
                source_quote=str(cl["source_quote"]) if cl.get("source_quote") is not None else None,
                source_id=str(cl["source_id"]) if cl.get("source_id") is not None else None,
                metric_scope=str(cl["metric_scope"]) if cl.get("metric_scope") is not None else None,
                confidence=cl.get("confidence"),
            )
            for cl in sm_raw.get("claims", [])
        ]
        story_model = StoryModelSpec(
            core_question=str(sm_raw["core_question"]) if sm_raw.get("core_question") is not None else None,
            claims=claims,
        )

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
                        evidence_refs=[str(r) for r in it.get("evidence_refs", [])],
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
                        evidence_refs=[str(r) for r in col.get("evidence_refs", [])],
                    )
                    for col in mx.get("columns", [])
                ],
            )

        frames: list[FrameSpec] = []
        for f_raw in s_raw.get("frames") or []:
            raw_obj_states = f_raw.get("object_states") or {}
            obj_states: dict[str, dict[str, Any]] = {}
            for k, v in raw_obj_states.items():
                if not isinstance(v, dict):
                    continue
                parsed_state: dict[str, Any] = {}
                for sk, sv in v.items():
                    key = str(sk)
                    if isinstance(sv, list):
                        parsed_state[key] = [str(x) for x in sv]
                    elif isinstance(sv, str):
                        parsed_state[key] = sv
                    else:
                        parsed_state[key] = int(sv)
                obj_states[str(k)] = parsed_state
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
                    visible_objects=(
                        [str(x) for x in f_raw["visible_objects"]]
                        if f_raw.get("visible_objects") is not None
                        else None
                    ),
                    focus_objects=(
                        [str(x) for x in f_raw["focus_objects"]]
                        if f_raw.get("focus_objects") is not None
                        else None
                    ),
                    object_states=obj_states,
                    show_annotations=bool(f_raw.get("show_annotations", True)),
                    show_pinned_flow=(
                        bool(f_raw["show_pinned_flow"])
                        if f_raw.get("show_pinned_flow") is not None
                        else None
                    ),
                    notes=str(f_raw.get("notes", "")),
                    subtitle=f_raw.get("subtitle"),
                )
            )

        grid: GridSpec | None = None
        if s_raw.get("grid"):
            g_raw = s_raw["grid"]
            grid = GridSpec(
                columns=int(g_raw.get("columns", 12)),
                rows=int(g_raw["rows"]) if g_raw.get("rows") is not None else None,
                gap=float(g_raw.get("gap", 28.0)),
            )

        regions: list[RegionSpec] = [
            RegionSpec(
                id=str(r["id"]),
                col=int(r.get("col", 1)),
                row=int(r.get("row", 1)),
                col_span=int(r.get("col_span", 12)),
                row_span=int(r.get("row_span", 1)),
                arrange=r.get("arrange", "stack"),
                gap=float(r.get("gap", 20.0)),
                padding=float(r.get("padding", 0.0)),
                title=str(r["title"]) if r.get("title") else None,
                frame=bool(r.get("frame", False)),
            )
            for r in s_raw.get("regions", [])
        ]

        objects: list[CanvasObjectSpec] = []
        for obj_raw in s_raw.get("objects", []):
            chart_spec: ChartSpec | None = None
            if obj_raw.get("chart"):
                ch_raw = obj_raw["chart"]
                chart_spec = ChartSpec(
                    chart_type=ch_raw["chart_type"],
                    categories=[str(c) for c in ch_raw.get("categories", [])],
                    series=[
                        ChartSeriesSpec(
                            name=str(sr["name"]),
                            values=[float(v) for v in sr.get("values", [])],
                            color_hex=str(sr["color_hex"]) if sr.get("color_hex") else None,
                        )
                        for sr in ch_raw.get("series", [])
                    ],
                    title=str(ch_raw["title"]) if ch_raw.get("title") else None,
                    unit=str(ch_raw["unit"]) if ch_raw.get("unit") else None,
                    show_title=ch_raw.get("show_title"),
                    show_legend=ch_raw.get("show_legend"),
                    show_value_labels=bool(ch_raw.get("show_value_labels", True)),
                    axis_min=float(ch_raw["axis_min"]) if ch_raw.get("axis_min") is not None else None,
                    axis_max=float(ch_raw["axis_max"]) if ch_raw.get("axis_max") is not None else None,
                    reveal=ch_raw.get("reveal", "whole"),
                    render_mode=ch_raw.get("render_mode", "auto"),
                    highlight_categories=[str(c) for c in ch_raw.get("highlight_categories", [])],
                    estimate_from=int(ch_raw["estimate_from"]) if ch_raw.get("estimate_from") is not None else None,
                    reference_lines=[dict(r) for r in ch_raw.get("reference_lines", []) if isinstance(r, dict)],
                )

            table_spec: TableSpec | None = None
            if obj_raw.get("table"):
                tb_raw = obj_raw["table"]
                table_spec = TableSpec(
                    headers=[str(h) for h in tb_raw.get("headers", [])],
                    rows=[[str(cell) for cell in row] for row in tb_raw.get("rows", [])],
                    title=str(tb_raw["title"]) if tb_raw.get("title") else None,
                    highlight_cols=[int(i) for i in tb_raw.get("highlight_cols", [])],
                    highlight_rows=[int(i) for i in tb_raw.get("highlight_rows", [])],
                    target_rows=[int(i) for i in tb_raw.get("target_rows", [])],
                    cell_tones=[
                        [str(t) if t is not None else None for t in row]
                        for row in tb_raw.get("cell_tones", [])
                    ],
                    reveal=tb_raw.get("reveal", "whole"),
                )

            diagram_spec: DiagramSpec | None = None
            if obj_raw.get("diagram"):
                dg_raw = obj_raw["diagram"]
                dg_nodes, dg_edges = _parse_nodes_and_edges(
                    dg_raw.get("nodes", []),
                    dg_raw.get("edges", []),
                )
                diagram_spec = DiagramSpec(
                    diagram_layout=dg_raw.get("diagram_layout", "horizontal"),
                    nodes=dg_nodes,
                    edges=dg_edges,
                )

            objects.append(
                CanvasObjectSpec(
                    id=str(obj_raw["id"]),
                    kind=obj_raw["kind"],
                    region=str(obj_raw["region"]) if obj_raw.get("region") else None,
                    step=int(obj_raw.get("step", 1)),
                    variant=obj_raw.get("variant", "primary"),
                    surface=obj_raw.get("surface", "filled"),
                    note=str(obj_raw.get("note", "")),
                    evidence_refs=[str(r) for r in obj_raw.get("evidence_refs", [])],
                    weight=float(obj_raw.get("weight", 1.0)),
                    label=str(obj_raw["label"]) if obj_raw.get("label") else None,
                    sublabel=str(obj_raw["sublabel"]) if obj_raw.get("sublabel") else None,
                    badge=str(obj_raw["badge"]) if obj_raw.get("badge") else None,
                    metric=str(obj_raw["metric"]) if obj_raw.get("metric") else None,
                    text=str(obj_raw["text"]) if obj_raw.get("text") else None,
                    font_size=float(obj_raw["font_size"]) if obj_raw.get("font_size") is not None else None,
                    bold=obj_raw.get("bold"),
                    align=obj_raw.get("align", "center"),
                    fill_hex=str(obj_raw["fill_hex"]) if obj_raw.get("fill_hex") else None,
                    border_hex=str(obj_raw["border_hex"]) if obj_raw.get("border_hex") else None,
                    color_hex=str(obj_raw["color_hex"]) if obj_raw.get("color_hex") else None,
                    shape_type=obj_raw.get("shape_type", "rounded_rect"),
                    svg_path=str(obj_raw["svg_path"]) if obj_raw.get("svg_path") else None,
                    dashed=bool(obj_raw.get("dashed", False)),
                    gauge=obj_raw.get("gauge") if isinstance(obj_raw.get("gauge"), dict) else None,
                    chart=chart_spec,
                    table=table_spec,
                    diagram=diagram_spec,
                )
            )

        connectors = [
            EdgeSpec(
                id=str(e["id"]),
                from_id=str(e["from"]),
                to_id=str(e["to"]),
                label=str(e["label"]) if e.get("label") else None,
                style=e.get("style", "solid"),
            )
            for e in s_raw.get("connectors", [])
        ]

        default_pacing = "manual" if frames else "auto"
        inferred_layout = "canvas" if ("objects" in s_raw or "regions" in s_raw) else "horizontal_flow"
        scenes.append(
            SceneSpec(
                id=str(s_raw["id"]),
                title=str(s_raw["title"]),
                layout=s_raw.get("layout", inferred_layout),
                subtitle=s_raw.get("subtitle"),
                source_section=str(s_raw["source_section"]) if s_raw.get("source_section") else None,
                claim=str(s_raw["claim"]) if s_raw.get("claim") is not None else None,
                visual_intent=(
                    dict(s_raw["visual_intent"])
                    if isinstance(s_raw.get("visual_intent"), dict)
                    else (str(s_raw["visual_intent"]) if s_raw.get("visual_intent") is not None else None)
                ),
                metric_scope=str(s_raw["metric_scope"]) if s_raw.get("metric_scope") is not None else None,
                evidence_refs=[str(r) for r in s_raw.get("evidence_refs", [])],
                pacing=s_raw.get("pacing", default_pacing),
                intro_note=str(s_raw.get("intro_note", "")),
                active_flow_node=str(s_raw["active_flow_node"]) if s_raw.get("active_flow_node") else None,
                show_pinned_flow=bool(s_raw.get("show_pinned_flow", True)),
                pinned_flow=_parse_pinned_flow(s_raw["pinned_flow"]) if isinstance(s_raw.get("pinned_flow"), dict) else None,
                palette=dict(s_raw["palette"]) if isinstance(s_raw.get("palette"), dict) else None,
                style_config=_parse_style_config(s_raw.get("style_config")),
                grid=grid,
                regions=regions,
                objects=objects,
                connectors=connectors,
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
        use_templates=bool(raw.get("use_templates", False)),
        theme=str(raw.get("theme", "slate_dark")),
        palette=dict(raw["palette"]) if isinstance(raw.get("palette"), dict) else None,
        slide_width=int(slide_size.get("width", 1920)),
        slide_height=int(slide_size.get("height", 1080)),
        pinned_flow=pinned_flow,
        story_model=story_model,
        style_config=_parse_style_config(raw.get("style_config")),
        scenes=scenes,
    )


