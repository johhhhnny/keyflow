"""Minimal stdio JSON-RPC 2.0 MCP server for KeyFlow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from keyflow import __version__
from keyflow.compiler import compile_deck, export_slide_pngs
from keyflow.outline import extract_markdown_outline, extract_outline_from_file
from keyflow.pace import pace_deck
from keyflow.schema import validate_deck
from keyflow.themes import THEMES

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_themes",
        "description": "List available KeyFlow visual theme presets for .keyx presentations.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "extract_outline",
        "description": "Stage 1: Extract structural summary, compact full-state scene_graph, and Stage 2 paced draft_deck from a Markdown article or README.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string", "description": "Inline Markdown article text."},
                "input_path": {"type": "string", "description": "Path to a Markdown README/article file."},
                "theme": {"type": "string", "enum": sorted(THEMES), "default": "slate_dark"},
                "density": {"type": "string", "enum": ["standard", "compact"], "default": "standard"},
            },
        },
    },
    {
        "name": "pace_storyboard",
        "description": "Stage 2: Deterministically expand Stage 1 full-state scenes (without frames) into progressive step-by-step frames across all layouts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "storyboard": {"type": "object", "description": "Inline Stage 1 scene graph or storyboard JSON."},
                "input_path": {"type": "string", "description": "Path to a JSON file."},
                "output_path": {"type": "string", "description": "Optional path to save the paced storyboard JSON."},
                "density": {"type": "string", "enum": ["standard", "compact"], "default": "standard"},
                "overwrite": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "validate_storyboard",
        "description": "Validate a KeyFlow Stage 1 scene graph or Stage 2 storyboard JSON and return structured errors and density warnings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "storyboard": {"type": "object", "description": "Inline storyboard JSON object."},
                "input_path": {"type": "string", "description": "Path to a storyboard JSON file."},
            },
        },
    },
    {
        "name": "compile_keyx",
        "description": "Compile a validated KeyFlow Stage 1 scene graph (auto-paced) or Stage 2 storyboard into a native .keyx file, with optional PNG preview export.",
        "inputSchema": {
            "type": "object",
            "required": ["output_path"],
            "properties": {
                "storyboard": {"type": "object", "description": "Inline storyboard JSON object."},
                "input_path": {"type": "string", "description": "Path to a storyboard JSON file."},
                "output_path": {"type": "string", "description": "Destination .keyx file path."},
                "theme": {"type": "string", "enum": sorted(THEMES), "description": "Optional theme override."},
                "preview_dir": {"type": "string", "description": "Optional directory to export PNG previews via Keynote."},
            },
        },
    },
    {
        "name": "preview_keyx",
        "description": "Export PNG slide previews from an existing .keyx file using macOS Keynote.",
        "inputSchema": {
            "type": "object",
            "required": ["input_path", "output_dir"],
            "properties": {
                "input_path": {"type": "string"},
                "output_dir": {"type": "string"},
            },
        },
    },
]


def _load_storyboard(args: dict[str, Any]) -> dict[str, Any]:
    if "storyboard" in args and isinstance(args["storyboard"], dict):
        return args["storyboard"]
    if "input_path" in args and args["input_path"]:
        with Path(args["input_path"]).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    raise ValueError("Provide either 'storyboard' or 'input_path'.")


def dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute one MCP tool call and return a JSON-serializable result."""
    if name == "list_themes":
        return {
            "themes": {
                k: {"description": v.description, "font_title": v.font_title, "font_body": v.font_body}
                for k, v in THEMES.items()
            }
        }

    if name == "extract_outline":
        theme = args.get("theme", "slate_dark")
        density = args.get("density", "standard")
        if "markdown" in args and isinstance(args["markdown"], str):
            return extract_markdown_outline(args["markdown"], theme=theme, density=density)
        if "input_path" in args and args["input_path"]:
            return extract_outline_from_file(args["input_path"], theme=theme, density=density)
        raise ValueError("Provide either 'markdown' or 'input_path'.")

    if name == "pace_storyboard":
        raw = _load_storyboard(args)
        val = validate_deck(raw)
        if not val.valid:
            return {"paced": False, **val.to_dict()}
        paced = pace_deck(
            raw,
            density=args.get("density", "standard"),
            overwrite_existing=bool(args.get("overwrite", False)),
        )
        paced_val = validate_deck(paced)
        if args.get("output_path"):
            out_path = Path(args["output_path"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(paced, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "paced": True,
            "storyboard": paced,
            "validation": paced_val.to_dict(),
        }

    if name == "validate_storyboard":
        raw = _load_storyboard(args)
        return validate_deck(raw).to_dict()

    if name == "compile_keyx":
        raw = _load_storyboard(args)
        val = validate_deck(raw)
        if not val.valid:
            return {"compiled": False, **val.to_dict()}
        out = compile_deck(raw, args["output_path"], theme_override=args.get("theme"))
        result: dict[str, Any] = {
            "compiled": True,
            "output_path": str(out),
            "warnings": val.warnings,
        }
        if args.get("preview_dir"):
            pngs = export_slide_pngs(out, args["preview_dir"])
            result["previews"] = [str(p) for p in pngs]
        return result

    if name == "preview_keyx":
        pngs = export_slide_pngs(args["input_path"], args["output_dir"])
        return {"previews": [str(p) for p in pngs]}

    raise ValueError(f"Unknown tool: {name}")


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC 2.0 request line."""
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "keyflow-mcp", "version": __version__},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method and method.startswith("notifications/"):
        return None
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}
    if method == "resources/templates/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resourceTemplates": []}}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {}) or {}
        try:
            payload = dispatch_tool(tool_name, tool_args)
            is_error = (
                payload.get("compiled") is False
                or payload.get("paced") is False
                or payload.get("valid") is False
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                    "isError": is_error,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            resp: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc.msg}"},
            }
        else:
            if not isinstance(req, dict):
                resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request: expected JSON object"},
                }
            else:
                resp = handle_request(req)
        if resp is not None:
            out_stream.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out_stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
