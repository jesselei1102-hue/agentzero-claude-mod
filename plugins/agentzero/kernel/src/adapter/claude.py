"""Claude Code adapter: CLAUDE.md pointer plus Trace hooks merged into settings.

Two differences from the Cursor adapter shape this:

`.claude/settings.json` is the operator's own file — permissions, env, model —
so AgentZero merges its hook entries in and leaves everything else untouched.
`.cursor/hooks.json` holds nothing but hooks, so that adapter owns its file.

Claude already reads `AGENTS.md` when no `CLAUDE.md` exists above the working
directory, so `System.md` reaches it by way of the `AGENTS.md` Codex also reads.
That stops silently the moment any `CLAUDE.md` appears, and does not happen at all
before v2.1.277 or on Bedrock — hence a `CLAUDE.md` that imports `AGENTS.md`
rather than relying on the default.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from adapter.codex import write_agents_md
from memory.host import interpreter, render

_ASSETS = Path(__file__).resolve().parent / "assets"
_HOOK_SCRIPT = ".claude/hooks/write-trace.py"

CLAUDE_MD = """\
# AgentZero System (generated)

Do not edit by hand. Refresh with:
`PYTHONPATH=src python -m adapter materialize --harness claude`

The System body lives in `AGENTS.md`, generated from the portable `System.md`.
This file imports it so Claude loads it whether or not a `CLAUDE.md` exists.

@AGENTS.md
"""

# (event, matcher) in the order Claude evaluates them; None means "every occurrence",
# which is all UserPromptSubmit and Stop support.
REGISTRATIONS: tuple[tuple[str, str | None], ...] = (
    ("UserPromptSubmit", None),
    ("PreToolUse", "Read"),
    ("PostToolUse", "Edit|Write"),
    ("PostToolUse", "mcp__.*"),
    ("PostToolUse", "Bash"),
    ("Stop", None),
)


def _hook_command() -> str:
    """Prefer python3 (macOS/Linux). Fall back to python (Windows, SETTLED #38).

    Anchored at `$CLAUDE_PROJECT_DIR`: a hook runs in the session's current
    directory, and once Bash has `cd`-ed into a subfolder a relative path names
    a script that is not there, so every later tool call loses its Trace event.
    """
    return f'{interpreter()} "{_PROJECT_DIR}/{_HOOK_SCRIPT}"'


_PROJECT_DIR = "$CLAUDE_PROJECT_DIR"


def materialize_claude(workspace: Path) -> None:
    """Write `CLAUDE.md`, merge hooks into `.claude/settings.json`, copy hook assets."""
    write_agents_md(workspace)  # AGENTS.md is the single generated System body
    (workspace / "CLAUDE.md").write_text(render(CLAUDE_MD), encoding="utf-8")

    hooks_dir = workspace / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for asset in _ASSETS.iterdir():
        if asset.is_file():
            target = hooks_dir / asset.name
            shutil.copy2(asset, target)
            if asset.suffix == ".sh":
                target.chmod(target.stat().st_mode | 0o111)

    settings_path = workspace / ".claude" / "settings.json"
    settings_path.write_text(
        json.dumps(merge_hooks(_read_settings(settings_path)), indent=2) + "\n",
        encoding="utf-8",
    )


def merge_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    """Replace AgentZero's hook groups, preserving every other key and entry.

    Identified by the command path, so re-materializing replaces rather than
    duplicating, and an operator's own hooks on the same events survive.
    """
    merged = dict(settings)
    hooks: dict[str, Any] = dict(merged.get("hooks") or {})
    command = _hook_command()

    for event in {name for name, _ in REGISTRATIONS}:
        kept = [
            group
            for group in hooks.get(event) or []
            if not _is_agentzero_group(group)
        ]
        hooks[event] = kept

    for event, matcher in REGISTRATIONS:
        group: dict[str, Any] = {}
        if matcher is not None:
            group["matcher"] = matcher
        group["hooks"] = [{"type": "command", "command": command, "timeout": 15}]
        hooks[event].append(group)

    merged["hooks"] = {name: entries for name, entries in hooks.items() if entries}
    return merged


def _is_agentzero_group(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    return any(
        _HOOK_SCRIPT in str(entry.get("command") or "")
        for entry in group.get("hooks") or []
        if isinstance(entry, dict)
    )


def _read_settings(path: Path) -> dict[str, Any]:
    """An unreadable settings file is the operator's; never silently replace it."""
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must be a JSON object")
    return loaded
