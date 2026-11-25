# Stage 0 Narrative Brief Template & Fidelity Checklist

Use this template **before** writing Stage 1 Scene Graph JSON. Keep it concise — the goal is crisp argumentative clarity, not prose bloat.

## 1. Epistemic Extraction & Source-Grounding Schema

Distill the article into atomic semantic units, binding every number or factual claim to its source quote so hypotheses or unverified stats never leak in:

```json
{
  "claim": "Starlink accounts for ~79% of Falcon 9 missions in 2026 (up from ~54% in 2020)",
  "evidence_type": "reported_fact",
  "metric_scope": "Falcon 9 launch mission count share (%)",
  "source_quote": "2026年，Starlink 已经占到猎鹰9号任务的大约79%，而2020年这一比例约为54%。",
  "confidence": "high"
}
```

| Type | Meaning | Visual Treatment in KeyFlow |
| :--- | :--- | :--- |
| `thesis` | Core question or central claim of the piece | Highlight early (`accent` or single-card `metrics_cards` with `badge: "THESIS"`); revisit at conclusion |
| `fact` / `metric` | Verifiable numbers, dates, or primary observations with explicit `source_quote` | Put exact numbers in `metric` or `proportion_bar` / `comparison_matrix`; keep `badge: "FACT"` and enforce one `metric_scope` per slide |
| `relation` | Upstream/downstream dependencies, resource contention, causal forks | `pinned_flow` (macro chain) or branching `flow_dag` (diverging/converging paths) with labeled edges |
| `inference` | Author deduction, attribution, or projection | Mark with `badge: "INFERENCE"` / `"CLAIM"` or `variant: "warn"` / `"accent"`, and qualify explicitly in `note` |
| `counter_evidence` | Bottlenecks, exceptions, or rival explanations | Dedicated `comparison` / `comparison_matrix` contrast column (`is_baseline` or `variant: "warn"`) |
| `conclusion` | Synthesized verdict preserving source qualifiers | Final scene keeping exact scope qualifiers (`"partially"`, `"gradually"`) instead of overclaiming absolutes |

---

## 2. Visual Form Selection Matrix (Logic First)

| Logical Pattern | Preferred KeyFlow Layout | Anti-Pattern to Avoid |
| :--- | :--- | :--- |
| Single startling stat or core conclusion | `metrics_cards` (`1–2` cards) | Forcing 3–4 filler boxes to make a diagram look busy |
| Resource fork / capacity crowding / causal split | Branching `flow_dag` (fork & merge paths) | Flattening a capacity split into a generic 4-step linear row |
| Value chain / persistent context + deep dives | Deck `pinned_flow` + scene `active_flow_node` | Repeating the full chain diagram from scratch on every slide |
| Single-denominator share or cost breakdown | `proportion_bar` (strictly one `metric_scope`) | Mixing revenue share and mission share on the same chart |
| Multi-company / baseline vs. target contrast | `comparison_matrix` (`≤ 3` columns) or `comparison` | Mixing actual price and long-term target cost without labels |
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

Before finalizing Stage 1 JSON, confirm all seven checks:
1. **No Dropped Spine**: Core thesis, decisive metrics, competitor/market context, and strongest counter-evidence are all represented.
2. **Source Grounding**: Every key statistic or factual statement traces to an explicit `source_quote` (or explicit model assumption).
3. **Metric-Scope Isolation**: Each chart/slide enforces one denominator/era (`metric_scope`); revenue share and unit share are never blurred into one visual claim.
4. **Anti-Overclaim Alignment**: Headlines, badges, and takeaways preserve original qualifiers (`"partially"`, `"gradually"`, `"design target"`) without escalating them into absolutes.
5. **Fact vs. Inference Separation**: Speculative claims carry explicit qualifiers (`badge` / `note`), never presented identically to raw data.
6. **Visual Variety with Intent**: Consecutive scenes vary layout form from logic first (fork/split DAG, proportion, scale contrast, synthesis).
7. **Zero Filler Nodes & Magic Move Continuity**: Every card earns its pixels, and `pinned_flow` preserves IDs cleanly across scenes.
