"""Cursor adapter: stdin hook payloads → Trace writer. Fail open."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from traces.normalize import task_as_asked, to_cursor_payload
from traces.writer import write_trace

_MCP_EVENT = "afterMCPExecution"
_STOP_EVENT = "stop"
_PROMPT_EVENT = "beforeSubmitPrompt"
_EDIT_EVENT = "afterFileEdit"
_READ_EVENT = "beforeReadFile"
_SHELL_EVENT = "afterShellExecution"
_SUBAGENT_STOP_EVENT = "subagentStop"

_MAX_COMMANDS = 200
_MAX_COMMAND_CHARS = 500
_MAX_WORK_FILES = 100
_MTIME_SLACK = 2.0
"""Seconds: some file systems keep whole-second mtimes, which can read as before the prompt."""
_STALE_STAGING = 24 * 3600
"""Seconds after which a staged run that never stopped is removed."""


def handle_event(payload: Mapping[str, Any], workspace_root: Path) -> Path | None:
    """Stage each event of a run; on stop, write a Trace under memory/traces.

    Every event is one appended line, never a read-modify-write: Codex runs tool calls
    in parallel, each fires a hook process, and processes rewriting one meta file left
    it as valid JSON plus another write's tail, so the Stop failed and the Trace of a
    real run was lost (SETTLED #90).
    """
    payload = to_cursor_payload(payload)
    run_id = payload.get("generation_id")
    if not run_id:
        raise ValueError("hook payload must include generation_id as the run id")
    staging_dir = workspace_root / "memory" / "traces" / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    events_path = staging_dir / f"{run_id}.jsonl"
    meta_path = staging_dir / f"{run_id}.meta.json"
    event_name = payload.get("hook_event_name")

    if event_name in _STAGED_EVENTS:
        _append(events_path, {**_staged(payload, event_name), "at": time.time()})
        return None
    if event_name not in (_STOP_EVENT, _SUBAGENT_STOP_EVENT):
        # Any other event still marks when a turn with no prompt event began.
        _append(events_path, {"hook_event_name": "seen", "at": time.time()})
        return None

    staged = _read_staged(events_path)
    meta = _fold(staged, _read_meta(meta_path), workspace_root)
    if event_name == _SUBAGENT_STOP_EVENT and "prompt" in meta:
        # Codex sends no Stop for a subagent's turn (SETTLED #83). Only a turn that
        # never had a prompt is a subagent's; a prompted turn is the parent's, and its
        # own Stop will come, whichever turn id this event carries.
        return None
    _sweep_staging(staging_dir)

    # A turn is a run when it called a work tool or left something under work/ (SETTLED #80).
    # Development chats do neither and must not become Traces (the framework repo shares
    # these projects), nor must a turn whose only calls drove the agent app itself (#79).
    from memory.taskclass import is_host_control

    mcp_events = [event for event in staged if event.get("hook_event_name") == _MCP_EVENT]
    work_files = _work_written(workspace_root, meta.get("started_epoch"))
    if not work_files and not any(
        not is_host_control(str(event.get("mcp_server_name") or "")) for event in mcp_events
    ):
        events_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return None

    stop = dict(payload)
    if event_name == _SUBAGENT_STOP_EVENT:
        stop["hook_event_name"] = _STOP_EVENT
        stop["subagent"] = str(payload.get("agent_type") or "subagent")
    if not stop.get("prompt"):
        stop["prompt"] = meta.get("prompt") or ""
    if not stop.get("output_yaml_path"):
        stop["output_yaml_path"] = meta.get("output_yaml_path") or ""
    if "loaded_skill_ids" not in stop:
        stop["loaded_skill_ids"] = meta.get("loaded_skill_ids") or []
    if "loaded_memory_ids" not in stop:
        stop["loaded_memory_ids"] = meta.get("loaded_memory_ids") or []
    stop["shell_commands"] = meta.get("shell_commands") or []
    stop["work_files"] = work_files
    if not stop.get("timestamp"):
        stop["timestamp"] = datetime.now(UTC).isoformat()
    stop["loaded_memory_ids"] = _with_hot_set(
        stop["loaded_memory_ids"], workspace_root, str(stop["timestamp"])
    )
    destination = write_trace([*mcp_events, stop], workspace_root / "memory" / "traces")
    events_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    return destination


_STAGED_EVENTS = frozenset({_PROMPT_EVENT, _SHELL_EVENT, _EDIT_EVENT, _READ_EVENT, _MCP_EVENT})


def _staged(payload: Mapping[str, Any], event_name: str) -> dict[str, Any]:
    """The line an event stages: the whole payload for an MCP call, else what is used."""
    if event_name == _MCP_EVENT:
        return dict(payload)
    if event_name == _PROMPT_EVENT:
        return {"hook_event_name": event_name, "prompt": str(payload.get("prompt") or "")}
    if event_name == _SHELL_EVENT:
        command = str(payload.get("command") or "")[:_MAX_COMMAND_CHARS]
        return {"hook_event_name": event_name, "command": command}
    return {"hook_event_name": event_name, "file_path": str(payload.get("file_path") or "")}


def _append(path: Path, record: Mapping[str, Any]) -> None:
    """One line in one write on an append-mode descriptor, so parallel hooks never interleave."""
    line = (json.dumps(dict(record), default=str, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(descriptor, line)
    finally:
        os.close(descriptor)


def _read_staged(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    staged: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            staged.append(loaded)
    return staged


def _fold(
    staged: list[dict[str, Any]], legacy: dict[str, Any], workspace_root: Path
) -> dict[str, Any]:
    """What the staged lines say about the run, as the meta file used to hold it.

    `legacy` is a meta file an older hook left for a run that began before the upgrade.
    """
    meta = dict(legacy)
    moments = [float(line["at"]) for line in staged if isinstance(line.get("at"), int | float)]
    if moments and "started_epoch" not in meta:
        # A subagent's turn has no prompt event; its first event is when it began.
        meta["started_epoch"] = min(moments)
    for line in staged:
        event = line.get("hook_event_name")
        if event == _PROMPT_EVENT:
            meta["prompt"] = task_as_asked(str(line.get("prompt") or ""))
            meta["started_epoch"] = line.get("at", meta.get("started_epoch"))
        elif event == _SHELL_EVENT:
            _record_command(meta, str(line.get("command") or ""))
        elif event == _EDIT_EVENT:
            file_path = str(line.get("file_path") or "")
            if _is_output_yaml(file_path, workspace_root):
                meta["output_yaml_path"] = file_path
        elif event == _READ_EVENT:
            _record_loaded(meta, str(line.get("file_path") or ""), workspace_root)
    return meta


def main() -> None:
    # Windows hosts (Cursor / PowerShell) often prepend a UTF-8 BOM on stdin.
    raw = sys.stdin.buffer.read().decode("utf-8-sig").lstrip("\ufeff")
    payload = json.loads(raw) if raw.strip() else None
    if not isinstance(payload, dict):
        print("{}", flush=True)
        return
    root = _root_from(payload)
    output: dict[str, Any] = {}
    try:
        handle_event(payload, root)
        output = hook_output(payload, root)
    except Exception as exc:
        print(f"trace hook failed: {exc}", file=sys.stderr)
    print(json.dumps(output), flush=True)


def hook_output(payload: Mapping[str, Any], workspace_root: Path) -> dict[str, Any]:
    """What the hook answers the harness: nothing, or one line asking for the hot set.

    Codex and Claude Code add a UserPromptSubmit hook's `additionalContext` to the turn;
    Cursor's beforeSubmitPrompt can only allow or block, so it gets nothing.
    """
    if payload.get("hook_event_name") != "UserPromptSubmit":
        return {}
    from memory.runstate import prompt_reminder

    session = payload.get("session_id")
    line = prompt_reminder(workspace_root, session=str(session) if session else None)
    if not line:
        return {}
    return {
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}
    }


def _root_from(payload: Mapping[str, Any]) -> Path:
    """Trust the payload over the process. Cursor sends workspace_roots; Codex and
    Claude Code send cwd, and falling through to Path.cwd() puts the Trace
    wherever the harness happened to launch the hook."""
    roots = payload.get("workspace_roots") or []
    if roots:
        return _workspace_root(str(roots[0]))
    cwd = payload.get("cwd")
    if cwd:
        return _enclosing_workspace(_workspace_root(str(cwd)))
    return Path.cwd()


def _enclosing_workspace(path: Path) -> Path:
    """Claude Code's cwd follows Bash, so after `cd work/x` it names a subfolder.

    Taken as the root, that put the Trace in `work/x/memory/traces/`, where no
    lint or scorer looks. Walk up to the folder that holds the workspace.
    """
    for candidate in (path, *path.parents):
        if (candidate / "System.md").is_file() and (candidate / "memory").is_dir():
            return candidate
    return path


def _workspace_root(raw: str) -> Path:
    """Normalize Cursor workspace_roots, including POSIX-style '/C:/...' on Windows."""
    text = raw.strip()
    if len(text) >= 3 and text[0] == "/" and text[2] == ":":
        text = text[1:]
    return Path(text)


def _read_meta(path: Path) -> dict[str, Any]:
    """A meta file an older hook wrote; a torn one keeps what parses before the tear."""
    if not path.is_file():
        return {}
    try:
        loaded, _end = json.JSONDecoder().raw_decode(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _is_output_yaml(file_path: str, workspace_root: Path) -> bool:
    if not file_path.endswith((".yaml", ".yml")):
        return False
    path = Path(file_path)
    resolved = _resolve(path)
    if path.name == "knowledge.yaml":
        return False
    traces = (workspace_root / "memory" / "traces").resolve()
    if traces == resolved or traces in resolved.parents:
        return False
    # Prepared reference material is written as YAML too, often dozens of files; it is
    # Knowledge, not what the run produced, and must not become the Scored output.
    knowledge = (workspace_root / "knowledge").resolve()
    if knowledge in resolved.parents:
        return False
    memory_root = (workspace_root / "memory").resolve()
    return resolved.parent != memory_root


def _record_loaded(meta: dict[str, Any], file_path: str, workspace_root: Path) -> None:
    path = Path(file_path)
    resolved = _resolve(path)
    skills = (workspace_root / "skills").resolve()
    memory = (workspace_root / "memory").resolve()
    traces = (workspace_root / "memory" / "traces").resolve()
    if traces == resolved or traces in resolved.parents:
        return
    if path.suffix == ".md" and (resolved.parent == skills or skills in resolved.parents):
        # A Skill with scripts is a directory; its id is the directory's name (#72).
        skill_id = resolved.parent.name if path.name == "SKILL.md" else path.stem
        _append_id(meta, "loaded_skill_ids", skill_id)
        return
    if path.suffix in {".yaml", ".yml"} and (
        resolved.parent == memory or memory in resolved.parents
    ):
        _append_id(meta, "loaded_memory_ids", path.stem)


def _with_hot_set(loaded: Any, workspace_root: Path, timestamp: str) -> list[str]:
    """Add the Facts this session's hot set loaded; it arrives as command output, not a read."""
    from memory.runstate import hot_set_fact_ids

    ids = [str(item) for item in loaded] if isinstance(loaded, list) else []
    try:
        at = datetime.fromisoformat(timestamp)
    except ValueError:
        return ids
    if at.tzinfo is None:
        at = at.astimezone()
    for fact_id in hot_set_fact_ids(workspace_root / "memory", at=at):
        if fact_id not in ids:
            ids.append(fact_id)
    return ids


def _sweep_staging(staging_dir: Path) -> None:
    """Drop staged runs that never stopped: a subagent whose end was never seen."""
    cutoff = time.time() - _STALE_STAGING
    for path in staging_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def _record_command(meta: dict[str, Any], command: str) -> None:
    current = meta.get("shell_commands")
    commands = list(current) if isinstance(current, list) else []
    if command and len(commands) < _MAX_COMMANDS:
        commands.append(command[:_MAX_COMMAND_CHARS])
    meta["shell_commands"] = commands


def _work_written(workspace_root: Path, started: Any) -> list[str]:
    """Files under work/ changed since the turn began, however they were written.

    A script run from the shell writes its deliverable without an edit event, so the
    folder, not the tool, is the evidence (#57, #72).
    """
    work = workspace_root / "work"
    if not isinstance(started, int | float) or not work.is_dir():
        return []
    written: list[str] = []
    for folder, _dirs, files in os.walk(work):
        for name in files:
            path = Path(folder) / name
            try:
                changed = path.stat().st_mtime >= started - _MTIME_SLACK
            except OSError:
                continue
            if changed:
                written.append(path.relative_to(workspace_root).as_posix())
    return sorted(written)[:_MAX_WORK_FILES]


def _append_id(meta: dict[str, Any], key: str, item: str) -> None:
    current = meta.get(key)
    ids = [str(existing) for existing in current] if isinstance(current, list) else []
    if item not in ids:
        ids.append(item)
    meta[key] = ids


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


if __name__ == "__main__":
    main()
