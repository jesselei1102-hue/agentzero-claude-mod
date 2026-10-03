# `agentzero` Claude Code plugin 1.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish AgentZero as an open-source Claude Code plugin that carries all of AgentZero and adds two engine-enforced features: loading the hot set, and checking the operator's words.

**Architecture:** A new repo holds a marketplace with one plugin. The plugin carries a hash-pinned copy of AgentZero (`kernel/`) and runs that Python code through `$.process.run`; its TypeScript adds only the two features and an `/agentzero` command. Pure logic lives in small TS modules with unit tests; `register.ts` only wires hooks to them.

**Tech Stack:** Claude Code function hooks (TypeScript, Claude Code 2.1.286 API, `claude plugin validate` / `claude plugin test`); Python 3.11 stdlib + pytest for the sync script; AgentZero's own Python kernel, unchanged.

**Spec:** `docs/spec.md` (copied from AgentZero's `.scratch/claude-mod/spec.md` on 2026-10-04).

## Global Constraints

- No file in `~/Documents/agentzero` changes. That repo is read only through `git archive`.
- New repo: `~/Documents/agentzero-claude-mod`. Lab workspace: `~/Documents/AgentZero-Claude-Lab`.
- Creating the GitHub repo, making it public, and every `git push` wait for the operator's explicit yes. Local commits are fine.
- Python: 3.11+ with PyYAML. Probe: `import sys, yaml; sys.exit(sys.version_info < (3, 11))`.
- Platforms: macOS and Linux. Windows unverified and documented as such.
- The plugin calls processes by argv only, never through a shell.
- Six hours = `21_600_000` ms. Hints = the prompt's first 200 characters. `./a0` timeout = `10_000` ms.
- Exact copy (do not reword):
  - hot set header line 1: `AgentZero hot set, loaded by the Claude Code plugin at <local time>.`
  - hot set header line 2: `Rule 3 is done for this session: do not run hot-set again unless your context is compacted or cleared.`
  - status, hot set failure: `AgentZero: hot set not loaded (<reason>)`
  - status, unreadable remember: `AgentZero: the operator's words in this remember were not checked`
  - context note on downgrade: `AgentZero plugin: the --said words were not found in what the operator typed in this session, so this was recorded as a proposal. Ask the operator.`
- Accepted prompt origins for the word check: `composer`, `bridge`, `sdk`.
- License MIT. Plugin version `1.0.0` at release.

## Review Focus

1. **Quotes copied with different whitespace.** The operator's words broken across lines, or with a full-width space (U+3000) or no-break space, must still match. Test in Task 3: `saidFound matches across newline, U+3000 and U+00A0`.
2. **The framework's own template opened as a project.** A session inside `kernel/template/` or AgentZero's `template/` must not get a hot set or a rewritten command. Test in Task 4: `findWorkspace skips a template folder beside src/adapter`.
3. **`/agentzero init` in the wrong folder.** Run from `$HOME`, from `/`, or inside an existing workspace, it must write nothing. Test in Task 7: `init refuses home, root and a folder inside a workspace`.
4. **A prompt with quotes, `$` or newlines as hints.** It must reach `./a0` intact as one argv item. Test in Task 5: `hints with quotes and $ reach a0 as one argv item`.
5. **`remember` run by a subagent.** The check still compares against the main conversation's prompts. Test in Task 6: `a subagent's remember is checked against the main session's prompts`.

---

### Task 1: Repo skeleton and the verification spike

The spec's "Verify first" list decides whether the rest of the plan stands. This task answers it with a plugin that does almost nothing, and records how the test kit is used, for every later task.

**Files:**
- Create: `.claude-plugin/marketplace.json`, `plugins/agentzero/.claude-plugin/plugin.json`, `plugins/agentzero/hooks/hooks.json`, `plugins/agentzero/hooks/register.ts`, `plugins/agentzero/hooks/smoke.test.ts`, `docs/spec.md` (copy of the spec), `docs/plan.md` (copy of this plan), `docs/verify.md`, `docs/test-kit.md`, `.gitignore`

**Interfaces:**
- Produces: `docs/test-kit.md` — the exact imports and calls for a unit test and for an engine test (raise `prompt.submit`, raise `tool.call` for `Bash`, mock `$.process.run`, advance the mocked clock). Every later TS test follows it.
- Produces: `docs/verify.md` — one answer per spec "Verify first" item (1–6), each with its evidence (command run, output seen).

- [x] **Step 1:** `git init ~/Documents/agentzero-claude-mod`; copy spec and plan into `docs/`. (Done 2026-10-04.)
- [ ] **Step 2:** Write `marketplace.json` (`name: "agentzero"`, one plugin entry, `source: "./plugins/agentzero"`) and `plugin.json` (`name: "agentzero"`, `version: "0.0.1"`, one-line description).
- [ ] **Step 3:** Write `register.ts` that on `session.start` calls `$.ui.status("AgentZero plugin loaded: " + $.plugin.root)`, and on `prompt.submit` shows `e.origin.kind` with `$.ui.toast`. Nothing else.
- [ ] **Step 4:** Write `smoke.test.ts`: `test("session.start shows the loaded status")` asserting the status text starts with `AgentZero plugin loaded: `.
- [ ] **Step 5:** Run `claude plugin validate plugins/agentzero` → no errors. Run `claude plugin test plugins/agentzero` → 1 passed.
- [ ] **Step 6:** In Claude Code, `/plugin marketplace add ~/Documents/agentzero-claude-mod`, then install `agentzero` with the narrowest scope Claude Code offers (project or local, in `~/Documents/AgentZero-Claude-Lab`, if such a scope exists). Record in `docs/verify.md` item 7: which install scopes exist, and whether the plugin loads in a session in `~/Documents/agentzero`. If it does, disable the plugin before any session in `~/Documents/agentzero` or any other real workspace, and keep it disabled there until Task 9 passes: AgentZero's own repo is a workspace, and a plugin under development must not touch it. Open a new session in an empty folder. Record in `docs/verify.md`: item 1 (did hooks run; was any consent asked), item 3 (`$.plugin.root` value), item 6 (the toast's origin kind in the desktop app, the terminal, and VS Code if available).
- [ ] **Step 7:** Leave item 2 (GitHub marketplace) pending for Task 10; items 4 and 5 pending for Task 5.
- [ ] **Step 8:** Write `docs/test-kit.md` from what made Step 4 pass, plus one engine test that raises `tool.call` for `Bash` and asserts the result.
- [ ] **Step 9: Gate.** If item 1 fails (hooks do not run from a marketplace install) or item 6 shows an origin outside `composer`/`bridge`/`sdk`, stop and bring `docs/verify.md` to the operator before Task 3.
- [ ] **Step 10: Commit** `git add -A && git commit -m "Skeleton plugin, and answers to the spec's verify list"`

