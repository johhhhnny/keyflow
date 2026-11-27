"""Minimal stdio JSON-RPC MCP server for KeyFlow v0.4.

Exposes both one-shot compilation/rendering tools and stateful iterative
design-session tools so an agent can create, compose, modify, render,
observe, and redesign slides in a tight feedback loop.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from keyflow.compiler import compile_deck
from keyflow.renderer import is_render_enabled, render_keyx_to_pngs
from keyflow.session import DesignSession
from keyflow.spec import DeckSpec
from keyflow.theme import list_themes, load_theme

_SESSIONS: dict[str, DesignSession] = {}


def _get_session(session_id: str) -> DesignSession:
    if session_id not in _SESSIONS:
        raise KeyError(f"Unknown design session: {session_id}")
    return _SESSIONS[session_id]


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_design_schema",
        "description": "Return the JSON Schema for DeckSpec (native Keynote visual objects).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "compile_design",
        "description": "Compile a complete DeckSpec or SlideSpec JSON into a validated .keyx file, with optional PNG rendering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "DeckSpec or SlideSpec object"},
                "output_path": {"type": "string", "description": "Output .keyx file path"},
                "render_png": {"type": "boolean", "description": "Override KEYFLOW_RENDER_PNG switch"},
                "png_dir": {"type": "string", "description": "Optional PNG output directory"},
            },
            "required": ["spec", "output_path"],
        },
    },
    {
        "name": "render_keyx",
        "description": "Render a .keyx file to per-slide PNGs via Apple Keynote for visual inspection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyx_path": {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "required": ["keyx_path", "output_dir"],
        },
    },
    {
        "name": "get_theme",
        "description": "List available themes or return the full global config of a specific theme (colors, typography, canvas, charts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Theme name (e.g. 'midnight_indigo') or JSON path; omit to list themes."}
            },
        },
    },
    {
        "name": "design_create",
        "description": "Create a new iterative slide design session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "default": "midnight_indigo"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "background": {},
                "note": {"type": "string"},
            },
        },
    },
    {
        "name": "design_add_object",
        "description": "Add a native visual object (textbox, shape, connection, image, table, chart, group) to a slide.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "object": {"type": "object"},
                "index": {"type": "integer"},
                "group_id": {"type": "string"},
            },
            "required": ["session_id", "object"],
        },
    },
    {
        "name": "design_update_object",
        "description": "Patch an existing visual object by ID (position, size, color, text, path, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "object_id": {"type": "string"},
                "patch": {"type": "object"},
            },
            "required": ["session_id", "object_id", "patch"],
        },
    },
    {
        "name": "design_remove_object",
        "description": "Remove a visual object by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "object_id": {"type": "string"},
            },
            "required": ["session_id", "object_id"],
        },
    },
    {
        "name": "design_reorder_object",
        "description": "Change z-order of a top-level object ('front', 'back', 'forward', 'backward', or integer index).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "object_id": {"type": "string"},
                "position": {},
            },
            "required": ["session_id", "object_id", "position"],
        },
    },
    {
        "name": "design_group_objects",
        "description": "Group multiple top-level objects into a native Group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "object_ids": {"type": "array", "items": {"type": "string"}},
                "group_id": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["session_id", "object_ids"],
        },
    },
    {
        "name": "design_set_background",
        "description": "Set slide background (hex color, gradient, or image fill).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "background": {},
            },
            "required": ["session_id", "background"],
        },
    },
    {
        "name": "design_set_brief",
        "description": "Stage 1: Record structured semantic understanding (core_thesis, audience, goal, key_facts, relationships, visual_subject).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "brief": {"type": "object"},
            },
            "required": ["session_id", "brief"],
        },
    },
    {
        "name": "design_set_composition",
        "description": "Stage 2 & 3: Record visual concept, central tension, expression form, focal point, and reading order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer", "default": 0},
                "composition": {"type": "object"},
            },
            "required": ["session_id", "composition"],
        },
    },
    {
        "name": "design_inspect",
        "description": "Inspect the current scene graph, object IDs, and bounding boxes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "slide_index": {"type": "integer"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "design_compile_and_render",
        "description": "Compile the session design to .keyx and optionally render PNGs (controlled by render_png or KEYFLOW_RENDER_PNG).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "output_path": {"type": "string"},
                "png_dir": {"type": "string"},
                "render_png": {"type": "boolean"},
            },
            "required": ["session_id", "output_path"],
        },
    },
]


def handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "get_design_schema":
        return DeckSpec.model_json_schema()

    if name == "compile_design":
        res = compile_deck(args["spec"], args["output_path"])
        out: dict[str, Any] = {
            "keyx_path": str(res.keyx_path),
            "slide_count": res.slide_count,
            "object_count": res.object_count,
            "geometry_notes": res.geometry_notes,
            "pngs": [],
        }
        render_flag = args.get("render_png")
        if render_flag is None and args.get("png_dir"):
            render_flag = True
        if is_render_enabled(render_flag):
            png_dir = Path(args["png_dir"]) if args.get("png_dir") else res.keyx_path.with_name(f"{res.keyx_path.stem}_previews")
            try:
                out["pngs"] = [str(p) for p in render_keyx_to_pngs(res.keyx_path, png_dir)]
            except RuntimeError as exc:
                out["render_skipped"] = str(exc)
        return out

    if name == "render_keyx":
        pngs = render_keyx_to_pngs(args["keyx_path"], args["output_dir"])
        return {"pngs": [str(p) for p in pngs]}

    if name == "get_theme":
        tname = args.get("name")
        if not tname:
            return {"themes": list_themes()}
        theme = load_theme(tname)
        if theme is None:
            raise FileNotFoundError(f"Theme not found: {tname}")
        return theme.model_dump(mode="json")

    if name == "design_create":
        sid = uuid.uuid4().hex[:10]
        _SESSIONS[sid] = DesignSession.create(
            theme=args.get("theme", "midnight_indigo"),
            width=args.get("width"),
            height=args.get("height"),
            background=args.get("background"),
            note=args.get("note"),
        )
        return {"session_id": sid}

    if name == "design_add_object":
        sess = _get_session(args["session_id"])
        oid = sess.add_object(
            args.get("slide_index", 0),
            args["object"],
            index=args.get("index"),
            group_id=args.get("group_id"),
        )
        return {"object_id": oid}

    if name == "design_update_object":
        sess = _get_session(args["session_id"])
        sess.update_object(
            args.get("slide_index", 0),
            args["object_id"],
            args["patch"],
        )
        return {"updated": args["object_id"]}

    if name == "design_remove_object":
        sess = _get_session(args["session_id"])
        sess.remove_object(args.get("slide_index", 0), args["object_id"])
        return {"removed": args["object_id"]}

    if name == "design_reorder_object":
        sess = _get_session(args["session_id"])
        sess.reorder_object(
            args.get("slide_index", 0),
            args["object_id"],
            args["position"],
        )
        return {"reordered": args["object_id"]}

    if name == "design_group_objects":
        sess = _get_session(args["session_id"])
        gid = sess.group_objects(
            args.get("slide_index", 0),
            args["object_ids"],
            group_id=args.get("group_id"),
            title=args.get("title"),
        )
        return {"group_id": gid}

    if name == "design_set_background":
        sess = _get_session(args["session_id"])
        sess.set_background(args.get("slide_index", 0), args["background"])
        return {"ok": True}

    if name == "design_set_brief":
        sess = _get_session(args["session_id"])
        sess.set_brief(args.get("slide_index", 0), args["brief"])
        return {"ok": True}

    if name == "design_set_composition":
        sess = _get_session(args["session_id"])
        sess.set_composition(args.get("slide_index", 0), args["composition"])
        return {"ok": True}

    if name == "design_inspect":
        sess = _get_session(args["session_id"])
        return sess.inspect(args.get("slide_index"))

    if name == "design_compile_and_render":
        sess = _get_session(args["session_id"])
        render_flag = args.get("render_png")
        if render_flag is None and args.get("png_dir"):
            render_flag = True
        res, pngs = sess.compile_and_render(
            args["output_path"],
            args.get("png_dir"),
            render_png=render_flag,
        )
        return {
            "keyx_path": str(res.keyx_path),
            "slide_count": res.slide_count,
            "object_count": res.object_count,
            "geometry_notes": res.geometry_notes,
            "pngs": [str(p) for p in pngs],
        }

    raise ValueError(f"Unknown tool: {name}")


def _respond(req_id: Any, result: Any) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _respond_error(req_id: Any, code: int, message: str) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _respond_error(None, -32700, f"Parse error: {exc}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "initialize":
            _respond(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "keyflow", "version": "0.4.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _respond(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            try:
                res = handle_tool_call(tool_name, tool_args)
                _respond(
                    req_id,
                    {
                        "content": [
                            {"type": "text", "text": json.dumps(res, ensure_ascii=False)}
                        ]
                    },
                )
            except Exception as exc:
                _respond(
                    req_id,
                    {
                        "isError": True,
                        "content": [{"type": "text", "text": str(exc)}],
                    },
                )
        else:
            if req_id is not None:
                _respond_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
