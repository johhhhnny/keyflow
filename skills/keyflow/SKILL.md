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
2. **Direct Like a Documentary Visual Designer (Open `visual_intent`, Not Component Lookup)**:
   Think like a commercial documentary director: understand the author's core conflict, causal mechanism, or surprising contrast, then **invent the visual language** that makes the audience *see* it immediately.
   - **Never map logic types mechanically to fixed templates**: Do not treat "profit -> waterfall" or "risks -> hub_spoke" as rules. You have full agency to **reject every preset layout and snippet** and compose freely with raw typography, shapes, charts, tables, and connectors.
   - **Express `visual_intent` as an open design brief** on each scene (instead of picking from a closed enum):
     ```json
     "visual_intent": {
       "audience_takeaway": "What the viewer must grasp in 3 seconds",
       "visual_metaphor": "Spatial or visual analogy (e.g. profit pool vs upstream/downstream squeeze)",
       "visual_focus": "What commands primary visual weight",
       "relationships": ["Entity A -> Entity B tension or flow"],
       "emotional_tone": "Investigative, restrained, high-contrast"
     }
     ```
   - **Full Visual Vocabulary Available When Needed**:
     - **Object-First Canvas (`layout: "canvas"`, default `use_templates: false`)**: Every visible primitive is an explicit object with an explicit `kind`. Supports two parallel spatial modes on the same slide:
       1. **Auto-Region Mode**: 12-column `grid` + non-overlapping `regions` (`stack`, `row`, `grid`) for structured cards, tables, and charts.
       2. **Agent-Directed Spatial Composition Mode**: Place any object freely via normalized `geometry` (`{"x", "y", "width", "height", "rotation"}` in `[0..1]` safe canvas), `anchor` (`{"to", "point", "offset_x", "offset_y", "width", "height"}`), `z_index` (layering order), and `group` (logical composition unit). Different `z_index` layers may overlap intentionally (e.g., background `shape` behind foreground `textbox`/callouts).
       Available primitives: `card` / `callout` (`surface`: `"filled" | "ghost" | "borderless" | "accent_bar"`, optional `gauge`: `{"type": "ring" | "range", ...}`), `textbox` (`font_size` in `10–140`), `shape` (`rounded_rect`, `rect`, `ellipse`, `pill`, or custom `svg_path`), `chart` (13 types: `column`, `bar`, `pie`, `donut`, `line`, `area`, `stacked_column`, `stacked_bar`, `scatter`, `waterfall`, `football_field`, `radar`, `progress_bars`, with `highlight_categories`, `estimate_from`, `reference_lines`), `table` (`cell_tones`, `target_rows`, `highlight_cols`, `highlight_rows`), inline `diagram`, `connectors`, and custom `palette`.
     - **10 Built-in Preset Layouts (optional tools, never mandatory defaults)**: `metrics_cards`, `flow_dag`, `pinned_flow`, `proportion_bar`, `comparison_matrix`, `comparison`, `horizontal_flow`, `vertical_flow`, `architecture_evolution`, `sequence_timeline`, `hub_spoke`. Use `use_templates: true` only when enforcing strict preset-only decks.
3. **Design the Narrative Arc Across Scenes**:
   For each scene in the Stage 0 brief, define:
   - `visual_intent`: open-ended design description (`audience_takeaway`, `visual_metaphor`, `visual_focus`, `relationships`, `emotional_tone`)
   - `claim`: the single takeaway the audience must remember from this scene
   - `metric_scope`: exact denominator/unit/era when numbers appear
   - `source_quote`: verbatim anchor from the source text backing every metric or factual claim
   - `protagonist` & `supporting`: what takes visual focus (`variant: "accent"`, `active_flow_node`, `focus_nodes`) vs muted context
   - `transition_intent`: how this scene connects to the previous/next scene
4. **Content-to-Visual Fidelity & Anti-Overclaim Check (Gate Before Stage 1)**:
   Verify against the source before writing JSON:
   - Did any scene omit the central thesis, key competitors/market context, or counter-evidence?
   - **Source Traceability**: Does every number and fact trace to an explicit `source_quote` in the input (no ungrounded filler stats)?
   - **Metric-Scope Purity**: Does each numeric scene stick to one denominator/timeframe without mixing incompatible percentages?
   - **Anti-Overclaim Alignment**: Do titles, badges, and headlines preserve original qualifiers ("partially stopped", "gradually phasing out", "design target") rather than escalating them into absolutes?
   - Are author claims/inferences visually distinguished from verified data, with zero redundant restatements or fabricated padding nodes?

---

## Stage 1: Design Full-State Scene Graphs (Visual Director -> Critic Loop)

Before finalizing Stage 1 JSON, run the **Director -> Critic** loop (see `references/visual_critic_rubric.md`):
- **Sketch 2–3 Visual Metaphors for Pivotal Scenes**: For central thesis, value-chain conflict, or valuation synthesis slides, briefly compare 2–3 distinct compositions (e.g., asymmetric `geometry`/`anchor`/`z_index` spatial gravity vs. `football_field`/`progress_bars` scale vs. `radar`/matrix) and pick the one with the fastest 3-second comprehension.
- **Critique Before Tweaking**: If a slide looks like "boxes stacked in a grid" with no focal point, **redesign the spatial composition** rather than tweaking font sizes.

Translate the Stage 0 brief into clean Stage 1 scenes. Do **not** hand-write `frames` unless custom choreography is required:

