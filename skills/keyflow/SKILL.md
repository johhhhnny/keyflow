---
name: keyflow
description: KeyFlow 0.4.0 — Single-Slide Visual Intelligence. Turn any meaningful text into a bespoke, professionally designed Keynote (.keyx) static slide through a 6-stage creativity-driven design loop.
---

# KeyFlow 0.4.0 — Single-Slide Visual Intelligence

KeyFlow 0.4.0 focuses on one foundational problem: **given a piece of text, can the Agent truly understand it, decide the most fitting visual expression, compose native Keynote visual objects, and produce a professional static slide (`.keyx`)?**

Multi-slide pacing and animations are intentionally deferred. The architecture preserves **Scene Graph**, **Semantic Identity**, and **Composition Model** so future multi-slide and motion layers build seamlessly on top.

## Core Philosophy

- **Creativity-Driven (Route B at the core, Route A as infrastructure)**: You are a visual designer, not a template-filling machine. Design principles, typography, and geometry checks support your decisions—they never dictate a fixed layout.
- **Anti-Card-Templating**: Never default to `title + 3 cards + icon` when a diagram, asymmetric hero visual, chart, comparison axis, typographic statement, or minimal whitespace composition expresses the idea better.
- **Native Primitives as Building Blocks**: `textbox`, `shape` (including custom SVG `BezierPath`), `connection`, `image`, `table`, `chart`, and `group` are raw expressive primitives—combine them freely.

## The 6-Stage Decoupled Workflow

Each stage has its own input, output, and evaluation standard:

| Stage | Input | Output | Evaluation Standard |
| :--- | :--- | :--- | :--- |
| **1. Semantic Understanding** | Raw text, facts, or thesis | `SemanticBriefSpec` (`design_set_brief`): core thesis, key facts, causal/contrast/comparison relations, visual subject, what stays text vs. becomes visual | Did it capture the core truth without distorting or omitting key facts? |
| **2. Visual Concept** | `SemanticBriefSpec` | `CompositionSpec` (`design_set_composition`): visual metaphor, central tension, expression form (open-ended), visual hero | Does the visual form genuinely fit the content with originality? |
| **3. Composition** | `CompositionSpec` | Scene Graph (`SlideSpec.objects` + `SemanticIdentity` on each object): spatial structure, focal point, L1/L2/L3 hierarchy, color & typography, reading order | Does it establish clear visual hierarchy and intentional spatial relationships? |
| **4. Layout & Geometry** | Scene Graph | `audit_slide_geometry()` (`geometry_notes`): exact coordinates, text-fit estimation, out-of-bounds & sibling collision checks | Is every object geometrically precise, unclipped, and conflict-free? |
| **5. KEYX Compiler** | Validated Scene Graph | Native `.keyx` via `creator-studio-doc-format` (`compile_deck` / `design_compile_and_render`) | Does it compile cleanly and pass `validate_document`? |
| **6. Visual Critique & Revision** | Rendered PNG (`KEYFLOW_RENDER_PNG=1` or `--render`) | Visual critique + targeted patches (`design_update_object`, `design_reorder_object`, etc.) | Can a viewer grasp the core message in 3 seconds? Is the focal point dominant? Are there unnecessary elements or dead whitespace? |

## Architectural Foundations Preserved

1. **Scene Graph**: Ordered hierarchy of native objects and `GroupSpec` nodes in `SlideSpec.objects`.
2. **Semantic Identity (`semantic`)**: Optional metadata on every object (`role`, `meaning`, `hierarchy`, `source_claim`) explaining *why* it exists.
3. **Composition Model (`composition`)**: Slide-level record of `visual_concept`, `central_tension`, `expression_form`, `focal_point`, and `reading_order`.

## Evaluation Reference

See [eval_rubric.md](references/eval_rubric.md) for the 8 single-slide design test archetypes and 5 quality metrics.
