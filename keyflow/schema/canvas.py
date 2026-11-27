"""Freeform canvas scene validator (grid, regions, objects, charts, tables, inline diagrams)."""

from __future__ import annotations

import math
from typing import Any

from keyflow.schema.references import (
    _as_float,
    _as_int,
    _check_allowed_keys,
    _check_evidence_refs,
    _check_label_density,
    _is_in,
    _schema_key_sets,
)
from keyflow.themes import is_valid_hex_color


def _validate_canvas_scene(
    s: dict[str, Any],
    *,
    prefix: str,
    claim_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Validate grid, regions, freeform .keyx objects, and cross-object connectors."""
    from keyflow.schema.validation import _validate_nodes_and_edges

    grid_cols = 12
    grid_rows: int | None = None
    if s.get("grid") is not None:
        g = s["grid"]
        if not isinstance(g, dict):
            errors.append(f"{prefix}.grid must be an object.")
        else:
            _check_allowed_keys(g, "grid", f"{prefix}.grid", errors)
            cols_val = _as_int(g.get("columns", 12))
            if cols_val is None or cols_val < 1 or cols_val > 24:
                errors.append(f"{prefix}.grid.columns must be an integer in [1, 24].")
            else:
                grid_cols = cols_val
            if g.get("rows") is not None:
                rows_val = _as_int(g["rows"])
                if rows_val is None or rows_val < 1 or rows_val > 12:
                    errors.append(f"{prefix}.grid.rows must be an integer in [1, 12].")
                else:
                    grid_rows = rows_val
            if "gap" in g:
                gap_val = _as_float(g["gap"])
                if gap_val is None or gap_val < 0:
                    errors.append(f"{prefix}.grid.gap must be non-negative.")

    region_ids: set[str] = set()
    occupied_cells: dict[tuple[int, int], str] = {}
    valid_arranges = {"stack", "row", "grid"}
    if s.get("regions") is not None:
        regs = s["regions"]
        if not isinstance(regs, list):
            errors.append(f"{prefix}.regions must be a list.")
        else:
            for r_idx, reg in enumerate(regs):
                if not isinstance(reg, dict):
                    errors.append(f"{prefix}.regions[{r_idx}]: must be an object.")
                    continue
                _check_allowed_keys(reg, "region", f"{prefix}.regions[{r_idx}]", errors)
                rid = reg.get("id")
                if not isinstance(rid, str) or not rid:
                    errors.append(f"{prefix}.regions[{r_idx}]: missing 'id'.")
                    continue
                if rid in region_ids:
                    errors.append(f"{prefix}: duplicate region id '{rid}'.")
                else:
                    region_ids.add(rid)
                arrange = reg.get("arrange", "stack")
                if not _is_in(arrange, valid_arranges):
                    errors.append(f"{prefix}.regions['{rid}']: invalid arrange '{arrange}'.")
                if reg.get("gap") is not None:
                    rgap = _as_float(reg["gap"])
                    if rgap is None or rgap < 0:
                        errors.append(f"{prefix}.regions['{rid}'].gap: must be a non-negative number.")
                if reg.get("padding") is not None:
                    rpad = _as_float(reg["padding"])
                    if rpad is None or rpad < 0:
                        errors.append(f"{prefix}.regions['{rid}'].padding: must be a non-negative number.")
                if reg.get("frame") is not None and not isinstance(reg["frame"], bool):
                    errors.append(f"{prefix}.regions['{rid}'].frame: must be a boolean.")
                if reg.get("title") is not None and not isinstance(reg["title"], str):
                    errors.append(f"{prefix}.regions['{rid}'].title: must be a string.")
                col = _as_int(reg.get("col", 1))
                row = _as_int(reg.get("row", 1))
                cspan = _as_int(reg.get("col_span", 12))
                rspan = _as_int(reg.get("row_span", 1))
                if col is None or row is None or cspan is None or rspan is None:
                    errors.append(
                        f"{prefix}.regions['{rid}']: col, row, col_span, and row_span must be integers."
                    )
                    continue
                if col < 1 or cspan < 1 or col + cspan - 1 > grid_cols:
                    errors.append(
                        f"{prefix}.regions['{rid}']: col={col}, col_span={cspan} exceeds grid columns={grid_cols}."
                    )
                if row < 1 or rspan < 1 or (grid_rows is not None and row + rspan - 1 > grid_rows):
                    errors.append(
                        f"{prefix}.regions['{rid}']: row={row}, row_span={rspan} out of grid row bounds."
                    )
                for rr in range(max(1, row), max(1, row) + max(0, rspan)):
                    for cc in range(max(1, col), max(1, col) + max(0, cspan)):
                        prev = occupied_cells.get((rr, cc))
                        if prev and prev != rid:
                            errors.append(
                                f"{prefix}.regions['{rid}']: overlaps grid cell ({rr}, {cc}) with region '{prev}'."
                            )
                        else:
                            occupied_cells[(rr, cc)] = rid

    valid_kinds = {"chart", "table", "card", "textbox", "shape", "callout", "diagram"}
    valid_variants = {"primary", "accent", "muted", "success", "warn"}
    valid_surfaces = {"filled", "ghost", "borderless", "accent_bar"}
    valid_chart_types = {"column", "bar", "pie", "donut", "line", "area", "stacked_column", "stacked_bar", "scatter", "waterfall", "football_field", "radar", "progress_bars"}
    valid_chart_reveals = {"whole", "by_series", "by_category"}
    valid_chart_render_modes = {"auto", "vector", "native"}
    valid_table_reveals = {"whole", "by_row", "by_column"}
    valid_shape_types = {"rounded_rect", "rect", "ellipse", "pill", "custom"}
    valid_diagram_layouts = {"horizontal", "vertical", "dag", "hub_spoke", "sequence"}

    object_map: dict[str, dict[str, Any]] = {}
    raw_objects = s.get("objects")
    if raw_objects is None:
        errors.append(f"{prefix}: layout='canvas' requires an 'objects' list.")
        return set(), object_map
    if not isinstance(raw_objects, list):
        errors.append(f"{prefix}.objects must be a list.")
        return set(), object_map

    for o_idx, obj in enumerate(raw_objects):
        if not isinstance(obj, dict):
            errors.append(f"{prefix}.objects[{o_idx}]: must be an object.")
            continue
        _check_allowed_keys(obj, "canvas_object", f"{prefix}.objects[{o_idx}]", errors)
        oid = obj.get("id")
        if not isinstance(oid, str) or not oid:
            errors.append(f"{prefix}.objects[{o_idx}]: missing 'id'.")
            continue
        if oid in object_map:
            errors.append(f"{prefix}: duplicate object id '{oid}'.")
            continue
        object_map[oid] = obj
        _check_evidence_refs(obj, claim_ids, f"{prefix}.objects['{oid}']", errors)

        kind = obj.get("kind")
        if not isinstance(kind, str) or kind not in valid_kinds:
            errors.append(f"{prefix}.objects['{oid}']: invalid kind '{kind}'.")
            continue

        reg_ref = obj.get("region")
        if reg_ref is not None and (not isinstance(reg_ref, str) or (region_ids and reg_ref not in region_ids)):
            errors.append(f"{prefix}.objects['{oid}']: unknown region '{reg_ref}'.")

        variant = obj.get("variant", "primary")
        if not _is_in(variant, valid_variants):
            errors.append(f"{prefix}.objects['{oid}']: invalid variant '{variant}'.")
        surface = obj.get("surface", "filled")
        if not _is_in(surface, valid_surfaces):
            errors.append(f"{prefix}.objects['{oid}']: invalid surface '{surface}'.")

        step_val = _as_int(obj.get("step", 1))
        if step_val is None or step_val < 0:
            errors.append(f"{prefix}.objects['{oid}']: 'step' must be a non-negative integer.")

        if "weight" in obj:
            w_val = _as_float(obj["weight"])
            if w_val is None or w_val < 0.1:
                errors.append(f"{prefix}.objects['{oid}'].weight: must be a finite number >= 0.1.")

        if obj.get("font_size") is not None:
            fs_val = _as_float(obj["font_size"])
            if fs_val is None or fs_val < 10.0 or fs_val > 140.0:
                errors.append(f"{prefix}.objects['{oid}'].font_size: must be a finite number in [10, 140].")

        if obj.get("bold") is not None and not isinstance(obj["bold"], bool):
            errors.append(f"{prefix}.objects['{oid}'].bold: must be a boolean.")
        if obj.get("dashed") is not None and not isinstance(obj["dashed"], bool):
            errors.append(f"{prefix}.objects['{oid}'].dashed: must be a boolean.")
        if obj.get("align") is not None and not _is_in(obj["align"], {"left", "center", "right"}):
            errors.append(f"{prefix}.objects['{oid}'].align: invalid align '{obj['align']}'.")

        for hex_field in ("fill_hex", "border_hex", "color_hex"):
            if obj.get(hex_field) is not None and not is_valid_hex_color(str(obj[hex_field])):
                errors.append(f"{prefix}.objects['{oid}'].{hex_field}: invalid hex color '{obj[hex_field]}'.")

        if kind in ("card", "callout"):
            lbl = obj.get("label")
            if not isinstance(lbl, str) or not lbl:
                errors.append(f"{prefix}.objects['{oid}']: kind='{kind}' requires 'label'.")
            else:
                _check_label_density(
                    f"{prefix}.objects['{oid}']",
                    lbl,
                    obj.get("sublabel") if isinstance(obj.get("sublabel"), str) else None,
                    obj.get("badge") if isinstance(obj.get("badge"), str) else None,
                    obj.get("metric") if isinstance(obj.get("metric"), str) else None,
                    warnings,
                )
        elif kind == "textbox":
            if not isinstance(obj.get("text"), str) or not obj.get("text"):
                errors.append(f"{prefix}.objects['{oid}']: kind='textbox' requires non-empty 'text'.")
        elif kind == "shape":
            st = obj.get("shape_type", "rounded_rect")
            if not _is_in(st, valid_shape_types):
                errors.append(f"{prefix}.objects['{oid}']: invalid shape_type '{st}'.")
            if st == "custom" and (not isinstance(obj.get("svg_path"), str) or not obj.get("svg_path")):
                errors.append(f"{prefix}.objects['{oid}']: shape_type='custom' requires 'svg_path'.")
        elif kind == "chart":
            ch = obj.get("chart")
            if not isinstance(ch, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='chart' requires 'chart' object.")
            else:
                _check_allowed_keys(ch, "chart", f"{prefix}.objects['{oid}'].chart", errors)
                ctype = ch.get("chart_type")
                if not _is_in(ctype, valid_chart_types):
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid chart_type '{ctype}'.")
                crev = ch.get("reveal", "whole")
                if not _is_in(crev, valid_chart_reveals):
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid reveal '{crev}'.")
                crm = ch.get("render_mode", "auto")
                if not _is_in(crm, valid_chart_render_modes):
                    errors.append(f"{prefix}.objects['{oid}'].chart: invalid render_mode '{crm}'.")
                cats = ch.get("categories")
                series = ch.get("series")
                if not isinstance(cats, list) or not cats or not all(isinstance(c, str) and c for c in cats):
                    errors.append(f"{prefix}.objects['{oid}'].chart: 'categories' must be a non-empty list of strings.")
                    cats = []
                ax_min_val: float | None = None
                ax_max_val: float | None = None
                if ch.get("axis_min") is not None:
                    ax_min_val = _as_float(ch["axis_min"])
                    if ax_min_val is None:
                        errors.append(f"{prefix}.objects['{oid}'].chart.axis_min: must be a finite number.")
                if ch.get("axis_max") is not None:
                    ax_max_val = _as_float(ch["axis_max"])
                    if ax_max_val is None:
                        errors.append(f"{prefix}.objects['{oid}'].chart.axis_max: must be a finite number.")
                if ax_min_val is not None and ax_max_val is not None and ax_min_val >= ax_max_val:
                    errors.append(
                        f"{prefix}.objects['{oid}'].chart: axis_min ({ax_min_val}) must be < axis_max ({ax_max_val})."
                    )
                if ch.get("show_title") is not None and not isinstance(ch["show_title"], bool):
                    errors.append(f"{prefix}.objects['{oid}'].chart.show_title: must be a boolean.")
                if ch.get("show_legend") is not None and not isinstance(ch["show_legend"], bool):
                    errors.append(f"{prefix}.objects['{oid}'].chart.show_legend: must be a boolean.")
                if "show_value_labels" in ch and not isinstance(ch["show_value_labels"], bool):
                    errors.append(f"{prefix}.objects['{oid}'].chart.show_value_labels: must be a boolean.")
                if not isinstance(series, list) or not series:
                    errors.append(f"{prefix}.objects['{oid}'].chart: 'series' must be a non-empty list.")
                else:
                    for sr_idx, sr in enumerate(series):
                        if not isinstance(sr, dict):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: must be an object.")
                            continue
                        _check_allowed_keys(sr, "chart_series", f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]", errors)
                        if not isinstance(sr.get("name"), str) or not sr.get("name"):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: missing 'name'.")
                        vals = sr.get("values")
                        if not isinstance(vals, list) or (cats and len(vals) != len(cats)):
                            errors.append(
                                f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: 'values' length must match 'categories' ({len(cats)})."
                            )
                        elif any(_as_float(v) is None for v in vals):
                            errors.append(f"{prefix}.objects['{oid}'].chart.series[{sr_idx}]: all values must be numeric.")
                        if sr.get("color_hex") is not None and not is_valid_hex_color(str(sr["color_hex"])):
                            errors.append(
                                f"{prefix}.objects['{oid}'].chart.series[{sr_idx}].color_hex: invalid hex '{sr['color_hex']}'."
                            )
        elif kind == "table":
            tb = obj.get("table")
            if not isinstance(tb, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='table' requires 'table' object.")
            else:
                _check_allowed_keys(tb, "table", f"{prefix}.objects['{oid}'].table", errors)
                trev = tb.get("reveal", "whole")
                if not _is_in(trev, valid_table_reveals):
                    errors.append(f"{prefix}.objects['{oid}'].table: invalid reveal '{trev}'.")
                hdrs = tb.get("headers")
                trows = tb.get("rows")
                if not isinstance(hdrs, list) or not hdrs or not all(isinstance(h, str) for h in hdrs):
                    errors.append(f"{prefix}.objects['{oid}'].table: 'headers' must be a non-empty list of strings.")
                    hdrs = []
                if not isinstance(trows, list) or not trows:
                    errors.append(f"{prefix}.objects['{oid}'].table: 'rows' must be a non-empty list.")
                    trows = []
                else:
                    for r_idx, row in enumerate(trows):
                        if not isinstance(row, list) or (hdrs and len(row) != len(hdrs)) or not all(isinstance(cell, str) for cell in row):
                            errors.append(
                                f"{prefix}.objects['{oid}'].table.rows[{r_idx}]: must be a list of {len(hdrs)} strings matching headers."
                            )
                for hl_key, limit in (("highlight_cols", len(hdrs)), ("highlight_rows", len(trows))):
                    if hl_key in tb and tb[hl_key] is not None:
                        hl_vals = tb[hl_key]
                        if not isinstance(hl_vals, list):
                            errors.append(f"{prefix}.objects['{oid}'].table.{hl_key}: must be a list of integers.")
                        else:
                            for idx_val in hl_vals:
                                iv = _as_int(idx_val)
                                if iv is None or iv < 0 or (limit > 0 and iv >= limit):
                                    errors.append(
                                        f"{prefix}.objects['{oid}'].table.{hl_key}: index {idx_val!r} out of range [0, {max(0, limit - 1)}]."
                                    )
        elif kind == "diagram":
            dg = obj.get("diagram")
            if not isinstance(dg, dict):
                errors.append(f"{prefix}.objects['{oid}']: kind='diagram' requires 'diagram' object.")
            else:
                _check_allowed_keys(dg, "diagram", f"{prefix}.objects['{oid}'].diagram", errors)
                dl = dg.get("diagram_layout", "horizontal")
                if not _is_in(dl, valid_diagram_layouts):
                    errors.append(f"{prefix}.objects['{oid}'].diagram: invalid diagram_layout '{dl}'.")
                _validate_nodes_and_edges(
                    dg.get("nodes", []),
                    dg.get("edges", []),
                    prefix=f"{prefix}.objects['{oid}'].diagram",
                    layout_kind=dl,
                    claim_ids=claim_ids,
                    errors=errors,
                    warnings=warnings,
                )

    connectors = s.get("connectors", [])
    if not isinstance(connectors, list):
        errors.append(f"{prefix}.connectors must be a list.")
    else:
        conn_ids: set[str] = set()
        for e_idx, e in enumerate(connectors):
            if not isinstance(e, dict):
                errors.append(f"{prefix}.connectors[{e_idx}]: must be an object.")
                continue
            _check_allowed_keys(e, "edge", f"{prefix}.connectors[{e_idx}]", errors)
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{prefix}.connectors[{e_idx}]: missing 'id'.")
            elif eid in conn_ids:
                errors.append(f"{prefix}: duplicate connector id '{eid}'.")
            else:
                conn_ids.add(eid)
            if not _is_in(e.get("from"), object_map):
                errors.append(f"{prefix}.connectors['{eid}']: unknown 'from' object '{e.get('from')}'.")
            if not _is_in(e.get("to"), object_map):
                errors.append(f"{prefix}.connectors['{eid}']: unknown 'to' object '{e.get('to')}'.")

    return set(object_map), object_map


