"""Tests for KeyFlow two-stage DSL, pacing engine, layouts, outline extraction, .keyx compilation, CLI, and MCP."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from keyflow import __version__, audit_deck
from keyflow.audit import _audit_deck_pinned_flow_stability, _audit_scene_anchor_stability
from keyflow.cli import main as cli_main
from keyflow.compiler import compile_deck, export_slide_pngs
from keyflow.layout import (
    BoxRect,
    PlacedBox,
    PlacedComparisonMatrix,
    PlacedEdge,
    PlacedMatrixColumn,
    PlacedPinnedFlow,
    PlacedProportionBar,
    PlacedProportionItem,
    PlacedRibbonNode,
    ResolvedFrame,
    resolve_scene,
)
from keyflow.mcp_server import dispatch_tool, handle_request, main as mcp_main
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
    assert 1_000 < compiled.stat().st_size < 50_000


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


def test_mcp_lifecycle_methods_and_malformed_stdin() -> None:
    import tomllib

    pyproject_version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init is not None
    assert init["result"]["serverInfo"]["version"] == __version__ == pyproject_version == "0.3.0"

    assert handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"}) == {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {},
    }
    assert handle_request({"jsonrpc": "2.0", "id": 3, "method": "resources/list"}) == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {"resources": []},
    }
    assert handle_request({"jsonrpc": "2.0", "id": 4, "method": "prompts/list"}) == {
        "jsonrpc": "2.0",
        "id": 4,
        "result": {"prompts": []},
    }
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None

    fake_in = io.StringIO("not json\n[]\n{\"jsonrpc\": \"2.0\", \"id\": 9, \"method\": \"ping\"}\n")
    fake_out = io.StringIO()
    assert mcp_main(stdin=fake_in, stdout=fake_out) == 0
    lines = [json.loads(line) for line in fake_out.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["error"]["code"] == -32600
    assert lines[2] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_export_slide_pngs_clear_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyflow.compiler.sys.platform", "linux")
    with pytest.raises(RuntimeError, match="requires macOS with Apple Keynote"):
        export_slide_pngs(tmp_path / "missing.keyx", tmp_path / "png")

    monkeypatch.setattr("keyflow.compiler.sys.platform", "darwin")
    monkeypatch.setattr("keyflow.compiler.shutil.which", lambda _: "/usr/bin/osascript")
    with pytest.raises(FileNotFoundError, match="Keynote file not found"):
        export_slide_pngs(tmp_path / "missing.keyx", tmp_path / "png")


def test_lines_emit_open_shape_paths_not_connection_lines(tmp_path: Path) -> None:
    """Ensure edges, dividers, proportion axes, and pinned flows emit open Shape lines for Magic Move."""
    from creator_studio_doc_format.core import KeyxDocument

    for sample in ("examples/llm_sampling_stage1.json", "examples/genres_showcase_stage1.json"):
        raw = json.loads(Path(sample).read_text(encoding="utf-8"))
        out = tmp_path / f"{Path(sample).stem}.keyx"
        compile_deck(raw, out)
        with KeyxDocument.open(out) as loaded:
            has_quadratic_curve = False
            for slide in loaded.payload.slides:
                for item in slide.contents or []:
                    assert item.object.connectionLine is None
                    sh = item.object.shape
                    if sh and sh.path and sh.path.bezier and " Q " in sh.path.bezier.path:
                        has_quadratic_curve = True
            if "genres_showcase" in sample:
                assert has_quadratic_curve is True


def test_audit_passes_strict_on_all_builtin_examples() -> None:
    for sample in sorted(Path("examples").glob("*.json")):
        raw = json.loads(sample.read_text(encoding="utf-8"))
        report = audit_deck(raw, strict=True)
        assert report.passed is True, f"{sample} failed strict audit: {report.errors}"
        assert report.errors == []
        assert report.warnings == []
        assert 1 in report.review_slides


def test_audit_catches_overflow_narrow_proportion_jitter_and_mcp_review_pngs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    crowded_deck = {
        "title": "Audit Edge Test",
        "scenes": [
            {
                "id": "s_crowded",
                "title": "Crowded Proportion",
                "layout": "proportion_bar",
                "proportion_bar": {
                    "axis_min": 0,
                    "axis_max": 100,
                    "items": [
                        {"id": "major", "label": "核心主体超长标签文字", "value": 99.0},
                        {"id": "tiny", "label": "极窄尾部", "value": 0.4},
                    ],
                },
            },
            {
                "id": "s_dense",
                "title": "Very Long Row",
                "layout": "horizontal_flow",
                "nodes": [
                    {"id": f"n{i}", "label": "超长节点名称演示测试溢出" if i == 1 else f"节点{i}"}
                    for i in range(1, 8)
                ],
                "edges": [],
            },
        ],
    }

    report = audit_deck(crowded_deck)
    cats = {w.category for w in report.warnings}
    assert "crowded_proportion" in cats
    assert "cramped_scale" in cats or "text_overflow" in cats
    assert all(w.suggestion for w in report.warnings)

    # CLI audit fails in --strict when warnings exist, succeeds otherwise
    deck_path = tmp_path / "crowded.json"
    deck_path.write_text(json.dumps(crowded_deck, ensure_ascii=False), encoding="utf-8")
    assert cli_main(["audit", "-i", str(deck_path)]) == 0
    capsys.readouterr()
    assert cli_main(["audit", "-i", str(deck_path), "--strict"]) == 1
    capsys.readouterr()

    # Anchor jitter check catches frame-to-frame coordinate drift on persistent boxes
    f0 = ResolvedFrame(
        scene_id="drift",
        frame_index=0,
        title="T",
        subtitle=None,
        title_rect=None,
        subtitle_rect=None,
        boxes=[PlacedBox(id="a", label="A", rect=BoxRect(100, 200, 220, 120), kind="card", variant="primary")],
    )
    f1 = ResolvedFrame(
        scene_id="drift",
        frame_index=1,
        title="T",
        subtitle=None,
        title_rect=None,
        subtitle_rect=None,
        boxes=[PlacedBox(id="a", label="A", rect=BoxRect(118, 200, 220, 120), kind="card", variant="primary")],
    )
    jitter_findings: list = []
    _audit_scene_anchor_stability([f0, f1], start_slide_num=1, findings=jitter_findings)
    assert len(jitter_findings) == 1
    assert jitter_findings[0].category == "anchor_jitter"

    # MCP audit_storyboard + compile_keyx review_pngs routing
    mcp_audit = dispatch_tool("audit_storyboard", {"storyboard": _agent_skill_stage1(), "strict": True})
    assert mcp_audit["passed"] is True
    assert mcp_audit["review_slides"] == [1, 6]

    fake_pngs = [tmp_path / "png" / f"slide.{i:03d}.png" for i in range(1, 7)]
    monkeypatch.setattr("keyflow.mcp_server.export_slide_pngs", lambda *_: fake_pngs)
    comp = dispatch_tool(
        "compile_keyx",
        {
            "storyboard": _agent_skill_stage1(),
            "output_path": str(tmp_path / "out.keyx"),
            "preview_dir": str(tmp_path / "png"),
        },
    )
    assert comp["compiled"] is True
    assert comp["audit"]["review_pngs"] == [str(fake_pngs[0]), str(fake_pngs[5])]


def test_outline_folds_mermaid_parallel_fanout_and_passes_strict_audit() -> None:
    md = """# FinMaster
[English](README.md) | 简体中文

> 把价值投资研究方法，变成一套可执行的工作流。

## 介绍
<table><tr><td>ignore</td></tr></table>
- **框架化**：先结构后结论

