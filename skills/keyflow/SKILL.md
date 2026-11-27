---
name: keyflow
description: Agent-led visual presentation design and native .keyx compilation. Use when turning an article, idea, or data into a bespoke Keynote (.keyx) slide or deck where the agent designs composition, hierarchy, and native visual objects iteratively.
---

# KeyFlow — Agent-Led Visual Design & Native `.keyx` Compiler

KeyFlow v0.4 gives you direct control over native Apple Keynote visual objects (`textbox`, `shape` with primitives or custom SVG Bezier paths, `connection`, `image`, `table`, `chart`, `group`) via `creator-studio-doc-format`. There are **no rigid templates or forced layouts**—you are the designer.

## The 6-Stage Design Loop

1. **Understand Article, Audience & Goal**
   - Identify who is in the room, what decision or mental shift the slide must trigger, and what single core truth must survive a 3-second glance.
2. **Discover Conflict & Establish Visual Concept**
   - Find the central tension (before vs. after, bottleneck vs. flow, scale vs. precision, consensus vs. reality).
   - Form a concrete visual concept & metaphor (e.g., asymmetric split, radial tension, layered depth, typographic hero, annotated diagram).
3. **Decide Composition, Visual Hierarchy & Spatial Relationships**
   - Choose canvas dimensions (default `1920 x 1080`), color palette, typographic scale, negative space, focal point, and z-order.
   - Place objects intentionally using coordinates (`x, y, w, h`), alignment, contrast, and grouping.
4. **Create, Compose & Modify Native Visual Objects**
   - Build the slide iteratively using `DesignSession` / MCP (`design_create`, `design_add_object`, `design_update_object`, `design_group_objects`, `design_reorder_object`) or a declarative `DeckSpec` JSON compiled via `keyflow compile`.
5. **Observe Rendered Result, Critique & Redesign**
   - Render `.keyx` to `.png` (`keyflow compile spec.json -o out.keyx --render previews/` or `design_compile_and_render`).
   - Inspect the rendered PNG visually. Critique legibility, contrast, alignment, breathing room, clipping/overlap, and whether the composition expresses the conflict.
   - Patch, reposition, restyle, or redesign weak elements and re-render until crisp.
6. **Finalize `.keyx`**
   - Output the validated native `.keyx` presentation (plus presenter notes if helpful).

## Native Visual Objects Reference

- `textbox`: Rich text (`string` or `paragraphs` with per-run `font`, `size`, `color`, `bold`, `italic`, `tracking` in em, `hyperlink`, `list_style`), optional `fill`, `stroke`, `shadow`, `padding`, `vertical_alignment`.
- `shape`: `rect`, `rounded_rect`, `pill`, `oval`, `triangle`, `diamond`, `pentagon`, `hexagon`, `octagon`, `star`, `arrow`, or `custom` (arbitrary SVG `path` in `0..1` unit space or custom `path_space`). Supports solid/gradient/image fills, strokes, shadows, reflections, and embedded text.
- `connection`: `straight`, `curved`, or `orthogonal` connectors with `from_point`/`to_point`, optional `from_anchor`/`to_anchor` (`object_id` + `magnet`), and `tail_end`/`head_end` arrowheads/markers.
- `image`: Local image file with optional `mask_shape` (`rect`, `rounded_rect`, `oval`, `custom`), frame `stroke`, `shadow`, `reflection`, `opacity`.
- `table`: Native Keynote table with `columns`, `rows`, per-cell `fill`/`text_color`/`bold`, alternating rows, and custom strokes.
- `chart`: `column`, `bar`, `line`, `area`, `pie`, `donut`, `scatter`, `bubble`, `radar`, `stacked_column`, `stacked_bar`, `stacked_area`, `mixed`.
- `group`: Hierarchical group of any native objects (`children`).

## Quick CLI Commands

- `keyflow schema` — Print the full JSON Schema for `DeckSpec`.
- `keyflow compile design.json -o deck.keyx [--render previews/]` — Compile & validate (and optionally render PNGs).
- `keyflow render deck.keyx -o previews/` — Export `.keyx` to per-slide PNGs via Keynote.
- `keyflow inspect design.json` — Inspect object IDs, types, and bounding boxes.
