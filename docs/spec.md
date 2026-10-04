Status: implemented in plugin 1.0.0-rc.1 (design approved 2026-10-04). In this document, "the operator" is the person who works with the assistant.

# Spec: `agentzero` — AgentZero as a Claude Code plugin

Sources: design discussion 2026-10-03 / 2026-10-04; AgentZero's own decision log (its entries on the six-hour reminder, on `remember --said`, and on the framework template folder); the Claude Code function-hooks API as shipped in Claude Code 2.1.286, read from the declaration file that ships with it. The public docs page for that API could not be fetched when this was written.

## Problem Statement

Today a person gets AgentZero by cloning the AgentZero repo and running `python3 -m adapter init`. The operator wants to publish AgentZero as an open-source Claude Code plugin. A person installs it from a plugin marketplace and has all of AgentZero, with nothing less.

The plugin also fixes two rules that depend on the agent obeying them:

1. **Rule 3 loads the hot set once per session, and again after compaction.** The agent must run the command. In a Codex workspace a preference was loaded one evening. The conversation resumed the next day. 19 hours and about 60 turns later, the agent did not apply it. The prompt hook now reminds the agent after six hours. The agent must still act on the reminder.
2. **`remember --said` must hold the operator's own words.** The command cannot see the conversation, so it cannot know whether the words are real.

A Claude Code plugin of function hooks runs inside the engine. It sees each prompt the operator types. It can attach context to a prompt. It can rewrite a tool call before the call runs. So on Claude Code the engine can do both rules.

**What this does and does not fix.** The documented failures happened in a Codex workspace, where this plugin does not run. On Claude Code the six-hour reminder already worked in the one session observed (it fired twice; the hot set was loaded both times). The word check would have stopped none of the three documented cases: in the first the agent cut the words, and a cut quote is still the operator's text; in the second the words were real and the sentence was rewritten, which the kernel already handles. What the check stops is words the operator never typed: made up, or translated.

**Why now.** The operator practises in Codex and tracks the work in Claude Code. Both will be used in the end. The plugin is also the base for later plugin-only features: the full text of each reply for the Journal, and a pane in the session.

## Decisions (operator, 2026-10-03 / 2026-10-04)

| Question | Answer |
|---|---|
| What the project is | An official AgentZero add-on, **published as open source** |
| What 1.0 means | **The plugin's own 1.0**: this spec built and verified. AgentZero keeps its own versions. |
| What a person gets from the plugin alone | **All of AgentZero, nothing less** |
| Effect on the AgentZero repo | **None.** The plugin changes no file there, and the AgentZero repo never waits for the plugin. |
| How parity is reached | **The plugin carries a pinned copy of AgentZero** and runs that same code. No rewrite. |
| Features beyond parity | **Load the hot set automatically**; **check the operator's words** |
| Where the features live | **In the plugin (option B).** Claude Code only. Codex and Cursor do not change. |
| When the word check fails | **The Fact becomes proposed**, not refused (as the kernel already does when the sentence says more than the words) |
| When the hot set is loaded | **First turn; first turn after compaction or `/clear`; first turn after six hours** |
| How it is installed | **A plugin marketplace** |

Rejected: rewriting the kernel in TypeScript. The kernel is about 8,500 lines with about 8,200 lines of tests. Codex and Cursor would keep the Python copy, and the two copies would drift.

## Solution

### Where things live

| Place | Holds |
|---|---|
| This repo, `agentzero-claude-mod` | the marketplace, the plugin, a pinned copy of AgentZero, the plugin's tests |
| A separate workspace (for example `AgentZero-Claude-Lab`) | made by the plugin's own `/agentzero init`; used only to try the plugin |
| The AgentZero repo | **unchanged** |

This repo:

