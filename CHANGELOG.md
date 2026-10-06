# Changelog

## 1.1.0-rc.3 — kernel 0.4.7 (333cd6e)

- **The memory band.** A band above the prompt shows the active Facts, the ones waiting for the operator's yes, when the hot set was last loaded (red with the reason when it failed), and how much of the context is used.
- **The review pane.** `查看待确认` on the band, or `/agentzero review`, opens a pane of what waits; keep and reject run the kernel's `memory review --confirm/--reject`. A press that fails shows the kernel's error on that item.
- **Write cards.** Each `./a0` write (remember, propose, forget, review, link, promote, skills draft, knowledge add) and each skill use (Read tool, shell read, `skills run`) is drawn as a card. In the desktop app the cards are drawn inside the folded command group; a card for a slow write often stays hidden there (see the README's limits).
- `tools/snapshot.py` prints the memory state as JSON through the workspace's own AgentZero modules; it names a Python without PyYAML as such, and the plugin looks for another Python when the cached one fails.
- `kernel/` carries AgentZero 0.4.7 (commit 333cd6e). From 0.4.6: a Skill read through the shell now counts as loaded (AgentZero #92). From 0.4.7: a drafted Skill no longer lists another task's scripts as its own when the run's result sat directly in `work/` (AgentZero #93, found in the lab workspace).
- Verified in the lab workspace: a Skill is offered and drafted when the operator says a task recurs (#91) and after a script turns a batch of inputs into the result (#72). See `docs/verify.md`.

## 1.0.0-rc.1 — kernel 0.4.5 (c7fcd47)

First release candidate. Carries AgentZero 0.4.5 (commit c7fcd47) in `kernel/`, checked file by file against `kernel/SOURCE.json`.

- `/agentzero init`, `upgrade` and `status`, running the kernel's `adapter init`, `materialize` and `preflight` for Claude Code. `init` refuses the home folder, the filesystem root and any folder in or at a workspace.
- Loads the hot set on the first prompt, after `/compact` or `/clear`, and after six hours, with the prompt's first 200 characters as hints. If it fails, it says why and attaches nothing.
- Checks the operator's words in `memory remember --said`. Words the operator did not type in this session turn the call into `memory propose fact`, with a note to ask the operator. A `remember` the plugin cannot read runs unchanged and says so.
- `scripts/sync_kernel.py` pins a commit of AgentZero into `kernel/` and refuses denylisted terms.
