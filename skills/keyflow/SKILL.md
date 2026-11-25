---
name: keyflow
description: Distill technical articles, design docs, or README files into progressive, minimalist Apple Keynote (.keyx) presentations using a two-stage workflow (Full-State Scene Graph -> Progressive Pacing).
---

# KeyFlow: Two-Stage Article-to-Keynote Storytelling

KeyFlow separates **what the visual structure is** (Stage 1) from **how it unfolds step-by-step** (Stage 2).

## Stage 1: Design Full-State Scene Graphs (Topology & Semantics)

Focus strictly on distilling the article into 1–4 clean conceptual diagrams. Do **not** write `frames` by hand in Stage 1:

1. **Zero-Bullet Canvas**: Each card holds **1 short `label`** (1–4 words / ≤ 12 CJK chars) plus optional micro-hierarchy fields:
   - `badge`: crisp eyebrow tag (e.g., `"LEGACY"`, `"TARGET"`, `"STEP 01"`, `"v2.0"`)
   - `metric`: hero number/stat for KPI cards (e.g., `"10×"`, `"19/19"`, `"0 依赖"`)
   - `sublabel`: brief secondary line (e.g., `"商业常识"`, `"7s → 0.7s"`)
   - `variant`: `"primary"` | `"accent"` (yellow highlight) | `"success"` (teal-green) | `"warn"` (amber) | `"muted"`
   Put all prose explanations, metrics context, and commands into each node/child's **`note`** field (and scene `intro_note`).
2. **Choose the Right Layout**:
   - `horizontal_flow`: Sequential pillars or lifecycle (3–5 nodes; unpack 2 children as `row`, 3–4 children as `grid`).
   - `flow_dag`: Workflows with branches, parallel lanes, and fork-join merges (supports `edge.label`).
   - `architecture_evolution`: Multi-era stacked architecture columns (`v1 -> v2 -> v3`) connected by evolution arrows, with `badge` and `warn`/`success` variants.
   - `sequence_timeline`: State machines or protocol sequences along a horizontal spine; forward skips bow above and backward retry/fallback loops bow below automatically.
   - `metrics_cards`: 2–6 KPI or benchmark highlight cards with large `metric` values (`1–4` in a row, `5–6` in a 3×2 grid).
   - `proportion_bar`: Quantitative 0–100 (or custom range) stacked proportion scale with optional left summary chip list (ideal for probability/latency/cost breakdowns).
   - `comparison_matrix`: Multi-column parameter/benchmark matrix with optional `formula` centerpiece, colored `↑`/`↓` trend indicators, `action_banner`, and `takeaway` callout pills.
   - `vertical_flow`: Layered architectures or top-down stacks.
   - `hub_spoke`: Central core (`variant: "accent"`) + 3–6 radiating spokes.
   - `comparison`: Side-by-side contrasts (`A vs B`) with automatic `VS` divider.
3. **Deck-Level Persistent Context Ribbon (`pinned_flow`)**:
   For multi-scene deep-dives (e.g., macro pipeline -> micro mechanism), define `pinned_flow` at the deck root (`nodes`, `edges`, optional `groups` with top border-embedded legend) and set `active_flow_node` on each scene to automatically highlight the current chapter in warm orange at the top of the slide.
3. **Optional Pre-Extraction for Long Articles**:
   ```bash
   uv run keyflow outline -i README.md --stage1 -o stage1.json
   ```
   Or via MCP tool `extract_outline` (use its `scene_graph` output).

## Stage 2: Expand Progressive Frames (`pace`), Self-Check & Compile

Once the Stage 1 full-state topology looks right, run a **2-round visual self-check feedback loop**:

1. **Tier 1 Geometry Audit (Fast, Cross-Platform)**:
   - Run `audit_storyboard` (MCP) or `uv run keyflow audit -i stage1.json` before rendering.
   - If `errors` or `warnings` appear (e.g., `out_of_bounds`, `overlap`, `cramped_scale`, `text_overflow`, `crowded_proportion`), apply the returned JSON `suggestion` fixes right away (shorten labels, enable `child_layout: "grid"`, split overcrowded scenes, or merge narrow segments).
2. **Tier 2 Keynote Render & Targeted PNG Inspection (macOS)**:
   - Expand and compile via `pace_storyboard` -> `compile_keyx(..., preview_dir=...)`, or directly:
     ```bash
     uv run keyflow pace -i stage1.json -o storyboard.json --density standard
     uv run keyflow compile -i storyboard.json -o output.keyx --preview-dir ./preview
     ```
   - Inspect only the PNGs listed in `audit.review_pngs` (all flagged slides plus slide 1 and each scene's final slide) to verify text wrapping, breathing room, and connector routing; refine and recompile once if any visual flaw remains.