## 执行流程图
```mermaid
flowchart TD
    A[选择技能与研究标的] --> B[汇集可用行情和资料]
    B --> C[选择执行模式]
    C -->|单角色或专题技能| D[按技能框架生成分析]
    C -->|多角色研究| E1[段永平视角：商业模式]
    C -->|多角色研究| E2[巴菲特视角：财务估值]
    C -->|多角色研究| E3[芒格视角：竞争风险]
    C -->|多角色研究| E4[李录视角：长期趋势]
    E1 --> F[研究总监汇总]
    E2 --> F
    E3 --> F
    E4 --> F
    F --> G[生成 Markdown 报告]
    G --> H[本地归档复核]
```
"""
    extracted = extract_markdown_outline(md)
    assert extracted["source_summary"]["tagline"] == "把价值投资研究方法，变成一套可执行的工作流。"
    dag_scene = extracted["scene_graph"]["scenes"][1]
    assert dag_scene["layout"] == "flow_dag"
    grid_nodes = [n for n in dag_scene["nodes"] if n.get("child_layout") == "grid"]
    assert len(grid_nodes) == 1
    assert grid_nodes[0]["label"] == "多角色研究"
    assert len(grid_nodes[0]["children"]) == 4
    assert grid_nodes[0]["children"][0]["sublabel"] == "商业模式"

    report = audit_deck(extracted["scene_graph"], strict=True)
    assert report.passed is True
    assert report.errors == []
    assert report.warnings == []
    assert report.min_scale >= 0.72


def test_flow_dag_topological_sort_independent_of_node_order_and_rejects_cycles(tmp_path: Path) -> None:
    """DAG pacing and layout must follow edges even when downstream nodes appear first in JSON."""
    out_of_order_dag = {
        "title": "Out-of-order DAG",
        "scenes": [
            {
                "id": "dag",
                "title": "Reversed Nodes",
                "layout": "flow_dag",
                "nodes": [
                    {"id": "C", "label": "阶段 C"},
                    {"id": "B", "label": "阶段 B"},
                    {"id": "A", "label": "阶段 A"},
                ],
                "edges": [
                    {"id": "e1", "from": "A", "to": "B"},
                    {"id": "e2", "from": "B", "to": "C"},
                ],
            }
        ],
    }
    assert validate_deck(out_of_order_dag).valid is True

    paced = pace_deck(out_of_order_dag)
    frames = paced["scenes"][0]["frames"]
    assert [f["visible_nodes"] for f in frames] == [["A"], ["A", "B"], ["A", "B", "C"]]

    parsed = parse_deck(paced)
    resolved = resolve_scene(parsed.scenes[0], parsed.slide_width, parsed.slide_height)
    final_boxes = {b.id: b.rect for b in resolved[-1].boxes}
    assert final_boxes["A"].x < final_boxes["B"].x < final_boxes["C"].x

    cyclic_dag = {
        "title": "Cyclic DAG",
        "scenes": [
            {
                "id": "cyc",
                "title": "Has Cycle",
                "layout": "flow_dag",
                "nodes": [
                    {"id": "A", "label": "A"},
                    {"id": "B", "label": "B"},
                ],
                "edges": [
                    {"id": "e1", "from": "A", "to": "B"},
                    {"id": "e2", "from": "B", "to": "A"},
                ],
            }
        ],
    }
    val_cyc = validate_deck(cyclic_dag)
    assert val_cyc.valid is False
    assert any("cyclic dependencies" in err for err in val_cyc.errors)


def test_schema_handles_malformed_types_gracefully() -> None:
    """Malformed non-dict/non-numeric inputs from LLMs must yield clean ValidationResult errors, not exceptions."""
    bad_inputs = [
        [],
        {"title": 123, "theme": 456, "pinned_flow": "not_a_dict", "scenes": ["not_a_scene"]},
        {
            "title": "Bad Proportion & Matrix",
            "scenes": [
                {
                    "id": "s1",
                    "title": "Prop",
                    "layout": "proportion_bar",
                    "nodes": ["bad_node"],
                    "edges": ["bad_edge"],
                    "proportion_bar": {
                        "axis_min": "zero",
                        "axis_max": True,
                        "items": [{"id": "i1", "label": "L", "value": "NaN"}],
                    },
                },
                {
                    "id": "s2",
                    "title": "Matrix",
                    "layout": "comparison_matrix",
                    "matrix": {"columns": [{"id": "c1", "caption": "C", "rows": ["bad_row"]}]},
                    "frames": ["bad_frame"],
                },
            ],
        },
    ]
    for payload in bad_inputs:
        res = validate_deck(payload)  # type: ignore[arg-type]
        assert res.valid is False
        assert len(res.errors) >= 1


def test_export_slide_pngs_passes_paths_via_osascript_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure paths containing quotes/spaces are passed as argv rather than interpolated into AppleScript."""
    monkeypatch.setattr("keyflow.compiler.sys.platform", "darwin")
    monkeypatch.setattr("keyflow.compiler.shutil.which", lambda _: "/usr/bin/osascript")
    captured: dict[str, object] = {}

    def _fake_run(cmd: list[str], **kwargs: object) -> object:
        captured["cmd"] = cmd
        return type("Proc", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("keyflow.compiler.subprocess.run", _fake_run)
    keyx_file = tmp_path / 'tricky "quote" deck.keyx'
    keyx_file.write_bytes(b"zip")
    out_dir = tmp_path / 'out "png" dir'
    export_slide_pngs(keyx_file, out_dir)

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:2] == ["osascript", "-e"]
    assert "on run argv" in cmd[2]
    assert 'tricky "quote"' not in cmd[2]
    assert cmd[3] == str(keyx_file.resolve())
    assert cmd[4] == str(out_dir.resolve())


def test_audit_findings_include_target_id_and_suggested_action() -> None:
    """Findings must expose machine-readable target_id and suggested_action for Agent auto-fix loops."""
    deck = {
        "title": "Structured Hints",
        "scenes": [
            {
                "id": "s_overflow",
                "title": "Overflow Node",
                "layout": "horizontal_flow",
                "nodes": [
                    {"id": "long_node", "label": "这是一个特别特别特别长肯定会在窄卡片里折行溢出的节点标题名称"},
                    {"id": "short_node", "label": "短节点"},
                    {"id": "third_node", "label": "第三步"},
                    {"id": "fourth_node", "label": "第四步"},
                ],
                "edges": [],
            },
            {
                "id": "s_prop",
                "title": "Tiny Proportion",
                "layout": "proportion_bar",
                "proportion_bar": {
                    "axis_min": 0,
                    "axis_max": 100,
                    "items": [
                        {"id": "main", "label": "Main", "value": 99.6},
                        {"id": "tiny_seg", "label": "Tail", "value": 0.4},
                    ],
                },
            },
        ],
    }
    report = audit_deck(deck)
    overflow = [w for w in report.warnings if w.category == "text_overflow"]
    assert overflow and overflow[0].target_id == "long_node"
    assert overflow[0].suggested_action == "shorten_label"

    tiny = [w for w in report.warnings if w.category == "crowded_proportion"]
    assert tiny and tiny[0].target_id == "tiny_seg"
    assert tiny[0].suggested_action == "merge_small_segments"
    serialized = report.to_dict()
    assert serialized["warnings"][0]["suggested_action"]


def test_audit_extended_stability_checks_edges_charts_matrices_and_pinned_flow() -> None:
    """Cross-frame stability must cover edges, proportion bars, matrices, and pinned_flow transitions."""
    box_a = PlacedBox(id="a", label="A", rect=BoxRect(100, 200, 200, 100), kind="card", variant="primary")
    box_b = PlacedBox(id="b", label="B", rect=BoxRect(400, 200, 200, 100), kind="card", variant="primary")

    f0 = ResolvedFrame(
        scene_id="s1",
        frame_index=0,
        title="T",
        subtitle=None,
        title_rect=None,
        subtitle_rect=None,
        boxes=[box_a, box_b],
        edges=[PlacedEdge(id="e1", from_id="a", to_id="b", tail_center=(200, 250), head_center=(500, 250))],
        proportion_bar=PlacedProportionBar(
            axis_start=(100, 400),
            axis_end=(800, 400),
            ticks=[(100, "0"), (800, "100")],
            bar_y=360,
            bar_h=40,
            items=[
                PlacedProportionItem(
                    id="p1",
                    label="P1",
                    display_value="50%",
                    color_index=0,
                    visible=True,
                    seg_rect=BoxRect(100, 360, 350, 40),
                    label_rect=BoxRect(100, 300, 120, 36),
                    arrow_tail=(160, 336),
                    arrow_head=(160, 360),
                )
            ],
        ),
        comparison_matrix=PlacedComparisonMatrix(
            formula="Y = X",
            formula_rect=BoxRect(300, 240, 400, 60),
            columns=[
                PlacedMatrixColumn(
                    id="col1",
                    box_rect=BoxRect(200, 350, 300, 300),
                    caption="Col 1",
                    caption_rect=BoxRect(200, 660, 300, 40),
                    cells=[],
                )
            ],
        ),
        pinned_flow=PlacedPinnedFlow(
            nodes=[PlacedRibbonNode(id="r1", label="R1", rect=BoxRect(300, 460, 200, 100), is_active=True)],
            groups=[],
            edges=[],
            is_centered=True,
        ),
    )
    f1 = ResolvedFrame(
        scene_id="s1",
        frame_index=1,
        title="T",
        subtitle=None,
        title_rect=None,
        subtitle_rect=None,
        boxes=[box_a, box_b],
        edges=[PlacedEdge(id="e1", from_id="a", to_id="b", tail_center=(215, 250), head_center=(500, 250))],
        proportion_bar=PlacedProportionBar(
            axis_start=(100, 400),
            axis_end=(800, 400),
            ticks=[(100, "0"), (800, "100")],
            bar_y=360,
            bar_h=40,
            items=[
                PlacedProportionItem(
                    id="p1",
                    label="P1",
                    display_value="50%",
                    color_index=0,
                    visible=True,
                    seg_rect=BoxRect(120, 360, 350, 40),
                    label_rect=BoxRect(100, 300, 120, 36),
                    arrow_tail=(160, 336),
                    arrow_head=(160, 360),
                )
            ],
        ),
        comparison_matrix=PlacedComparisonMatrix(
            formula="Y = X",
            formula_rect=BoxRect(300, 240, 400, 60),
            columns=[
                PlacedMatrixColumn(
                    id="col1",
                    box_rect=BoxRect(212, 350, 300, 300),
                    caption="Col 1",
                    caption_rect=BoxRect(200, 660, 300, 40),
                    cells=[],
                )
            ],
        ),
        pinned_flow=PlacedPinnedFlow(
            nodes=[PlacedRibbonNode(id="r1", label="R1", rect=BoxRect(300, 64, 180, 80), is_active=True)],
            groups=[],
            edges=[],
            is_centered=False,
        ),
    )
    findings: list = []
    _audit_scene_anchor_stability([f0, f1], start_slide_num=1, findings=findings)
    targets = {f.target_id for f in findings}
    assert {"e1", "p1", "col1"}.issubset(targets)
    assert "r1" not in targets  # Intentional centered -> top-dock shrink passes cleanly

    # Cross-scene docked -> docked drift on pinned_flow must be flagged
    f2_docked_shifted = ResolvedFrame(
        scene_id="s2",
        frame_index=0,
        title="T2",
        subtitle=None,
        title_rect=None,
        subtitle_rect=None,
        pinned_flow=PlacedPinnedFlow(
            nodes=[PlacedRibbonNode(id="r1", label="R1", rect=BoxRect(320, 64, 180, 80), is_active=True)],
            groups=[],
            edges=[],
            is_centered=False,
        ),
    )
    cross_findings: list = []
    _audit_deck_pinned_flow_stability([f1, f2_docked_shifted], cross_findings)
    assert len(cross_findings) == 1
    assert cross_findings[0].category == "anchor_jitter"
    assert cross_findings[0].target_id == "r1"


