"""Command-line interface for KeyFlow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from keyflow import __version__
from keyflow.audit import audit_deck
from keyflow.compiler import compile_deck
from keyflow.exporter import export_slide_pngs
from keyflow.outline import extract_outline_from_file
from keyflow.pace import pace_deck
from keyflow.schema import validate_deck
from keyflow.themes import THEMES


def _load_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _cmd_themes(_: argparse.Namespace) -> int:
    for name, preset in THEMES.items():
        print(f"{name}: {preset.description}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    raw = _load_json(args.input)
    res = validate_deck(raw, use_templates=args.use_templates)
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    return 0 if res.valid else 1


def _cmd_audit(args: argparse.Namespace) -> int:
    raw = _load_json(args.input)
    report = audit_deck(raw, strict=args.strict, use_templates=args.use_templates)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


def _cmd_compile(args: argparse.Namespace) -> int:
    raw = _load_json(args.input)
    use_templates = getattr(args, "use_templates", None)
    res = validate_deck(raw, use_templates=use_templates)
    if not res.valid:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    strict = bool(getattr(args, "strict", False))
    fail_on_audit = bool(getattr(args, "fail_on_audit", False)) or strict
    report = audit_deck(raw, strict=strict, use_templates=use_templates)
    if fail_on_audit and not report.passed:
        print(
            json.dumps(
                {
                    "compiled": False,
                    "error": "Visual audit failed.",
                    "audit": report.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    out = compile_deck(
        raw,
        args.output,
        theme_override=args.theme,
        use_templates=use_templates,
        overrides=args.overrides,
    )
    pngs: list[Path] | None = None
    if args.preview_dir:
        pngs = export_slide_pngs(out, args.preview_dir)
    payload: dict[str, object] = {
        "output": str(out),
        "warnings": res.warnings,
        "audit": report.to_dict(preview_paths=pngs),
    }
    if pngs is not None:
        payload["previews"] = [str(p) for p in pngs]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    pngs = export_slide_pngs(args.input, args.output_dir)
    print(json.dumps({"previews": [str(p) for p in pngs]}, ensure_ascii=False, indent=2))
    return 0


def _cmd_outline(args: argparse.Namespace) -> int:
    extracted = extract_outline_from_file(args.input, theme=args.theme, density=args.density)
    selected_key = "scene_graph" if args.stage1 else "draft_deck"
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(extracted[selected_key], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "draft_path": str(out_path),
                    "stage": "scene_graph" if args.stage1 else "paced_deck",
                    "source_summary": extracted["source_summary"],
                    "draft_validation": extracted["draft_validation"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(json.dumps(extracted, ensure_ascii=False, indent=2))
    return 0


def _cmd_pace(args: argparse.Namespace) -> int:
    raw = _load_json(args.input)
    use_templates = getattr(args, "use_templates", None)
    val = validate_deck(raw, use_templates=use_templates)
    if not val.valid:
        print(json.dumps(val.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    paced = pace_deck(raw, density=args.density, overwrite_existing=args.overwrite)
    paced_val = validate_deck(paced, use_templates=use_templates)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(paced, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(out_path),
                    "frame_counts": {s["id"]: len(s.get("frames", [])) for s in paced.get("scenes", [])},
                    "validation": paced_val.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(json.dumps(paced, ensure_ascii=False, indent=2))
    return 0 if paced_val.valid else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keyflow",
        description="Compile progressive cognitive storyboards directly into native Apple Keynote (.keyx) decks.",
    )
    parser.add_argument("--version", action="version", version=f"keyflow {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_themes = sub.add_parser("themes", help="List built-in visual theme presets.")
    p_themes.set_defaults(func=_cmd_themes)

    p_val = sub.add_parser("validate", help="Validate a Stage 1 scene graph or Stage 2 storyboard JSON.")
    p_val.add_argument("-i", "--input", required=True, help="Path to storyboard JSON.")
    p_val.add_argument("--use-templates", action=argparse.BooleanOptionalAction, default=None, help="Enforce preset template-only mode (--use-templates) or freeform canvas mode (--no-templates; default).")
    p_val.set_defaults(func=_cmd_validate)

    p_aud = sub.add_parser("audit", help="Run visual geometry, anchor stability, and overflow self-checks.")
    p_aud.add_argument("-i", "--input", required=True, help="Path to Stage 1 or Stage 2 storyboard JSON.")
    p_aud.add_argument("--strict", action="store_true", help="Treat visual warnings as failures.")
    p_aud.add_argument("--use-templates", action=argparse.BooleanOptionalAction, default=None, help="Override deck use_templates switch.")
    p_aud.set_defaults(func=_cmd_audit)

    p_comp = sub.add_parser("compile", help="Compile a scene graph or storyboard JSON into a .keyx presentation.")
    p_comp.add_argument("-i", "--input", required=True, help="Path to storyboard JSON.")
    p_comp.add_argument("-o", "--output", required=True, help="Output .keyx path.")
    p_comp.add_argument("--theme", help=f"Override theme preset ({', '.join(sorted(THEMES))}) or .json theme file.")
    p_comp.add_argument("--use-templates", action=argparse.BooleanOptionalAction, default=None, help="Override deck use_templates switch.")
    p_comp.add_argument("--preview-dir", help="Optional directory to export PNG slide previews via Keynote.")
    p_comp.add_argument("--overrides", help="Optional JSON patch file keyed by slide object identifier.")
    p_comp.add_argument(
        "--fail-on-audit",
        action="store_true",
        help="Abort compilation when Tier 1 visual audit reports errors.",
    )
    p_comp.add_argument(
        "--strict",
        action="store_true",
        help="Treat visual audit warnings as errors and block compilation if any fail.",
    )
    p_comp.set_defaults(func=_cmd_compile)

    p_prev = sub.add_parser("preview", help="Export slide PNG previews from a .keyx file via Keynote.")
    p_prev.add_argument("-i", "--input", required=True, help="Path to .keyx file.")
    p_prev.add_argument("-o", "--output-dir", required=True, help="Directory to write PNG slides.")
    p_prev.set_defaults(func=_cmd_preview)

    p_out = sub.add_parser("outline", help="Extract structure and starter scene graph / storyboard from a Markdown article.")
    p_out.add_argument("-i", "--input", required=True, help="Path to Markdown README or article.")
    p_out.add_argument("-o", "--output", help="Optional path to write the extracted JSON.")
    p_out.add_argument("--theme", default="slate_dark", help=f"Theme preset ({', '.join(sorted(THEMES))}) or .json theme file.")
    p_out.add_argument("--density", default="standard", choices=["standard", "compact"], help="Pacing density.")
    p_out.add_argument("--stage1", action="store_true", help="Write compact Stage 1 full-state scene_graph without frames.")
    p_out.set_defaults(func=_cmd_outline)

    p_pace = sub.add_parser("pace", help="Stage 2: expand full-state scenes into progressive step-by-step frames.")
    p_pace.add_argument("-i", "--input", required=True, help="Path to Stage 1 scene graph JSON.")
    p_pace.add_argument("-o", "--output", help="Optional path to write the expanded storyboard JSON.")
    p_pace.add_argument("--density", default="standard", choices=["standard", "compact"], help="Pacing density.")
    p_pace.add_argument("--overwrite", action="store_true", help="Re-pace scenes that already define manual frames.")
    p_pace.add_argument("--use-templates", action=argparse.BooleanOptionalAction, default=None, help="Override deck use_templates switch.")
    p_pace.set_defaults(func=_cmd_pace)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