### Task 2: `sync_kernel.py` and the first kernel copy

**Files:**
- Create: `scripts/sync_kernel.py`, `tests/test_sync_kernel.py`, `tests/test_kernel_manifest.py`, `plugins/agentzero/kernel/` (generated), `plugins/agentzero/kernel/SOURCE.json` (generated)

**Interfaces:**
- Produces: CLI `python3 scripts/sync_kernel.py SOURCE_CHECKOUT [--ref REF] --denylist FILE [--dest plugins/agentzero/kernel]`, exit 0 on success, 1 with a one-line reason on stderr.
- Produces: `kernel/SOURCE.json` = `{"commit": str, "ref": str, "version": str, "synced_at": str (ISO 8601), "files": {relpath: sha256hex}}`.
- Produces: `kernel/src/adapter/__main__.py` and `kernel/template/` at the same relative layout as AgentZero.

- [ ] **Step 1: Write the failing tests** in `tests/test_sync_kernel.py`, each building a throwaway git repo in `tmp_path` with `src/adapter/x.py`, `template/System.md`, `template/memory/traces/.gitkeep`, `template/memory/traces/run.yaml`, `pyproject.toml` (`version = "9.9.9"`), `LICENSE`, and an uncommitted `src/dirty.py`:
  - `test_copies_the_four_items_from_the_ref` — `kernel/src/adapter/x.py`, `kernel/template/System.md`, `kernel/pyproject.toml`, `kernel/LICENSE` exist.
  - `test_uncommitted_work_is_not_copied` — `kernel/src/dirty.py` does not exist.
  - `test_trace_content_is_skipped_but_gitkeep_kept` — `.gitkeep` exists, `run.yaml` does not.
  - `test_manifest_names_every_file_with_its_hash` — `SOURCE.json["version"] == "9.9.9"`, `commit` equals `git rev-parse HEAD`, every copied file's sha256 matches.
  - `test_a_denylisted_term_fails_and_keeps_the_old_copy` — denylist holds a word present in `System.md`; exit 1; an existing `kernel/` is unchanged.
  - `test_a_second_sync_replaces_the_old_copy` — a file removed upstream is gone after re-sync.