```
.claude-plugin/marketplace.json        the marketplace: lists one plugin
plugins/agentzero/
  .claude-plugin/plugin.json           version 1.0.0 at release
  hooks/hooks.json                     { "modules": ["./register.ts"] }
  hooks/register.ts                    wires the hooks; holds no logic of its own
  hooks/*.ts                           one file per feature
  hooks/*.test.ts                      run by `claude plugin test`
  kernel/                              the pinned copy of AgentZero (below)
scripts/sync_kernel.py                 copies a release of AgentZero into kernel/ (stdlib only)
tests/                                 pytest: sync_kernel, and kernel/ against its manifest
DECISIONS.md                           this project's decisions, numbered
README.md, README.zh-CN.md, CHANGELOG.md, LICENSE (MIT)
```

### The pinned copy of AgentZero

`kernel/` holds, from one commit of the AgentZero repo: `src/`, `template/`, `pyproject.toml`, `LICENSE`. That is what `adapter init` and `adapter materialize` need: `adapter` finds the template at `parents[2] / "template"`, so the layout is kept as it is in the AgentZero repo.

`python3 scripts/sync_kernel.py <path to an AgentZero checkout> --ref <commit or tag> --denylist <file>`:

1. Reads the four items from the commit `--ref` names (default `HEAD`) with `git archive`, so uncommitted work in the checkout is never copied and the checkout is never touched.
2. Replaces `kernel/` with them, without `__pycache__`, `memory/traces/` content (except `.gitkeep`), or `.DS_Store`.
3. Writes `kernel/SOURCE.json`: the commit, the version from `pyproject.toml`, the date, and a SHA-256 for each file copied.
4. Fails if any copied file contains a term from a denylist file whose path is given with `--denylist` (the maintainer's own list of private terms; it is not published).

A test in the plugin repo checks every file in `kernel/` against `SOURCE.json`. A file that differs, or a file the manifest does not name, fails the test. So the copy is AgentZero exactly, and parity is shown by a hash, not by a list of features.

To follow a new AgentZero release, run `sync_kernel.py` again and release a new plugin version. This repo does nothing.

### Finding Python

The kernel needs Python 3.11+ with PyYAML, as AgentZero does today.

- **Inside a workspace**, the plugin runs `./a0`. The launcher finds Python itself.
- **Before a workspace exists** (`/agentzero init`), the plugin tries, in order: `python3`, `python`, `/usr/bin/python3`, `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`, `/Library/Frameworks/Python.framework/Versions/Current/bin/python3`. That is the launcher's own list. It takes the first one for which `-c "import sys, yaml; sys.exit(sys.version_info < (3, 11))"` exits 0. If none does, it says what is missing and how to install it: `python3 -m pip install pyyaml`.

1.0 supports macOS and Linux. Windows is not verified, and the README says so. **[ASSUMED]**

### How the plugin behaves

- It loads in every Claude Code session.
- At `session.start` it walks up from `$.session.root()` to a folder that holds `System.md` and `memory/`. That folder is the workspace. A workspace made by the AgentZero repo's `adapter init` counts too.
- A folder named `template` whose parent holds `src/adapter/` is a framework's template, not a workspace, and is skipped (an earlier AgentZero hook took `template/` for a workspace). This covers the AgentZero repo's `template/` and the plugin's `kernel/template/`.
- With no workspace, only the `/agentzero` command is active.
- It calls Python only through `$.process.run`, by argv, never through a shell.

### The `/agentzero` command

| Command | Does | Runs |
|---|---|---|
| `/agentzero init` | makes the session's project root a workspace for Claude Code | `<python> -m adapter init <root> --harness claude`, with `PYTHONPATH=<kernel>/src` |
| `/agentzero upgrade` | brings the workspace to the plugin's kernel version | `<python> -m adapter materialize <workspace> --harness claude`, same `PYTHONPATH` |
| `/agentzero status` | says whether the workspace can run, and which versions | `<python> -m adapter preflight <workspace>`, plus the plugin and kernel versions |

- `init` refuses a folder that already has `Role.md`, as `adapter init` does.
- `init` refuses the person's home directory and the filesystem root, and a folder inside a workspace. It names the folder and asks for a project folder.
- `upgrade` never passes `--force`. When the kernel stops on a framework file the operator edited, the plugin shows that output as it is.
- After `init`, the plugin tells the person to start a new session. The workspace's `CLAUDE.md` and hooks load when a session starts.

A workspace made this way is the same as one made from the AgentZero repo: same files, same `CLAUDE.md`, same Trace hooks, same `./a0`.

### Feature 1: load the hot set

**When.** On `prompt.submit`, inside a workspace, the plugin attaches the hot set if any of these is true:

1. No hot set was attached yet in this session.
2. A compaction or `/clear` happened since the last one. The plugin notes `session.compact`, and `session.end` with `reason: 'clear'`.
3. More than six hours passed since the last one. This is the same six hours as `runstate._FRESH`.

**How.**

1. The plugin runs `./a0 memory hot-set --scope project --hints "<the prompt's first 200 characters>"`.
2. It adds this to the prompt's `context`. The model reads it. The operator does not see it.

   ```
   AgentZero hot set, loaded by the Claude Code plugin at <local time>.
   Rule 3 is done for this session: do not run hot-set again unless your context is compacted or cleared.

   <the command's output>
   ```

3. The command writes the hot-set state file as it does today, so the stale-prompt reminder stays silent.

**If it fails.** If `./a0` exits non-zero, runs past 10 seconds, or prints nothing, the plugin attaches nothing. It shows one status-line message: `AgentZero: hot set not loaded (<reason>)`. The #89 reminder still works as the fallback.

**Cost.** The hot set is about 1,300 characters today, about 400 tokens, once per session without compaction. The command takes about 90 ms on the operator's machine (measured 2026-10-04). The API states that a `$` call in flight does not count against a hook's budget.

### Feature 2: check the operator's words

**When.** On `tool.call` for `Bash`, inside a workspace, when the command runs `a0 memory remember` (or `python -m memory remember`) with `--said`.

**How.**

1. The plugin splits the command into words, with POSIX shell quoting. It accepts one form only: an optional `cd <dir> &&`, then one `remember` command. It reads the sentence and the values of `--said`, `--fact-key`, `--scope`, `--tag` (repeatable) and `--source-run`.
2. It compares against the operator's prompts. The plugin keeps, per session, the `text` of every `prompt.submit` whose `origin.kind` is `composer` (typed at the prompt), `bridge` (Remote Control) or `sdk` (the desktop app starts Claude Code through the SDK). After a resume, it first adds the `text` of each user row in `$.session.messages()` that carries no `toolResults`.
3. It removes repeated whitespace on both sides. Then it checks whether the `--said` text occurs, whole, inside one of the operator's prompts.
4. **Found:** the command runs unchanged.
5. **Not found:** the plugin rewrites the command to `[cd <dir> &&] ./a0 memory propose fact "<sentence>"` with the same `--fact-key`, `--scope`, `--tag` and `--source-run`, and no `--said`. It runs it, and adds to the tool result's `context`: `AgentZero plugin: the --said words were not found in what the operator typed in this session, so this was recorded as a proposal. Ask the operator.`

The kernel's own output then says `proposed:` and prints the usual `→ ask the operator … keep it?` line. The words that did not match are not stored: they were not the operator's.

**If the plugin cannot read the command** (another shape, unbalanced quotes, `--said` built from a variable): the command runs unchanged. The plugin shows one status-line message: `AgentZero: the operator's words in this remember were not checked`.

**Limit.** A cut quote is still a whole substring of the real prompt, so it passes. The check proves the words are the operator's. It does not prove that they are all of them. An agent can cut a quote this way, and this plugin does not remove that harm.

### Open source

- MIT, as AgentZero is. `kernel/LICENSE` is AgentZero's own.
- `README.md` and `README.zh-CN.md`: what it is; install from the marketplace; `/agentzero init`; what the plugin adds over plain AgentZero; the Python requirement; the Windows gap.
- `CHANGELOG.md` starts at 1.0.0 and names the kernel version each release carries.
- `DECISIONS.md` records this spec's decisions, numbered from 1.
- Creating the GitHub repo, making it public, and every push wait for the operator's yes (standing Fact: no push without asking).

## Verify first

These come before feature work. Each is answered by a test in the lab workspace.

1. Can a plugin installed from a marketplace run function hooks? Does the person have to switch anything on or agree to anything first?
2. Does installing from a GitHub marketplace bring the whole plugin folder, `kernel/` included?
3. ~~How does the hooks module learn its own folder?~~ Answered by the declaration: `$.plugin.root`. Still confirm that it is the installed folder with `kernel/` in it.
4. In one prompt, which runs first: the settings hook (`UserPromptSubmit`, AgentZero's six-hour reminder) or the plugin's `prompt.submit`? If the reminder runs first in a stale session, the agent sees both. Then the plugin hooks `classic.UserPromptSubmit` and drops the reminder line when it attaches the hot set.
5. Does `./a0 memory hot-set` finish inside the hook's limits in practice? About 90 ms was measured.
6. Which `origin.kind` do the operator's prompts carry in the desktop app, in the terminal, and in VS Code? If one is none of `composer`, `bridge`, `sdk`, every check there fails and every `remember` becomes a proposal.

7. Can the plugin be installed for one project only? AgentZero's own repo is a workspace, so a plugin under development installed for the whole user would load there too. Until acceptance passes, the plugin is kept off in every real workspace.

If 1, 2 or 3 fails, installation changes before anything else does.

## Testing

**Repo** (pytest): `sync_kernel.py` copies the four items, skips what it must, refuses a dirty checkout and a denylisted term; `kernel/` matches `SOURCE.json`, file by file.

**Plugin** (`claude plugin test`, each on `terminal` and `desktop`):

- Not a workspace: no hot set attached, no command changed; `/agentzero init` is offered.
- `/agentzero init` in an empty folder: the kernel's `init` runs with the found Python; the person is told to start a new session. In a folder with `Role.md`: refused, nothing written. With no usable Python: the message names what is missing.
- `/agentzero upgrade` and `/agentzero status` run the matching kernel commands and show their output.
- First prompt: hot set attached, with the prompt's words as hints and the header above. Second prompt: nothing attached. After `session.compact`, after a `/clear`, after six hours on the mocked clock: attached again. `./a0` fails or times out: nothing attached, one status message.
- `remember` with words the operator typed: unchanged. With words the operator did not type: rewritten to `propose fact` with the same key, scope, tags and source run, no `--said`, and the context note. With a shape the plugin cannot read: unchanged, one status message.

**By hand, in the lab workspace:**

1. In an empty folder, run `/agentzero init`. Start a new session. `./a0 --which`, `./a0 memory review`, `./a0 knowledge list`, `./a0 skills list` and `./a0 memory lint` all run.
2. Ask a question. The agent answers using the hot set and does not run `hot-set` itself.
3. Run `/compact`. Ask again. The hot set is attached again.
4. Say a fact. Ask the agent to record it, quoting you in other words. The Fact is proposed, not active.
5. Install the plugin from the published marketplace on a machine or user account that has never had AgentZero. Repeat step 1.

## Out of scope

- Any change to the AgentZero repo.
- Codex and Cursor. They keep the rule and the six-hour reminder.
- Windows, until verified.
- The confirmation pane, the write guard, the Journal capture, native tools. Each is a later plugin version.
- Checking `propose`, `promote` or `link`. Proving a quote is complete (see Limit).

## What would show this is wrong

- Agents still run `hot-set` themselves after the plugin attached it: the header is not enough, and the session pays twice.
- Most real `remember` calls end as "not checked": agents write commands in more shapes than the one accepted.
- Operators reject Facts that the check downgraded but that were their words: the comparison is too strict (punctuation, full-width characters, pasted text).
- People install the plugin and stop at the Python requirement: parity through the Python kernel costs more adoption than it saves work.
- 1.0 moves to Codex first, or Claude Code stays a tracking tool only: the plugin rarely runs where the work is done.