def test_compile_audit_gate_blocks_cli_and_mcp_when_enabled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Compile quality gates (--fail-on-audit / --strict) must block bad decks while keeping default permissive."""
    # Deck with a pure warning (text_overflow) and a deck with a layout collision (out_of_bounds via cramped grid/long deck)
    warning_deck = {
        "title": "Warning Gate",
        "scenes": [
            {
                "id": "warn_scene",
                "title": "Warn",
                "layout": "horizontal_flow",
                "nodes": [
                    {"id": "w1", "label": "这是一个特别特别特别长肯定会在窄卡片里折行溢出的节点标题名称"},
                    {"id": "w2", "label": "短节点"},
                    {"id": "w3", "label": "第三步"},
                    {"id": "w4", "label": "第四步"},
                ],
                "edges": [],
            }
        ],
    }
    warn_json = tmp_path / "warn.json"
    warn_json.write_text(json.dumps(warning_deck, ensure_ascii=False), encoding="utf-8")

    # --fail-on-audit allows warnings-only decks (errors == 0), whereas --strict blocks warnings
    out_ok = tmp_path / "warn_ok.keyx"
    assert cli_main(["compile", "-i", str(warn_json), "-o", str(out_ok), "--fail-on-audit"]) == 0
    assert out_ok.exists()
    capsys.readouterr()

    out_strict = tmp_path / "warn_blocked.keyx"
    assert cli_main(["compile", "-i", str(warn_json), "-o", str(out_strict), "--strict"]) == 1
    assert not out_strict.exists()
    capsys.readouterr()

    # MCP compile_keyx respects strict=True / fail_on_audit=True
    mcp_blocked = dispatch_tool(
        "compile_keyx",
        {
            "storyboard": warning_deck,
            "output_path": str(tmp_path / "mcp_blocked.keyx"),
            "strict": True,
        },
    )
    assert mcp_blocked["compiled"] is False
    assert mcp_blocked["audit"]["passed"] is False
    assert not (tmp_path / "mcp_blocked.keyx").exists()

    # Deck with an audit error (out_of_bounds matrix extending past slide_size.height): fail_on_audit=True blocks compilation
    error_deck = {
        "title": "Error Gate",
        "slide_size": {"width": 1280, "height": 360},
        "scenes": [
            {
                "id": "oob",
                "title": "Too Tall Matrix",
                "layout": "comparison_matrix",
                "matrix": {
                    "columns": [
                        {
                            "id": "c1",
                            "caption": "C1",
                            "headers": ["Val"],
                            "rows": [{"chip": f"R{i}", "values": [str(i)]} for i in range(1, 6)],
                        }
                    ]
                },
            }
        ],
    }
    err_json = tmp_path / "err.json"
    err_json.write_text(json.dumps(error_deck, ensure_ascii=False), encoding="utf-8")
    out_cli_err = tmp_path / "cli_err.keyx"
    assert cli_main(["compile", "-i", str(err_json), "-o", str(out_cli_err), "--fail-on-audit"]) == 1
    assert not out_cli_err.exists()
    capsys.readouterr()

    mcp_err_blocked = dispatch_tool(
        "compile_keyx",
        {
            "storyboard": error_deck,
            "output_path": str(tmp_path / "mcp_err.keyx"),
            "fail_on_audit": True,
        },
    )
    assert mcp_err_blocked["compiled"] is False
    assert mcp_err_blocked["audit"]["error_count"] >= 1
    assert not (tmp_path / "mcp_err.keyx").exists()


def test_single_hero_metrics_card_paces_compiles_and_passes_strict_audit(tmp_path: Path) -> None:
    """Single-card hero metrics/thesis slides must render as generous centerpiece cards without audit warnings."""
    hero_deck = {
        "title": "Hero Stat",
        "scenes": [
            {
                "id": "hero",
                "title": "Core Thesis",
                "layout": "metrics_cards",
                "nodes": [
                    {
                        "id": "claim",
                        "badge": "THESIS",
                        "metric": "~75%",
                        "label": "Gross Margin Capture",
                        "sublabel": "Hypothesis to verify",
                        "variant": "accent",
                        "note": "Explicitly marked as thesis rather than settled fact.",
                    }
                ],
            }
        ],
    }
    report = audit_deck(hero_deck, strict=True)
    assert report.passed is True
    assert report.errors == []
    assert report.warnings == []

    parsed = parse_deck(pace_deck(hero_deck))
    frames = resolve_scene(parsed.scenes[0], parsed.slide_width, parsed.slide_height)
    assert len(frames) == 1
    assert frames[0].boxes[0].rect.w >= 520.0

    out = tmp_path / "hero.keyx"
    compile_deck(hero_deck, out)
    assert out.exists()


def test_master_layout_gradient_keeps_keyx_compact(tmp_path: Path) -> None:
    """Decks should share one vector Preset fill while keeping valid White theme metadata and compact .keyx size."""
    from creator_studio_doc_format.core import KeyxDocument

    out = tmp_path / "compact_showcase.keyx"
    raw = json.loads(Path("examples/genres_showcase_stage1.json").read_text(encoding="utf-8"))
    compile_deck(raw, out)
    assert out.stat().st_size < 50_000  # Previously ~10+ MB with per-slide base64 noise PNGs

    with KeyxDocument.open(out) as loaded:
        assert loaded.payload.theme is not None
        assert loaded.payload.theme.name == "White"
        assert loaded.payload.theme.slide_layouts is None
        bg_presets = [p for p in (loaded.presets or []) if p.identifier == "keyflow_bg_fill"]
        assert len(bg_presets) == 1
        assert "gradient" in bg_presets[0].properties
        for slide in loaded.payload.slides:
            bg = slide.background.get()
            assert bg is not None
            assert bg.standard is not None
            assert bg.standard.preset_identifier == "keyflow_bg_fill"

    with zipfile.ZipFile(out) as zf:
        main_json = zf.read("main.json").decode("utf-8")
        assert "base64_encoded" not in main_json


def test_outline_strips_yaml_frontmatter_before_tagline() -> None:
    """Obsidian/Hugo YAML frontmatter (`--- ... ---`) must never leak into tagline or intro_note."""
    md = """---
tags:
  - research/ai
status: draft
---

# 猎鹰9号谢幕倒计时

## 核心规模
- **高频复用**：单枚最高 36 次
"""
    extracted = extract_markdown_outline(md)
    assert extracted["source_summary"]["title"] == "猎鹰9号谢幕倒计时"
    assert extracted["source_summary"]["tagline"] == ""
    assert extracted["scene_graph"]["scenes"][0]["intro_note"] == "Overview of 猎鹰9号谢幕倒计时."


def test_mcp_pace_storyboard_failure_and_workspace_root_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pace_storyboard must report failures accurately, and workspace_root must block escaping paths."""
    valid_stage1 = _agent_skill_stage1()
    bad_paced = {"title": "Broken", "scenes": [{"id": "s1", "title": "S1", "nodes": [{"id": "n1", "label": "N1"}], "frames": [{"visible_nodes": ["missing_id"], "notes": "x"}]}]}
    monkeypatch.setattr("keyflow.mcp_server.pace_deck", lambda *_, **__: bad_paced)

    blocked_out = tmp_path / "should_not_exist.json"
    res = dispatch_tool("pace_storyboard", {"storyboard": valid_stage1, "output_path": str(blocked_out)})
    assert res["paced"] is False
    assert not blocked_out.exists()

    rpc_res = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "pace_storyboard", "arguments": {"storyboard": valid_stage1}},
        }
    )
    assert rpc_res is not None
    assert rpc_res["result"]["isError"] is True

    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside allowed workspace root"):
        dispatch_tool("validate_storyboard", {"input_path": str(outside)}, workspace_root=ws)

    monkeypatch.setenv("KEYFLOW_MCP_WORKSPACE", str(ws))
    with pytest.raises(ValueError, match="outside allowed workspace root"):
        dispatch_tool(
            "compile_keyx",
            {"storyboard": valid_stage1, "output_path": str(tmp_path / "escape.keyx")},
        )

    inside_out = ws / "ok.keyx"
    ok = dispatch_tool("compile_keyx", {"storyboard": valid_stage1, "output_path": str(inside_out)})
    assert ok["compiled"] is True
    assert inside_out.exists()


