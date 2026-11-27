# KeyFlow Visual Design Knowledge Base (Route A as Infrastructure)

> **Purpose**: Equip strong models with visual design judgment, `.keyx` native material craft, and anti-patterns—never rigid layout templates.

## 1. Visual Hierarchy & The 3-Second Test
- **One Unmistakable Focal Point**: At least one element must command immediate attention via **scale (3:1+)**, **luminance contrast**, or **isolation in negative space**.
- **Layering by Luminance, Not Borders**: Separate hierarchy using subtle background luminance steps (`$surface_1`, `$surface_2`), hairline dividers, and typography scale rather than wrapping everything in bordered boxes.
- **Intentional Negative Space**: Whitespace is an active structural tool that groups related items and isolates the focal point.

## 2. Expressive `.keyx` Native Material Craft
- **Layered `Shape` Silhouettes (`BezierPath` + `Gradient` + `Shadow`)**: Build real-world objects from 2–4 layered `Shape`s rather than a single flat box. Remember Keynote `Linear` gradient `angle: 270` flows top-to-bottom.
- **Meaningful `ConnectionLine` Routing**: Use `curved` for converging flows, `orthogonal` for schematic routing, `straight` for direct causal steps. Never route a line across a textbox.
- **Native `Chart` Craft**: A chart's `geometry` is its plot area; leave ~150pt left and ~80pt bottom margin inside panels. Theme defaults (`midnight_indigo`) automatically set legible axis & legend colors.

## 3. Typography & Visual-First Compression
- **Zero Synonymous Repetition**: Keep on-slide text to distilled concepts and conclusions; move all explanatory prose into `SlideSpec.note`.
- **Theme Token References**: Use `"$text_primary"`, `"$accent_primary"`, `"$hero"`, `"$title"`, `"$body"` or override with any explicit hex/size when your visual concept calls for it.
- **Avoid Awkward 1-Character Wraps**: Non-rectangular shapes (`oval`, `pill`, `diamond`) have ~70% inscribed text area; keep labels short or use a dedicated `Textbox`.

## 4. Anti-Patterns to Reject in Critique
1. **Box-in-Box-in-Box**: Nesting rounded-rect cards inside larger bordered panels.
2. **Equal-Weight Everything**: Giving title, diagram nodes, and footnotes similar font sizes.
3. **Orphan Shapes Without Semantic Connection**: Floating decorative icons that encode no `SemanticModel` entity or relation.
4. **Prose Walls on Slide**: Multi-sentence explanations on the canvas instead of presenter `note`.
