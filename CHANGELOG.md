# Changelog

All notable changes to **KeyFlow** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed (Breaking)
- **Object-First Scene Generation**: `SceneSpec.layout` is now required unless explicit non-null canvas keys (`objects`, `grid`, `regions`, `connectors`) are present; scenes no longer implicitly default to `horizontal_flow`.
- **`outline` Semantic Seed**: `extract_markdown_outline()` now emits an empty-canvas seed (`objects: []`) with `design_constraints` instead of pre-generating `horizontal_flow` cards.

---

## [0.3.3] - 2026-11-27

### Added
- **Editorial Cover Slide (`cover`)**:
  - Added optional root `cover: true | { kicker, title, subtitle, meta, align, accent_bar }` in schema, parsers, and compiler (`_render_cover_slide()`), with `audit_deck` slide-number offset alignment.
- **Agent-Directed Spatial Composition (`geometry`, `anchor`, `z_index`, `group`)**:
  - Added normalized `[0..1]` spatial positioning (`geometry` with `rotation`), 9-point relative `anchor` placement with topological resolution and cycle detection, `z_index` render ordering, and `group` composition identifiers across `keyflow/schema/`, `keyflow/layouts/canvas.py`, and `keyflow/compiler.py`.
  - Upgraded `keyflow/audit/geometry.py` to allow intentional overlap across distinct `z_index` layers while strictly catching same-layer collisions.
- **Three-Tier Audit & Visual Critic Diagnostics**:
  - Added `tier: "engineering" | "content" | "critique"` to `AuditFinding`; `--strict` now blocks only on `engineering` and `content` issues, keeping `critique` findings (`visual_monotony`, `card_text_bloat`, `design_critique`, `intent_form_alignment`) non-blocking.
  - Added non-blocking `design_critique` signals for uncrafted fallback stacks, unmarked forecast series (`2026E`), and flat dense tables.
- **Visual Director -> Critic Workflow**:
  - Replaced closed 10-way `visual_intent` enum with open-ended structured design briefs (`audience_takeaway`, `visual_metaphor`, `visual_focus`, `relationships`, `emotional_tone`).
  - Refactored `keyflow/outline.py` to emit objective `content_signals` without prescribing components, and added `skills/keyflow/references/visual_critic_rubric.md`.

---

## [0.3.2] - 2026-11-27

### Added
- **Batch 1 & Batch 2 Visual Building Blocks**:
  - Added `surface: "accent_bar"` for `card` / `callout` (borderless tinted fill + 4.5px left semantic accent bar).
  - Added `table.cell_tones` (`"good" | "bad" | "neutral" | null`) for semantic cell coloring with contrast-safe text and `table.target_rows` for left target-row accent bars.
  - Added `chart.highlight_categories` and `chart.estimate_from` across `bar`, `column`, `line`, and `area` charts (highlighting target categories, dimming/dashing forecast segments, and shading the forecast region on line/area charts).
  - Added `chart_type: "football_field"` horizontal min–median–max range bar chart with vertical `reference_lines` (`label`, `value`, `color_hex`) and top pill badges.
  - Added `chart_type: "radar"` multi-axis polygon spider chart with concentric grid rings, dashed benchmark polygons, and axis highlighting.
  - Added `chart_type: "progress_bars"` horizontal capsule proportion bars with automatic top-line percentage badges.
  - Added `gauge` mini-widgets on `card` / `callout` (`type: "ring"` circular arc progress gauge and `type: "range"` horizontal slider track with marker dot).
- **Visual Intent Contract & Diversity Audit**:
  - Added `scene.visual_intent` contract, `recommended_visual_intents` signals in [keyflow/outline.py](keyflow/outline.py), `intent_form_alignment` & `visual_monotony` checks in [keyflow/audit/](keyflow/audit/), and Stage 0 Visual Intent guidance in [skills/keyflow/SKILL.md](skills/keyflow/SKILL.md).
- **Design System & Magic Move Hardening**:
  - Added 1.25 modular typography scale, unified 80px margins, elevation tokens, and `border_visibility` / `series_distinguishability` aesthetic audits.
  - Emitted independent per-line textboxes on cards aligned with `group_dashed` Magic Move IDs and baseline stub anchors with unified `corner_px=0.0` paths for smooth Magic Move bar growth.
  - Added `unpack_breakdown` in-place group unpack snippet template.

### Fixed
- **Table & Typography Polish**: Unified table header row strokes, added alternating tint on `highlight_cols`, tightened text-fit factor, and prevented docked ribbon title clipping.
- **Chart & Audit Fidelity**: Fixed `waterfall` and `comparison_matrix` takeaway contrast, centered wide charts, added box textbox geometry audits, and resolved P0 story fidelity gaps.

---

## [0.3.1] - 2026-11-26

