"""Schema key extraction, DAG layer computation, and shared validation helpers."""

from __future__ import annotations

from collections import deque
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from keyflow.themes import is_valid_hex_color


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
    f = float(val)
    return f if math.isfinite(f) else None


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool) or not isinstance(val, int):
        return None
    return int(val)


def _is_in(val: Any, pool: set[str] | frozenset[str] | dict[str, Any]) -> bool:
    return isinstance(val, str) and val in pool


@lru_cache(maxsize=1)
def _schema_key_sets() -> dict[str, frozenset[str]]:
    """Extract allowed property sets directly from deck.schema.json to prevent validator drift."""
    pkg_schema = Path(__file__).resolve().parent.parent / "deck.schema.json"
    repo_schema = Path(__file__).resolve().parent.parent.parent / "schemas" / "deck.schema.json"
    schema_path = pkg_schema if pkg_schema.exists() else repo_schema
    if not schema_path.exists():
        return {}
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    props = raw.get("properties", {})
    defs = raw.get("$defs", {})
    pf_props = defs.get("pinned_flow", {}).get("properties", {}) or props.get("pinned_flow", {}).get("properties", {})
    sm_props = props.get("story_model", {}).get("properties", {})
    sc_props = props.get("scenes", {}).get("items", {}).get("properties", {})
    node_props = defs.get("node", {}).get("properties", {})
    child_props = node_props.get("children", {}).get("items", {}).get("properties", {})
    edge_props = defs.get("edge", {}).get("properties", {})
    pb_props = sc_props.get("proportion_bar", {}).get("properties", {})
    pb_item_props = pb_props.get("items", {}).get("items", {}).get("properties", {})
    mx_props = sc_props.get("matrix", {}).get("properties", {})
    mx_col_props = mx_props.get("columns", {}).get("items", {}).get("properties", {})
    mx_row_props = mx_col_props.get("rows", {}).get("items", {}).get("properties", {})
    frame_props = sc_props.get("frames", {}).get("items", {}).get("properties", {})
    obj_props = sc_props.get("objects", {}).get("items", {}).get("properties", {})
    chart_props = obj_props.get("chart", {}).get("properties", {})
    table_props = obj_props.get("table", {}).get("properties", {})
    diagram_props = obj_props.get("diagram", {}).get("properties", {})
    return {
        "deck": frozenset(props),
        "palette": frozenset(defs.get("palette", {}).get("properties", {})),
        "style_config": frozenset(defs.get("style_config", {}).get("properties", {})),
        "slide_size": frozenset(props.get("slide_size", {}).get("properties", {})),
        "pinned_flow": frozenset(pf_props),
        "pf_node": frozenset(pf_props.get("nodes", {}).get("items", {}).get("properties", {})),
        "pf_edge": frozenset(pf_props.get("edges", {}).get("items", {}).get("properties", {})),
        "pf_group": frozenset(pf_props.get("groups", {}).get("items", {}).get("properties", {})),
        "story_model": frozenset(sm_props),
        "story_claim": frozenset(sm_props.get("claims", {}).get("items", {}).get("properties", {})),
        "scene": frozenset(sc_props),
        "grid": frozenset(sc_props.get("grid", {}).get("properties", {})),
        "region": frozenset(sc_props.get("regions", {}).get("items", {}).get("properties", {})),
        "canvas_object": frozenset(obj_props),
        "chart": frozenset(chart_props),
        "chart_series": frozenset(chart_props.get("series", {}).get("items", {}).get("properties", {})),
        "table": frozenset(table_props),
        "diagram": frozenset(diagram_props),
        "node": frozenset(node_props),
        "child": frozenset(child_props),
        "edge": frozenset(edge_props),
        "proportion_bar": frozenset(pb_props),
        "proportion_item": frozenset(pb_item_props),
        "matrix": frozenset(mx_props),
        "matrix_column": frozenset(mx_col_props),
        "matrix_row": frozenset(mx_row_props),
        "frame": frozenset(frame_props),
        "object_state": frozenset(
            frame_props.get("object_states", {}).get("additionalProperties", {}).get("properties", {})
        ),
    }


def _check_allowed_keys(
    obj: dict[str, Any],
    schema_key: str,
    path: str,
    errors: list[str],
) -> None:
    allowed = _schema_key_sets().get(schema_key)
    if not allowed:
        return
    unknown = sorted(set(obj) - allowed)
    for key in unknown:
        errors.append(f"{path}: unknown property '{key}'.")


def _check_evidence_refs(
    obj: dict[str, Any],
    claim_ids: set[str],
    path: str,
    errors: list[str],
) -> None:
    refs = obj.get("evidence_refs")
    if refs is None:
        return
    if not isinstance(refs, list):
        errors.append(f"{path}.evidence_refs must be a list of claim ids.")
        return
    for cid in refs:
        if not isinstance(cid, str) or cid not in claim_ids:
            errors.append(f"{path}: unknown evidence_ref '{cid}'.")


def _validate_style_config(sc: Any, path: str, errors: list[str]) -> None:
    if not isinstance(sc, dict):
        errors.append(f"{path} must be an object.")
        return
    _check_allowed_keys(sc, "style_config", path, errors)
    bounds = {
        "title_max_size": (24.0, 96.0),
        "subtitle_size": (14.0, 48.0),
        "card_corner_px": (0.0, 40.0),
        "arrow_width": (1.0, 12.0),
    }
    for k, (lo, hi) in bounds.items():
        if k in sc and sc[k] is not None:
            v = _as_float(sc[k])
            if v is None or v < lo or v > hi:
                errors.append(f"{path}.{k}: must be a finite number in [{lo}, {hi}].")


def _validate_palette(pal: Any, path: str, errors: list[str]) -> None:
    if not isinstance(pal, dict):
        errors.append(f"{path} must be an object.")
        return
    _check_allowed_keys(pal, "palette", path, errors)
    for k, v in pal.items():
        if k == "series_colors":
            if not isinstance(v, list) or not v:
                errors.append(f"{path}.series_colors must be a non-empty list of #RRGGBB hex colors.")
            else:
                for idx, item in enumerate(v):
                    if not isinstance(item, str) or not is_valid_hex_color(item):
                        errors.append(f"{path}.series_colors[{idx}]: invalid hex color '{item}' (expected #RRGGBB).")
        elif not isinstance(v, str) or not is_valid_hex_color(v):
            errors.append(f"{path}.{k}: invalid hex color '{v}' (expected #RRGGBB).")