def test_schema_rejects_unknown_properties_and_matches_deck_schema_json() -> None:
    """validate_deck must enforce additionalProperties=false aligned with schemas/deck.schema.json."""
    from keyflow.schema import _schema_key_sets

    key_sets = _schema_key_sets()
    assert {"deck", "story_model", "story_claim", "scene", "node", "frame"}.issubset(key_sets)
    assert Path("keyflow/deck.schema.json").read_text(encoding="utf-8") == Path("schemas/deck.schema.json").read_text(encoding="utf-8")

    bad_deck = {
        "title": "Typo Check",
        "typo_root": True,
        "scenes": [
            {
                "id": "s1",
                "title": "S1",
                "typo_scene": 1,
                "nodes": [{"id": "n1", "label": "Node", "typo_node": "x"}],
                "frames": [{"visible_nodes": ["n1"], "notes": "ok", "typo_frame": 1}],
            }
        ],
    }
    res = validate_deck(bad_deck)
    assert res.valid is False
    joined = "\n".join(res.errors)
    assert "typo_root" in joined
    assert "typo_scene" in joined
    assert "typo_node" in joined
    assert "typo_frame" in joined


def test_story_model_validation_and_fidelity_audit_checks(tmp_path: Path) -> None:
    """Structured story_model + evidence_refs must validate cleanly and catch epistemic/scope violations."""
    good_deck = {
        "title": "Story Grounded Deck",
        "story_model": {
            "core_question": "Is capacity shifting internally?",
            "claims": [
                {
                    "id": "fact_share",
                    "type": "fact",
                    "claim": "Internal missions reached 79%.",
                    "source_quote": "Internal share reached 79% in 2026.",
                    "metric_scope": "launch_count_share_pct",
                    "confidence": "high",
                },
                {
                    "id": "inf_squeeze",
                    "type": "inference",
                    "claim": "External slots tighten as internal share rises.",
                    "confidence": "medium",
                },
                {
                    "id": "counter_gov",
                    "type": "counter_evidence",
                    "claim": "Long-term government contracts continue past 2028.",
                    "source_quote": "Government missions continue through 2030.",
                },
            ],
        },
        "scenes": [
            {
                "id": "share_scene",
                "title": "Internal Share",
                "claim": "Internal missions dominate launches.",
                "metric_scope": "launch_count_share_pct",
                "evidence_refs": ["fact_share"],
                "layout": "proportion_bar",
                "proportion_bar": {
                    "items": [
                        {"id": "int", "label": "Internal", "value": 79, "evidence_refs": ["fact_share"]},
                        {"id": "ext", "label": "External", "value": 21},
                    ]
                },
            },
            {
                "id": "logic_scene",
                "title": "Strategic Shift",
                "layout": "horizontal_flow",
                "nodes": [
                    {"id": "n1", "badge": "FACT", "label": "79% Internal", "evidence_refs": ["fact_share"]},
                    {"id": "n2", "badge": "INFERENCE", "label": "Slots Tighten", "evidence_refs": ["inf_squeeze"]},
                    {"id": "n3", "badge": "FACT", "label": "Gov Continues", "evidence_refs": ["counter_gov"]},
                ],
                "edges": [
                    {"id": "e1", "from": "n1", "to": "n2"},
                    {"id": "e2", "from": "n2", "to": "n3"},
                ],
            },
        ],
    }
    assert validate_deck(good_deck).valid is True
    clean_report = audit_deck(good_deck, strict=True)
    assert clean_report.passed is True
    assert clean_report.errors == []
    assert clean_report.warnings == []

    out = tmp_path / "story_model.keyx"
    compile_deck(good_deck, out)
    assert out.exists()

    # Now introduce 4 fidelity flaws: epistemic mismatch, unsourced fact, scope mixing, and dropped counter_evidence
    flawed = json.loads(json.dumps(good_deck))
    flawed["story_model"]["claims"].append(
        {"id": "fact_rev", "type": "fact", "claim": "Revenue share is 61%.", "metric_scope": "total_revenue_pct"}
    )
    flawed["scenes"][0]["proportion_bar"]["items"][1]["evidence_refs"] = ["fact_rev"]
    flawed["scenes"][1]["nodes"][1]["badge"] = "FACT"  # Mismatch: inf_squeeze is type='inference'
    flawed["scenes"][1]["nodes"][2]["evidence_refs"] = []  # Dropped counter_gov

    flawed_report = audit_deck(flawed)
    err_cats = {e.category for e in flawed_report.errors}
    warn_cats = {w.category for w in flawed_report.warnings}
    assert "epistemic_mismatch" in err_cats
    assert {"scope_mixing", "unsourced_fact", "dropped_story_claim"}.issubset(warn_cats)

    # Unknown evidence_refs must fail schema validation
    flawed["scenes"][0]["evidence_refs"] = ["missing_claim_id"]
    bad_val = validate_deck(flawed)
    assert bad_val.valid is False
    assert any("missing_claim_id" in e for e in bad_val.errors)


def _freeform_canvas_stage1() -> dict:
    return {
        "title": "Freeform Canvas & Native Chart/Table Demo",
        "palette": {
            "bg_hex": "#1B2230",
            "bg_gradient_end_hex": "#111622",
            "title_hex": "#F5D76E",
            "text_hex": "#FFFFFF",
            "series_colors": ["#F5D76E", "#4ECDC4", "#FF6B6B"],
        },
        "story_model": {
            "core_question": "How do illustrative examples and real metrics coexist cleanly?",
            "claims": [
                {
                    "id": "fact_latency",
                    "type": "fact",
                    "claim": "Compiler latency dropped from 7.0s to 0.7s.",
                    "source_quote": "Compile latency dropped from 7.0s to 0.7s.",
                    "metric_scope": "compile_seconds",
                },
                {
                    "id": "ex_alloc",
                    "type": "example",
                    "claim": "Illustrative token allocation split across 3 buckets.",
                    "metric_scope": "illustrative_pct",
                },
                {
                    "id": "ex_latency_note",
                    "type": "example",
                    "claim": "Illustrative breakdown of parse vs layout latency.",
                    "metric_scope": "compile_seconds",
                },
            ],
        },
        "scenes": [
            {
                "id": "chart_and_table",
                "title": "Latency & Allocation Overview",
                "source_section": "Section 2: Performance",
                "grid": {"columns": 12, "rows": 2, "gap": 24},
                "regions": [
                    {"id": "left", "col": 1, "row": 1, "col_span": 7, "row_span": 2, "frame": True, "title": "Native Chart"},
                    {"id": "right_top", "col": 8, "row": 1, "col_span": 5, "row_span": 1, "arrange": "stack"},
                    {"id": "right_bot", "col": 8, "row": 2, "col_span": 5, "row_span": 1, "arrange": "row"},
                ],
                "objects": [
                    {
                        "id": "latency_col",
                        "kind": "chart",
                        "region": "left",
                        "step": 1,
                        "note": "对比优化前后的延迟变化。",
                        "evidence_refs": ["fact_latency"],
                        "chart": {
                            "chart_type": "column",
                            "title": "Latency (s)",
                            "unit": "s",
                            "categories": ["Parse", "Layout", "Save"],
                            "series": [
                                {"name": "Before", "values": [2.1, 3.4, 1.5]},
                                {"name": "After", "values": [0.2, 0.3, 0.2]},
                            ],
                            "reveal": "by_series",
                        },
                    },
                    {
                        "id": "perf_tbl",
                        "kind": "table",
                        "region": "right_top",
                        "step": 2,
                        "note": "关键指标对照表。",
                        "table": {
                            "title": "Benchmarks",
                            "headers": ["Metric", "Before", "After"],
                            "rows": [
                                ["Latency", "7.0s", "0.7s"],
                                ["Size", "20 MB", "20 KB"],
                            ],
                            "highlight_cols": [2],
                            "reveal": "by_row",
                        },
                    },
                    {
                        "id": "hero_kpi",
                        "kind": "callout",
                        "region": "right_bot",
                        "step": 3,
                        "badge": "FACT",
                        "metric": "10x",
                        "label": "Faster Compile",
                        "evidence_refs": ["fact_latency"],
                        "note": "实证提速 10 倍。",
                    },
                    {
                        "id": "ex_badge_card",
                        "kind": "card",
                        "region": "right_bot",
                        "step": 3,
                        "badge": "EXAMPLE",
                        "label": "Sample Breakdown",
                        "sublabel": "Illustrative",
                        "evidence_refs": ["ex_latency_note"],
                        "note": "示意算例说明。",
                    },
                ],
                "connectors": [
                    {"id": "c1", "from": "latency_col", "to": "perf_tbl", "style": "dashed"}
                ],
            },
            {
                "id": "pie_and_diagram",
                "title": "Share & Inline Flow",
                "grid": {"columns": 12, "rows": 1, "gap": 24},
                "regions": [
                    {"id": "pie_zone", "col": 1, "row": 1, "col_span": 5, "row_span": 1},
                    {"id": "flow_zone", "col": 6, "row": 1, "col_span": 7, "row_span": 1},
                ],
                "objects": [
                    {
                        "id": "share_pie",
                        "kind": "chart",
                        "region": "pie_zone",
                        "step": 1,
                        "evidence_refs": ["ex_alloc"],
                        "note": "示意占比分布。",
                        "chart": {
                            "chart_type": "donut",
                            "title": "Token Split",
                            "categories": ["Context", "Code", "Tests"],
                            "series": [{"name": "Share", "values": [50, 30, 20]}],
                        },
                    },
                    {
                        "id": "mini_flow",
                        "kind": "diagram",
                        "region": "flow_zone",
                        "step": 2,
                        "note": "局部逻辑流程。",
                        "diagram": {
                            "diagram_layout": "horizontal",
                            "nodes": [
                                {"id": "a", "label": "Read"},
                                {"id": "b", "label": "Solve"},
                                {"id": "c", "label": "Emit", "variant": "success"},
                            ],
                            "edges": [
                                {"id": "de1", "from": "a", "to": "b"},
                                {"id": "de2", "from": "b", "to": "c"},
                            ],
                        },
                    },
                ],
            },
        ],
    }


