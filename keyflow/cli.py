"""Command-line interface for KeyFlow v0.4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from keyflow.compiler import compile_deck
from keyflow.renderer import is_render_enabled, render_keyx_to_pngs
from keyflow.session import DesignSession
from keyflow.spec import DeckSpec


def _cmd_compile(args: argparse.Namespace) -> int:
    spec_data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = compile_deck(spec_data, args.output)
    payload: dict[str, object] = {
        "keyx_path": str(result.keyx_path),
        "slide_count": result.slide_count,
        "object_count": result.object_count,
        "geometry_notes": result.geometry_notes,
    }
    render_flag: bool | None = False if args.no_render else (True if args.render is not None else None)
    if is_render_enabled(render_flag):
        png_dir = args.render or result.keyx_path.with_name(f"{result.keyx_path.stem}_previews")
        pngs = render_keyx_to_pngs(result.keyx_path, png_dir)
        payload["pngs"] = [str(p) for p in pngs]
    else:
        payload["pngs"] = []
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    pngs = render_keyx_to_pngs(args.keyx, args.output)
    print(json.dumps({"pngs": [str(p) for p in pngs]}, indent=2))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    session = DesignSession.from_file(args.spec)
    print(json.dumps(session.inspect(), indent=2, ensure_ascii=False))
    return 0


def _cmd_schema(_args: argparse.Namespace) -> int:
    print(json.dumps(DeckSpec.model_json_schema(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keyflow",
        description="Native-first Keynote (.keyx) compiler for agent-designed slides.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="Compile a design spec JSON into .keyx")
    p_compile.add_argument("spec", type=Path, help="Path to DeckSpec or SlideSpec JSON")
    p_compile.add_argument("-o", "--output", type=Path, required=True, help="Output .keyx path")
    p_compile.add_argument("--render", type=Path, default=None, help="Enable PNG export to this directory")
    p_compile.add_argument("--no-render", action="store_true", help="Disable PNG export even if KEYFLOW_RENDER_PNG is set")
    p_compile.set_defaults(func=_cmd_compile)

    p_render = sub.add_parser("render", help="Render an existing .keyx file to PNGs via Keynote")
    p_render.add_argument("keyx", type=Path, help="Input .keyx path")
    p_render.add_argument("-o", "--output", type=Path, required=True, help="Output PNG directory")
    p_render.set_defaults(func=_cmd_render)

    p_inspect = sub.add_parser("inspect", help="Inspect scene graph of a design spec JSON")
    p_inspect.add_argument("spec", type=Path, help="Path to DeckSpec or SlideSpec JSON")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_schema = sub.add_parser("schema", help="Print the JSON Schema for DeckSpec")
    p_schema.set_defaults(func=_cmd_schema)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