### Added
- **Modular Registry Architecture & Reusable Snippets**:
  - Modularized layout solvers, canvas object renderers, schema validators, and audit checks into registry-based packages (`keyflow/layouts/`, `keyflow/objects/`, `keyflow/schema/`, `keyflow/audit/`).
  - Added reusable freeform canvas snippets library (`keyflow/snippets.py`), `surface` styles (`filled`, `ghost`, `borderless`), `card.align`, and canvas `sequence` diagram arcs.
  - Unlocked custom `.json` theme paths and style overrides in `keyflow-mcp`, plus cross-page consistency checks and benchmark suite.

### Changed
- **Theme Visual Differentiation**: Differentiated `midnight_indigo`, `paper_light`, and `slate_dark` visual languages (including monochrome + single-accent refinement and `paper_light` orange contrast boost).

### Fixed
- **MCP Security Hardening**: Hardened MCP path boundaries, isolated builtin snippets, and capped JSON input limits.

---

## [0.3.0] - 2026-11-26

### Added
- **Freeform Compositional Canvas (`layout: "canvas"`, default `use_templates: false`)**:
  - Added 12-column `grid`, non-overlapping `regions` (`stack`, `row`, `grid`), custom `palette` overrides, and 7 composable canvas object types (`card`, `callout`, `textbox`, `shape`, `chart`, `table`, and inline `diagram`) plus cross-object `connectors`.
  - Added `use_templates` toggle (`--use-templates` in CLI, `use_templates: true` in MCP/JSON) to enforce preset-only layouts when desired.
  - Added [examples/freeform_canvas_stage1.json](examples/freeform_canvas_stage1.json) and updated `README.md` / `README.zh-CN.md` / `skills/keyflow/SKILL.md`.
- **10 Data-Driven Chart Types & Native Tables**:
  - Added dual-path chart compilation (`render_mode`: `auto` | `vector` | `native`): static `reveal: "whole"` charts compile as native editable `.keyx` `Chart` objects (including `COLUMNS_AS_SERIES` per-slice `PieChart`/`DonutChart` mapping), while progressive `by_series` / `by_category` charts compile as pure `Shape` + `Textbox` vectors with locked cluster widths for zero-jitter Keynote Magic Move.
  - Added progressive vector `waterfall` chart (`chart_type: "waterfall"`) with cumulative axis bounds, start/total vs. positive/negative delta styling, dashed bridge connectors, zero-baseline rendering, and collision-safe value labels.
  - Added native `.keyx` `Table` compilation with `by_row` / `by_column` progressive reveal and `highlight_rows` / `highlight_cols`.
- **Step Pacing & Inline Diagram Decomposition**:
  - Added `step`-based canvas pacing, progressive `chart` (`by_series` / `by_category`) and `table` (`by_row` / `by_column`) expansion, and node-by-node / layer-by-layer progressive decomposition for inline `diagram` objects in [keyflow/pace.py](keyflow/pace.py).
- **Regression & Packaging Hardening**:
  - Added P1-A Magic Move cross-frame geometry regression harness (`_assert_magic_move_stable`) in [tests/test_keyflow.py](tests/test_keyflow.py).
  - Bundled `keyflow/deck.schema.json` as wheel package data (`pyproject.toml`) with byte-identity test against `schemas/deck.schema.json`, and enabled feature-branch matrix CI in `.github/workflows/ci.yml`.

### Fixed
- **Bright Accent Auto-Contrast**: Added `_readable_text_rgb()` in [keyflow/compiler.py](keyflow/compiler.py) so bright `accent_fill_hex` or card fills automatically select dark legible text in `callout`/`card` payloads and `table.highlight_rows`.
- **Strict Schema Validation**: Added `_as_int()`, finite `_as_float()`, `_is_in()` unhashable enum/ref guards, chart axis/series checks, table highlight index bounds, region overlap detection, and `frames[].object_states` ref validation in [keyflow/schema.py](keyflow/schema.py).

---

## [0.2.0] - 2026-11-26

### Added
- **Stage 0 Narrative Brief & Structured `story_model` Contract**:
  - Formalized the three-stage narrative workflow (**Stage 0** Narrative Brief → **Stage 1** Scene Graph → **Stage 2** Progressive Pacing & Visual Audit) in [skills/keyflow/SKILL.md](skills/keyflow/SKILL.md) and [skills/keyflow/references/narrative_brief_template.md](skills/keyflow/references/narrative_brief_template.md).
  - Added optional root `story_model` (`core_question` + `claims` with `id`, `type`, `claim`, `source_quote`, `source_id`, `metric_scope`, `confidence`), per-scene `claim` & `metric_scope`, and element-level `evidence_refs` across [keyflow/schema.py](keyflow/schema.py) and [schemas/deck.schema.json](schemas/deck.schema.json).
