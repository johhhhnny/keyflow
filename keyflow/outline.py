"""Markdown article and README skeleton extractor for KeyFlow's two-stage workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from keyflow.pace import DensityMode, pace_deck
from keyflow.schema import validate_deck

_BOILERPLATE_TITLES = {
    "license",
    "acknowledgments",
    "contributing",
    "changelog",
    "许可",
    "致谢",
    "许可与致谢",
    "贡献",
    "更新日志",
    "docker",
    "开发与测试",
}

_MERMAID_NODE_RE = re.compile(r"([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\{([^}]+)\}|\(([^)]+)\))?")
_MERMAID_EDGE_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+(?:\s*(?:\[[^\]]+\]|\{[^}]+\}|\([^)]+\)))?)\s*"
    r"[-.=]+>(?:\|([^|]+)\|)?\s*"
    r"([A-Za-z0-9_]+(?:\s*(?:\[[^\]]+\]|\{[^}]+\}|\([^)]+\)))?)"
)


@dataclass(slots=True)
class MarkdownSection:
    """Extracted top-level section from a Markdown article."""

    title: str
    subheadings: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    table_headers: list[list[str]] = field(default_factory=list)


def _extract_content_signals(sec: MarkdownSection) -> list[str]:
    """Extract objective content characteristics without prescribing specific visual components."""
    blob = " ".join([sec.title, *sec.subheadings, *sec.key_points, *sec.summary_lines]).lower()
    signals: list[str] = []
    if any(k in blob for k in ("毛利", "营业利润", "净利润", "成本", "ebitda", "营收", "revenue", "operating income", "margin", "profit")):
        signals.append("has_profit_or_cost_breakdown")
    if any(k in blob for k in ("10年", "衰减", "趋势", "增长率", "cagr", "trajectory", "fade", "forecast", "y1", "y10", "同比")):
        signals.append("has_time_series_or_trajectory")
    if any(k in blob for k in ("估值", "对比", "方法", "比较", "versus", "vs", "matrix", "ablation", "权衡", "同业")) or len(sec.table_headers) >= 2:
        signals.append("has_multi_party_comparison")
    if any(k in blob for k in ("风险", "催化", "张力", "争议", "risk", "catalyst", "tension", "边界", "看多", "看空")):
        signals.append("has_tension_or_risk_factors")
    if any(k in blob for k in ("循环", "回退", "重试", "迭代", "loop", "retry", "fallback", "state")):
        signals.append("has_iterative_or_loop_process")
    if any(k in blob for k in ("占比", "份额", "分布", "比例", "share", "allocation", "breakdown")):
        signals.append("has_part_to_whole_allocation")
    if any(k in blob for k in ("目标价", "现价", "上行", "回撤", "upside", "fair value", "target price", "估值区间")):
        signals.append("has_valuation_or_range_gap")
    return signals or ["has_structured_concepts"]


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"[`*_~]", "", cleaned)
    return cleaned.strip()


def _short_label(text: str, max_len: int = 12) -> str:
    cleaned = _clean_text(text)
    cleaned = re.sub(r"^[^\w\u4e00-\u9fff]+", "", cleaned)
    cleaned = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", cleaned).strip()
    if len(cleaned) <= max_len:
        return cleaned or text.strip()[:max_len]
    for sep in ("：", ":", "—", "-", "、", "或", "及"):
        if sep in cleaned:
            head = cleaned.split(sep, 1)[0].strip()
            if 2 <= len(head) <= max_len:
                return head
    # Only split on space for pure-Latin phrases to avoid truncating "生成 Markdown ..."
    if " " in cleaned and not any(ord(c) > 127 for c in cleaned):
        head = cleaned.split(" ", 1)[0].strip()
        if 2 <= len(head) <= max_len:
            return head
    # Avoid slicing mid-ASCII word at max_len (e.g. "FinMas", "Markdow")
    cut = max_len
    if cut < len(cleaned) and cleaned[cut - 1].isascii() and cleaned[cut - 1].isalnum() and cleaned[cut].isalnum():
        end = cut
        while end < len(cleaned) and cleaned[end].isascii() and cleaned[end].isalnum():
            end += 1
        if end - max_len <= 3:
            return cleaned[:end].strip()
        start = cut
        while start > 0 and cleaned[start - 1].isascii() and cleaned[start - 1].isalnum():
            start -= 1
        if start >= 2:
            return cleaned[:start].strip()
    return cleaned[:max_len].strip()


def _mermaid_node_parts(raw_label: str) -> tuple[str, str | None, str]:
    """Split 'A：B' Mermaid labels into crisp card label, optional sublabel, and full note."""
    cleaned = _clean_text(raw_label)
    for sep in ("：", ":"):
        if sep in cleaned:
            head, tail = (part.strip() for part in cleaned.split(sep, 1))
            if 2 <= len(head) <= 10 and 2 <= len(tail) <= 10:
                return head, tail, cleaned
    short = _short_label(raw_label, max_len=10)
    note = cleaned if cleaned != short else ""
    return short, None, note


def _dag_column_count(node_ids: list[str], edges: list[dict[str, str]]) -> int:
    """Estimate topological layer count of a DAG."""
    depths = {nid: 0 for nid in node_ids}
    for _ in range(len(node_ids)):
        changed = False
        for e in edges:
            u, v = e["from"], e["to"]
            if u in depths and v in depths and depths[v] < depths[u] + 1:
                depths[v] = depths[u] + 1
                changed = True
        if not changed:
            break
    return (max(depths.values()) + 1) if depths else 0


def _compact_linear_mermaid_pairs(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    *,
    max_cols: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Merge unlabeled 1->1 linear chain steps into label+sublabel cards when DAG depth exceeds max_cols."""
    cur_nodes = [dict(n) for n in nodes]
    cur_edges = [dict(e) for e in edges]

    while _dag_column_count([n["id"] for n in cur_nodes], cur_edges) > max_cols:
        out_map: dict[str, list[dict[str, str]]] = {}
        in_map: dict[str, list[dict[str, str]]] = {}
        for e in cur_edges:
            out_map.setdefault(e["from"], []).append(e)
            in_map.setdefault(e["to"], []).append(e)

        node_by_id = {n["id"]: n for n in cur_nodes}
        merged_pair: tuple[str, str] | None = None
        # Prefer folding chains without children and without sublabel already set
        for e in reversed(cur_edges):
            u, v = e["from"], e["to"]
            if e.get("label"):
                continue
            if len(out_map.get(u, [])) != 1 or len(in_map.get(v, [])) != 1:
                continue
            nu, nv = node_by_id.get(u), node_by_id.get(v)
            if not nu or not nv or nu.get("children") or nv.get("children"):
                continue
            if nu.get("sublabel") or nv.get("sublabel"):
                continue
            merged_pair = (u, v)
            break

        if merged_pair is None:
            break

        u, v = merged_pair
        nu = node_by_id[u]
        nv = node_by_id[v]
        nu["sublabel"] = _short_label(nv["label"], max_len=10)
        note_parts = [p for p in (nu.get("note", ""), nv.get("note", "") or nv["label"]) if p]
        if note_parts:
            nu["note"] = " -> ".join(note_parts)

        cur_nodes = [n for n in cur_nodes if n["id"] != v]
        next_edges: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for e in cur_edges:
            if e["from"] == u and e["to"] == v:
                continue
            src = u if e["from"] == v else e["from"]
            dst = u if e["to"] == v else e["to"]
            if src == dst or (src, dst) in seen_pairs:
                continue
            seen_pairs.add((src, dst))
            obj: dict[str, str] = {"id": f"m_{len(next_edges) + 1}", "from": src, "to": dst}
            if e.get("label"):
                obj["label"] = e["label"]
            next_edges.append(obj)
        cur_edges = next_edges

    return cur_nodes, cur_edges


