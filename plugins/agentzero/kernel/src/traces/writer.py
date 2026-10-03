"""Write a Trace from Cursor hook payloads (afterMCPExecution + stop)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

_MCP_EVENT = "afterMCPExecution"
_STOP_EVENT = "stop"


def write_trace(events: Sequence[Mapping[str, Any]], traces_dir: Path) -> Path:
    """Consume MCP-completion and stop-style payloads; write a Trace YAML for the run."""
    stop = _stop_event(events)
    mcp_events = [event for event in events if event.get("hook_event_name") == _MCP_EVENT]
    run_id = _run_id(stop, events)
    traces_dir.mkdir(parents=True, exist_ok=True)
    destination = traces_dir / f"{run_id}.yaml"
    payload: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": str(stop.get("timestamp") or ""),
        "task_as_asked": str(stop.get("prompt") or ""),
        "connected_mcps": _connected_mcps(stop, mcp_events),
        "tool_calls": [_tool_call(event) for event in mcp_events],
        "shell_commands": [str(item) for item in (stop.get("shell_commands") or [])],
        "work_files": [str(item) for item in (stop.get("work_files") or [])],
        "loaded_skill_ids": [str(item) for item in (stop.get("loaded_skill_ids") or [])],
        "loaded_memory_ids": [str(item) for item in (stop.get("loaded_memory_ids") or [])],
        "output_yaml": _output_yaml(stop),
    }
    if stop.get("subagent"):
        payload["subagent"] = str(stop["subagent"])
    source = _run_id_source(stop, events)
    if source:
        payload["run_id_source"] = source
    if any(event.get("run_id_degraded") for event in (stop, *events)):
        payload["run_id_degraded"] = True
    destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return destination


def run_is_valid(run_id: str, traces_dir: Path) -> bool:
    """A run counts for DoD only when a Trace for that run id exists."""
    return (traces_dir / f"{run_id}.yaml").is_file()


def _stop_event(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    for event in reversed(events):
        if event.get("hook_event_name") == _STOP_EVENT:
            return event
    raise ValueError("write_trace requires a stop-style payload")


def _run_id(stop: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> str:
    for event in (stop, *reversed(events)):
        run_id = event.get("generation_id")
        if run_id:
            return str(run_id)
    raise ValueError("hook payloads must include generation_id as the run id")


def _run_id_source(
    stop: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
) -> str | None:
    """Which harness field the run id came from, when it was not generation_id."""
    for event in (stop, *reversed(events)):
        source = event.get("run_id_source")
        if source:
            return str(source)
    return None


def _connected_mcps(stop: Mapping[str, Any], mcp_events: Sequence[Mapping[str, Any]]) -> list[str]:
    if "connected_mcps" in stop:
        return [str(name) for name in stop.get("connected_mcps") or [] if name]
    names: list[str] = []
    for event in mcp_events:
        name = event.get("mcp_server_name")
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _tool_call(event: Mapping[str, Any]) -> dict[str, Any]:
    result = event.get("result_json")
    if isinstance(result, str):
        result_text = result
    elif result is None:
        result_text = ""
    else:
        result_text = json.dumps(result)
    return {
        "server": str(event.get("mcp_server_name") or ""),
        "name": str(event.get("tool_name") or ""),
        "arguments": _arguments(event.get("tool_input")),
        "result_size": len(result_text.encode("utf-8")),
        "error": _error(event),
        "retry": bool(event.get("retry")),
    }


def _error(event: Mapping[str, Any]) -> str | None:
    error = event.get("error")
    if error in (None, ""):
        return None
    return str(error)


def _arguments(tool_input: Any) -> Any:
    if isinstance(tool_input, str):
        try:
            return json.loads(tool_input)
        except json.JSONDecodeError:
            return tool_input
    return tool_input if tool_input is not None else {}


def _output_yaml(stop: Mapping[str, Any]) -> dict[str, str]:
    raw_path = stop.get("output_yaml_path") or ""
    if not raw_path:
        return {"path": "", "hash": ""}
    path = Path(str(raw_path))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "hash": f"sha256:{digest}"}