def test_use_templates_switch_defaults_false_and_enforces_true() -> None:
    canvas_deck = _freeform_canvas_stage1()
    # Default (use_templates omitted -> false) permits freeform canvas + palette
    val_free = validate_deck(canvas_deck)
    assert val_free.valid is True, val_free.errors

    # Explicitly enabling template-only mode rejects freeform canvas & palette
    val_locked = validate_deck(canvas_deck, use_templates=True)
    assert val_locked.valid is False
    joined = "\n".join(val_locked.errors)
    assert "use_templates=true" in joined

    # Legacy preset deck continues to pass in both modes
    assert validate_deck(_agent_skill_stage1(), use_templates=True).valid is True
    assert validate_deck(_agent_skill_stage1(), use_templates=False).valid is True


def test_freeform_canvas_paces_compiles_native_charts_and_tables(tmp_path: Path) -> None:
    from creator_studio_doc_format.core import KeyxDocument

    raw = _freeform_canvas_stage1()
    paced = pace_deck(raw)
    s0_frames = paced["scenes"][0]["frames"]
    # step1 by_series (2 frames) + step2 by_row (2 frames) + step3 (1 frame) = 5 frames (no auto-dim/summary frame)
    assert len(s0_frames) == 5
    assert s0_frames[0]["object_states"]["latency_col"]["series_count"] == 1
    assert s0_frames[1]["object_states"]["latency_col"]["series_count"] == 2
    assert s0_frames[2]["object_states"]["perf_tbl"]["row_count"] == 1
    assert s0_frames[3]["object_states"]["perf_tbl"]["row_count"] == 2

    # Scene 1: step1 donut (1 frame) + step2 3-node diagram decomposed node-by-node (3 frames) = 4 frames
    s1_frames = paced["scenes"][1]["frames"]
    assert len(s1_frames) == 4
    assert s1_frames[1]["object_states"]["mini_flow"]["visible_nodes"] == ["a"]
    assert s1_frames[2]["object_states"]["mini_flow"]["visible_nodes"] == ["a", "b"]
    assert s1_frames[3]["object_states"]["mini_flow"]["visible_nodes"] == ["a", "b", "c"]

    # Audit passes strictly with zero errors or warnings
    report = audit_deck(paced, strict=True)
    assert report.passed is True, [e.to_dict() for e in report.errors]
    assert report.errors == []
    assert report.warnings == []

    # Axis bounds, coordinates, and full series slots must stay locked across progressive frames
    parsed = parse_deck(paced)
    resolved_s0 = resolve_scene(parsed.scenes[0], parsed.slide_width, parsed.slide_height)
    assert resolved_s0[0].charts[0].rect == resolved_s0[1].charts[0].rect
    assert resolved_s0[0].charts[0].axis_min == resolved_s0[1].charts[0].axis_min
    assert resolved_s0[0].charts[0].axis_max == resolved_s0[1].charts[0].axis_max
    assert len(resolved_s0[0].charts[0].series) == len(resolved_s0[1].charts[0].series) == 2
    assert resolved_s0[0].charts[0].use_vector is True
    assert resolved_s0[2].tables[0].rect == resolved_s0[3].tables[0].rect

    # Inline diagram nodes keep locked coordinates across progressive frames
    resolved_s1 = resolve_scene(parsed.scenes[1], parsed.slide_width, parsed.slide_height)
    assert len(resolved_s1[1].boxes) == 1
    assert len(resolved_s1[2].boxes) == 2
    assert resolved_s1[1].boxes[0].rect == resolved_s1[3].boxes[0].rect

    # Compile to .keyx and verify pure Shape vector chart (for progressive) + native Table/DonutChart
    out = tmp_path / "freeform_loop.keyx"
    compile_deck(raw, out)
    assert out.exists()

    with KeyxDocument.open(out) as loaded:
        slides = loaded.payload.slides
        assert len(slides) == 9  # 5 frames (scene 0) + 4 frames (scene 1)
        # First slide compiles progressive by_series chart as pure Shape vectors (exact locked bar widths)
        first_charts = [obj.object.chart for obj in slides[0].contents if obj.object.chart is not None]
        assert first_charts == []
        s1_bars = {
            obj.object.shape.identifier.removeprefix("s1_"): obj.object.shape.geometry
            for obj in slides[0].contents
            if obj.object.shape is not None and "_latency_col_c_0_" in obj.object.shape.identifier
        }
        s2_bars = {
            obj.object.shape.identifier.removeprefix("s2_"): obj.object.shape.geometry
            for obj in slides[1].contents
            if obj.object.shape is not None and "_latency_col_c_0_" in obj.object.shape.identifier
        }
        assert len(s1_bars) == 3 and set(s1_bars) == set(s2_bars)
        for bid in s1_bars:
            assert s1_bars[bid].size.width == pytest.approx(s2_bars[bid].size.width, abs=0.01)
            assert s1_bars[bid].size.height == pytest.approx(s2_bars[bid].size.height, abs=0.01)
            assert s1_bars[bid].position.x == pytest.approx(s2_bars[bid].position.x, abs=0.01)
            assert s1_bars[bid].position.y == pytest.approx(s2_bars[bid].position.y, abs=0.01)
        # Fourth slide has native Table
        fourth_tables = [obj.object.table for obj in slides[3].contents if obj.object.table is not None]
        assert len(fourth_tables) == 1
        assert fourth_tables[0].number_of_columns == 3
        assert fourth_tables[0].number_of_rows == 3
        # Sixth slide (scene 1 frame 0, reveal=whole) keeps native DonutChart
        donut_charts = [obj.object.chart for obj in slides[5].contents if obj.object.chart is not None]
        assert len(donut_charts) == 1 and donut_charts[0].donut is not None