def _fold_mermaid_parallel_branches(
    node_meta: dict[str, tuple[str, str | None, str]],
    edges: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Collapse 2-4 parallel siblings sharing exact predecessors/successors into one container node."""
    sigs: dict[str, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]] = {}
    for nid in node_meta:
        inc = tuple(sorted((e["from"], e.get("label", "")) for e in edges if e["to"] == nid))
        out = tuple(sorted((e["to"], e.get("label", "")) for e in edges if e["from"] == nid))
        sigs[nid] = (inc, out)

    by_sig: dict[tuple[Any, Any], list[str]] = {}
    for nid, sig in sigs.items():
        if not sig[0] and not sig[1]:
            continue
        by_sig.setdefault(sig, []).append(nid)

    member_to_group: dict[str, str] = {}
    group_specs: dict[str, dict[str, Any]] = {}
    consumed_edge_labels: set[tuple[str, str]] = set()

    for sig, group_nids in by_sig.items():
        if not (2 <= len(group_nids) <= 4):
            continue
        gid = f"grp_{group_nids[0]}"
        in_labels = [lbl for _, lbl in sig[0] if lbl]
        if in_labels and len(set(in_labels)) == 1:
            g_label = _short_label(in_labels[0], max_len=10)
            for src_id, _ in sig[0]:
                consumed_edge_labels.add((src_id, gid))
        else:
            g_label = "并行分支" if any(ord(c) > 127 for nid in group_nids for c in node_meta[nid][0]) else "Parallel Group"

        children: list[dict[str, Any]] = []
        for nid in group_nids:
            member_to_group[nid] = gid
            lbl, sub, note = node_meta[nid]
            child: dict[str, Any] = {"id": nid, "label": lbl}
            if sub:
                child["sublabel"] = sub
            if note:
                child["note"] = note
            children.append(child)

        group_specs[gid] = {
            "id": gid,
            "label": g_label,
            "child_layout": "grid" if len(group_nids) >= 3 else "row",
            "children": children,
        }

    folded_nodes: list[dict[str, Any]] = []
    emitted_groups: set[str] = set()
    for nid, (lbl, sub, note) in node_meta.items():
        gid = member_to_group.get(nid)
        if gid is not None:
            if gid not in emitted_groups:
                folded_nodes.append(group_specs[gid])
                emitted_groups.add(gid)
            continue
        node_obj: dict[str, Any] = {"id": nid, "label": lbl}
        if sub:
            node_obj["sublabel"] = sub
        if note:
            node_obj["note"] = note
        folded_nodes.append(node_obj)

    folded_edges: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for e in edges:
        src = member_to_group.get(e["from"], e["from"])
        dst = member_to_group.get(e["to"], e["to"])
        if src == dst or (src, dst) in seen_pairs:
            continue
        seen_pairs.add((src, dst))
        edge_obj: dict[str, str] = {"id": f"m_{len(folded_edges) + 1}", "from": src, "to": dst}
        elabel = e.get("label")
        if elabel and (src, dst) not in consumed_edge_labels:
            edge_obj["label"] = elabel
        folded_edges.append(edge_obj)

    return _compact_linear_mermaid_pairs(folded_nodes, folded_edges)


def _parse_mermaid_flowchart(lines: list[str]) -> dict[str, Any] | None:
    node_meta: dict[str, tuple[str, str | None, str]] = {}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()

    def _register_node(token: str) -> str:
        m = _MERMAID_NODE_RE.match(token.strip())
        if not m:
            nid = re.sub(r"\W+", "_", token.strip()) or "node"
            node_meta.setdefault(nid, (nid, None, ""))
            return nid
        nid = m.group(1)
        raw_label = m.group(2) or m.group(3) or m.group(4)
        if raw_label:
            node_meta[nid] = _mermaid_node_parts(raw_label)
        else:
            node_meta.setdefault(nid, (nid, None, ""))
        return nid

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("flowchart", "graph", "%%", "subgraph", "end")):
            continue
        em = _MERMAID_EDGE_RE.match(line)
        if not em:
            continue
        src = _register_node(em.group(1))
        dst = _register_node(em.group(3))
        elabel = _short_label(em.group(2), max_len=5) if em.group(2) else None
        if (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            edge_obj: dict[str, str] = {"id": f"m_{len(edges) + 1}", "from": src, "to": dst}
            if elabel:
                edge_obj["label"] = elabel
            edges.append(edge_obj)

    if len(node_meta) < 2 or not edges:
        return None
    folded_nodes, folded_edges = _fold_mermaid_parallel_branches(node_meta, edges)
    return {
        "nodes": folded_nodes,
        "edges": folded_edges,
    }


def _strip_yaml_frontmatter(lines: list[str]) -> list[str]:
    """Drop leading YAML/Obsidian frontmatter (`--- ... ---`) before parsing Markdown structure."""
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].strip() == "---":
        for end in range(idx + 1, min(len(lines), idx + 80)):
            if lines[end].strip() in ("---", "..."):
                return lines[end + 1 :]
    return lines


def extract_markdown_outline(
    markdown_text: str,
    *,
    theme: str = "slate_dark",
    density: DensityMode = "standard",
) -> dict[str, Any]:
    """Extract a semantic seed without selecting visual objects, then return its paced placeholder deck."""
    doc_title = "Technical Overview"
    tagline = ""
    sections: list[MarkdownSection] = []
    mermaid_flows: list[dict[str, Any]] = []

    current: MarkdownSection | None = None
    in_code = False
    code_lang = ""
    code_buf: list[str] = []

    for raw in _strip_yaml_frontmatter(markdown_text.splitlines()):
        stripped = raw.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip().lower()
                code_buf = []
            else:
                if code_lang == "mermaid":
                    parsed = _parse_mermaid_flowchart(code_buf)
                    if parsed:
                        mermaid_flows.append(parsed)
                in_code = False
                code_lang = ""
                code_buf = []
            continue

        if in_code:
            code_buf.append(raw)
            continue

        if stripped.startswith("# ") and doc_title == "Technical Overview":
            doc_title = _clean_text(stripped[2:])
            doc_title = re.sub(r"^[^\w\u4e00-\u9fff]+", "", doc_title).strip() or "Technical Overview"
            continue

        if stripped.startswith("> ") and not tagline and current is None:
            tagline = _clean_text(stripped[2:])
            continue

        if stripped.startswith("## "):
            current = MarkdownSection(title=_clean_text(stripped[3:]))
            sections.append(current)
            continue

        if current is None:
            if (
                stripped
                and not stripped.startswith(("---", "***", "___", "![", "[![", "<"))
                and not re.match(r"^\[[^\]]+\]\([^)]+\)\s*\|", stripped)
                and not tagline
            ):
                tagline = _clean_text(stripped)
            continue

        if stripped.startswith("### "):
            current.subheadings.append(_clean_text(stripped[4:]))
        elif stripped.startswith(("- ", "* ")):
            bullet = _clean_text(stripped[2:])
            bold_m = re.match(r"^\*\*([^*]+)\*\*", raw.strip()[2:].strip())
            if bold_m:
                current.key_points.append(_short_label(bold_m.group(1), max_len=14))
            else:
                current.key_points.append(_short_label(bullet, max_len=14))
            current.summary_lines.append(bullet)
        elif stripped.startswith("|"):
            if "---" not in stripped:
                cells = [_clean_text(c) for c in stripped.strip("|").split("|")]
                if cells and any(cells):
                    current.table_headers.append(cells)
        elif stripped and not stripped.startswith(("[![", "<")):
            current.summary_lines.append(_clean_text(stripped))

    substantive = [
        sec
        for sec in sections
        if _short_label(sec.title).lower() not in _BOILERPLATE_TITLES
    ]
    pillars = substantive[:5] if len(substantive) >= 2 else sections[:5]
    if not pillars:
        pillars = [MarkdownSection(title=doc_title, summary_lines=[tagline] if tagline else [])]

    section_labels = [_short_label(sec.title, max_len=24) for sec in pillars]
    design_constraints = [
        "No visual objects have been selected; choose a visual form from the argument rather than defaulting to cards."
    ]

    # Stage 1 is a semantic seed. The Agent chooses and authors visual objects.
    scenes: list[dict[str, Any]] = [
        {
            "id": "overview",
            "title": _short_label(doc_title, max_len=24),
            "layout": "canvas",
            "objects": [],
            "visual_intent": {
                "audience_takeaway": tagline or doc_title,
                "visual_focus": ", ".join(section_labels),
                "design_constraints": design_constraints,
            },
            "intro_note": (
                f"{tagline} 已提取章节结构；请先选择视觉表达，再创建对象。"
                if tagline
                else f"已提取《{doc_title}》的章节结构；请先选择视觉表达，再创建对象。"
            ),
        }
    ]

    if mermaid_flows:
        mf = mermaid_flows[0]
        labels: dict[str, str] = {}

        def _collect_mermaid_labels(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                labels[str(node["id"])] = str(node["label"])
                _collect_mermaid_labels(node.get("children", []))

        _collect_mermaid_labels(mf["nodes"])
        relationships: list[str] = []
        for edge in mf["edges"]:
            source = labels.get(str(edge["from"]), str(edge["from"]))
            target = labels.get(str(edge["to"]), str(edge["to"]))
            connector = f" —{edge['label']}→ " if edge.get("label") else " → "
            relationships.append(f"{source}{connector}{target}")
        scenes.append(
            {
                "id": "workflow_dag",
                "title": f"{_short_label(doc_title, max_len=16)} 流程图",
                "layout": "canvas",
                "objects": [],
                "visual_intent": {
                    "visual_focus": ", ".join(labels.values()),
                    "relationships": relationships,
                    "design_constraints": design_constraints,
                },
                "intro_note": "保留源 Mermaid 的节点与关系；尚未选择视觉对象或构图。",
            }
        )

    scene_graph: dict[str, Any] = {
        "title": doc_title,
        "theme": theme,
        "scenes": scenes,
    }
    # Stage 2: expand into progressive frames
    draft_deck = pace_deck(scene_graph, density=density, overwrite_existing=True)
    validation = validate_deck(draft_deck)

    return {
        "source_summary": {
            "title": doc_title,
            "tagline": tagline,
            "sections": [
                {
                    "title": sec.title,
                    "subheadings": sec.subheadings,
                    "key_points": sec.key_points[:6],
                    "table_count": len(sec.table_headers),
                    "content_signals": _extract_content_signals(sec),
                }
                for sec in sections
            ],
            "mermaid_flow_count": len(mermaid_flows),
        },
        "scene_graph": scene_graph,
        "draft_validation": validation.to_dict(),
        "draft_deck": draft_deck,
    }


def extract_outline_from_file(
    path: str | Path,
    *,
    theme: str = "slate_dark",
    density: DensityMode = "standard",
) -> dict[str, Any]:
    """Read a Markdown file and return its extracted Stage 1 scene_graph + Stage 2 draft_deck."""
    text = Path(path).read_text(encoding="utf-8")
    return extract_markdown_outline(text, theme=theme, density=density)