- [ ] **Step 2:** `pytest tests/test_sync_kernel.py -v` → all FAIL (no script).
- [ ] **Step 3:** Implement `scripts/sync_kernel.py`, stdlib only: `git -C SRC archive REF src template pyproject.toml LICENSE` read with `tarfile`; filter `__pycache__`, `.DS_Store`, `memory/traces/*` except `.gitkeep`; scan text files against the denylist (case-insensitive, one term per line, `#` comments); write to a temp sibling of `--dest`, then rename, so a failure leaves the old copy; write `SOURCE.json`.
- [ ] **Step 4:** `pytest tests/test_sync_kernel.py -v` → all PASS.
- [ ] **Step 5: Write** `tests/test_kernel_manifest.py::test_kernel_matches_its_manifest`: every file under `plugins/agentzero/kernel/` except `SOURCE.json` is named in `files` with a matching sha256, and every name in `files` exists.
- [ ] **Step 6:** Note `git -C ~/Documents/agentzero status --short`. Run `python3 scripts/sync_kernel.py ~/Documents/agentzero --ref HEAD --denylist ~/Documents/agentzero/private/denylist.txt`. Run `pytest -v` → all PASS. Run the same `git status` again → identical output (the source repo is untouched).
- [ ] **Step 7:** Reinstall the plugin; record in `docs/verify.md` item 3 that `kernel/` sits under `$.plugin.root`.
- [ ] **Step 8: Commit** `git add -A && git commit -m "Pin AgentZero <version> (<short commit>) into kernel/"`

### Task 3: Reading a `remember` command (pure logic)

**Files:**
- Create: `plugins/agentzero/hooks/words.ts`, `plugins/agentzero/hooks/words.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export type RememberCall = {
    cd: string | null;          // the dir of a leading `cd <dir> &&`, else null
    prefix: string[];           // words before `remember`: ['./a0','memory'] or ['PYTHONPATH=src','python3','-m','memory']
    sentence: string;
    said: string;
    factKey?: string; scope?: string; tags: string[]; sourceRun?: string;
  };
  export type RememberParse = { kind: 'none' } | { kind: 'unreadable' } | { kind: 'remember'; call: RememberCall };
  export function splitWords(command: string): string[] | null;   // POSIX quoting; null on unbalanced quotes, $( ), backticks, an unquoted $
  export function parseRemember(command: string): RememberParse;
  export function normalizeSpace(text: string): string;           // every run of Unicode whitespace → one ASCII space, trimmed
  export function saidFound(said: string, prompts: readonly string[]): boolean;
  export function proposeCommand(call: RememberCall): string;     // `[cd '<dir>' && ]<prefix> propose fact '<sentence>'` + flags, quoted as needed
  ```
- `parseRemember` returns `none` when the command does not run `memory remember`; `unreadable` when it does and `splitWords` fails or the shape is not `[cd X &&] <prefix> remember …`.

- [ ] **Step 1: Write the failing tests** in `words.test.ts`:
  - `splitWords handles single, double and escaped quotes` — `./a0 memory remember "a b" --said 'c "d"'` → `['./a0','memory','remember','a b','--said','c "d"']`.
  - `splitWords refuses what it cannot read` — `null` for `echo "a`, `x $(y)`, a backtick command, `x $Y`.
  - `parseRemember reads every flag` — `./a0 memory remember "S" --said "W" --fact-key k --scope task --tag a --tag b --source-run r` → `sentence:'S', said:'W', factKey:'k', scope:'task', tags:['a','b'], sourceRun:'r', prefix:['./a0','memory'], cd:null`.
  - `parseRemember keeps a leading cd` — `cd /w && ./a0 memory remember "S" --said "W"` → `cd:'/w'`.
  - `parseRemember accepts python -m memory` — `PYTHONPATH=src python3 -m memory remember "S" --said "W"` → `prefix:['PYTHONPATH=src','python3','-m','memory']`.
  - `parseRemember says none for other commands` — `./a0 memory review`, `ls` → `{kind:'none'}`.
  - `parseRemember says unreadable for other shapes` — `./a0 memory remember "S" --said "$X"`, `a && ./a0 memory remember "S" --said "W" && b` → `{kind:'unreadable'}`.
  - `saidFound matches a whole substring` — said `毫米` in `['这个项目全部用毫米']` → true; said `厘米` → false.
  - `saidFound matches across newline, U+3000 and U+00A0` — said `a b c` vs prompt `x a\n b　 c y` → true.
  - `saidFound is false for an empty prompt list`.
  - `proposeCommand round-trips through splitWords` — for the "reads every flag" call → `['./a0','memory','propose','fact','S','--fact-key','k','--scope','task','--tag','a','--tag','b','--source-run','r']`; no `--said`.
  - `proposeCommand quotes a sentence with ' and $` — sentence `it's $5` survives the round trip.
