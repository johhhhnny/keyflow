"""Tests for KeyFlow two-stage DSL, pacing engine, layouts, outline extraction, .keyx compilation, CLI, and MCP."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from keyflow.cli import main as cli_main
from keyflow.compiler import compile_deck
from keyflow.layout import resolve_scene
from keyflow.mcp_server import dispatch_tool, handle_request
from keyflow.outline import extract_markdown_outline
from keyflow.pace import expand_scene_frames, pace_deck
from keyflow.schema import parse_deck, validate_deck
from keyflow.themes import THEMES


def _agent_skill_stage1() -> dict:
    return {
        "title": "Agent Skill Progressive Overview",
        "theme": "slate_dark",
        "scenes": [
            {
                "id": "agent_skill",
                "title": "Agent Skill",
                "layout": "horizontal_flow",
                "intro_note": "开场仅展示主题：Agent Skill。",
                "nodes": [
                    {"id": "concept", "label": "概念", "note": "核心概念说明。"},
                    {"id": "basic", "label": "基本用法", "note": "基础 SKILL.md 写法。"},
                    {
                        "id": "advanced",
                        "label": "高级用法",
                        "note": "高级用法模块。",
                        "children": [
                            {"id": "ref", "label": "Reference", "note": "按需参考文档"},
                            {"id": "script", "label": "Script", "note": "确定性脚本"},
                        ],
                    },
                    {"id": "compare", "label": "与MCP比较", "note": "与 MCP 对比。"},
                ],
                "edges": [
                    {"id": "e1", "from": "concept", "to": "basic"},
                    {"id": "e2", "from": "basic", "to": "advanced"},
                    {"id": "e3", "from": "advanced", "to": "compare"},
                ],
            }
        ],
    }


def _agent_skill_deck() -> dict:
    return pace_deck(_agent_skill_stage1(), overwrite_existing=True)


def _dag_and_grid_stage1() -> dict:
    return {
        "title": "DAG and Grid Test",
        "theme": "slate_dark",
        "scenes": [
            {
                "id": "dag_scene",
                "title": "Workflow DAG",
                "layout": "flow_dag",
                "nodes": [
                    {"id": "start", "label": "选择标的", "note": "选定研究目标。"},
                    {"id": "single", "label": "单角色分析", "sublabel": "专题深度研究", "note": "快速专题分析。"},
                    {
                        "id": "multi",
                        "label": "四大师并行",
                        "child_layout": "grid",
                        "note": "触发四大师并行研究。",
                        "children": [
                            {"id": "a", "label": "段永平", "sublabel": "商业常识"},
                            {"id": "b", "label": "巴菲特", "sublabel": "现金流"},
                            {"id": "c", "label": "芒格", "sublabel": "逆向风险"},
                            {"id": "d", "label": "李录", "sublabel": "长期趋势"},
                        ],
                    },
                    {"id": "merge", "label": "研究总监汇总", "variant": "accent", "note": "汇总与复核。"},
                ],
                "edges": [
                    {"id": "e1", "from": "start", "to": "single", "label": "单角色"},
                    {"id": "e2", "from": "start", "to": "multi", "label": "多角色"},
                    {"id": "e3", "from": "single", "to": "merge"},
                    {"id": "e4", "from": "multi", "to": "merge"},
                ],
            }
        ],
    }


def test_stage1_validates_and_paces_to_6_frames() -> None:
    stage1 = _agent_skill_stage1()
    val = validate_deck(stage1)
    assert val.valid is True
    assert val.warnings == []

    paced = pace_deck(stage1)
    frames = paced["scenes"][0]["frames"]
    assert len(frames) == 6
    assert frames[0]["visible_nodes"] == []
    assert frames[0]["notes"] == "开场仅展示主题：Agent Skill。"
    assert frames[4]["expanded_nodes"] == ["advanced"]
    assert "按需参考文档" in frames[4]["notes"]
    assert "确定性脚本" in frames[4]["notes"]

    compact = pace_deck(stage1, density="compact")
    assert len(compact["scenes"][0]["frames"]) == 5


def test_pace_all_layouts() -> None:
    dag_frames = expand_scene_frames(_dag_and_grid_stage1()["scenes"][0], density="standard")
    # start -> single -> multi (collapsed) -> multi (expanded) -> merge
    assert len(dag_frames) == 5
    assert dag_frames[2]["visible_nodes"] == ["start", "single", "multi"]
    assert dag_frames[2]["expanded_nodes"] == []
    assert dag_frames[3]["expanded_nodes"] == ["multi"]

    hub_scene = {
        "id": "hub",
        "title": "Hub",
        "layout": "hub_spoke",
        "nodes": [{"id": "c", "label": "Core"}, {"id": "s1", "label": "S1"}, {"id": "s2", "label": "S2"}],
    }
    hub_frames = expand_scene_frames(hub_scene)
    assert [len(f["visible_nodes"]) for f in hub_frames] == [1, 2, 3]

    cmp_scene = {
        "id": "cmp",
        "title": "Compare",
        "layout": "comparison",
        "nodes": [
            {"id": "left", "label": "Left", "kind": "group_dashed", "children": [{"id": "l1", "label": "L1"}]},
            {"id": "right", "label": "Right", "kind": "group_dashed", "children": [{"id": "r1", "label": "R1"}]},
        ],
    }
    cmp_frames = expand_scene_frames(cmp_scene)
    assert len(cmp_frames) == 2
    assert cmp_frames[0]["visible_nodes"] == ["left"]
    assert cmp_frames[1]["visible_nodes"] == ["left", "right"]


def test_validation_rejects_bad_refs_and_warns_on_bullets_and_crowded_row() -> None:
    bad = _agent_skill_deck()
    bad["scenes"][0]["nodes"][0]["label"] = "• 第一点\n• 第二点"
    bad["scenes"][0]["nodes"][2]["children"].extend(
        [{"id": "c3", "label": "Prompt"}, {"id": "c4", "label": "Eval"}]
    )
    bad["scenes"][0]["edges"].append({"id": "bad_e", "from": "missing", "to": "basic"})
    bad["scenes"][0]["frames"][0]["expanded_nodes"] = ["concept"]
    res = validate_deck(bad)
    assert res.valid is False
    assert any("missing" in err for err in res.errors)
    assert any("expanded node 'concept'" in err for err in res.errors)
    assert any("line breaks or bullets" in w for w in res.warnings)
    assert any("child_layout='grid'" in w for w in res.warnings)


def test_validation_warns_on_single_frame_multi_node_scene() -> None:
    single = _dag_and_grid_stage1()
    single["scenes"][0]["frames"] = [
        {"visible_nodes": ["start", "single", "multi", "merge"], "expanded_nodes": ["multi"], "notes": "All at once."}
    ]
    res = validate_deck(single)
    assert res.valid is True
    assert any("single frame" in w for w in res.warnings)


def test_horizontal_flow_preserves_anchors_across_progressive_frames() -> None:
    deck = parse_deck(_agent_skill_deck())
    frames = resolve_scene(deck.scenes[0])
    assert len(frames) == 6
    assert frames[0].boxes == []
    assert frames[0].depth == 1
    assert frames[1].depth == 2

    def box_rect(frame_idx: int, box_id: str):
        for b in frames[frame_idx].boxes:
            if b.id == box_id:
                return b.rect
        raise AssertionError(f"{box_id} missing in frame {frame_idx}")

    concept_ref = box_rect(1, "concept")
    for idx in range(2, 6):
        assert box_rect(idx, "concept") == concept_ref

    basic_ref = box_rect(2, "basic")
    for idx in range(3, 6):
        assert box_rect(idx, "basic") == basic_ref

    adv_collapsed = box_rect(3, "advanced")
    adv_expanded = box_rect(4, "advanced")
    assert adv_collapsed.x == pytest.approx(adv_expanded.x)
    assert adv_expanded.w > adv_collapsed.w


def test_grid_subcards_and_flow_dag_layers() -> None:
    paced = pace_deck(_dag_and_grid_stage1())
    deck = parse_deck(paced)
    frames = resolve_scene(deck.scenes[0])
    f = frames[3]  # expanded multi frame

    by_id = {b.id: b for b in f.boxes}
    assert by_id["start"].rect.x < by_id["single"].rect.x
    assert by_id["start"].rect.x < by_id["multi"].rect.x
    assert by_id["single"].rect.y + by_id["single"].rect.h < by_id["multi"].rect.y
    assert by_id["multi__a"].rect.y == pytest.approx(by_id["multi__b"].rect.y)
    assert by_id["multi__c"].rect.y == pytest.approx(by_id["multi__d"].rect.y)
    assert by_id["multi__c"].rect.y > by_id["multi__a"].rect.y
    labeled = [e for e in f.edges if e.label]
    assert {e.label for e in labeled} == {"单角色", "多角色"}


def test_comparison_emits_vs_divider() -> None:
    raw = {
        "title": "Compare",
        "scenes": [
            {
                "id": "cmp",
                "title": "A vs B",
                "layout": "comparison",
                "nodes": [
                    {"id": "a", "label": "方案 A"},
                    {"id": "b", "label": "方案 B"},
                ],
            }
        ],
    }
    frames = resolve_scene(parse_deck(pace_deck(raw)).scenes[0])
    assert len(frames) == 2
    assert frames[0].dividers == []
    assert len(frames[1].dividers) == 1
    assert frames[1].dividers[0].label == "VS"


def test_stage1_compiles_directly_without_manual_frames(tmp_path: Path) -> None:
    from creator_studio_doc_format.core import KeyxDocument

    out = tmp_path / "direct_stage1.keyx"
    compiled = compile_deck(_agent_skill_stage1(), out)
    assert compiled.exists()
    with KeyxDocument.open(compiled) as loaded:
        assert len(loaded.payload.slides) == 6


@pytest.mark.parametrize(
    "layout",
    [
        "horizontal_flow",
        "vertical_flow",
        "comparison",
        "hub_spoke",
        "flow_dag",
        "architecture_evolution",
        "sequence_timeline",
        "metrics_cards",
    ],
)
def test_all_layout_modes_compile(tmp_path: Path, layout: str) -> None:
    if layout == "flow_dag":
        raw = _dag_and_grid_stage1()
    elif layout == "metrics_cards":
        raw = {
            "title": "Metrics",
            "scenes": [
                {
                    "id": "m",
                    "title": "KPIs",
                    "layout": "metrics_cards",
                    "nodes": [
                        {"id": "k1", "badge": "SPEED", "metric": "10x", "label": "Faster", "sublabel": "Headless", "variant": "success"},
                        {"id": "k2", "badge": "RISK", "metric": "0", "label": "GUI Locks", "variant": "warn"},
                    ],
                }
            ],
        }
    else:
        raw = _agent_skill_stage1()
    raw["scenes"][0]["layout"] = layout
    out = tmp_path / f"{layout}.keyx"
    compiled = compile_deck(raw, out)
    assert compiled.exists()
    with zipfile.ZipFile(compiled) as zf:
        assert any(name.endswith(".json") for name in zf.namelist())


def test_sequence_timeline_curved_arcs_and_pacer() -> None:
    raw = {
        "title": "State Flow",
        "scenes": [
            {
                "id": "seq",
                "title": "Lifecycle",
                "layout": "sequence_timeline",
                "nodes": [
                    {"id": "a", "label": "Draft", "badge": "S1"},
                    {"id": "b", "label": "Check"},
                    {"id": "c", "label": "Done", "variant": "success"},
                ],
                "edges": [
                    {"id": "e1", "from": "a", "to": "b", "label": "validate"},
                    {"id": "e2", "from": "b", "to": "c", "label": "pass"},
                    {"id": "e3", "from": "b", "to": "a", "label": "retry", "style": "dashed"},
                    {"id": "e4", "from": "a", "to": "c", "label": "fast-track", "style": "dashed"},
                ],
            }
        ],
    }
    paced = pace_deck(raw)
    frames = resolve_scene(parse_deck(paced).scenes[0])
    assert len(frames) == 6  # start + 4 edge steps + final un-dimmed summary
    final = frames[-1]
    edges = {e.id: e for e in final.edges}
    assert edges["e1"].curve_control is None  # adjacent straight
    assert edges["e3"].curve_control is not None and edges["e3"].curve_control[1] > final.boxes[0].rect.cy  # lower feedback arc
    assert edges["e4"].curve_control is not None and edges["e4"].curve_control[1] < final.boxes[0].rect.cy  # upper skip arc


def test_showcase_example_compiles_cleanly(tmp_path: Path) -> None:
    showcase = json.loads(Path("examples/genres_showcase_stage1.json").read_text(encoding="utf-8"))
    val = validate_deck(showcase)
    assert val.valid is True
    assert val.warnings == []
    out = tmp_path / "showcase.keyx"
    compile_deck(showcase, out)
    assert out.exists()


def test_pinned_flow_proportion_bar_and_comparison_matrix(tmp_path: Path) -> None:
    from creator_studio_doc_format.core import KeyxDocument

    raw = json.loads(Path("examples/llm_sampling_stage1.json").read_text(encoding="utf-8"))
    val = validate_deck(raw)
    assert val.valid is True
    assert val.warnings == []

    paced = pace_deck(raw)
    deck = parse_deck(paced)
    assert deck.pinned_flow is not None

    # Scene 0: macro-only -> centered pinned_flow
    f_macro = resolve_scene(deck.scenes[0], pinned_flow=deck.pinned_flow)
    assert len(f_macro) == 1
    assert f_macro[0].pinned_flow is not None and f_macro[0].pinned_flow.is_centered is True
    assert any(n.is_active and n.id == "temp" for n in f_macro[0].pinned_flow.nodes)

    # Scene 1: comparison_matrix -> baseline first, then remaining columns, then annotations
    f_mx = resolve_scene(deck.scenes[1], pinned_flow=deck.pinned_flow)
    assert len(f_mx) == 4
    assert f_mx[0].pinned_flow is not None and f_mx[0].pinned_flow.is_centered is False
    assert f_mx[0].comparison_matrix is not None
    assert [c.id for c in f_mx[0].comparison_matrix.columns] == ["t_base"]
    assert f_mx[2].comparison_matrix is not None and f_mx[2].comparison_matrix.columns[0].action_banner is None
    assert f_mx[3].comparison_matrix is not None and f_mx[3].comparison_matrix.columns[0].takeaway == "低温稳定"

    # Scene 2: proportion_bar -> empty scale first, then 5 items progressively
    f_pb = resolve_scene(deck.scenes[2], pinned_flow=deck.pinned_flow)
    assert len(f_pb) == 6
    assert f_pb[0].proportion_bar is not None
    assert all(not it.visible for it in f_pb[0].proportion_bar.items)
    assert f_pb[-1].proportion_bar is not None
    assert all(it.visible for it in f_pb[-1].proportion_bar.items)
    # Narrow adjacent segments (bike 3%, hello 2%) should not have overlapping labels
    bike_rect = f_pb[-1].proportion_bar.items[3].label_rect
    hello_rect = f_pb[-1].proportion_bar.items[4].label_rect
    assert (hello_rect.x >= bike_rect.x + bike_rect.w) or (hello_rect.y != bike_rect.y)

    out = tmp_path / "llm_sampling.keyx"
    compile_deck(raw, out)
    with KeyxDocument.open(out) as loaded:
        assert len(loaded.payload.slides) == 11


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_all_themes_compile(tmp_path: Path, theme_name: str) -> None:
    out = tmp_path / f"{theme_name}.keyx"
    compiled = compile_deck(_dag_and_grid_stage1(), out, theme_override=theme_name)
    assert compiled.exists()
    assert compiled.stat().st_size > 10_000


def test_extract_markdown_outline_returns_stage1_and_paced_deck(tmp_path: Path) -> None:
    md = """# Demo Project
