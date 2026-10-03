# Operator checklist

**Daily path:** open this folder → give work in plain language → correct project facts → optionally confirm procedures. **First-time setup** may be agent-guided; Role defaults to **general** (SETTLED #50) unless the operator wants a specialty. This file is **implementer fallback** only.

Portable AgentZero workspace. Domain-agnostic: this folder is **not** tied to any one industry. What the assistant is for lives in `Role.md` (general by default).

1. Open this directory as the workspace in your agent harness (for Cursor: local Agent Chat; Cloud Agent hooks are out of v1). Cursor, Codex and Claude Code each have an adapter; `python3 -m adapter materialize --harness <name>` refreshes one.
2. Ensure `Role.md` states identity and lens only. Default template is **general** (no specialty). Specialty Role only if the operator wants one — do not force an interview (SETTLED #50).
3. Optionally give the agent reference material (standards, regulations, templates, an index). It declares each one with `./a0 knowledge add` into `knowledge.yaml` (`docs` | `index` | `raw`); `./a0 knowledge list` shows what is declared and whether it is reachable. Material that needs preparing (`raw`, e.g. PDFs to clause-by-clause YAML) is prepared only after you agree to how, into `knowledge/`. If Knowledge is missing, the agent may self-study from Role and must mark those conclusions `proposed`.
4. Optionally install domain MCP tools yourself (e.g. from [MCP World](https://www.mcpworld.com/en) or the [official MCP Registry](https://registry.modelcontextprotocol.io/)). AgentZero does not bundle Tools. MCP is an accelerator, not required.
5. **Optional — scored improvement only:** if this Role needs measurable runs, pin a fixed sample into `audit/answer_key.yaml`, sign every row, then score outside the agent into `memory/scores/<run-id>.yaml`. Versioned evidence is that Score plus `audit/runs/<run-id>.yaml`. Skip this entire step for ordinary collaboration.
6. Human-readable deliverables the operator asks to keep on disk go under `work/` (ad-hoc subfolders allowed). Not Memory, not Skills.
7. Project facts the operator (or a confirmed agent draft) should remember go in `memory/*.yaml` as one-sentence Facts — not JSON archives, not reports. Episodes: `memory/episodes/*.yaml`.
8. **Seeing what the assistant can already do is a command:** `./a0 skills list` shows the procedures you confirmed and the built-in capabilities, each with one sentence saying when it applies.
9. **Checking that Memory and Skills still hang together is a command too.** `./a0 memory lint` reports dangling references and items that may have stopped earning their place; `--strict` exits non-zero on the defects, for CI.
10. **Confirming what the agent proposed is a command, not a file edit.** `./a0 memory review` lists everything waiting across Facts, Episodes, graph entities/edges and Skills; `--confirm <id>` keeps one, `--reject <id>` retires it. Nothing is ever deleted, and nothing is confirmed without being named.

**Trace gate (Cursor):** hooks only write a Trace when the run included at least one MCP call. Generated Traces under `memory/traces/` stay local (gitignored).

**Trace writer:** hooks call the AgentZero `traces` package, which `adapter init` copies into this workspace's `src/` (stamped in `src/VERSION.yaml`). It needs `pyyaml` in whatever interpreter the hooks use — `python3 -m adapter preflight` checks that and names the command to run if it is missing.

Commands here use `python3`; on Windows use `python`. To refresh Cursor rules and hooks from `System.md` (from a checkout that has the adapter):

```
PYTHONPATH=src python3 -m adapter materialize
```
