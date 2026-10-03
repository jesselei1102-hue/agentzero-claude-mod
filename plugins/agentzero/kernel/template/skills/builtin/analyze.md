---
id: analyze
status: active
source_runs:
  - product:layer-1
memory_ids: []
description: Structure, compare, diagnose or evaluate material already at hand, from Memory, earlier research, or files the operator supplied.
---

# Analyze

Task class: structure given material, compare options, identify patterns, or draw inferences — with all assumptions stated. Shared conventions: `_shared.md`. Chaining: `_routing.md`.

## Trigger & Boundary

Activate when the operator asks to analyze, compare, diagnose, evaluate, assess, or break down material already provided or already available (Memory, prior Research notes, files).

Key distinction from Research: Analyze works with EXISTING material. If the question requires gathering new information first, compose `research` → then Analyze. If critical data turns out to be missing mid-analysis, pause, mark the `[GAP]`, and tell the operator what you need (or propose a Research step) — do not fill the gap with assumptions.

## Step 1: Frame the Analysis

- State the analysis goal in one sentence ("determine which option best fits X" / "identify root causes of Y" / "compare A vs B on these dimensions").
- List all materials in scope: operator content, files, prior Research notes, relevant Memory facts.
- Identify what is NOT in scope.
- State the operator's implied success criteria: what would a USEFUL analysis look like for them?

## Step 2: Choose Analysis Method

Match the question type to a framework **(default — Role may override)**:

| Question type | Framework options |
|---------------|-------------------|
| "Which option?" | Weighted criteria matrix, pros/cons, decision table |
| "Why did this happen?" | Root cause analysis, 5-whys, fishbone |
| "What's the pattern?" | Trend analysis, clustering, timeline mapping |
| "How do these compare?" | Feature matrix, SWOT per option, radar chart |
| "What's the risk?" | Risk matrix (likelihood × impact), scenario analysis |
| "Is this good/bad?" | Benchmark comparison, gap analysis |
| "What could go wrong?" | Pre-mortem, failure mode analysis |

If the material is quantitative, consider whether a statistical summary is needed (mean, distribution, outliers), whether visualization would make patterns clearer, and whether sample size / data quality supports the conclusions.

State the chosen method and WHY before proceeding.

## Step 3: Structure & Decompose

- Organize the material along the chosen framework's axes.
- State ALL assumptions explicitly before inferring:
  - Data assumptions ("treating these numbers as comparable because…")
  - Scope assumptions ("excluding X because…")
  - Causal assumptions ("inferring A causes B because…")
- Where data points conflict, present both rather than silently picking one.

## Step 4: Analyze & Stress-test

For each major finding:

1. State the finding.
2. Label it `[FACT]` / `[INFERENCE]` / `[OPINION]`.
3. Show the evidence chain: data → reasoning → conclusion.
4. Falsify: "This conclusion would be WRONG if…"
5. Steel-man the opposite for the top 2–3 conclusions: "Someone could argue instead that…"

For comparisons: evaluate every option on the SAME dimensions. Avoid pros for Option A and cons for Option B.

## Step 5: Deliver

1. Analysis Summary — the "so what" in 2–3 sentences
2. Method & Assumptions — framework used and what was assumed
3. Findings — organized by the framework, each with evidence pointers and labels
4. Risks & Unknowns — what could change the conclusions; `[GAP]` items
5. Implications / Next Steps — what this means for the operator's decision; offer `report` if a write-up is the natural next builtin

## Critical Thinking

Apply `_shared.md`: separate `[FACT]` / `[INFERENCE]` / `[OPINION]`; never present guesses as measured results; falsify and steel-man major conclusions; mark missing data as `[GAP]` instead of inventing it.

## Anti-patterns

- Force-fit messy reality into a neat framework — if the material does not fit, say so
- Skip the "so what" — structure without interpretation is a spreadsheet, not an analysis
- Self-score; offer Memory/Skill changes only as `proposed` when asked
