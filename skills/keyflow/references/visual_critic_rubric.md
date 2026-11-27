# Visual Director & Critic Rubric

Use this rubric during **Stage 1** (before committing to a single layout) and **Stage 2** (when reviewing `review_pngs` and `critique`-tier audit signals).

---

## 1. The Visual Director Loop (For Pivotal / Complex Scenes)

For high-stakes scenes (central thesis, value-chain conflict, multi-force trade-off, valuation synthesis):

1. **Sketch 2–3 Distinct Visual Metaphors** before writing JSON:
   - *Option A (Spatial Gravity / Relationship)*: Center protagonist on `z_index: 1` over a subtle background `shape` (`z_index: -1`), flanked asymmetrically by opposing forces (`geometry` + `anchor` + weighted `connectors`).
   - *Option B (Scale / Bridge / Range)*: Contrast magnitude or valuation gaps with `football_field`, `progress_bars`, `waterfall`, or `>= 60pt` borderless hero typography.
   - *Option C (Structured Matrix / Multi-Dim)*: Compare entities across consistent dimensions via `radar`, `comparison_matrix`, or `table` with `target_rows` / `cell_tones`.
2. **Pick on Comprehension Speed, Not Familiarity**: Choose the metaphor that lets a viewer grasp the tension or conclusion in **under 3 seconds**, not the easiest 4-card grid.

---

## 2. The Visual Critic Checklist (Redesign vs. Micro-Fix)

Ask these five questions when inspecting `critique` findings and rendered PNGs:

| Question | If "No" → Action |
| :--- | :--- |
| Does this slide express the scene's core conflict or mechanism without reading body prose? | **Redesign composition** (change visual metaphor or spatial hierarchy, do not just tweak font size). |
| Is there an unmistakable primary focal point (`visual_focus`) and receding context? | Use `z_index`, `surface: "borderless"` / `"accent_bar"`, `highlight_categories`, or `target_rows` to separate protagonist from background. |
| Are objects placed deliberately (`geometry`, `anchor`, or explicit `regions`) rather than dumped into the default stack? | Author explicit spatial relationships or purposeful `regions`. |
| If consecutive slides share the same layout, does that repetition serve deliberate horizontal comparison? | If yes, keep it intentionally; if not, vary the visual rhythm. |
| Can any redundant card, border, or decorative label be removed without losing meaning? | Strip clutter; move prose explanations into `note` (Presenter Notes). |
