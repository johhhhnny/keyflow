"""End-to-end tests for KeyFlow v0.4 native-first architecture."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest
from creator_studio_doc_format.core import KeyxDocument
from creator_studio_doc_format.validation import validate_document

from keyflow.cli import main as cli_main
from keyflow.compiler import compile_deck
from keyflow.mcp_server import handle_tool_call
from keyflow.session import DesignSession


def _make_tiny_png(path: Path) -> Path:
    """Write a valid 1x1 RGBA PNG file without external dependencies."""
    raw = b"\x00\xff\x00\x00\xff"
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return path


def test_compile_all_native_objects(tmp_path: Path) -> None:
    img_path = _make_tiny_png(tmp_path / "sample.png")
    out_keyx = tmp_path / "all_objects.keyx"

    design = {
        "slide_size": {"w": 1920, "h": 1080},
        "slides": [
            {
                "background": {
                    "type": "linear",
                    "angle": 135,
                    "stops": [
                        {"color": "#0B1120", "position": 0.0},
                        {"color": "#1E293B", "position": 1.0},
                    ],
                },
                "note": "Test slide with all native visual objects.",
                "objects": [
                    {
                        "type": "textbox",
                        "id": "hero_title",
                        "geometry": {"x": 100, "y": 80, "w": 900, "h": 180},
                        "text": {
                            "alignment": "left",
                            "line_spacing": 1.15,
                            "paragraphs": [
                                {
                                    "runs": [
                                        {
                                            "text": "Native ",
                                            "style": {
                                                "font": "Helvetica Neue",
                                                "size": 64,
                                                "color": "#F8FAFC",
                                                "bold": True,
                                            },
                                        },
                                        {
                                            "text": "Design",
                                            "style": {
                                                "font": "Helvetica Neue",
                                                "size": 64,
                                                "color": "#38BDF8",
                                                "italic": True,
                                                "hyperlink": "https://example.com",
                                            },
                                        },
                                    ]
                                },
                                {
                                    "runs": "Bullet item one",
                                    "list_style": {"type": "bullet", "bullet": "•"},
                                },
                            ],
                        },
                    },
                    {
                        "type": "shape",
                        "id": "node_a",
                        "geometry": {"x": 100, "y": 320, "w": 280, "h": 140},
                        "shape": "rounded_rect",
                        "corner_radius": 0.15,
                        "fill": "#1D4ED8",
                        "stroke": {"color": "#93C5FD", "width": 2.0, "style": "solid"},
                        "shadow": {"type": "drop", "opacity": 0.4, "offset": 8, "radius": 16},
                        "text": "Source Node",
                    },
                    {
                        "type": "shape",
                        "id": "node_b",
                        "geometry": {"x": 560, "y": 320, "w": 280, "h": 140},
                        "shape": "custom",
                        "path": "M 0,0.2 L 0.8,0 L 1,0.5 L 0.8,1 L 0,0.8 Z",
                        "fill": "#0F766E",
                        "reflection": {"opacity": 0.25},
                        "text": "Custom Path",
                    },
                    {
                        "type": "connection",
                        "id": "link_ab",
                        "line_type": "curved",
                        "from_point": [380, 390],
                        "to_point": [560, 390],
                        "from_anchor": {"object_id": "node_a", "magnet": "east"},
                        "to_anchor": {"object_id": "node_b", "magnet": "west"},
                        "head_end": "filled_arrow",
                        "stroke": {"color": "#FBBF24", "width": 3.0, "style": "dashed"},
                    },
                    {
                        "type": "image",
                        "id": "photo_1",
                        "geometry": {"x": 100, "y": 540, "w": 240, "h": 240, "angle": -3},
                        "src": str(img_path),
                        "mask_shape": "oval",
                        "stroke": {"color": "#FFFFFF", "width": 4.0},
                    },
                    {
                        "type": "table",
                        "id": "metrics_table",
                        "geometry": {"x": 400, "y": 540, "w": 560, "h": 260},
                        "columns": [
                            {"title": "Metric", "width": 260, "alignment": "left"},
                            {"title": "Delta", "width": 300, "alignment": "right"},
                        ],
                        "rows": [
                            ["Latency", {"value": "-42%", "fill": "#064E3B", "text_color": "#6EE7B7", "bold": True}],
                            ["Throughput", "+3.1x"],
                        ],
                        "alternating_rows": True,
                    },
                    {
                        "type": "chart",
                        "id": "perf_chart",
                        "geometry": {"x": 1060, "y": 140, "w": 760, "h": 420},
                        "chart_type": "mixed",
                        "title": "Latency vs Throughput",
                        "categories": ["v0.1", "v0.2", "v0.3", "v0.4"],
                        "series": [
                            {"name": "Throughput", "values": [10, 18, 25, 42], "mixed_type": "column"},
                            {"name": "Latency", "values": [90, 65, 50, 28], "mixed_type": "line"},
                        ],
                    },
                    {
                        "type": "group",
                        "id": "badge_group",
                        "title": "Badge",
                        "children": [
                            {
                                "type": "shape",
                                "id": "badge_bg",
                                "geometry": {"x": 1060, "y": 640, "w": 220, "h": 60},
                                "shape": "pill",
                                "fill": "#334155",
                            },
                            {
                                "type": "textbox",
                                "id": "badge_txt",
                                "geometry": {"x": 1080, "y": 650, "w": 180, "h": 40},
                                "text": {"string": "v0.4.0", "alignment": "center"},
                            },
                        ],
                    },
                ],
            }
        ],
    }

    res = compile_deck(design, out_keyx)
    assert res.keyx_path.exists()
    assert res.slide_count == 1
    assert res.object_count == 9
    assert res.geometry_notes == []

    # Re-open and validate with creator-studio-doc-format
    loaded = KeyxDocument.open(out_keyx)
    assert validate_document(loaded) is None


@pytest.mark.parametrize("chart_type", ["bar", "column", "line", "area", "pie", "donut", "scatter", "radar"])
def test_compile_chart_variants(tmp_path: Path, chart_type: str) -> None:
    out = tmp_path / f"{chart_type}.keyx"
    spec = {
        "background": "#111827",
        "objects": [
            {
                "type": "chart",
                "geometry": {"x": 200, "y": 180, "w": 1400, "h": 700},
                "chart_type": chart_type,
                "categories": ["A", "B", "C"],
                "series": [{"name": "S1", "values": [10, 25, 18]}],
            }
        ],
    }
    res = compile_deck(spec, out)
    assert res.keyx_path.exists()


def test_iterative_design_session(tmp_path: Path) -> None:
    sess = DesignSession.create(background="#0F172A", note="Iterative test")
    id_a = sess.add_object(
        0,
        {
            "type": "shape",
            "id": "card_bg",
            "geometry": {"x": 120, "y": 120, "w": 400, "h": 300},
            "shape": "rounded_rect",
            "fill": "#1E293B",
        },
    )
    id_b = sess.add_object(
        0,
        {
            "type": "textbox",
            "id": "card_title",
            "geometry": {"x": 150, "y": 150, "w": 340, "h": 80},
            "text": "Initial Title",
        },
    )
    sess.update_object(0, id_b, {"text": {"string": "Critiqued & Refined Title"}})
    gid = sess.group_objects(0, [id_a, id_b], group_id="card_group", title="Card")
    sess.update_object(0, id_a, {"fill": "#334155"})

    summary = sess.inspect(0)
    assert summary["slides"][0]["object_count"] == 1
    assert summary["slides"][0]["objects"][0]["id"] == gid

    sess.ungroup_object(0, gid)
    sess.reorder_object(0, id_a, "front")
    assert sess.inspect(0)["slides"][0]["objects"][-1]["id"] == id_a

    sess.remove_object(0, id_a)
    res = sess.compile(tmp_path / "iterative.keyx")
    assert res.object_count == 1
    assert res.keyx_path.exists()


def test_cli_and_mcp_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_file = tmp_path / "design.json"
    out_keyx = tmp_path / "cli.keyx"
    spec_file.write_text(
        json.dumps(
            {
                "background": "#09090B",
                "objects": [
                    {
                        "type": "textbox",
                        "id": "t1",
                        "geometry": {"x": 100, "y": 100, "w": 800, "h": 120},
                        "text": "Hello KeyFlow v0.4",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert cli_main(["compile", str(spec_file), "-o", str(out_keyx)]) == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured["object_count"] == 1
    assert out_keyx.exists()

    # MCP session roundtrip
    sid = handle_tool_call("design_create", {"background": "#0F172A"})["session_id"]
    oid = handle_tool_call(
        "design_add_object",
        {
            "session_id": sid,
            "object": {
                "type": "shape",
                "geometry": {"x": 200, "y": 200, "w": 300, "h": 300},
                "shape": "star",
                "fill": "#F59E0B",
            },
        },
    )["object_id"]
    handle_tool_call(
        "design_update_object",
        {"session_id": sid, "object_id": oid, "patch": {"fill": "#10B981"}},
    )
    mcp_keyx = tmp_path / "mcp.keyx"
    res = handle_tool_call(
        "design_compile_and_render",
        {"session_id": sid, "output_path": str(mcp_keyx)},
    )
    assert res["object_count"] == 1
    assert res["pngs"] == []
    assert mcp_keyx.exists()


def test_png_render_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from keyflow.renderer import ENV_RENDER_PNG, is_render_enabled

    monkeypatch.delenv(ENV_RENDER_PNG, raising=False)
    assert is_render_enabled() is False
    assert is_render_enabled(True) is True
    assert is_render_enabled(False) is False

    monkeypatch.setenv(ENV_RENDER_PNG, "1")
    assert is_render_enabled() is True
    assert is_render_enabled(False) is False

    monkeypatch.setenv(ENV_RENDER_PNG, "off")
    assert is_render_enabled() is False

    # Graceful skip on non-macOS / Keynote unavailable when strict_render=False
    monkeypatch.setattr("keyflow.renderer.can_render_png", lambda: False)
    sess = DesignSession.create()
    sess.add_object(
        0,
        {"type": "textbox", "geometry": {"x": 50, "y": 50, "w": 400, "h": 100}, "text": "Prod"},
    )
    res, pngs = sess.compile_and_render(tmp_path / "prod.keyx", render_png=True)
    assert res.keyx_path.exists()
    assert pngs == []
