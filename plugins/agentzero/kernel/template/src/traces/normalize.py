"""Normalize Codex and Claude Code hook payloads into the Cursor-shaped Trace path."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_PATCH_FILE = re.compile(
    r"\*\*\* (?:Update|Add|Delete) File:\s*(.+)",
    re.MULTILINE,
)
_READ_TOOLS = frozenset(
    {
        "Read",
        "read_file",
        "ReadFile",
        "view_file",
        "View",
    }
)
# Claude Code and Codex name their shell tool Bash (Codex's unified exec matches as Bash
# too); Cursor sends afterShellExecution itself.
_SHELL_TOOLS = frozenset({"Bash", "exec_command"})
# The Codex app wraps what the operator typed: its own UI state in a block it marks
# as not the request, then "## My request:" before the operator's words.
_AMBIENT_BLOCK = re.compile(
    r"<([\w-]+)[^>]*source=\"ambient-ui-state\"[^>]*>.*?</\1>", re.DOTALL
)
_REQUEST_LABEL = re.compile(r"\A\s*## My request:\s*")


def to_cursor_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Map Codex lifecycle fields onto the Cursor hook contract used by traces.hook."""
    out = dict(payload)
    if not out.get("generation_id"):
        _adopt_run_id(out)
    if not out.get("workspace_roots") and out.get("cwd"):
        out["workspace_roots"] = [str(out["cwd"])]

    event = str(out.get("hook_event_name") or "")
    if event == "UserPromptSubmit":
        out["hook_event_name"] = "beforeSubmitPrompt"
        return out
    if event == "Stop":
        out["hook_event_name"] = "stop"
        return out
    if event == "SubagentStop":
        out["hook_event_name"] = "subagentStop"
        return out
    if event in {"PreToolUse", "PostToolUse"}:
        return _normalize_tool_event(out, event)
    return out


# Harness field carrying the run id, best granularity first. SETTLED #37 pins
# run_id to the harness's *generation* id: Claude's session_id spans a whole
# session, so preferring it would collapse many turns into one Trace and break
# the "two runs of the same task class" Review trigger.
_RUN_ID_FIELDS = ("turn_id", "prompt_id", "session_id")
_DEGRADED_RUN_ID_FIELDS = frozenset({"session_id"})


def task_as_asked(prompt: str) -> str:
    """What the operator typed, without the UI state an agent app wraps around it."""
    text = _AMBIENT_BLOCK.sub("", prompt)
    return _REQUEST_LABEL.sub("", text).strip()


def _adopt_run_id(payload: dict[str, Any]) -> None:
    """Fill generation_id from whichever id this harness supplies, and say which."""
    for field in _RUN_ID_FIELDS:
        value = payload.get(field)
        if not value:
            continue
        payload["generation_id"] = str(value)
        payload["run_id_source"] = field
        if field in _DEGRADED_RUN_ID_FIELDS:
            # ADR 0003 / SETTLED #25: a degraded capture is recorded, never silent.
            payload["run_id_degraded"] = True
        return


def _normalize_tool_event(payload: dict[str, Any], event: str) -> dict[str, Any]:
    tool = str(payload.get("tool_name") or "")
    if event == "PostToolUse" and tool.startswith("mcp__"):
        server, name = _split_mcp_tool(tool)
        payload["hook_event_name"] = "afterMCPExecution"
        payload["mcp_server_name"] = server
        payload["tool_name"] = name
        if "result_json" not in payload:
            payload["result_json"] = payload.get("tool_response")
        return payload

    if event == "PostToolUse" and tool in {"apply_patch", "Edit", "Write"}:
        # Codex sends an apply_patch command string; Claude Code sends the path
        # directly, and without this an edit never becomes afterFileEdit, so
        # output_yaml_path stays empty and a scored run loses its output hash.
        paths = _paths_from_apply_patch(payload.get("tool_input"))
        direct = _file_path_from_input(payload.get("tool_input"))
        chosen = paths[-1] if paths else direct
        if chosen:
            payload["hook_event_name"] = "afterFileEdit"
            payload["file_path"] = chosen
            return payload

    if event == "PostToolUse" and tool in _SHELL_TOOLS:
        command = _command_from_input(payload.get("tool_input"))
        if command:
            payload["hook_event_name"] = "afterShellExecution"
            payload["command"] = command
            return payload

    if tool in _READ_TOOLS:
        path = _file_path_from_input(payload.get("tool_input"))
        if path:
            payload["hook_event_name"] = "beforeReadFile"
            payload["file_path"] = path
            return payload
    return payload


def _split_mcp_tool(tool: str) -> tuple[str, str]:
    # mcp__server__tool_name (tool_name may contain underscores / __)
    parts = tool.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return "", tool
    return parts[1], "__".join(parts[2:])


def _paths_from_apply_patch(tool_input: Any) -> list[str]:
    command = ""
    if isinstance(tool_input, Mapping):
        command = str(tool_input.get("command") or "")
    elif isinstance(tool_input, str):
        command = tool_input
    return [match.strip() for match in _PATCH_FILE.findall(command) if match.strip()]


def _file_path_from_input(tool_input: Any) -> str | None:
    if not isinstance(tool_input, Mapping):
        return None
    for key in ("file_path", "path", "target_file"):
        value = tool_input.get(key)
        if value:
            return str(value)
    return None


def _command_from_input(tool_input: Any) -> str | None:
    if not isinstance(tool_input, Mapping):
        return None
    command = tool_input.get("command")
    if isinstance(command, list):
        return " ".join(str(part) for part in command) or None
    return str(command) if command else None