- **Two-Tier Visual & Fidelity Audit Engine (`keyflow/audit.py`)**:
  - Added Tier 1 deterministic checks for canvas bounds, box/group/edge-label collisions, typography scale, text wrap overflow, narrow proportion segments, and cross-frame anchor stability (covering boxes, persistent edges, dividers, `proportion_bar`, `comparison_matrix`, and intra/cross-scene `pinned_flow` transitions).
  - Added automated `story_model` fidelity checks (`epistemic_mismatch`, `scope_mixing`, `unsourced_fact`, `dropped_story_claim`).
  - Added structured `target_id` and `suggested_action` hints on findings plus targeted `review_slides` / `review_pngs` routing across CLI (`keyflow audit`, `keyflow compile --preview-dir`) and MCP (`audit_storyboard`, `compile_keyx`).
  - Added compilation quality gates (`--fail-on-audit`, `--strict` in CLI; `fail_on_audit`, `strict` in MCP `compile_keyx`).
- **Mermaid & Single-Hero Layout Enhancements**:
  - Automatically folds 2–4 symmetric fan-out/convergence siblings in Mermaid flowcharts into grid/row group containers inside [keyflow/outline.py](keyflow/outline.py).
  - Added centerpiece sizing for single-card `metrics_cards` hero stat/thesis slides in [keyflow/layout.py](keyflow/layout.py).

### Changed
- **Compact Vector Master Backgrounds (~1,900× Smaller `.keyx`)**:
  - Replaced per-slide `1920×1080` inline base64 PNG noise backgrounds with a single shared vector gradient or solid `Fill` preset (`keyflow_bg_fill` in `presets.json`) while keeping `KeynoteTheme(name="White", locale="en_US")` metadata valid so Keynote opens decks cleanly with no theme warnings and ~15–25 KB archives instead of ~10–28 MB.
- **Single-Source Schema Contract**:
  - Updated `validate_deck()` in [keyflow/schema.py](keyflow/schema.py) to load allowed property sets directly from [schemas/deck.schema.json](schemas/deck.schema.json) and reject unknown fields across all object levels.
- **Documentation & Examples**:
  - Updated [examples/genres_showcase_stage1.json](examples/genres_showcase_stage1.json) to reflect all 10 supported layout modes and updated `README.md` / `SKILL.md`.

### Fixed
- **Topological Ordering & Cycle Detection (`flow_dag`)**: Replaced input-order-dependent parent resolution in `pace.py` and `layout.py` with Kahn's topological sort (`compute_dag_layers`) and rejected cyclic `flow_dag` dependencies during validation.
- **AppleScript Argument Safety**: Updated `export_slide_pngs()` in [keyflow/compiler.py](keyflow/compiler.py) to pass paths via `osascript -e ... <src> <out>` (`on run argv`) instead of string interpolation.
- **Defensive Schema Type Handling**: Hardened `validate_deck()` against malformed non-dict, non-list, boolean, or non-numeric LLM inputs so invalid payloads return clean `ValidationResult` errors.
- **YAML Frontmatter Stripping**: Updated [keyflow/outline.py](keyflow/outline.py) to strip leading YAML/Obsidian frontmatter (`--- ... ---`) before extracting titles and taglines.
- **MCP Pacing Status & Workspace Boundary**: Fixed `pace_storyboard` to return `paced: False` (and avoid writing invalid output) when post-pacing validation fails, and added optional `--workspace` / `KEYFLOW_MCP_WORKSPACE` root containment checks to [keyflow/mcp_server.py](keyflow/mcp_server.py).

---

## [0.1.0] - 2026-11-25

### Added
- **Two-Stage Article-to-Keynote Pipeline**:
  - Stage 1 Markdown skeleton & Mermaid extractor (`keyflow outline`) and full-state Scene Graph DSL.
  - Stage 2 deterministic progressive frame expansion (`keyflow pace`) supporting `standard` and `compact` densities.
- **10 Visual Layout Primitives & 3 Built-in Themes**:
  - Layouts: `horizontal_flow`, `vertical_flow`, `flow_dag`, `comparison`, `comparison_matrix`, `proportion_bar`, `metrics_cards`, `hub_spoke`, `architecture_evolution`, and `sequence_timeline`, plus deck-level `pinned_flow` context ribbon.
  - Themes: `slate_dark`, `midnight_indigo`, and `paper_light`.
- **Native `.keyx` Compiler & Magic Move Alignment**:
  - Layout-first geometry solver (`keyflow/layout.py`) ensuring zero element coordinate jitter across progressive steps.
  - Open-path `Shape` line and quadratic Bezier arc rendering (`keyflow/compiler.py`) for reliable Keynote Magic Move transitions.
- **CLI, Stdio MCP Server & CI**:
  - `keyflow` CLI and `keyflow-mcp` JSON-RPC 2.0 stdio server (`list_themes`, `extract_outline`, `pace_storyboard`, `validate_storyboard`, `compile_keyx`, `preview_keyx`).
  - Initial `pytest` suite and GitHub Actions CI matrix across Ubuntu & macOS (Python 3.13 / 3.14).
