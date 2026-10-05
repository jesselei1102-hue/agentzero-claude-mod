Status: design approved in conversation 2026-10-05; this written spec waits for the operator's review.

# Spec: the memory HUD (plugin 1.1, sub-project A)

In this document, "the operator" is the person who works with the assistant. "The HUD" is the set of views this spec adds: a band above the prompt, a review pane, and cards in the transcript.

## Problem

AgentZero's memory is invisible while you work. You cannot see how many Facts are active, what waits for your yes, when the hot set was last loaded, or what the assistant just wrote. To find out, you open a terminal and run `./a0 memory review`. Proposals pile up because nobody looks.

The plugin runs inside the Claude Code engine, so it can draw this information where you already look.

## Goals

- You see the state of the memory at all times, without a terminal.
- You confirm or reject proposals with one click.
- Each write to memory shows as a readable card, not as a long shell command.
- It looks good enough to demo.

Order of priority (operator, 2026-10-05): it serves the operator's own daily use first; the demo effect also matters.

## Scope

This is sub-project A of the HUD work. It covers ideas 1, 2, 5 and 10 from the 2026-10-05 brainstorm:

| # | Idea | Where it lands |
|---|---|---|
| 1 | Memory status band | The band above the prompt |
| 2 | Write cards | Cards in the transcript |
| 5 | Context gauge | A ring in the band |
| 10 | Skill label | A card when a skill is used |

Later sub-projects, each with its own spec: B conflict alarm (6), C multi-session sync (7), D memory graph pane (4).

## Decisions (operator, 2026-10-05)

| Question | Answer |
|---|---|
| Who is it for | The operator's daily use first; demo quality also matters |
| When the band shows | Always, inside a workspace |
| What "view" does | Opens a side pane; each proposal has keep and reject buttons that run the kernel's `review --confirm/--reject` |
| Which commands get cards | Every `./a0` write, plus skill use |
| Where the snapshot comes from | A small Python script in the plugin that imports the workspace's own AgentZero modules and prints JSON |
| Band style | B: SVG pills and a context ring |
| Pane style | The 2026-10-05 mockup: header with count chips, one rounded card per proposal, text buttons under it |
| Card style | B1: soft rounded card, white icon disc, label chip, bold title, grey detail line |

## What the desktop app can draw (probe, 2026-10-05, Claude Code 2.1.286)

| Element | Desktop app |
|---|---|
| Band above the prompt (`AbovePrompt`), with buttons | Yes |
| Side pane (`Pane`), docked right | Yes |
| `Svg` in band, pane and transcript | Yes; CSS hover works; `<title>` tooltips do not show |
| Tool row redrawn (`ToolUse`) | Yes |
| Assistant text redrawn (`AssistantMessage`) | Yes |
| Status line (`$.ui.status`) | Yes, small, left of the model name |
| Toast | Unreliable: one from a button press showed, one from a running tool call did not |
| Spinner text, prompt hint, mode labels | No |
| `$.model.classify` | Yes, about 0.6 s |

Two findings shape this design:

- A transcript row is drawn once. It does not redraw when plugin state changes later. So a card shows the state at the time of the write, and the band and pane carry the live state.
- The desktop app folds consecutive tool calls into one collapsed row. A card inside a folded group is hidden until the operator opens it.

## Design

### Components

| File | Does | Kind |
|---|---|---|
| `plugins/agentzero/tools/snapshot.py` | Run with the workspace's Python and `PYTHONPATH=<workspace>/src`. Imports the workspace's own `memory` modules and prints one JSON snapshot (below). Reads; never writes. | Python, pytest |
| `hooks/snapshot.ts` | Validates the JSON into a `Snapshot`. Builds the band's pill texts and colours from a snapshot, the context percent and the time now. Holds the refresh logic, called with a `run` closure. | Pure, unit tests |
| `hooks/cards.ts` | Classifies a Bash command and its output as one write kind, and builds a card model: icon, label, colours, title, detail. Also classifies skill use. | Pure, unit tests |
| `hooks/svg.ts` | Builds the SVG strings: band pills and ring, pane header, pending item, B1 card. Wraps long text at punctuation or spaces. Escapes text. | Pure, unit tests |
| `hooks/feature-hud.ts` | Wiring: the snapshot in `$.state`; the `AbovePrompt`, `Pane` and `ToolUse` render hooks; the pane's buttons; `/agentzero review`. | Engine tests |
| `types/index.d.ts` | The `$.state` contract for the snapshot and the pane's per-item results. | Types |

