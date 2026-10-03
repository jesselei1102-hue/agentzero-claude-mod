---
id: brainstorm
status: active
source_runs:
  - product:layer-1
memory_ids: []
description: Generate options, explore alternatives, or work through "what if" before committing to one direction.
---

# Brainstorm

Task class: diverge options, challenge assumptions, and expand the solution space — without false certainty. Shared conventions: `_shared.md`. Chaining: `_routing.md`.

## Trigger

Activate when the operator asks to brainstorm, ideate, explore alternatives, generate options, think outside the box, or "what if."

## Step 1: Frame the Space

- Restate the prompt and hard constraints (from operator, Role, and Memory).
- Surface IMPLICIT assumptions in the question:
  - "What is the operator taking for granted?"
  - "What if the opposite were true?"
  - "What problem behind the problem might exist?"
- State boundaries: what is truly fixed vs what FEELS fixed but could be challenged?

## Step 2: Diverge with Structure

Do not just "generate ideas." Use at least 2–3 deliberate divergence strategies **(default — Role may override)**:

- Dimension shifting — vary one axis at a time (cost, timeline, scope, audience, technology, geography…)
- Analogy transfer — "How does [different domain] solve a similar problem?"
- Constraint inversion — "10× the budget? 1/10 the time? Zero legacy systems?"
- Extreme versions — push an idea to its extreme, then find the useful kernel
- Assumption negation — for each identified assumption, generate an option that violates it
- Adjacent possibles — what opens up if one constraint is relaxed?

Quantity targets: quick 5–8; full exploration 10–15; creative sprint 15–25 (when the operator wants volume).

Quality checks per option:

- Genuinely distinct (not a cosmetic variant)?
- Addresses the actual problem?
- Tagged `[GROUNDED]` (evidence/precedent) / `[SPECULATIVE]` (untested) / `[WILD CARD]` (deliberately provocative)?

## Step 3: Organize (but don't converge)

Default: a flat list, each option with a one-line description, the key tradeoff or tension it surfaces, its grounding tag, and a flag if it conflicts with active Memory or Role constraints.

Only cluster, rank, or score if the operator explicitly asks. Premature ranking kills the options that need the most exploration.

## Step 4: Bridge to Action

For each promising cluster or option note:

- What would need to be true for this to work? (assumptions to test)
- Cheapest way to validate it? (quick experiment, `research`, existing data to `analyze`)
- Does it open a new sub-question worth exploring?

Offer a next step: "Want me to go deeper on any of these? I can Research [X], Analyze [Y], or run another round on [Z]."

## Iteration Pattern

Brainstorming is multi-round: Round 1 broad divergence (this skill) → operator picks 2–3 directions → Round 2 focused divergence → operator narrows → transition to `research` or `analyze`. Deliver Round 1 and invite steering; do not do all rounds at once.

## Critical Thinking

Apply `_shared.md`: tag every idea's grounding; never invent sources or evidence to make a speculative idea look grounded; keep "interesting" separate from "evidenced"; never promote brainstorm items into Memory or Skills without the operator asking.

## Anti-patterns

- Converge prematurely — resist recommending "the best" option
- Generate 8 options that are really 2 ideas with surface variations
- Suppress wild ideas because they seem impractical — that is what `[WILD CARD]` is for
- Skip assumption-questioning — the most valuable output is often reframing the question
