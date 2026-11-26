# Changelog

All notable changes to **KeyFlow** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