- [ ] **Step 2:** `claude plugin test plugins/agentzero` → these FAIL.
- [ ] **Step 3:** Implement `words.ts` to those signatures.
- [ ] **Step 4:** `claude plugin test plugins/agentzero` → PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Read a remember command, and build its propose twin"`

### Task 4: Workspace, timing, Python and the hot-set text (pure logic)

**Files:**
- Create: `plugins/agentzero/hooks/workspace.ts`, `plugins/agentzero/hooks/hotset.ts`, `plugins/agentzero/hooks/python.ts`, a `.test.ts` beside each

**Interfaces:**
- Produces:
  ```ts
  // workspace.ts
  export type Probe = (path: string) => Promise<boolean>;            // true when the path exists
  export async function findWorkspace(start: string, exists: Probe): Promise<string | null>;
  //   walks up from start; a dir with System.md and memory/ is a workspace,
  //   unless its basename is 'template' and its parent has src/adapter
  // hotset.ts
  export const SIX_HOURS_MS = 21_600_000;
  export type InjectState = { lastAt: number | null; resetSince: boolean };
  export function needsHotSet(s: InjectState, now: number): boolean;
  export function hintsFrom(prompt: string): string;                  // first 200 code points, line breaks → spaces
  export function hotSetContext(output: string, localTime: string): string; // header line 1, line 2, '', output
  // python.ts
  export const PYTHON_CANDIDATES: readonly string[];                  // the spec's six, in order
  export const PYTHON_PROBE = 'import sys, yaml; sys.exit(sys.version_info < (3, 11))';
  export async function findPython(run: (argv: string[]) => Promise<{ exitCode: number }>): Promise<string | null>;
  ```

- [ ] **Step 1: Write the failing tests:**
  - `findWorkspace finds the folder above` — exists true for `/w/System.md`, `/w/memory`; start `/w/a/b` → `/w`.
  - `findWorkspace returns null with none` — start `/x/y` → `null`.
  - `findWorkspace skips a template folder beside src/adapter` — exists true for `/repo/template/System.md`, `/repo/template/memory`, `/repo/src/adapter`; start `/repo/template/work` → `null`.
  - `needsHotSet` — `{lastAt:null,resetSince:false}` → true; `{lastAt:0,resetSince:true}` at 1 → true; `{lastAt:0,resetSince:false}` at `SIX_HOURS_MS` → false, at `SIX_HOURS_MS + 1` → true.
  - `hintsFrom cuts at 200 code points and flattens lines` — 250 × `中` → 200 code points; `a\nb\r\nc` → `a b c`.
  - `hotSetContext puts the two exact lines first` — line 1 equals Global Constraints line 1 with the time filled; line 2 equals line 2; then `''`; then the output.
  - `findPython takes the first passing candidate, probing with PYTHON_PROBE` — a fake `run` passing only `/opt/homebrew/bin/python3` → that path; each call's argv was `[candidate, '-c', PYTHON_PROBE]`.
  - `findPython returns null when none passes`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement to the signatures. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit.**

### Task 5: Feature 1 — load the hot set (wiring)

**Files:**
- Create: `plugins/agentzero/hooks/session.ts`, `plugins/agentzero/hooks/feature-hotset.ts`, `plugins/agentzero/hooks/feature-hotset.test.ts`
- Modify: `plugins/agentzero/hooks/register.ts` (replace the Task 1 smoke behaviour)

**Interfaces:**
- Consumes: `findWorkspace`, `needsHotSet`, `hintsFrom`, `hotSetContext`, `InjectState` (Task 4).
- Produces (`session.ts`, module state keyed by `$.session.id()`):
  ```ts
  export type SessionData = { workspace: string | null; inject: InjectState; prompts: string[]; seeded: boolean };
  export function sessionData(id: string): SessionData;
  export function forgetSession(id: string): void;
  ```