1. **No Default Visual Primitive**: Explicitly choose `layout` and, for every visible canvas primitive, `kind`. Canvas may be inferred only from explicit canvas fields; a `nodes` list never implies a card layout. Do not turn headings, claims, or entities into cards by default. Begin with the argument and choose among typography (`textbox`), spatial geometry (`shape`), data displays (`chart`/`table`), diagrams, or a card only when a bounded information unit genuinely benefits from a container. A card is an opt-in choice, not a generic node renderer. If a composition is not yet justified, leave `objects` empty in the Stage 1 seed rather than inventing cards.
   When a card is intentionally selected, keep it to **one short `label` line** (1–4 words / ≤ 12 CJK chars). Do **not** pack `badge + label + sublabel` onto every card—move explanations into `note` (Presenter Notes). Add extra text layers only when they serve an explicit visual purpose:
   - `children` in-place unpack (total -> parts decomposition across frames);
   - `badge`: crisp epistemic or sequence tag (e.g., `"FACT"`, `"THESIS"`, `"COUNTER"`, `"STEP 01"`);
   - `metric`: hero number/stat for KPI or single-thesis centerpiece blocks (e.g., `"75%"`, `"10×"`, `"0 依赖"`);
   - `sublabel`: brief secondary line only when needed for `callout` or `metric` context;
   - `variant`: `"primary"` | `"accent"` (yellow highlight) | `"success"` (teal-green) | `"warn"` (amber) | `"muted"`
   - `surface`: `"filled"` (solid container) | `"ghost"` (border-only lightweight frame) | `"borderless"` (no fill/border; prefer open editorial typography for hero stats and core thesis statements instead of wrapping them in cards)
   Put all prose explanations, caveats, citations, and presenter context into each node/child's **`note`** field (and scene `intro_note`).
2. **Structured Story Model & Evidence Grounding (Recommended for Analytical Decks)**:
   Include optional `story_model` at the deck root (`core_question`, `claims`: `id`, `type`, `claim`, `source_quote`, `metric_scope`, `confidence`), set per-scene `claim` & `metric_scope`, and link elements via `evidence_refs: [...]`. `keyflow audit` automatically enforces epistemic alignment (e.g., rejects `badge: "FACT"` pointing to an `inference` claim), flags `scope_mixing` across incompatible denominators, warns on `unsourced_fact`, and catches dropped `thesis` / `counter_evidence` claims.
3. **Optional Cover Slide (`cover`)**:
   Set root `"cover": true` or `"cover": {"kicker": "...", "title": "...", "subtitle": "...", "meta": "...", "align": "left" | "center", "accent_bar": true}` to generate an editorial cover slide as Slide 1 (omitted by default).
4. **Freeform vs. Template Mode (`use_templates`)**:
   `use_templates` defaults to `false`, enabling `layout: "canvas"`, `palette`, native/vector `chart`, native `table`, and inline `diagram`. Pass `--use-templates` (CLI) or `use_templates: true` only when validating strict preset-only decks.
4. **Optional Structural Seed for Long Articles**:
   Run `uv run keyflow outline -i article.md --stage1 -o starter.json` (or MCP `extract_outline`) only as a mechanical starting skeleton — replace generic chapter summaries with your Stage 0 narrative plan.
5. **Reusable Canvas Snippets (`keyflow snippets`)**:
   Instead of authoring 12-column `grid`/`regions` from scratch, inspect built-in canvas templates via `uv run keyflow snippets` (or `--show <id>` / MCP `list_snippets`): `chart_with_takeaway`, `two_column_counter`, `kpi_waterfall_breakdown`, `architecture_with_table`, `thesis_evidence_matrix`, and `unpack_breakdown`. Each snippet is pre-audited for strict Magic Move alignment and contrast.
   - **In-Place Unpack (`children`)**: When decomposing a concept into 2–4 sub-capabilities ("whole -> parts"), use `node.children` only when an explicit node-based diagram/layout is the best fit; otherwise compose the parent and parts as independently typed canvas objects rather than defaulting to nested cards.
   - **Nonlinear Flows (`sequence`)**: Inside `canvas` `diagram`, use `diagram_layout: "sequence"` whenever expressing forward-skip or backward-retry loops.

---

## Stage 2: Progressive Pacing, Quality-Gated Compile & Fidelity Loop

Once the Stage 1 topology satisfies your Stage 0 narrative check, run the **2-tier verification loop**:

1. **Three-Tier Audit (Engineering vs. Content vs. Critique)**:
   - Run `audit_storyboard` (MCP) or `uv run keyflow audit -i stage1.json --strict` before rendering.
   - `engineering` (bounds, collisions, coordinate stability) and `content` (`story_model` fidelity, scope mixing) findings block `--strict` compilation and must be fixed.
   - `critique` findings (`visual_monotony`, `card_text_bloat`, `intent_form_alignment`) are **non-blocking design reflections**: if repeating a layout serves rigorous horizontal comparison across entities, keep it intentionally; otherwise use it as a cue to sharpen visual hierarchy.
2. **Tier 2 Keynote Render & Targeted PNG Inspection (macOS)**:
   - Expand and compile with audit gate enabled via `pace_storyboard` -> `compile_keyx(..., preview_dir=..., fail_on_audit=True)`, or CLI:
     ```bash
     uv run keyflow pace -i stage1.json -o storyboard.json --density standard
     uv run keyflow compile -i storyboard.json -o output.keyx --fail-on-audit --preview-dir ./preview
     ```
   - Inspect the PNGs listed in `audit.review_pngs` (all flagged slides plus slide 1 and each scene's final slide) for real Keynote text wrapping, breathing room, visual balance, connector clarity, and fidelity to the Stage 0 argument; make targeted node/scene edits and recompile once if needed.
