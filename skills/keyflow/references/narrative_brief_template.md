# Stage 0 Narrative Brief Template & Fidelity Checklist

Use this template **before** writing Stage 1 Scene Graph JSON. Keep it concise — the goal is crisp argumentative clarity, not prose bloat.

## 1. Epistemic Extraction Table

Distill the article into atomic semantic units so hypotheses are never disguised as facts:

| Type | Meaning | Visual Treatment in KeyFlow |
| :--- | :--- | :--- |
| `thesis` | Core question or central claim of the piece | Highlight early (`accent` or single-card `metrics_cards` with `badge: "THESIS"`); revisit at conclusion |
| `fact` / `metric` | Verifiable numbers, dates, or benchmark observations | Put exact numbers in `metric` or `proportion_bar` / `comparison_matrix`; keep `badge: "FACT"` when contrasting against claims |
| `relation` | Upstream/downstream dependencies, causal links, trade-offs | `pinned_flow` (macro chain) or `flow_dag` / `horizontal_flow` with labeled edges |
| `inference` | Author deduction, attribution, or projection | Mark with `badge: "CLAIM"` / `"INFERENCE"` or `variant: "warn"` / `"accent"`, and qualify explicitly in `note` |
| `counter_evidence` | Bottlenecks, exceptions, or rival explanations | Dedicated `comparison` / `comparison_matrix` contrast column (`is_baseline` or `variant: "warn"`) |
| `conclusion` | Synthesized verdict conditioned on evidence | Final scene re-docking `pinned_flow` or high-contrast synthesis card |

---

## 2. Visual Form Selection Matrix

| Logical Pattern | Preferred KeyFlow Layout | Anti-Pattern to Avoid |
| :--- | :--- | :--- |
| Single startling stat or core conclusion | `metrics_cards` (`1–2` cards) | Forcing 3–4 filler boxes to make a diagram look busy |
| Value chain / persistent context + deep dives | Deck `pinned_flow` + scene `active_flow_node` | Repeating the full chain diagram from scratch on every slide |
| Profit / cost / latency share breakdown | `proportion_bar` | Listing percentages as disconnected bullet cards |
| Multi-company / multi-strategy quantitative comparison | `comparison_matrix` (`≤ 3` columns) or `comparison` | Mixing prose paragraphs inside narrow cards |
| Causal loops / parallel execution / bottlenecks | `flow_dag` (use `child_layout: "grid"` for fan-out) | Linear `horizontal_flow` hiding branches and dependencies |
| Chronological eras or protocol rounds | `architecture_evolution` or `sequence_timeline` | Static timeline bullets without forward/backward transitions |

---

## 3. Worked Narrative Brief Sketch (Example: Industry Value-Chain Profit Debate)

```yaml
article_question: "Does one chip leader capture most AI infrastructure profits, and why?"
deck_arc:
  - scene_id: macro_chain
    role: overview
    claim: "AI compute value flows through five linked stages from lithography to cloud."
    visual_form: "pinned_flow (centered macro overview, no scene body cards)"
    protagonist: "Full 5-node value chain"
    transition_intent: "Establish shared mental map before zooming in."

  - scene_id: hero_margin_claim
    role: thesis
    claim: "Core hypothesis: compute silicon captures ~70%+ of incremental hardware gross profit."
    visual_form: "metrics_cards (1–2 hero cards: FACT vs THESIS)"
    protagonist: "Hero gross-margin stat + explicit HYPOTHESIS badge"
    transition_intent: "Pin macro chain to top ribbon; highlight GPU node."

  - scene_id: profit_split
    role: evidence
    claim: "Compare estimated profit pool share across lithography, foundry, HBM, GPU, and cloud."
    visual_form: "proportion_bar (with pinned_flow docked on top)"
    protagonist: "GPU segment vs memory/foundry segments"
    transition_intent: "Ground the thesis quantitatively."

  - scene_id: pricing_power_vs_counter
    role: contrast
    claim: "High margin reflects CUDA lock-in & scarcity, offset by hyperscaler custom ASIC pressure."
    visual_form: "comparison_matrix (Bull Thesis vs Counter-Evidence columns)"
    protagonist: "Moat metrics vs CapEx/ASIC risk rows"
    transition_intent: "Prevent one-sided cherry-picking before synthesis."

  - scene_id: causal_verdict
    role: synthesis
    claim: "Profit concentration holds near-term while ecosystem lock-in outpaces ASIC substitution."
    visual_form: "flow_dag (or comparison verdict)"
    protagonist: "Causal condition leading to verdict"
    transition_intent: "Close loop back to original thesis."
```

---

## 4. Pre-Compile Fidelity Checklist

Before finalizing Stage 1 JSON, confirm all five checks:
1. **No Dropped Spine**: Core thesis, decisive metrics, and strongest counter-evidence are all represented.
2. **Fact vs. Inference Separation**: Speculative claims carry explicit qualifiers (`badge` / `note`), never presented identically to raw data.
3. **Visual Variety with Intent**: Consecutive scenes vary layout form to match shifting reasoning (chain -> proportion -> contrast -> synthesis).
4. **Zero Filler Nodes**: Every card earns its pixels; single-thesis beats use `1–2` hero `metrics_cards` instead of padded triads.
5. **Progressive Magic Move Continuity**: Where an overview maps to deep dives, deck-level `pinned_flow` preserves IDs cleanly for Keynote Magic Move.