- Produces (`feature-hotset.ts`): `export function registerHotSet(on: On): void` — hooks `session.start` (find and store the workspace from `$.session.root()`, probing with `$.fs.stat`), `session.compact` and `session.end` with `reason: 'clear'` (set `resetSince`), `prompt.submit` (attach when `needsHotSet`, then set `lastAt`, clear `resetSince`).
- Runs `[<workspace>/a0, 'memory', 'hot-set', '--scope', 'project', '--hints', hintsFrom(e.text)]` with `{ cwd: workspace, timeoutMs: 10_000 }`.

- [ ] **Step 1: Write the failing engine tests** (pattern from `docs/test-kit.md`), `$.process.run` mocked to print `## Facts (1)`:
  - `no workspace: nothing attached`.
  - `first prompt attaches the hot set with hints` — `e.context` ends with `hotSetContext('## Facts (1)', …)`; the mocked argv equals the line above.
  - `second prompt attaches nothing`.
  - `after session.compact the next prompt attaches again`; `after a /clear …`; `after six hours on the mocked clock …`.
  - `a0 fails: nothing attached and the status says why` — status `AgentZero: hot set not loaded (exit 1)`; `(timed out)` on timeout; `(no output)` on empty stdout; `(a0 not found)` when `<workspace>/a0` is missing.
  - `hints with quotes and $ reach a0 as one argv item` — prompt `say "x" $HOME` → the `--hints` argv item is exactly that text.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; `claude plugin validate plugins/agentzero` → clean.
