# KeyFlow v0.4.0+ Development Roadmap

## Current Focus: Single-Slide Visual Intelligence (Raising the Ceiling)
- **Intent-Driven 5-Stage Pipeline**: `SemanticModel` (Intent Model) → `VisualConcept` (Rhetorical Intent + Multi-Candidate Divergence) → `Scene Graph` → `Geometry & KEYX Compiler` → `Intent Critic & Design Critic`.
- **Global Theme System (`keyflow/themes/`)**: Component-agnostic config files (`midnight_indigo.json`, etc.) managing background, contrast-checked color tokens, typography scale, canvas rhythm, and chart/connector defaults—overridable at any time.
- **Visual Design Knowledge Base** (`skills/keyflow/references/visual_craft.md`): Principles, `.keyx` native material craft, and anti-patterns to elevate strong models to editorial/infographic-grade visual expression.

## Planned: Deterministic Floor-Raising Infrastructure (Without Restricting Composition)
1. **Shape & Textbox Safe Sizing (`auto_fit`)**: Optional deterministic box/font auto-fitting respecting inscribed geometry of non-rectangular shapes (`oval`, `pill`, `diamond`, `octagon`).
2. **Connector Midpoint & Anchor Snapping**: Automatic endpoint resolution from `from_anchor`/`to_anchor` + object geometry.
3. **Theme Contrast Verification**: Automated foreground-vs-background contrast checks against `theme.constraints.min_contrast_ratio`.

## Deferred (Post-0.4.0)
- **Multi-Slide Narrative & Magic Move Continuity**.
- **Visual Reference Retrieval & Experience Accumulation**.