def test_vector_chart_modes_and_native_override(tmp_path: Path) -> None:
    from creator_studio_doc_format.core import KeyxDocument

    raw = {
        "title": "Vector & Native Chart Modes",
        "scenes": [
            {
                "id": "vec_test",
                "title": "Progressive Vector Charts + Native Override",
                "grid": {"columns": 12, "rows": 2, "gap": 24},
                "regions": [
                    {"id": "tl", "col": 1, "row": 1, "col_span": 6, "row_span": 1},
                    {"id": "tr", "col": 7, "row": 1, "col_span": 6, "row_span": 1},
                    {"id": "bl", "col": 1, "row": 2, "col_span": 6, "row_span": 1},
                    {"id": "br", "col": 7, "row": 2, "col_span": 6, "row_span": 1},
                ],
                "objects": [
                    {
                        "id": "v_area",
                        "kind": "chart",
                        "region": "tl",
                        "step": 1,
                        "chart": {
                            "chart_type": "area",
                            "categories": ["Q1", "Q2", "Q3"],
                            "series": [{"name": "Revenue", "values": [10, 25, 42]}],
                            "reveal": "by_category",
                        },
                    },
                    {
                        "id": "v_donut",
                        "kind": "chart",
                        "region": "tr",
                        "step": 2,
                        "chart": {
                            "chart_type": "donut",
                            "categories": ["A", "B", "C"],
                            "series": [{"name": "Share", "values": [50, 30, 20]}],
                            "reveal": "by_category",
                        },
                    },
                    {
                        "id": "v_bar_forced",
                        "kind": "chart",
                        "region": "bl",
                        "step": 2,
                        "chart": {
                            "chart_type": "bar",
                            "categories": ["Item 1", "Item 2"],
                            "series": [{"name": "Score", "values": [80, 95]}],
                            "render_mode": "vector",
                        },
                    },
                    {
                        "id": "native_forced",
                        "kind": "chart",
                        "region": "br",
                        "step": 3,
                        "chart": {
                            "chart_type": "column",
                            "categories": ["C1", "C2"],
                            "series": [{"name": "S1", "values": [10, 20]}, {"name": "S2", "values": [15, 25]}],
                            "reveal": "by_series",
                            "render_mode": "native",
                        },
                    },
                ],
            }
        ],
    }
    assert validate_deck(raw).valid is True
    assert audit_deck(raw, strict=True).passed is True
    out = tmp_path / "vector_modes.keyx"
    compile_deck(raw, out)
    with KeyxDocument.open(out) as loaded:
        slides = loaded.payload.slides
        assert len(slides) >= 6
        # Last slide contains native_forced rendered as a native ColumnChart
        last_native_charts = [obj.object.chart for obj in slides[-1].contents if obj.object.chart is not None]
        assert len(last_native_charts) == 1 and last_native_charts[0].column is not None


def test_freeform_all_native_chart_types_and_shapes_compile(tmp_path: Path) -> None:
    raw = {
        "title": "All Native Primitives",
        "scenes": [
            {
                "id": "all_objs",
                "title": "Shapes, Text, and Charts",
                "grid": {"columns": 12, "rows": 2, "gap": 24},
                "regions": [
                    {"id": "r1", "col": 1, "row": 1, "col_span": 4, "row_span": 1},
                    {"id": "r2", "col": 5, "row": 1, "col_span": 4, "row_span": 1},
                    {"id": "r3", "col": 9, "row": 1, "col_span": 4, "row_span": 1},
                    {"id": "r4", "col": 1, "row": 2, "col_span": 6, "row_span": 1, "arrange": "row"},
                    {"id": "r5", "col": 7, "row": 2, "col_span": 6, "row_span": 1},
                ],
                "objects": [
                    {
                        "id": "c_bar",
                        "kind": "chart",
                        "region": "r1",
                        "chart": {
                            "chart_type": "stacked_bar",
                            "categories": ["Q1", "Q2"],
                            "series": [{"name": "A", "values": [30, 45]}, {"name": "B", "values": [70, 55]}],
                            "reveal": "by_category",
                        },
                    },
                    {
                        "id": "c_line",
                        "kind": "chart",
                        "region": "r2",
                        "chart": {
                            "chart_type": "line",
                            "categories": ["W1", "W2", "W3"],
                            "series": [{"name": "Trend", "values": [12, 25, 41]}],
                        },
                    },
                    {
                        "id": "c_pie",
                        "kind": "chart",
                        "region": "r3",
                        "chart": {
                            "chart_type": "pie",
                            "categories": ["Alpha", "Beta"],
                            "series": [{"name": "Mix", "values": [65, 35]}],
                        },
                    },
                    {
                        "id": "sh_ellipse",
                        "kind": "shape",
                        "region": "r4",
                        "shape_type": "ellipse",
                        "label": "Core",
                    },
                    {
                        "id": "sh_custom",
                        "kind": "shape",
                        "region": "r4",
                        "shape_type": "custom",
                        "svg_path": "M 0,0.5 L 0.5,0 L 1,0.5 L 0.5,1 Z",
                        "label": "Gate",
                    },
                    {
                        "id": "tb_note",
                        "kind": "textbox",
                        "region": "r5",
                        "text": "Freeform summary block",
                        "align": "left",
                        "font_size": 26,
                    },
                ],
            }
        ],
    }
    assert validate_deck(raw).valid is True
    assert audit_deck(raw, strict=True).passed is True
    out = tmp_path / "all_primitives.keyx"
    compile_deck(raw, out)
    assert out.exists()


def test_freeform_audit_catches_contrast_bad_pie_and_example_as_fact() -> None:
    bad = _freeform_canvas_stage1()
    # 1) Contrast violation: dark text on dark fill
    bad["scenes"][0]["objects"][3]["fill_hex"] = "#1A1A1A"
    bad["scenes"][0]["objects"][3]["color_hex"] = "#222222"
    # 2) Epistemic mismatch: FACT badge referencing example claim
    bad["scenes"][0]["objects"][3]["badge"] = "FACT"
    # 3) Negative slice in donut chart
    bad["scenes"][1]["objects"][0]["chart"]["series"][0]["values"] = [50, -10, 60]

    report = audit_deck(bad)
    err_cats = {e.category for e in report.errors}
    assert {"low_contrast", "epistemic_mismatch", "invalid_chart_data"}.issubset(err_cats)

    # 4) Overlapping grid regions caught by schema validation
    overlap_deck = _freeform_canvas_stage1()
    overlap_deck["scenes"][0]["regions"][1]["col"] = 6
    val = validate_deck(overlap_deck)
    assert val.valid is False
    assert any("overlaps grid cell" in err for err in val.errors)


def test_cli_and_mcp_use_templates_switch_and_freeform_compile(tmp_path: Path) -> None:
    raw = _freeform_canvas_stage1()
    stage1_path = tmp_path / "freeform.json"
    out_keyx = tmp_path / "freeform.keyx"
    stage1_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    # Default CLI validate allows freeform
    assert cli_main(["validate", "-i", str(stage1_path)]) == 0
    # Strict --use-templates rejects freeform
    assert cli_main(["validate", "-i", str(stage1_path), "--use-templates"]) == 1
    # Default CLI compile succeeds with audit gate
    assert cli_main(["compile", "-i", str(stage1_path), "-o", str(out_keyx), "--fail-on-audit"]) == 0
    assert out_keyx.exists()

    # MCP dispatch supports use_templates switch
    mcp_locked = dispatch_tool("validate_storyboard", {"storyboard": raw, "use_templates": True})
    assert mcp_locked["valid"] is False
    mcp_out = tmp_path / "mcp_freeform.keyx"
    mcp_ok = dispatch_tool("compile_keyx", {"storyboard": raw, "output_path": str(mcp_out), "fail_on_audit": True})
    assert mcp_ok["compiled"] is True
    assert mcp_ok["audit"]["passed"] is True
    assert mcp_out.exists()


def test_canvas_schema_rejects_malformed_types_bounds_and_refs() -> None:
    import math

    # 1. Float step, bad weight, out-of-range font_size, float grid/region coords
    bad1 = _freeform_canvas_stage1()
    bad1["scenes"][0]["grid"]["columns"] = 12.5
    bad1["scenes"][0]["regions"][0]["col"] = 1.5
    bad1["scenes"][0]["objects"][0]["step"] = 1.5
    bad1["scenes"][0]["objects"][0]["weight"] = "heavy"
    bad1["scenes"][0]["objects"][3]["font_size"] = 220
    res1 = validate_deck(bad1)
    assert res1.valid is False
    joined1 = "\n".join(res1.errors)
    assert "grid.columns" in joined1
    assert "col, row, col_span, and row_span must be integers" in joined1
    assert "'step' must be a non-negative integer" in joined1
    assert ".weight: must be a finite number >= 0.1" in joined1
    assert ".font_size: must be a finite number in [10, 140]" in joined1

    # 2. Chart NaN/Inf values, axis_min >= axis_max, and out-of-range table highlight indices
    bad2 = _freeform_canvas_stage1()
    bad2["scenes"][0]["objects"][0]["chart"]["series"][0]["values"] = [10, math.nan, 30]
    bad2["scenes"][0]["objects"][0]["chart"]["axis_min"] = 50
    bad2["scenes"][0]["objects"][0]["chart"]["axis_max"] = 10
    bad2["scenes"][0]["objects"][1]["table"]["highlight_cols"] = [9]
    bad2["scenes"][0]["objects"][1]["table"]["highlight_rows"] = [-1]
    res2 = validate_deck(bad2)
    assert res2.valid is False
    joined2 = "\n".join(res2.errors)
    assert "all values must be numeric" in joined2
    assert "axis_min (50.0) must be < axis_max (10.0)" in joined2
    assert "highlight_cols" in joined2
    assert "highlight_rows" in joined2

    # 3. Unknown diagram node/edge ids inside frames[].object_states
    bad3 = _freeform_canvas_stage1()
    bad3["scenes"][1]["frames"] = [
        {
            "visible_objects": ["mix_donut", "mini_flow"],
            "object_states": {
                "mini_flow": {
                    "visible_nodes": ["a", "ghost_node"],
                    "visible_edges": ["ghost_edge"],
                }
            },
            "notes": "Bad inline diagram state",
        }
    ]
    res3 = validate_deck(bad3)
    assert res3.valid is False
    joined3 = "\n".join(res3.errors)
    assert "unknown diagram node 'ghost_node'" in joined3
    assert "unknown diagram edge 'ghost_edge'" in joined3


