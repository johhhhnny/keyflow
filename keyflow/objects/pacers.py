"""Progressive sub-stage pacers for freeform canvas object kinds."""

from __future__ import annotations

from typing import Any, Callable

from keyflow.objects.registry import register_object_pacer

_DIAGRAM_LAYOUT_MAP = {
    "horizontal": "horizontal_flow",
    "vertical": "vertical_flow",
    "dag": "flow_dag",
    "hub_spoke": "hub_spoke",
    "sequence": "sequence_timeline",
}


def step_counts(total: int, max_steps: int = 4) -> list[int]:
    """Return strictly increasing cumulative counts ending at total, capped at max_steps."""
    if total <= 1:
        return [total] if total == 1 else []
    if total <= max_steps:
        return list(range(1, total + 1))
    counts: list[int] = []
    for i in range(1, max_steps + 1):
        c = max(1, round(total * i / max_steps))
        if not counts or c > counts[-1]:
            counts.append(c)
    if counts[-1] != total:
        counts[-1] = total
    return counts


@register_object_pacer("chart")
def pace_chart(
    obj: dict[str, Any],
    base_note: str,
    *,
    expand_frames_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> tuple[list[tuple[dict[str, dict[str, Any]], str]], dict[str, Any] | None]:
    oid = str(obj["id"])
    ch = obj.get("chart") or {}
    rev = ch.get("reveal", "whole")
    stages: list[tuple[dict[str, dict[str, Any]], str]] = []
    if rev == "by_series" and len(ch.get("series", [])) > 1:
        for k in range(1, len(ch["series"]) + 1):
            sr_name = ch["series"][k - 1].get("name", f"Series {k}")
            stages.append(({oid: {"series_count": k}}, f"{base_note}（{sr_name}）"))
        return stages, {"series_count": len(ch["series"])}
    if rev == "by_category" and len(ch.get("categories", [])) > 1:
        for k in step_counts(len(ch["categories"]), max_steps=6):
            cat_name = ch["categories"][k - 1]
            stages.append(({oid: {"category_count": k}}, f"{base_note}（{cat_name}）"))
        return stages, {"category_count": len(ch["categories"])}
    return [], None


@register_object_pacer("table")
def pace_table(
    obj: dict[str, Any],
    base_note: str,
    *,
    expand_frames_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> tuple[list[tuple[dict[str, dict[str, Any]], str]], dict[str, Any] | None]:
    oid = str(obj["id"])
    tb = obj.get("table") or {}
    rev = tb.get("reveal", "whole")
    stages: list[tuple[dict[str, dict[str, Any]], str]] = []
    if rev == "by_row" and len(tb.get("rows", [])) > 1:
        for k in step_counts(len(tb["rows"]), max_steps=4):
            stages.append(({oid: {"row_count": k}}, f"{base_note}（前 {k} 行）"))
        return stages, {"row_count": len(tb["rows"])}
    if rev == "by_column" and len(tb.get("headers", [])) > 1:
        for k in step_counts(len(tb["headers"]), max_steps=4):
            hdr = tb["headers"][k - 1]
            stages.append(({oid: {"col_count": k}}, f"{base_note}（{hdr}）"))
        return stages, {"col_count": len(tb["headers"])}
    return [], None


@register_object_pacer("diagram")
def pace_diagram(
    obj: dict[str, Any],
    base_note: str,
    *,
    expand_frames_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> tuple[list[tuple[dict[str, dict[str, Any]], str]], dict[str, Any] | None]:
    oid = str(obj["id"])
    dg = obj.get("diagram") or {}
    dg_nodes = dg.get("nodes", [])
    has_children = any(bool(n.get("children")) for n in dg_nodes)
    if (len(dg_nodes) <= 1 and not has_children) or expand_frames_fn is None:
        return [], None

    sub_layout = _DIAGRAM_LAYOUT_MAP.get(dg.get("diagram_layout", "horizontal"), "horizontal_flow")
    dummy_dg_scene = {
        "id": oid,
        "title": str(obj.get("label") or oid),
        "layout": sub_layout,
        "nodes": dg_nodes,
        "edges": dg.get("edges", []),
    }
    d_frames = expand_frames_fn(dummy_dg_scene, density="standard")
    non_empty_d_frames = [df for df in d_frames if df.get("visible_nodes")] or d_frames

    stages: list[tuple[dict[str, dict[str, Any]], str]] = []
    for df in non_empty_d_frames:
        d_st: dict[str, Any] = {
            "visible_nodes": list(df.get("visible_nodes", [])),
            "expanded_nodes": list(df.get("expanded_nodes", [])),
        }
        if df.get("visible_edges", "auto") != "auto":
            d_st["visible_edges"] = list(df["visible_edges"])
        if df.get("focus_nodes") is not None:
            d_st["focus_nodes"] = list(df["focus_nodes"])
        d_note = str(df.get("notes") or "")
        full_note = (
            f"{base_note}：{d_note}"
            if (base_note and d_note and base_note not in d_note)
            else (d_note or base_note)
        )
        stages.append(({oid: d_st}, full_note))

    committed: dict[str, Any] | None = None
    if non_empty_d_frames:
        last_df = non_empty_d_frames[-1]
        committed = {
            "visible_nodes": list(last_df.get("visible_nodes", [])),
            "expanded_nodes": list(last_df.get("expanded_nodes", [])),
        }
        if last_df.get("visible_edges", "auto") != "auto":
            committed["visible_edges"] = list(last_df["visible_edges"])
    return stages, committed
