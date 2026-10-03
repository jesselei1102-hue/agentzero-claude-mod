# Routing for Layer 1 builtins

Convention the harness planner reads to pick and chain builtins. Not a Skill; not an orchestration runtime (planning stays Layer 0, ADR 0001). Referenced from System rule 5.

## Pick one

| Operator intent | Builtin |
|-----------------|---------|
| Look up, investigate, gather evidence, compare across sources | `research` |
| Structure, compare, diagnose, evaluate material already at hand | `analyze` |
| Generate options, explore alternatives, "what if" | `brainstorm` |
| Write a report, memo, brief, summary for a reader | `report` |

Before any of these: if a matching project `active` Skill exists under `skills/`, use it instead (System rule 5). Role lens applies throughout.

**Inline, no builtin:** a single-fact lookup answerable in one to three searches; a one-line summary of text already in the chat.

## Chain

Natural order is Brainstorm → Research → Analyze → Report, but start wherever the operator is.

| Signal | Do |
|--------|----|
| "Research X then write a report" | `research` → `report` (Report step 2 will confirm evidence is enough) |
| Analyze finds data missing | Stop; state the `[GAP]`; propose `research` — do not fill with assumptions |
| Report step 2 finds unsupported claims | Run `research` for those claims first; say so in the delivery |
| Brainstorm ends with promising options | Offer `research` (validate) or `analyze` (compare) as next round |
| Operator names one builtin explicitly | Run only that one; suggest the next as an offer |

Rules:

- Say which builtins you are composing; do not hide the chain.
- Deliver per step when the chain is long; invite steering between steps.
- Do not loop Research past diminishing returns; hand off to Analyze or Report with the `[GAP]` list.

## Disable

Operator may disable a builtin for a workspace by removing or renaming its file under `skills/builtin/`, or by saying so in chat for one task.