- [ ] **Step 5:** In a lab workspace (made with the kernel's `adapter init --harness claude` if Task 7 has not landed), answer `docs/verify.md` items 4 and 5: does the #89 reminder line also appear when stale; how long `prompt.submit` takes with the real `./a0`. If the reminder also appears, add a `classic.UserPromptSubmit` hook that drops the reminder's `additionalContext` when this prompt attached the hot set, with the test `the stale reminder is dropped when the hot set is attached`.
- [ ] **Step 6: Commit.**

### Task 6: Feature 2 — check the operator's words (wiring)

**Files:**
- Create: `plugins/agentzero/hooks/feature-said.ts`, `plugins/agentzero/hooks/feature-said.test.ts`
- Modify: `plugins/agentzero/hooks/register.ts`

**Interfaces:**
- Consumes: `parseRemember`, `saidFound`, `proposeCommand` (Task 3); `sessionData` (Task 5).
- Produces: `export function registerSaidCheck(on: On): void` — hooks `prompt.submit` (append `e.text` to `prompts` when `e.origin.kind` is `composer`, `bridge` or `sdk`) and `tool.call` matched on `{ tool: 'Bash' }`. Before the first check in a session with `seeded: false`, add the `text` of each `$.session.messages()` user row with no `toolResults`, then set `seeded: true`.

- [ ] **Step 1: Write the failing engine tests:**
  - `words the operator typed: command unchanged`.
  - `words the operator did not type: rewritten to propose fact with the note` — the command reaching the tool equals `proposeCommand(call)`; the result's `context` contains the exact note.
  - `an unreadable remember: unchanged, one status message` — exact status text.
  - `a prompt from a plugin or a task notification is not the operator's` — words only in a `{kind:'task-notification'}` prompt → downgraded.
  - `after a resume, earlier user rows count` — `$.session.messages()` mocked with a user row holding the words → unchanged.
  - `a subagent's remember is checked against the main session's prompts` — `tool.call` with an `agentId`, words in a main-session prompt → unchanged.
  - `outside a workspace nothing is checked`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; validate clean.
- [ ] **Step 5: Commit.**

### Task 7: The `/agentzero` command

**Files:**
- Create: `plugins/agentzero/hooks/command.ts`, `plugins/agentzero/hooks/command.test.ts`
- Modify: `plugins/agentzero/hooks/register.ts`

**Interfaces:**
- Consumes: `findPython`, `findWorkspace` (Task 4); `$.plugin.root`.
- Produces: `export function registerCommand(on: On): void` — registers `agentzero` in `session.start`; answers `command.run` for `args` `init`, `upgrade`, `status`, and anything else with a usage line.
- Runs with `env: { PYTHONPATH: <$.plugin.root>/kernel/src }`:
  - init: `[python, '-m', 'adapter', 'init', root, '--harness', 'claude']`
  - upgrade: `[python, '-m', 'adapter', 'materialize', workspace, '--harness', 'claude']`
  - status: `[python, '-m', 'adapter', 'preflight', workspace]`, then `plugin <plugin.json version>, kernel <SOURCE.json version> (<commit[:7]>)`.

- [ ] **Step 1: Write the failing engine tests:**
  - `init runs the kernel's init and says to start a new session`.
  - `init refuses home, root and a folder inside a workspace` — no process run in each case; the text names the folder.
  - `init refuses a folder with Role.md` — the kernel's own refusal (mocked exit 1 with that stderr) is shown.
  - `no usable Python: the message names it and the pip line` — text contains `python3 -m pip install pyyaml`.
  - `upgrade never passes --force, and shows the kernel's output as is`.
  - `status shows preflight output and both versions`.
  - `unknown args show usage`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; validate clean.
- [ ] **Step 5:** By hand: in an empty `~/Documents/AgentZero-Claude-Lab`, run `/agentzero init`. In the scratchpad, make a reference workspace with `PYTHONPATH=<plugin>/kernel/src python3 -m adapter init <scratch>/ref --harness claude`. Compare the two file lists and file contents: only the stamp's timestamps may differ.
- [ ] **Step 6: Commit.**

### Task 8: Open-source files

**Files:**
- Create: `README.md`, `README.zh-CN.md`, `CHANGELOG.md`, `DECISIONS.md`, `LICENSE`
- Modify: `plugins/agentzero/.claude-plugin/plugin.json` (`version: "1.0.0-rc.1"`), `.claude-plugin/marketplace.json` (description)

- [ ] **Step 1:** `LICENSE`: MIT, the same holder line as `~/Documents/agentzero/LICENSE`.
- [ ] **Step 2:** `README.md` / `README.zh-CN.md` with the spec's sections: what it is; install (`/plugin marketplace add <repo>`, install `agentzero`); `/agentzero init`; what the plugin adds over plain AgentZero, with its limits (Claude Code only; the cut-quote limit); the Python requirement; Windows unverified. The Chinese text uses short sentences, one idea each.
- [ ] **Step 3:** `DECISIONS.md`: the spec's Decisions table as entries 1–10, plus 11 (TypeScript rewrite rejected) and 12 (`propose fact` drops the unmatched words), each dated and attributed to the operator.
- [ ] **Step 4:** `CHANGELOG.md`: `1.0.0-rc.1 — kernel <version> (<commit[:7]>)`, then the features.
- [ ] **Step 5:** `grep -rniF -f ~/Documents/agentzero/private/denylist.txt --exclude-dir=.git .` → no output. `grep -rnE "/Users/[A-Za-z]" --exclude-dir=.git --exclude-dir=kernel .` → no output (the bracket keeps this line from matching itself).
- [ ] **Step 6:** `claude plugin validate plugins/agentzero`, `claude plugin test plugins/agentzero`, `pytest` → all clean.
- [ ] **Step 7: Commit.**

### Task 9: Acceptance in the lab workspace

**Files:**
- Modify: `docs/verify.md`

- [ ] **Step 1:** Reinstall the plugin from the local marketplace. In `~/Documents/AgentZero-Claude-Lab`, start a new session. Run the spec's by-hand steps 1–4. For each, record in `docs/verify.md`: what was done, what was seen, pass or fail.
- [ ] **Step 2:** For each fail: add a test to the owning task's test file that reproduces it, fix, rerun this task.
- [ ] **Step 3: Commit** `docs/verify.md`.

### Task 10: Publish (each step waits for the operator's yes)

- [ ] **Step 1:** Ask the operator: create `agentzero-claude-mod` on GitHub, public? Wait for yes.
- [ ] **Step 2:** Ask: push `main`? Wait for yes, then push.
- [ ] **Step 3:** On a macOS user account or machine that never had AgentZero: `/plugin marketplace add <owner>/agentzero-claude-mod`, install, run the spec's by-hand step 5. Record `docs/verify.md` item 2.
- [ ] **Step 4:** Set `version: "1.0.0"` and CHANGELOG `1.0.0`; commit; ask, then push and tag `v1.0.0`.

---

## Execution notes

- Tasks 3 and 4 do not depend on each other and may run in parallel after Task 2. Task 5 needs 4; Task 6 needs 3 and 5; Task 7 needs 4.
- Task 1's gate can end the plan early. That is a result, not a failure.
