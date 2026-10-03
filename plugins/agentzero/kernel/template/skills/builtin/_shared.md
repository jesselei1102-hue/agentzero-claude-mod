# Shared conventions for Layer 1 builtins

Reference for `research`, `analyze`, `brainstorm`, `report`. Not a Skill itself (no frontmatter; not loaded on its own). Each builtin points here from its Critical Thinking section.

## Precedence and override

System rule 5: Role lens → matching project `active` Skill → else builtin. Inside a builtin, every point marked **(default — Role may override)** yields to `Role.md` or a project Skill when they say otherwise. Examples: source authority order, analysis method, report structure, tone.

## Claim labels (use verbatim)

| Label | Meaning |
|-------|---------|
| `[FACT]` | Observed: verbatim quote, tool output, or operator statement |
| `[INFERENCE]` | Derived from facts by stated reasoning |
| `[OPINION]` | Judgement or preference; no claim of evidence |
| `[GAP]` | Missing, unverified, or contradictory evidence; say what is missing |

Brainstorm ideas use grounding tags instead: `[GROUNDED]` (evidence or precedent), `[SPECULATIVE]` (untested), `[WILD CARD]` (deliberately provocative).

Confidence, when stated: `high` / `medium` / `low`.

## Evidence handling

- Record source, date, and whether it is observed or interpreted.
- Default source authority: operator material and Knowledge > official docs > peer-reviewed > reputable press > blogs and forums **(default — Role may override)**.
- Never invent sources, URLs, numbers, or tool results. Prefer `[GAP]` to a plausible fill.
- Where sources conflict, show both; do not silently pick one.
- For every major conclusion or recommendation: state what would falsify it.

## Memory and Knowledge

- Load relevant Memory (project facts) and Knowledge before working; when `memory/graph.yaml` exists, also use the activated graph index (ADR 0006) — not the whole graph.
- Query Timeline / full graph only when the question needs past runs or relationships beyond the activation set.
- Operator audits the graph by opening `memory/graph.yaml` anytime.
- Project facts stay in Memory YAML, not in Skill text; graph links Fact ids only.
- Never write Memory, Skills, or graph items as `active` from inside a builtin. Offer `proposed` only when the operator asks to keep something.

## Delivery hygiene

- Lead with the answer or the "so what".
- Mark gaps in-line; do not smooth over thin evidence.
- Do not self-score. Do not describe the output as verified unless a source shows it.
- When composing other builtins (see `_routing.md`), say which ones you used.