Engine rules that shape the wiring, learned in 1.0: one hook per event and matcher per plugin, and `$` never passed into another file. So the refresh after a write is started from the existing Bash `tool.call` hook in `feature-said.ts`, and the snapshot refresh after a prompt from the existing `prompt.submit` hook in `feature-hotset.ts`. Each passes a closure made at the call site, as 1.0 does for `findPython`.

### The snapshot

`python <plugin>/tools/snapshot.py <workspace>` prints:

```json
{
  "schema": 1,
  "active": 12,
  "pending": [
    { "id": "fact:friday-20261004-104918", "kind": "fact", "sentence": "Never deploy on Fridays.",
      "provenance": "agent proposed it", "createdAt": "2026-10-04T10:49:18+08:00" }
  ],
  "hotSet": { "at": "2026-10-04T10:48:31+08:00", "factIds": ["..."] }
}
```

- `pending` comes from the kernel's `review.collect_pending(workspace)`, which covers Facts, Episodes, graph entities and edges, and Skills. `id` is the `qualified_id` that `review --confirm` takes.
- `active` is `len(lifecycle.live_fact_ids(memory_dir))` minus the pending Facts.
- `hotSet` is read from the kernel's hot-set state file (`memory/traces/hot-set.last`); `null` when there is none.
- On any error the script prints `{"schema": 1, "error": "<one line>"}` and exits 0. A missing kernel function gives the error `this workspace's AgentZero is too old for the HUD; run /agentzero upgrade`.
- Python: the path `./a0` cached in `memory/traces/a0.python`, else `findPython` (1.0). Timeout 2 s.

### The band (style B)

One SVG strip, left to right, then one real button:

```
[● AgentZero]  [12 条生效]  [2 条待确认]  [hot set · 3 分钟前]  ◔ 上下文 41%    [查看待确认]
```

