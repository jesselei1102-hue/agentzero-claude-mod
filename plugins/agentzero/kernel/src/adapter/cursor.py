"""Cursor adapter: materialize portable System.md into native Cursor files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from memory.host import interpreter, render

_ASSETS = Path(__file__).resolve().parent / "assets"
_RULE_NAME = "system.mdc"
_FRONTMATTER = """\
---
description: AgentZero System — discover Role, Knowledge, Tools; when Review may run
alwaysApply: true
---

"""
HOOK_EVENTS = (
    "beforeSubmitPrompt",
    "beforeReadFile",
    "afterFileEdit",
    "afterMCPExecution",
    "afterShellExecution",
    "stop",
)


def _hook_command() -> str:
    """Prefer python3 (macOS/Linux). Fall back to python (Windows, SETTLED #38)."""
    return f"{interpreter()} .cursor/hooks/write-trace.py"


def system_rule(system: str) -> str:
    """What `.cursor/rules/system.mdc` holds for this System body; preflight compares."""
    return _FRONTMATTER + render(system.lstrip())


def materialize_cursor(workspace: Path) -> None:
    """Write `.cursor/rules` and Trace hooks from `System.md`. Fail if System.md is missing."""
    system = (workspace / "System.md").read_text(encoding="utf-8")
    rules_dir = workspace / ".cursor" / "rules"
    hooks_dir = workspace / ".cursor" / "hooks"
    rules_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / _RULE_NAME).write_text(system_rule(system), encoding="utf-8")
    hooks_config = {
        "version": 1,
        "hooks": {
            name: [{"command": _hook_command(), "timeout": 15}] for name in HOOK_EVENTS
        },
    }
    (workspace / ".cursor" / "hooks.json").write_text(
        json.dumps(hooks_config, indent=2) + "\n",
        encoding="utf-8",
    )
    for asset in _ASSETS.iterdir():
        if asset.is_file():
            target = hooks_dir / asset.name
            shutil.copy2(asset, target)
            if asset.suffix == ".sh":
                target.chmod(target.stat().st_mode | 0o111)
