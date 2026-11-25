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
    for sep in ("：", ":", "—", "-", "、"):
        if sep in cleaned:
            head = cleaned.split(sep, 1)[0].strip()
            if 2 <= len(head) <= max_len:
                return head
    # Only split on space for pure-Latin phrases to avoid truncating "生成 Markdown ..."
    if " " in cleaned and not any(ord(c) > 127 for c in cleaned):
        head = cleaned.split(" ", 1)[0].strip()
        if 2 <= len(head) <= max_len:
            return head
    return cleaned[:max_len]


def _parse_mermaid_flowchart(lines: list[str]) -> dict[str, Any] | None:
    nodes: dict[str, str] = {}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()

    def _register_node(token: str) -> str:
        m = _MERMAID_NODE_RE.match(token.strip())
        if not m:
            nid = re.sub(r"\W+", "_", token.strip()) or "node"
            nodes.setdefault(nid, nid)
            return nid
        nid = m.group(1)
        raw_label = m.group(2) or m.group(3) or m.group(4)
        if raw_label:
            nodes[nid] = _short_label(raw_label, max_len=14)
        else:
            nodes.setdefault(nid, nid)
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
        elabel = _short_label(em.group(2), max_len=10) if em.group(2) else None
        if (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            edge_obj: dict[str, str] = {"id": f"m_{len(edges) + 1}", "from": src, "to": dst}
            if elabel:
                edge_obj["label"] = elabel
            edges.append(edge_obj)

    if len(nodes) < 2 or not edges:
        return None
    return {
        "nodes": [{"id": nid, "label": label} for nid, label in nodes.items()],
        "edges": edges,
    }


def extract_markdown_outline(
    markdown_text: str,
    *,
    theme: str = "slate_dark",
    density: DensityMode = "standard",
) -> dict[str, Any]:
    """Parse a Markdown README/article into Stage 1 full-state scene_graph and Stage 2 paced draft_deck."""
    doc_title = "Technical Overview"
    tagline = ""
    sections: list[MarkdownSection] = []
    mermaid_flows: list[dict[str, Any]] = []

    current: MarkdownSection | None = None
    in_code = False
    code_lang = ""
    code_buf: list[str] = []

    for raw in markdown_text.splitlines():
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
            if stripped and not stripped.startswith("[![") and not tagline:
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
        elif stripped and not stripped.startswith("[!["):
            current.summary_lines.append(_clean_text(stripped))

    substantive = [
        sec
        for sec in sections
        if _short_label(sec.title).lower() not in _BOILERPLATE_TITLES
    ]
    pillars = substantive[:5] if len(substantive) >= 2 else sections[:5]
    if not pillars:
        pillars = [MarkdownSection(title=doc_title, summary_lines=[tagline] if tagline else [])]

    overview_nodes: list[dict[str, Any]] = []
    overview_edges: list[dict[str, str]] = []
    unpacked_once = False

    for idx, sec in enumerate(pillars):
        nid = f"p{idx + 1}"
        note_text = " ".join(sec.summary_lines[:2]).strip() or f"Section: {sec.title}"
        node_obj: dict[str, Any] = {
            "id": nid,
            "label": _short_label(sec.title, max_len=12),
            "note": note_text,
        }
        sub_candidates = sec.subheadings or sec.key_points
        dedup_subs: list[str] = []
        for s in sub_candidates:
            sl = _short_label(s, max_len=12)
            if sl and sl != node_obj["label"] and sl not in dedup_subs:
                dedup_subs.append(sl)
        if not unpacked_once and 2 <= len(dedup_subs) <= 4:
            node_obj["children"] = [
                {"id": f"c{c_i + 1}", "label": sub}
                for c_i, sub in enumerate(dedup_subs)
            ]
            if len(dedup_subs) >= 3:
                node_obj["child_layout"] = "grid"
            unpacked_once = True

        overview_nodes.append(node_obj)
        if idx > 0:
            overview_edges.append({"id": f"e{idx}", "from": f"p{idx}", "to": nid})

    # Stage 1: compact full-state scenes (no frames yet)
    scenes: list[dict[str, Any]] = [
        {
            "id": "overview",
            "title": _short_label(doc_title, max_len=24),
            "layout": "horizontal_flow",
            "intro_note": tagline or f"Overview of {doc_title}.",
            "nodes": overview_nodes,
            "edges": overview_edges,
        }
    ]

    if mermaid_flows:
        mf = mermaid_flows[0]
        scenes.append(
            {
                "id": "workflow_dag",
                "title": f"{_short_label(doc_title, max_len=16)} 流程图",
                "layout": "flow_dag",
                "nodes": mf["nodes"],
                "edges": mf["edges"],
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