> A concise tagline for the project.

## 核心理念
- **结构化输入**：用统一格式描述流程

## 系统架构
### 提炼层
### 编译层

## 工作流程
```mermaid
flowchart TD
    A[输入文档] -->|解析| B[分镜草稿]
    B -->|编译| C[Keynote文稿]
```

## License
MIT
"""
    extracted = extract_markdown_outline(md)
    assert extracted["draft_validation"]["valid"] is True
    assert "frames" not in extracted["scene_graph"]["scenes"][0]
    scenes = extracted["draft_deck"]["scenes"]
    assert scenes[0]["layout"] == "horizontal_flow"
    assert len(scenes[0]["nodes"]) == 3
    assert scenes[1]["layout"] == "flow_dag"
    assert len(scenes[1]["frames"]) == 3

    out_keyx = tmp_path / "auto.keyx"
    compile_deck(extracted["draft_deck"], out_keyx)
    assert out_keyx.exists()


def test_cli_two_stage_outline_pace_and_compile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    md_path = tmp_path / "README.md"
    md_path.write_text("# Sample\n\n## Concept\nHello.\n\n## Usage\nRun it.\n", encoding="utf-8")
    stage1_path = tmp_path / "stage1.json"
    paced_path = tmp_path / "paced.json"
    out_path = tmp_path / "deck.keyx"

    assert cli_main(["outline", "-i", str(md_path), "--stage1", "-o", str(stage1_path)]) == 0
    stage1_data = json.loads(stage1_path.read_text(encoding="utf-8"))
    assert "frames" not in stage1_data["scenes"][0]
    capsys.readouterr()

    assert cli_main(["pace", "-i", str(stage1_path), "-o", str(paced_path)]) == 0
    paced_data = json.loads(paced_path.read_text(encoding="utf-8"))
    assert len(paced_data["scenes"][0]["frames"]) == 3
    capsys.readouterr()

    assert cli_main(["compile", "-i", str(paced_path), "-o", str(out_path)]) == 0
    assert out_path.exists()


def test_mcp_server_dispatch_two_stage(tmp_path: Path) -> None:
    themes_res = dispatch_tool("list_themes", {})
    assert "slate_dark" in themes_res["themes"]

    outline_res = dispatch_tool("extract_outline", {"markdown": "# Test\n\n## Part A\nFoo\n\n## Part B\nBar\n"})
    assert "scene_graph" in outline_res
    assert outline_res["draft_validation"]["valid"] is True

    paced_res = dispatch_tool("pace_storyboard", {"storyboard": _agent_skill_stage1()})
    assert paced_res["paced"] is True
    assert len(paced_res["storyboard"]["scenes"][0]["frames"]) == 6

    out = tmp_path / "mcp_out.keyx"
    resp = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "compile_keyx",
                "arguments": {"storyboard": _dag_and_grid_stage1(), "output_path": str(out)},
            },
        }
    )
    assert resp is not None
    assert resp["result"]["isError"] is False
    assert out.exists()