def test_freeform_builtin_example_compiles_with_locked_bars_and_native_chart(tmp_path: Path) -> None:
    from creator_studio_doc_format.core import KeyxDocument

    raw = json.loads(Path("examples/freeform_canvas_stage1.json").read_text(encoding="utf-8"))
    assert validate_deck(raw).valid is True
    paced = pace_deck(raw)
    rep = audit_deck(paced, strict=True)
    assert rep.passed is True, [e.to_dict() for e in rep.errors]

    out = tmp_path / "builtin_freeform.keyx"
    compile_deck(paced, out)
    with KeyxDocument.open(out) as loaded:
        slides = loaded.payload.slides
        assert len(slides) == 9  # 5 frames scene 0 + 4 frames scene 1
        # Progressive vector bars on slides 1 & 2 keep exact locked width
        s1_bars = {
            obj.object.shape.identifier.removeprefix("s1_"): obj.object.shape.geometry
            for obj in slides[0].contents
            if obj.object.shape is not None and "_compile_col_c_0_" in obj.object.shape.identifier
        }
        s2_bars = {
            obj.object.shape.identifier.removeprefix("s2_"): obj.object.shape.geometry
            for obj in slides[1].contents
            if obj.object.shape is not None and "_compile_col_c_0_" in obj.object.shape.identifier
        }
        assert len(s1_bars) == 3 and set(s1_bars) == set(s2_bars)
        for bid in s1_bars:
            assert s1_bars[bid].size.width == pytest.approx(s2_bars[bid].size.width, abs=0.01)
            assert s1_bars[bid].position.x == pytest.approx(s2_bars[bid].position.x, abs=0.01)
        # Native DonutChart preserved on slide 6 (scene 1 frame 0)
        donut_charts = [obj.object.chart for obj in slides[5].contents if obj.object.chart is not None]
        assert len(donut_charts) == 1 and donut_charts[0].donut is not None


@pytest.mark.parametrize("bad_val", [["accent"], {"bad": 1}, None, True, 123])
def test_schema_rejects_unhashable_or_non_string_enum_and_ref_values(bad_val: object) -> None:
    # Canvas enum + ref fields
    deck1 = _freeform_canvas_stage1()
    deck1["scenes"][0]["regions"][0]["arrange"] = bad_val
    deck1["scenes"][0]["objects"][0]["variant"] = bad_val
    deck1["scenes"][0]["objects"][0]["chart"]["chart_type"] = bad_val
    deck1["scenes"][0]["objects"][0]["chart"]["reveal"] = bad_val
    deck1["scenes"][0]["objects"][0]["chart"]["render_mode"] = bad_val
    deck1["scenes"][0]["objects"][1]["table"]["reveal"] = bad_val
    deck1["scenes"][0]["objects"][3]["align"] = bad_val
    res1 = validate_deck(deck1)
    assert res1.valid is False
    assert len(res1.errors) >= 6

    # Inline diagram + shape + node/edge ref fields
    deck2 = _freeform_canvas_stage1()
    deck2["scenes"][1]["objects"][1]["diagram"]["diagram_layout"] = bad_val
    deck2["scenes"][1]["objects"][1]["diagram"]["nodes"][0]["variant"] = bad_val
    deck2["scenes"][1]["objects"][1]["diagram"]["nodes"][0]["child_layout"] = bad_val
    deck2["scenes"][1]["objects"][1]["diagram"]["edges"][0]["from"] = bad_val
    deck2["scenes"][0]["objects"].append(
        {"id": "sh_bad", "kind": "shape", "region": "main_right", "shape_type": bad_val}
    )
    res2 = validate_deck(deck2)
    assert res2.valid is False
    assert len(res2.errors) >= 4


# ---------------------------------------------------------------------------
# P1-A: Magic Move cross-frame geometry regression harness
# ---------------------------------------------------------------------------

def _assert_magic_move_stable(slides: list, *, tol: float = 0.01, skip_last: int = 1) -> None:
    """Assert all persistent Shape objects have identical geometry on consecutive slides.

    For every pair of consecutive slides (i, i+1), collect all Shape objects by their
    canonical identifier (stripping the ``s{n}_`` slide prefix).  For identifiers
    present on *both* slides assert that position x/y, size width/height, fill RGBA,
    and path string are equal within *tol*.  This verifies that Magic Move can smoothly
    animate between frames rather than dissolving or jumping.
    """
    def _shape_map(slide, slide_idx: int) -> dict[str, tuple]:
        prefix = f"s{slide_idx + 1}_"
        result: dict[str, tuple] = {}
        for obj in slide.contents:
            sh = obj.object.shape
            if sh is None or not sh.identifier:
                continue
            ident = sh.identifier.removeprefix(prefix)
            fill_sig = str(sh.fill) if sh.fill is not None else None
            path_sig = str(sh.path) if sh.path is not None else None
            result[ident] = (sh.geometry.position, sh.geometry.size, fill_sig, path_sig)
        return result

    limit = len(slides) - 1 if skip_last <= 1 else max(0, len(slides) - skip_last)
    for slide_i in range(limit):
        map_a = _shape_map(slides[slide_i], slide_i)
        map_b = _shape_map(slides[slide_i + 1], slide_i + 1)
        shared = set(map_a) & set(map_b)
        for ident in shared:
            pos_a, sz_a, fill_a, path_a = map_a[ident]
            pos_b, sz_b, fill_b, path_b = map_b[ident]
            assert pos_a.x == pytest.approx(pos_b.x, abs=tol), (
                f"Magic Move jitter: '{ident}' x changed {pos_a.x:.2f} -> {pos_b.x:.2f} between slides {slide_i + 1}->{slide_i + 2}"
            )
            assert pos_a.y == pytest.approx(pos_b.y, abs=tol), (
                f"Magic Move jitter: '{ident}' y changed {pos_a.y:.2f} -> {pos_b.y:.2f} between slides {slide_i + 1}->{slide_i + 2}"
            )
            assert sz_a.width == pytest.approx(sz_b.width, abs=tol), (
                f"Magic Move jitter: '{ident}' width changed {sz_a.width:.2f} -> {sz_b.width:.2f} between slides {slide_i + 1}->{slide_i + 2}"
            )
            assert sz_a.height == pytest.approx(sz_b.height, abs=tol), (
                f"Magic Move jitter: '{ident}' height changed {sz_a.height:.2f} -> {sz_b.height:.2f} between slides {slide_i + 1}->{slide_i + 2}"
            )
            assert fill_a == fill_b, (
                f"Magic Move fill changed for '{ident}' between slides {slide_i + 1}->{slide_i + 2}"
            )
            assert path_a == path_b, (
                f"Magic Move path changed for '{ident}' between slides {slide_i + 1}->{slide_i + 2}"
            )


def test_magic_move_stable_on_freeform_canvas(tmp_path: Path) -> None:
    """P1-A: Persistent canvas objects must not jitter in position/size between consecutive frames."""
    from creator_studio_doc_format.core import KeyxDocument

    raw = _freeform_canvas_stage1()
    out = tmp_path / "p1a_mm.keyx"
    compile_deck(raw, out)
    assert out.exists()

    with KeyxDocument.open(out) as loaded:
        slides = list(loaded.payload.slides)
    assert len(slides) >= 2, "Need at least 2 slides to test Magic Move stability"
    _assert_magic_move_stable(slides)


@pytest.mark.parametrize("reveal", ["whole", "by_series", "by_category"])
def test_magic_move_stable_chart_reveals(tmp_path: Path, reveal: str) -> None:
    """P1-A: Parametric chart reveal modes must keep the chart container rect stable across slides."""
    from creator_studio_doc_format.core import KeyxDocument

    raw = _freeform_canvas_stage1()
    for sc in raw.get("scenes", []):
        for obj in sc.get("objects", []):
            if obj.get("chart"):
                obj["chart"]["reveal"] = reveal
    out = tmp_path / f"p1a_chart_{reveal}.keyx"
    compile_deck(raw, out)
    assert out.exists()
    with KeyxDocument.open(out) as loaded:
        slides = list(loaded.payload.slides)
    if len(slides) >= 2:
        _assert_magic_move_stable(slides)


@pytest.mark.parametrize("reveal", ["whole", "by_row"])
def test_magic_move_stable_table_reveals(tmp_path: Path, reveal: str) -> None:
    """P1-A: Table reveal modes must keep the table container rect stable across slides."""
    from creator_studio_doc_format.core import KeyxDocument

    raw = _freeform_canvas_stage1()
    for sc in raw.get("scenes", []):
        for obj in sc.get("objects", []):
            if obj.get("table"):
                obj["table"]["reveal"] = reveal
    out = tmp_path / f"p1a_table_{reveal}.keyx"
    compile_deck(raw, out)
    assert out.exists()
    with KeyxDocument.open(out) as loaded:
        slides = list(loaded.payload.slides)
    if len(slides) >= 2:
        _assert_magic_move_stable(slides)



