---
name: keyflow
description: Distill technical articles, analytical essays, or README files into narrative-first, progressive Apple Keynote (.keyx) presentations using a three-stage workflow (Stage 0 Narrative Brief -> Stage 1 Full-State Scene Graph -> Stage 2 Progressive Pacing & Visual Audit).
---

# KeyFlow: Narrative-First Article-to-Keynote Storytelling

KeyFlow separates **story & logical architecture** (Stage 0) from **visual scene topology** (Stage 1) and **progressive animation & verification** (Stage 2). Never mirror a document's table of contents blindly as bullet cards; extract the underlying argument and design a visual arc.

---

## Stage 0: Content Logic & Visual Narrative Planning (Before Writing JSON)

Before authoring any Scene Graph JSON, produce a concise **Stage 0 Narrative Brief** (see `references/narrative_brief_template.md`):

1. **Extract Logical Structure With Source Grounding (Not Section Headings)**:
   Tag source material into explicit epistemic units, each tied to a verifiable `source_quote` (or explicit calculation assumptions if derived):
   - `thesis`: core claim or central question the article argues
   - `fact` / `metric`: verifiable numbers, benchmarks, or primary-source observations — **never introduce unsourced figures to make a chart look complete**
   - `relation`: supply-chain, causal, or resource-allocation links between entities
   - `inference`: author interpretation or hypothesis — **never flatten inferences into settled facts**; mark them in `badge` (e.g., `"THESIS"`, `"CLAIM"`, `"INFERENCE"`) or `note`
   - `counter_evidence`: caveats, bottlenecks, or competing explanations
   - `conclusion`: synthesized takeaway conditioned strictly on the stated qualifiers
2. **Choose Visual Expression From Logic First (And Isolate Metric Scopes)**:
   Decide the visual form by reasoning structure BEFORE reaching for cards, and vary visual rhythm across scenes. You have **two complementary modes** controlled by top-level `use_templates` (defaults to `false`):
   - **Freeform Compositional Canvas (`layout: "canvas"`, default `use_templates: false`) — Preferred for Heterogeneous / Analytical Scenes**:
     Combine heterogeneous visual objects on a 12-column `grid` partitioned into non-overlapping `regions` (`col`, `row`, `col_span`, `row_span`, `arrange`: `"stack" | "row" | "grid"`, `title`, `frame`), keeping **<= 3–4 regions** and **<= 5–6 top-level objects** per slide for generous breathing room:
     - `card` / `callout`: concise structural anchors or highlighted conclusions (`label`, optional `badge`, `metric`, `sublabel`, `variant`, `weight`)
     - `textbox` / `shape`: typography blocks (`align`, `font_size` in `10–140`) and geometric shapes (`rounded_rect`, `rect`, `ellipse`, `pill`, or custom normalized `svg_path`)
     - `chart`: 9 data-driven chart types (`column`, `bar`, `pie`, `donut`, `line`, `area`, `stacked_column`, `stacked_bar`, `scatter`) with `reveal`: `"whole" | "by_series" | "by_category"` and `render_mode`: `"auto" | "vector" | "native"`. Under `render_mode: "auto"` (recommended), progressive charts (`reveal != "whole"`) compile into pure `.keyx` `Shape` + `Textbox` vectors with locked cluster widths so Keynote Magic Move keeps earlier bars rock-solid; static `reveal: "whole"` charts compile as editable native `.keyx` `Chart` objects.
     - `table`: native `.keyx` `Table` (`headers`, `rows`, `reveal`: `"whole" | "by_row" | "by_column"`, `highlight_cols`, `highlight_rows`)
     - `diagram`: inline node-and-edge subgraph (`diagram_layout`: `"horizontal" | "vertical" | "dag" | "hub_spoke"`) embedded inside a region; `pace` automatically decomposes multi-node diagrams node-by-node / layer-by-layer with locked coordinates.
     - `connectors`: cross-object arrows (`from`, `to`, `label`, `style`) across objects on the canvas; `step` controls object appearance order, and deck/scene `palette` lets you customize visual colors (`bg_hex`, `title_hex`, `accent_fill_hex`, `series_colors`, etc.).
   - **10 Built-in Preset Layouts (also enforceable via `use_templates: true` / `--use-templates`)**:
     - **Single Hero Stat / Core Thesis**: `metrics_cards` with **1–2** bold centerpiece cards (`metric` + crisp `label`, generous whitespace). Never invent dummy cards just to fill a 4-node row.
     - **Causal Split / Resource Contention / Bottleneck**: `flow_dag` with explicit **fork/merge branches** (e.g., shared scarce capacity splitting between internal demand and external clients), labeled edges, and `FACT` vs `INFERENCE` badges.
     - **Value Chain / Persistent Chapter Spine**: deck-level `pinned_flow` (centered macro overview -> docked top ribbon via `active_flow_node`) paired with focused deep-dive scenes.
     - **Single-Denominator Share / Allocation**: `proportion_bar` — **enforce single `metric_scope` per chart** (never put revenue share in the subtitle of a launch-count share chart; split incompatible scopes across scenes).
     - **Multi-Party Quantitative / Strategic Contrast**: `comparison_matrix` (columns, `formula`, `↑`/`↓` trends, `action_banner`, `takeaway`) or side-by-side `comparison` — label clearly if comparing actual price vs. target cost so differing accounting bases are never blurred.
     - **Sequential Evolution / Milestones**: `horizontal_flow` (3–5 pillars; unpack 2 children as `row`, 3–4 as `grid`), `architecture_evolution` (`v1 -> v2 -> v3`), or `sequence_timeline` (forward skips + backward loops).
     - **Core + Radiating Factors**: `hub_spoke` (center `variant: "accent"` + 3–6 spokes).