| Pill | Normal | Other states |
|---|---|---|
| AgentZero | dark pill, white text | — |
| active | green | — |
| pending | amber with count | grey "0 条待确认" when none; the button is then hidden |
| hot set | grey, time since load | red "hot set 未加载（<reason>）" after a failed load (1.0's message, now visible) |
| context ring | blue arc, percent | amber from 80%, with the text "压缩后自动重新加载" |
| (snapshot failed) | — | one grey pill "记忆状态读取失败" replaces active and pending; the reason shows in the status line |

The band shows only inside a workspace, and yields to a survey (`hasSurvey`). The context percent comes from `$.session.usage().context.percent`, read at each draw. Times are relative ("3 分钟前") and recomputed at each draw.

### The review pane

Opened by the band's button or `/agentzero review`. Title "AgentZero · 待确认".

- Header SVG: "待你确认" with the line "助手推断的内容，等你点头才算数", then two chips: "N 条待确认" and "M 条已处理".
- One rounded card per pending item: a kind chip (Fact, Episode, 实体, 关系, 技能), the creation time, the sentence in bold (wrapped to at most two lines, then cut with `…`), and the provenance.
- Under each card, two text buttons: "✓ 保留" and "✗ 拒绝".
- A press runs `[<workspace>/a0, 'memory', 'review', '--confirm' | '--reject', <id>]` with `cwd: workspace`, timeout 10 s. Success: the card turns green "✓ 已保留" or grey with the sentence struck through "✗ 已拒绝", and the snapshot refreshes. Failure: the card shows the kernel's first error line in red, and the buttons stay.
- Items decided in this pane stay listed, in their decided colour, until the pane closes; this is the "M 条已处理" count. There is no undo: a mistaken keep or reject is fixed with the kernel's own commands, as today.
- Empty: "没有等你确认的东西 ✓".

### Write cards (style B1)

A card replaces the tool row of a finished `./a0` write. The card is a full-width SVG (about 640 px) with a "原始命令" text button under it that shows the command and its output in a `Code` block.

| Command (and output) | Icon | Label | Colour | Title | Detail |
|---|---|---|---|---|---|
| `memory remember`, `remembered:` | 📌 | 已记住 | green | the sentence | `你的原话 “<said>” ✓ 已核对` |
| `memory remember` rewritten by the word check, or `memory propose fact`, `proposed:` | ⏳ | 待你确认 | amber | the sentence | `引用不在你说过的话里，已改为提议` / `助手推断，等你确认` |
| `memory remember` the check could not read | 📌 | 已记住 | green, grey outline | the sentence | `引用未核对` |
| `memory forget` | 🗑 | 已撤回 | grey | the target | — |
| `memory review --confirm` / `--reject` | ✓ / ✗ | 已确认 / 已拒绝 | green / grey | the id | — |
| `memory propose entity|edge|episode`, `memory link`, `memory promote` | ⏳ / 🔗 | 待你确认 / 已关联 | amber / blue | the label or relation | — |
| `skills draft` | 🧩 | 技能草稿 | amber | the skill id | its description |
| `knowledge add` | 📚 | 资料已加入 | blue | the name | the type |
| Read of `skills/builtin/<name>.md` or `skills/<id>/…`, or `./a0 skills run <id>` | 🧭 | 使用技能 | blue | the skill name | — |

- The card is drawn from the command and the stored output. If the call is running, errored, or its output does not start with the line the table names, the engine's own row is kept.
- The word check (1.0) marks the calls it rewrote or could not read, so the card can tell "rewritten" from "proposed by the agent". This mark lives in module state keyed by `tool_use_id`.
- **Verify first:** whether a plugin can redraw the desktop's folded group row (`ToolGroup`). If yes, the folded row shows a summary of the writes inside ("📌 记住 1 · ⏳ 待确认 1"). If no, this is recorded as a limit.

### Refresh

The snapshot refreshes at session start, on each prompt, after each `./a0` write (from the card table above), when the pane opens, and after each keep or reject. One refresh runs at a time; a request during a run sets a flag and runs once more after it. A refresh that fails keeps the last good snapshot and marks it stale.

## Error handling

The rule: a failure in the HUD never blocks work and never hides the engine's own output.

| Case | Result |
|---|---|
| Not in a workspace | No band, no pane, no cards |
| Snapshot script fails or takes over 2 s | Grey "记忆状态读取失败" pill; reason in the status line; the last good snapshot is kept if there is one |
| Workspace AgentZero too old for the script | Same, with the reason `run /agentzero upgrade` |
| Keep or reject fails | The pane card shows the kernel's error line; nothing else changes |
| A card's command or output is not understood | The engine's own row is drawn |
| An SVG is refused by the surface | The engine's own drawing (the engine reports the refusal in the transcript) |

## Testing

- **pytest:** `snapshot.py` against a temporary workspace made by the kernel's `adapter init`, with active and proposed Facts, a proposed Skill and a hot-set state file; and against the pinned `kernel/` copy, so a kernel upgrade that breaks the script fails the build.
- **Unit (`claude plugin test`):** `cards.ts` for each row of the card table and for the "keep the engine's row" cases; `snapshot.ts` for parsing, the error JSON and every band state; `svg.ts` for escaping, wrapping at punctuation, and pill widths for mixed Chinese and Latin text.
- **Engine:** band, pane and card drawn through `$.ui.mount` on `desktop` and `terminal`; a keep and a reject press with the kernel mocked (success and failure); refresh after a write and after a prompt; no band outside a workspace.
- **By hand, in the lab workspace:** the band with real numbers; a remember, a downgraded remember and a skill use each give the right card; keep and reject in the pane change the files (`./a0 memory review` agrees); screenshots saved to `docs/hud/` for the README.

## Out of scope

- The conflict alarm, multi-session sync and graph pane (sub-projects B, C, D).
- Undo in the pane.
- Light and dark theme variants: the colours are tuned for the desktop's light theme; a dark theme is checked by hand and fixed only if unreadable.
- Changing anything in the AgentZero repo.

## What would show this is wrong

- The operator stops looking at the band after a week: it is noise, and should show only when something needs attention (the rejected option B).
- Keep and reject from the pane lead to Facts the operator later regrets: one click is too easy, and the pane needs the sentence in full or a confirmation.
- Cards are mostly hidden in folded groups: the summary on the folded row is required, not optional.
