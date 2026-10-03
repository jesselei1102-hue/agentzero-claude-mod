# Decisions

Each entry was decided by the operator. Dates are when it was decided.

| # | Date | Question | Decision |
|---|---|---|---|
| 1 | 2026-10-03 / 2026-10-04 | What the project is | An official AgentZero add-on, published as open source. |
| 2 | 2026-10-03 / 2026-10-04 | What 1.0 means | The plugin's own 1.0: the spec built and verified. AgentZero keeps its own versions. |
| 3 | 2026-10-03 / 2026-10-04 | What a person gets from the plugin alone | All of AgentZero, nothing less. |
| 4 | 2026-10-03 / 2026-10-04 | Effect on the AgentZero repo | None. The plugin changes no file there, and AgentZero never waits for the plugin. |
| 5 | 2026-10-03 / 2026-10-04 | How parity is reached | The plugin carries a pinned copy of AgentZero (`kernel/`) and runs that same code. No rewrite. |
| 6 | 2026-10-03 / 2026-10-04 | Features beyond parity | Load the hot set automatically; check the operator's words. |
| 7 | 2026-10-03 / 2026-10-04 | Where the features live | In the plugin. Claude Code only. Codex and Cursor do not change. |
| 8 | 2026-10-03 / 2026-10-04 | When the word check fails | The Fact becomes proposed, not refused. |
| 9 | 2026-10-03 / 2026-10-04 | When the hot set is loaded | First turn; first turn after compaction or `/clear`; first turn after six hours. |
| 10 | 2026-10-03 / 2026-10-04 | How it is installed | A plugin marketplace. |
| 11 | 2026-10-04 | Rewrite the kernel in TypeScript? | Rejected. The kernel is about 8,500 lines with about 8,200 lines of tests. Codex and Cursor would keep the Python copy, and the two copies would drift. |
| 12 | 2026-10-04 | What `propose fact` keeps when the check fails | The sentence, key, scope, tags and source run are kept. The `--said` words that did not match are dropped: they were not the operator's. |