3. **Design the Narrative Arc Across Scenes**:
   For each scene in the Stage 0 brief, define:
   - `claim`: the single takeaway the audience must remember from this scene
   - `metric_scope`: exact denominator/unit/era when numbers appear
   - `source_quote`: verbatim anchor from the source text backing every metric or factual claim
   - `protagonist` & `supporting`: what takes visual focus (`variant: "accent"`, `active_flow_node`, `focus_nodes`) vs muted context
   - `transition_intent`: how this scene connects to the previous/next scene (zoom in from `pinned_flow`, fork capacity bottleneck, contrast counter-argument, return to synthesis)
4. **Content-to-Visual Fidelity & Anti-Overclaim Check (Gate Before Stage 1)**:
   Verify against the source before writing JSON:
   - Did any scene omit the central thesis, key competitors/market context, or counter-evidence?
   - **Source Traceability**: Does every number and fact trace to an explicit `source_quote` in the input (no ungrounded filler stats)?
   - **Metric-Scope Purity**: Does each numeric scene stick to one denominator/timeframe without mixing incompatible percentages?
   - **Anti-Overclaim Alignment**: Do titles, badges, and headlines preserve original qualifiers ("partially stopped", "gradually phasing out", "design target") rather than escalating them into absolutes?
   - Are author claims/inferences visually distinguished from verified data, with zero redundant restatements or fabricated padding nodes?

---

## Stage 1: Design Full-State Scene Graphs (Topology & Semantics)

Translate the Stage 0 brief into clean Stage 1 diagrams. Do **not** hand-write `frames` unless custom choreography is required:

1. **Zero-Bullet Canvas**: Each card holds **1 short `label`** (1–4 words / ≤ 12 CJK chars) plus optional micro-hierarchy fields:
   - `badge`: crisp eyebrow tag (e.g., `"FACT"`, `"THESIS"`, `"LEGACY"`, `"TARGET"`, `"STEP 01"`)
   - `metric`: hero number/stat for KPI or single-thesis centerpiece cards (e.g., `"75%"`, `"10×"`, `"0 依赖"`)
   - `sublabel`: brief secondary line (e.g., `"商业常识"`, `"7s → 0.7s"`)
   - `variant`: `"primary"` | `"accent"` (yellow highlight) | `"success"` (teal-green) | `"warn"` (amber) | `"muted"`
   Put all prose explanations, caveats, citations, and presenter context into each node/child's **`note`** field (and scene `intro_note`).
2. **Structured Story Model & Evidence Grounding (Recommended for Analytical Decks)**:
   Include optional `story_model` at the deck root (`core_question`, `claims`: `id`, `type`, `claim`, `source_quote`, `metric_scope`, `confidence`), set per-scene `claim` & `metric_scope`, and link elements via `evidence_refs: [...]`. `keyflow audit` automatically enforces epistemic alignment (e.g., rejects `badge: "FACT"` pointing to an `inference` claim), flags `scope_mixing` across incompatible denominators, warns on `unsourced_fact`, and catches dropped `thesis` / `counter_evidence` claims.
3. **Freeform vs. Template Mode (`use_templates`)**:
   `use_templates` defaults to `false`, enabling `layout: "canvas"`, `palette`, native/vector `chart`, native `table`, and inline `diagram`. Pass `--use-templates` (CLI) or `use_templates: true` only when validating strict preset-only decks.
4. **Optional Structural Seed for Long Articles**:
   Run `uv run keyflow outline -i article.md --stage1 -o starter.json` (or MCP `extract_outline`) only as a mechanical starting skeleton — replace generic chapter summaries with your Stage 0 narrative plan.

---

## Stage 2: Progressive Pacing, Quality-Gated Compile & Fidelity Loop

Once the Stage 1 topology satisfies your Stage 0 narrative check, run the **2-tier verification loop**:

1. **Tier 1 Geometry & Stability Audit (Fast, Cross-Platform)**:
   - Run `audit_storyboard` (MCP) or `uv run keyflow audit -i stage1.json --strict` before rendering.
   - Use structured finding fields (`target_id`, `suggested_action`, `suggestion`) to make surgical fixes (shorten labels, enable `child_layout: "grid"`, split overcrowded scenes, or merge narrow segments).
2. **Tier 2 Keynote Render & Targeted PNG Inspection (macOS)**:
   - Expand and compile with audit gate enabled via `pace_storyboard` -> `compile_keyx(..., preview_dir=..., fail_on_audit=True)`, or CLI:
     ```bash
     uv run keyflow pace -i stage1.json -o storyboard.json --density standard
     uv run keyflow compile -i storyboard.json -o output.keyx --fail-on-audit --preview-dir ./preview
     ```
   - Inspect the PNGs listed in `audit.review_pngs` (all flagged slides plus slide 1 and each scene's final slide) for real Keynote text wrapping, breathing room, visual balance, connector clarity, and fidelity to the Stage 0 argument; make targeted node/scene edits and recompile once if needed.
