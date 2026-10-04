# AgentZero for Claude Code

**English** | [简体中文](./README.zh-CN.md)

MIT · A Claude Code plugin

This plugin gives you all of [AgentZero](https://github.com/jesselei1102-hue/agentzero) in Claude Code, from a plugin marketplace. It carries a pinned copy of AgentZero and runs that same code. Nothing is rewritten, so nothing drifts.

On top of that it adds two things only a plugin can do, because it runs inside the Claude Code engine:

1. **It loads the hot set for you.** On your first prompt, after `/compact` or `/clear`, and after six hours, the plugin runs `./a0 memory hot-set` and hands the result to the model with your prompt. The agent no longer has to remember to do it.
2. **It checks the words you are quoted on.** When the agent runs `memory remember --said "…"`, the plugin looks for those words in what you typed in this session. If they are there, the command runs as written. If they are not, the Fact is recorded as a **proposal** and the agent is told to ask you.

## Install

In Claude Code:

```text
/plugin marketplace add jesselei1102-hue/agentzero-claude-mod
/plugin install agentzero@agentzero
```

Choose the narrowest scope you are offered (project or local) so the plugin is on only where you want it.

## Set up a project

Open the folder you want to work in and run:

```text
/agentzero init
```

This makes the folder an AgentZero workspace for Claude Code: the same files, `CLAUDE.md`, Trace hooks and `./a0` launcher that AgentZero's own `adapter init --harness claude` makes. Then **start a new session** in that folder. `CLAUDE.md` and the hooks load when a session starts.

`init` refuses your home folder, the filesystem root, a folder that is already a workspace, and a folder inside one.

Other commands:

| Command | Does |
|---|---|
| `/agentzero upgrade` | Brings the workspace to the plugin's AgentZero version. It never overwrites a framework file you edited; it shows what stopped it. |
| `/agentzero status` | Shows whether the workspace can run, and the plugin and AgentZero versions. |

## What the plugin adds, and its limits

- **Claude Code only.** Codex and Cursor keep AgentZero's own rule and reminder; this plugin does not touch them.
- **The word check proves the words are yours, not that they are all of them.** A quote cut short is still part of what you typed, so it passes.
- **Some `remember` shapes are not checked.** The plugin reads one form: an optional `cd <dir> &&`, then `./a0 memory remember …` (or `python -m memory remember …`) with plain quoted values. A command built from variables, pipes, or `--workspace` runs unchanged, and you see "the operator's words in this remember were not checked".
- **Messages appear in two places.** The desktop app draws no status line, so each plugin message also appears as a toast.
- If the hot set cannot be loaded (`./a0` fails, takes over 10 seconds, or prints nothing), the plugin says why and adds nothing. AgentZero's own six-hour reminder is still there as a fallback.

## Requirements

- Claude Code with function hooks (tested on 2.1.280 in the terminal and 2.1.286 in the desktop app).
- Python 3.11 or newer with PyYAML: `python3 -m pip install pyyaml`. The plugin looks for `python3`, `python`, and the usual install folders. Inside a workspace, `./a0` finds Python itself.
- macOS or Linux. **Windows is not verified.**

## Versions

The plugin has its own version. `kernel/SOURCE.json` names the AgentZero commit, version and the SHA-256 of every file in the pinned copy; a test checks that copy against it. See [CHANGELOG.md](./CHANGELOG.md) and [DECISIONS.md](./DECISIONS.md).