def test_bright_accent_auto_switches_to_dark_text_for_contrast(tmp_path: Path) -> None:
    """Bright accent_fill_hex (e.g. #FACC15) must auto-select dark readable text in callout & table highlight."""
    from creator_studio_doc_format.core import KeyxDocument

    raw = {
        "title": "Bright Accent Contrast",
        "palette": {
            "bg_hex": "#0F172A",
            "title_hex": "#FACC15",
            "text_hex": "#F8FAFC",
            "accent_fill_hex": "#FACC15",
        },
        "scenes": [
            {
                "id": "contrast_scene",
                "title": "Contrast Check",
                "grid": {"columns": 12, "rows": 1, "gap": 24},
                "regions": [
                    {"id": "left", "col": 1, "row": 1, "col_span": 5, "row_span": 1},
                    {"id": "right", "col": 6, "row": 1, "col_span": 7, "row_span": 1},
                ],
                "objects": [
                    {
                        "id": "bright_callout",
                        "kind": "callout",
                        "region": "left",
                        "variant": "accent",
                        "badge": "THESIS",
                        "label": "Readable Dark Text",
                        "step": 1,
                    },
                    {
                        "id": "hl_tbl",
                        "kind": "table",
                        "region": "right",
                        "step": 1,
                        "table": {
                            "headers": ["Key", "Val"],
                            "rows": [["Row 1", "100"], ["Row 2", "200"]],
                            "highlight_rows": [0],
                        },
                    },
                ],
            }
        ],
    }
    out = tmp_path / "contrast.keyx"
    compile_deck(raw, out)
    with KeyxDocument.open(out) as loaded:
        slide = loaded.payload.slides[0]
        callout_shape = next(
            o.object.shape for o in slide.contents
            if o.object.shape is not None and o.object.shape.identifier.endswith("_bright_callout")
        )
        # First paragraph (badge) must have dark text RGB (< 0.2), not white (> 0.9)
        from keyflow.compiler import _readable_text_rgb
        dark = _readable_text_rgb((0.98, 0.80, 0.08), (1.0, 1.0, 1.0))
        assert dark[0] < 0.2 and dark[1] < 0.2 and dark[2] < 0.2

        c_dump = callout_shape.text.paragraphs[0].style.character_properties.model_dump()
        badge_rgba = c_dump["character_fill"]["color"]["rgba"]
        assert badge_rgba["red"] < 0.2 and badge_rgba["green"] < 0.2 and badge_rgba["blue"] < 0.2

        tbl = next(o.object.table for o in slide.contents if o.object.table is not None)
        t_dump = tbl.content[1].cells[0].text_properties.model_dump()
        hl_rgba = t_dump["character_properties"]["character_fill"]["color"]["rgba"]
        assert hl_rgba["red"] < 0.2 and hl_rgba["green"] < 0.2 and hl_rgba["blue"] < 0.2


def test_waterfall_chart_progressive_compile_and_magic_move_stable(tmp_path: Path) -> None:
    """P1-D: Waterfall chart computes cumulative bounds, renders bridge connectors, and keeps Magic Move stable."""
    from creator_studio_doc_format.core import KeyxDocument

    raw = {
        "title": "Waterfall P1-D Test",
        "theme": "slate_dark",
        "scenes": [
            {
                "id": "wf_scene",
                "title": "Profit Bridge",
                "grid": {"columns": 12, "rows": 1, "gap": 24},
                "regions": [{"id": "main", "col": 1, "row": 1, "col_span": 12, "row_span": 1, "frame": True}],
                "objects": [
                    {
                        "id": "profit_wf",
                        "kind": "chart",
                        "region": "main",
                        "step": 1,
                        "chart": {
                            "chart_type": "waterfall",
                            "title": "Operating Profit Bridge ($B)",
                            "unit": "$B",
                            "categories": ["Start", "GPU Growth", "R&D Cost", "Tax", "Ending"],
                            "series": [{"name": "Bridge", "values": [100, 45, -25, -10, 110]}],
                            "reveal": "by_category",
                        },
                    }
                ],
            }
        ],
    }
    res = validate_deck(raw)
    assert res.valid, res.errors
    paced = pace_deck(raw)
    assert len(paced["scenes"][0]["frames"]) == 5
    report = audit_deck(paced, strict=True)
    assert report.passed is True, [e.to_dict() for e in report.errors]

    parsed = parse_deck(paced)
    resolved = resolve_scene(parsed.scenes[0], parsed.slide_width, parsed.slide_height)
    assert resolved[0].charts[0].use_vector is True
    assert resolved[0].charts[0].axis_min == pytest.approx(0.0)
    assert resolved[0].charts[0].axis_max > 145.0  # peak cumulative 145 + headroom

    out = tmp_path / "waterfall.keyx"
    compile_deck(raw, out)
    assert out.exists()
    with KeyxDocument.open(out) as loaded:
        slides = list(loaded.payload.slides)
        assert len(slides) == 5
        _assert_magic_move_stable(slides)
        # Final slide should have 5 waterfall bars + 4 dashed bridge connectors
        wf_bars = [
            o.object.shape for o in slides[-1].contents
            if o.object.shape is not None
            and "_profit_wf_wf_" in o.object.shape.identifier
            and "_vl_" not in o.object.shape.identifier
            and "_link_" not in o.object.shape.identifier
        ]
        wf_links = [
            o.object.shape for o in slides[-1].contents
            if o.object.shape is not None and "_profit_wf_wf_link_" in o.object.shape.identifier
        ]
        assert len(wf_bars) == 5
        assert len(wf_links) == 4


def test_v031_palette_border_derivation_region_visibility_and_grouped_chart_audit() -> None:
    """Verify accent_border_rgb derivation, active-only region frames, and series-aware chart_crowded audit."""
    from keyflow.themes import apply_palette_overrides, get_theme

    # 1. accent_fill_hex without accent_border_hex derives a coordinated border instead of keeping yellow
    base = get_theme("slate_dark")
    derived = apply_palette_overrides(base, {"accent_fill_hex": "#76B900"})
    assert derived.accent_border_rgb != base.accent_border_rgb
    assert derived.accent_border_rgb[1] > derived.accent_fill_rgb[1]  # lightened on dark bg

    # 2. Region frame stays hidden on frames where none of its objects are visible yet
    raw = {
        "title": "Region Visibility Test",
        "scenes": [
            {
                "id": "rv",
                "title": "Step Reveal",
                "grid": {"columns": 12, "rows": 1, "gap": 24},
                "regions": [
                    {"id": "left", "col": 1, "row": 1, "col_span": 5, "row_span": 1},
                    {"id": "right", "col": 6, "row": 1, "col_span": 7, "row_span": 1, "frame": True, "title": "Details"},
                ],
                "objects": [
                    {"id": "intro", "kind": "card", "region": "left", "label": "Intro", "step": 1},
                    {"id": "detail", "kind": "card", "region": "right", "label": "Detail", "step": 2},
                ],
            }
        ],
    }
    paced = pace_deck(raw)
    parsed = parse_deck(paced)
    frames = resolve_scene(parsed.scenes[0], parsed.slide_width, parsed.slide_height)
    assert [rf.id for rf in frames[0].region_frames] == []
    assert [rf.id for rf in frames[1].region_frames] == ["right"]

    # 3. Grouped column chart with 3 series x 5 categories triggers chart_crowded when width is tight
    crowded_raw = {
        "title": "Crowded Grouped Column",
        "scenes": [
            {
                "id": "cc",
                "title": "Crowded Chart",
                "grid": {"columns": 12, "rows": 1, "gap": 24},
                "regions": [
                    {"id": "narrow", "col": 1, "row": 1, "col_span": 4, "row_span": 1},
                    {"id": "rest", "col": 5, "row": 1, "col_span": 8, "row_span": 1},
                ],
                "objects": [
                    {
                        "id": "grp_col",
                        "kind": "chart",
                        "region": "narrow",
                        "step": 1,
                        "chart": {
                            "chart_type": "column",
                            "categories": ["A", "B", "C", "D", "E"],
                            "series": [
                                {"name": "S1", "values": [10, 20, 30, 40, 50]},
                                {"name": "S2", "values": [12, 22, 32, 42, 52]},
                                {"name": "S3", "values": [14, 24, 34, 44, 54]},
                            ],
                        },
                    },
                    {"id": "note_card", "kind": "card", "region": "rest", "label": "Summary", "step": 1},
                ],
            }
        ],
    }
    rep = audit_deck(crowded_raw, strict=True)
    assert any(f.category == "chart_crowded" and f.target_id == "grp_col" for f in rep.errors + rep.warnings)
