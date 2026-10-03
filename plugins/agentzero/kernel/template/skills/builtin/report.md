---
id: report
status: active
source_runs:
  - product:layer-1
memory_ids: []
description: Write a report, memo, brief or summary that synthesizes information for a reader.
---

# Report

Task class: produce a structured, audience-shaped write-up with claims tied to evidence. Shared conventions: `_shared.md`. Chaining: `_routing.md`.

## Trigger

Activate when the operator asks for a report, memo, brief, summary, write-up, or any structured document that synthesizes information for a reader (including the operator themselves).

## Step 1: Scope Lock (ask ONCE if unclear)

Confirm before drafting:

- Audience — who reads this? What do they already know?
- Decision — what will they DO with it? (approve, invest, prioritize, learn, share)
- Format — memo / executive brief / full report / slide narrative
- Length — approximate words or pages
- Tone — formal / conversational / technical **(default — Role may override)**

If more than two are unclear, ask once. Otherwise infer from context and state the inference.

## Step 2: Information Audit

Before outlining, assess what you have vs what you need:

- Load relevant Memory (project facts), Knowledge, prior Research notes, Timeline summaries.
- List the major claims the report must make.
- For each claim: is there evidence? Is it fresh enough?
- If gaps exist, say so: "I need to research X before writing this section" — compose `research` first; do not hide the dependency.

## Step 3: Outline with Evidence Map

Choose a structure pattern by report type **(default — Role may override)**:

- Decision memo: Recommendation → Context → Options → Analysis → Risks
- Progress update: Summary → Accomplishments → Blockers → Next Steps
- Competitive analysis: Overview → Per-competitor → Comparison → Implications
- General brief: Executive Summary → Findings by Topic → Gaps → Next Steps

For each section annotate key claim(s), evidence source (operator material, Knowledge, Tool output, Memory fact id, or `[GAP]`), and confidence (`high` / `medium` / `low`).

## Step 4: Draft

- Lead with the answer: bottom line first, supporting detail below.
- One idea per paragraph; 3–5 sentences max.
- Scannable: headers, bullets, bold key terms (unless the operator prefers otherwise).
- Evidence density: every non-trivial claim gets an inline pointer or an explicit `[GAP]`.
- Where evidence is thin or conflicting, say so in-line — do NOT smooth over with confident prose.
- Match tone to audience: technical → precise language and methodology; executive → implications first, detail in appendix.

## Step 5: Self-check before Delivery

- [ ] Every major claim has an evidence pointer or `[GAP]`
- [ ] `[FACT]` / `[INFERENCE]` / `[OPINION]` are distinguishable
- [ ] No invented citations or fabricated data points
- [ ] Structure matches what the audience needs to DO
- [ ] Length is within the agreed scope
- [ ] "What would falsify the key recommendation?" is addressed, at least briefly

## Step 6: Deliver

- The report in the agreed format
- A short claims-vs-evidence checklist (appendix or inline)
- If sections needed new research, note what was gathered and what remains `[GAP]`
- When the operator asks to **save a file**, write under workspace `work/` (SETTLED #49). Use an ad-hoc subfolder if helpful (e.g. `work/research/`). Do **not** put deliverables in `Grill me/`, `memory/`, or `skills/`.

## Critical Thinking

Apply `_shared.md`: every non-trivial claim needs an evidence pointer or `[GAP]`; no invented citations; state what would falsify the key recommendation; audience tone never overrides honesty about gaps.

## Anti-patterns

- Self-score the report quality
- Write Memory/Skill updates as `active`; offer `proposed` only when the operator asks
- Start drafting before the evidence audit — writing first and fact-checking later produces worse results
