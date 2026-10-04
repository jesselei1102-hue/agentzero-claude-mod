# agentzero-claude-mod

**English** | [简体中文](./README.zh-CN.md)

[AgentZero](https://github.com/jesselei1102-hue/agentzero) as a Claude Code plugin. Install it from a marketplace and you have all of AgentZero, plus two things that only work from inside the engine:

- it **loads the hot set for you**, so the agent doesn't have to remember to;
- it **checks that a quote is yours** before a Fact is recorded as something you said.

The plugin carries a pinned, hash-checked copy of AgentZero and runs that same Python code. Nothing is rewritten, so nothing drifts. The plugin's own TypeScript is about 600 lines.

## Install

```text
/plugin marketplace add jesselei1102-hue/agentzero-claude-mod
/plugin install agentzero@agentzero
```

Pick the narrowest scope offered (project or local), so it is on only where you want it. Then, in the project folder:

```text
/agentzero init
```

Start a **new session** there. `CLAUDE.md` and the hooks load at session start. You now have the same workspace that AgentZero's own `adapter init --harness claude` makes.

Needs Python 3.11+ with PyYAML (`python3 -m pip install pyyaml`), on macOS or Linux.

## What it does

### 1. The hot set arrives with your prompt

AgentZero's Rule 3: load the hot set once per session, and again after compaction. Until now the agent had to run the command itself, and sometimes didn't (the 19-hour case, SETTLED #89 in AgentZero).

The plugin runs `./a0 memory hot-set --hints "<your first 200 characters>"` and attaches the output to your prompt, as context the model reads and you don't see. It does this:

- on your first prompt in a session,
- on the first prompt after `/compact` or `/clear`,
- on the first prompt after six hours.

The attached text tells the agent not to run `hot-set` again. It takes about 100 ms. If `./a0` fails, takes over 10 s, or prints nothing, the plugin attaches nothing and says why: `AgentZero: hot set not loaded (exit 1)`.

### 2. A quote has to be yours

`memory remember --said "<words>"` records a Fact as something you said. The command can't see the conversation, so it can't tell your words from words the agent made up.

The plugin can. When the agent runs `remember`, it looks for the `--said` text, whole, in what you typed this session (whitespace differences, including full-width and no-break spaces, are ignored).

```text
you:    我们这个项目所有尺寸都用毫米。
agent:  ./a0 memory remember "…mm…" --said "我们这个项目所有尺寸都用毫米。"
plugin: found → runs unchanged → remembered: …

agent:  ./a0 memory remember "…mm…" --said "(paraphrase) operator confirmed mm"
plugin: not found → runs `./a0 memory propose fact "…mm…"` instead, and tells the agent
        "recorded as a proposal. Ask the operator."
```

A proposal waits for your yes (`./a0 memory review`). The words that didn't match are not stored.

### 3. `/agentzero`

| Command | Does |
|---|---|
| `init` | Makes this folder an AgentZero workspace for Claude Code. Refuses your home folder, `/`, an existing workspace, and anything inside one. |
| `upgrade` | Brings the workspace to the plugin's AgentZero version. Never overwrites a framework file you edited; shows what stopped it. |
| `status` | Whether the workspace can run, and the plugin and AgentZero versions. |

## Limits

- **Claude Code only.** Codex and Cursor keep AgentZero's own rule and reminder.
- **A cut quote passes.** The check proves the words are yours, not that they are all of them. A shortened quote is still a substring of what you typed.
- **One `remember` shape is read:** an optional `cd <dir> &&`, then `./a0 memory remember …` (or `python -m memory remember …`), plain quoted values, flags `--said --fact-key --scope --tag --source-run`. Anything else (variables, pipes, `--workspace`) runs unchanged and you see `the operator's words in this remember were not checked`.
- **The desktop app has no status line**, so every plugin message also appears as a toast.
- **Not verified:** Windows; the terminal and VS Code origin kinds (the check accepts `composer`, `bridge` and `sdk`; the desktop app sends `composer`); a first install on a machine that never had AgentZero.
- Written against Claude Code's function-hooks API, which is early access and moves between releases. Tested on 2.1.280 (terminal) and 2.1.286 (desktop app).

## How it's built

```text
.claude-plugin/marketplace.json     one plugin
plugins/agentzero/
  hooks/                            the two features and /agentzero, with their tests
  kernel/                           AgentZero, pinned; SOURCE.json holds its commit and file hashes
scripts/sync_kernel.py              copies a commit of AgentZero into kernel/
tests/                              pytest: the sync script, and kernel/ against its manifest
docs/                               the spec, the plan, and what was verified (verify.md)
```

Run the tests:

```bash
claude plugin test plugins/agentzero      # the hooks
python3 -m pytest                          # the sync script and the kernel manifest
```

To follow a new AgentZero release: `python3 scripts/sync_kernel.py <AgentZero checkout> --ref <tag> --denylist <file>`, then release a new plugin version.

See [CHANGELOG.md](./CHANGELOG.md) and [DECISIONS.md](./DECISIONS.md).

## License

MIT. `kernel/LICENSE` is AgentZero's own.
