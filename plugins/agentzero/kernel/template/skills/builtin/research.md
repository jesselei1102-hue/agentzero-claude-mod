---
id: research
status: active
source_runs:
  - product:layer-1
memory_ids: []
description: Look something up, investigate a question, or gather and compare evidence across sources — not a single-search fact lookup.
---

# Research

Task class: investigate a question using structured multi-step retrieval and synthesis. Shared conventions: `_shared.md`. Chaining: `_routing.md`.

## Trigger & Scope

Activate when the operator asks to research, look up, compare across sources, investigate, or gather evidence on a topic. NOT for simple fact-lookups (single-search answers) — handle those inline.

## Step 1: Understand & Classify

- Restate the question and success criteria in 1–2 sentences.
- Identify what would falsify a premature answer.
- Classify complexity:
  - SIMPLE: single fact, 1–3 searches sufficient → answer directly
  - STANDARD: 3–5 sub-questions, multiple sources → structured plan
  - DEEP: 5–15 sub-questions, cross-domain synthesis → full workflow

## Step 2: Decompose & Plan

- Break the question into independently researchable sub-questions (aim 5–15 for DEEP).
- For each sub-question:
  - Priority: P1 = blocks others, P2 = important, P3 = nice-to-have
  - Candidate sources: Knowledge, Tools, web, operator materials
  - What you will NOT invent or assume
- Load relevant Memory (project facts) and Knowledge. Query Timeline only if the question is about past runs.
- State the plan in the reply before executing.

## Step 3: Search & Gather

- Start broad, then narrow: short general queries first, refine on what is available.
- Per sub-question:
  - Execute searches; record each query tried.
  - For each piece of evidence record: source (URL / doc / tool output), authority tier per `_shared.md` **(default — Role may override)**, date/freshness, and `[FACT]` (verbatim quote or tool output) vs `[INFERENCE]` (your interpretation).
  - Note gaps and contradictions between sources as `[GAP]`.
- Progress check every 5–10 tool calls: "Do I have enough to answer the original question? What is still missing?"
- Guidance, not a hard rule: soft stop near ~30 tool calls → early synthesis if coverage is adequate; near 50 → synthesize with what you have.

## Step 4: Synthesize & Deliver

1. Executive Summary — 2–3 sentences answering the question
2. Findings — by sub-question, inline source references, claims labelled `[FACT]` / `[INFERENCE]` / `[OPINION]`; flag low-confidence and conflicting sources
3. Open Gaps — `[GAP]` items you could not find or verify
4. Confidence Assessment — `high` / `medium` / `low`, with why
5. Recommended Next Steps — how the operator could close gaps; offer `analyze` or `report` if that is the natural next builtin

## Critical Thinking

Apply `_shared.md`: label every claim; never invent sources, URLs, or tool results; prefer `[GAP]` over polished prose that masks thin evidence; state what would falsify the headline answer.

## Anti-patterns

- Continue searching past diminishing returns
- Skip the plan and jump straight to searching
- Write project Facts as `active`; offer `proposed` Memory only when asked
