---
name: keyflow
description: Distill technical articles, analytical essays, or README files into narrative-first, progressive Apple Keynote (.keyx) presentations using a three-stage workflow (Stage 0 Narrative Brief -> Stage 1 Full-State Scene Graph -> Stage 2 Progressive Pacing & Visual Audit).
---

# KeyFlow: Narrative-First Article-to-Keynote Storytelling

KeyFlow separates **story & logical architecture** (Stage 0) from **visual scene topology** (Stage 1) and **progressive animation & verification** (Stage 2). Never mirror a document's table of contents blindly as bullet cards; extract the underlying argument and design a visual arc.

---

## Stage 0: Content Logic & Visual Narrative Planning (Before Writing JSON)

Before authoring any Scene Graph JSON, produce a concise **Stage 0 Narrative Brief** (see `references/narrative_brief_template.md`):

1. **Extract Logical Structure (Not Section Headings)**:
   Tag source material into explicit epistemic units:
   - `thesis`: core claim or central question the article argues
   - `fact` / `metric`: verifiable numbers, benchmarks, or primary-source observations
   - `relation`: supply-chain, causal, or dependency links between entities
   - `inference`: author interpretation or hypothesis — **never flatten inferences into settled facts**; mark them in `badge` (e.g., `"THESIS"`, `"CLAIM"`, `"HYPOTHESIS"`) or `note`
   - `counter_evidence`: caveats, bottlenecks, or competing explanations
   - `conclusion`: synthesized takeaway grounded in the preceding evidence
2. **Select the Right Visual Form (And Know When Less Is More)**:
   Choose each scene's layout by its reasoning structure — avoid repeating the same layout back-to-back unless deliberately contrasting:
   - **Single Hero Stat / Core Thesis**: `metrics_cards` with **1–2** bold centerpiece cards (`metric` + crisp `label`, generous whitespace). Never invent dummy cards just to fill a 4-node row.
   - **Causal / Dependency Mechanism**: `flow_dag` (branches, parallel lanes, fork-join merges, labeled edges).
   - **Value Chain / Persistent Chapter Spine**: deck-level `pinned_flow` (centered macro overview -> docked top ribbon via `active_flow_node`) paired with focused deep-dive scenes.
   - **Share / Distribution / Margin Breakdown**: `proportion_bar` (proportional scale + left summary chips).
   - **Multi-Party Quantitative / Strategic Contrast**: `comparison_matrix` (columns, `formula`, `↑`/`↓` trends, `action_banner`, `takeaway`) or side-by-side `comparison`.
   - **Sequential Evolution / Milestones**: `horizontal_flow` (3–5 pillars; unpack 2 children as `row`, 3–4 as `grid`), `architecture_evolution` (`v1 -> v2 -> v3`), or `sequence_timeline` (forward skips + backward loops).
   - **Core + Radiating Factors**: `hub_spoke` (center `variant: "accent"` + 3–6 spokes).
3. **Design the Narrative Arc Across Scenes**:
   For each scene in the Stage 0 brief, define:
   - `claim`: the single takeaway the audience must remember from this scene
   - `protagonist` & `supporting`: what takes visual focus (`variant: "accent"`, `active_flow_node`, `focus_nodes`) vs muted context
   - `transition_intent`: how this scene connects to the previous/next scene (zoom in from `pinned_flow`, unpack evidence, contrast counter-argument, return to synthesis)
4. **Content-to-Visual Fidelity Check (Gate Before Stage 1)**:
   Verify against the source before writing JSON:
   - Did any scene omit the central thesis or key counter-evidence?
   - Are author claims/inferences visually distinguished from verified data?
   - Does every scene add distinct argumentative value (no redundant restatement of the previous scene)?
   - Were any nodes fabricated solely for visual symmetry?

---

## Stage 1: Design Full-State Scene Graphs (Topology & Semantics)

Translate the Stage 0 brief into clean Stage 1 diagrams. Do **not** hand-write `frames` unless custom choreography is required:

1. **Zero-Bullet Canvas**: Each card holds **1 short `label`** (1–4 words / ≤ 12 CJK chars) plus optional micro-hierarchy fields:
   - `badge`: crisp eyebrow tag (e.g., `"FACT"`, `"THESIS"`, `"LEGACY"`, `"TARGET"`, `"STEP 01"`)
   - `metric`: hero number/stat for KPI or single-thesis centerpiece cards (e.g., `"75%"`, `"10×"`, `"0 依赖"`)
   - `sublabel`: brief secondary line (e.g., `"商业常识"`, `"7s → 0.7s"`)
   - `variant`: `"primary"` | `"accent"` (yellow highlight) | `"success"` (teal-green) | `"warn"` (amber) | `"muted"`
   Put all prose explanations, caveats, citations, and presenter context into each node/child's **`note`** field (and scene `intro_note`).
2. **Optional Structural Seed for Long Articles**:
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
