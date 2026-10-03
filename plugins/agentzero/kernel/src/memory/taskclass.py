"""Derive a task class from what a run did, not from what it called itself.

SETTLED #25: a Trace written by the agent is the agent deciding what to record
about itself — the same blind spot as self-review. So a task class is *derived*
from evidence the harness already wrote, never declared by the agent.

The derivation is the convention's own words made computable. The hard Review
trigger says "two or more scored runs of the same task class with roughly
consistent tool-call sequences": the tool-call sequence *is* the class.

A run with no tool calls has no derivable class. That is not a gap — SETTLED #53
says a workspace with no repeating head correctly stays at T2, and silence is
the right answer there.

Calls to the agent app's own controls (naming a chapter, renaming the chat) are
not work, and a run of only those has no class either (SETTLED #79).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_LABEL_STEPS = 6

HOST_CONTROL_PREFIXES: tuple[str, ...] = ("ccd_", "cursor-app-control", "codex_app")
"""MCP servers that drive the agent app itself, not the operator's work: the Claude
desktop app's `ccd_*` (chapters, panes, PR binding), Cursor's app control, and the
Codex app's own (`open_in_codex`)."""


def is_host_control(server: str) -> bool:
    return server.startswith(HOST_CONTROL_PREFIXES)


@dataclass(frozen=True)
class TaskClass:
    """One derived class, and the runs that fall into it."""

    key: str
    label: str
    steps: tuple[str, ...]
    mcps: tuple[str, ...]
    run_ids: tuple[str, ...]

    @property
    def recurred(self) -> bool:
        return len(self.run_ids) > 1


def derive(trace: Mapping[str, Any]) -> tuple[str, str, tuple[str, ...], tuple[str, ...]] | None:
    """(key, label, steps, mcps) for a Trace, or None when it made no tool calls."""
    connected = [str(name) for name in trace.get("connected_mcps") or [] if name]
    mcps = tuple(sorted(name for name in connected if not is_host_control(name)))
    # Traces written before calls carried their server cannot say which call was the
    # app's; when every server connected was, so was every call.
    steps = _steps(trace.get("tool_calls"), unattributed_is_host=bool(connected) and not mcps)
    if not steps:
        return None
    # The same sequence against a different set of servers is a different class:
    # Skills re-bind Tools each run (#34), so the available surface is part of what
    # made the sequence work.
    material = "|".join(mcps) + "::" + ">".join(steps)
    key = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return key, _label(steps, mcps), steps, mcps


def detect(traces: Sequence[Mapping[str, Any]]) -> tuple[TaskClass, ...]:
    """Group Traces into task classes, most-seen first."""
    grouped: dict[str, dict[str, Any]] = {}
    for trace in traces:
        derived = derive(trace)
        if derived is None:
            continue
        key, label, steps, mcps = derived
        run_id = str(trace.get("run_id") or "")
        bucket = grouped.setdefault(
            key, {"label": label, "steps": steps, "mcps": mcps, "runs": []}
        )
        if run_id and run_id not in bucket["runs"]:
            bucket["runs"].append(run_id)
    classes = [
        TaskClass(
            key=key,
            label=str(bucket["label"]),
            steps=tuple(bucket["steps"]),
            mcps=tuple(bucket["mcps"]),
            run_ids=tuple(bucket["runs"]),
        )
        for key, bucket in grouped.items()
    ]
    classes.sort(key=lambda item: (len(item.run_ids), item.label), reverse=True)
    return tuple(classes)


def _steps(tool_calls: Any, *, unattributed_is_host: bool = False) -> tuple[str, ...]:
    """Tool names in order, with consecutive repeats collapsed.

    Calling the same tool three times instead of five is the same way of working;
    "roughly consistent" has to mean something, and this is the cheapest reading
    of it that does not need a similarity threshold nobody has tuned.
    """
    if not isinstance(tool_calls, list):
        return ()
    names: list[str] = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            continue
        server = call.get("server")
        if is_host_control(str(server or "")) or (server is None and unattributed_is_host):
            continue
        name = str(call.get("name") or "").strip()
        if not name:
            continue
        if names and names[-1] == name:
            continue
        names.append(name)
    return tuple(names)


def _label(steps: Sequence[str], mcps: Sequence[str]) -> str:
    if len(steps) > MAX_LABEL_STEPS:
        hidden = len(steps) - MAX_LABEL_STEPS + 1
        shown = [*steps[: MAX_LABEL_STEPS - 1], f"…(+{hidden})", steps[-1]]
    else:
        shown = list(steps)
    prefix = f"{', '.join(mcps)}: " if mcps else ""
    return prefix + " > ".join(shown)


@dataclass(frozen=True)
class ScoredRun:
    run_id: str
    task_class: str
    score_path: str
    timestamp: str


def scored_runs_by_class(
    traces: Sequence[Mapping[str, Any]], scores: Mapping[str, str]
) -> dict[str, tuple[ScoredRun, ...]]:
    """Scored runs grouped by derived class, oldest first.

    `evaluate_reuse` compares a later Score against an earlier one but has no way
    to say which two runs belong together; SETTLED #18.4's "a third run of the
    same task class" was a pairing a human had to make by hand. This is that
    pairing, computed from the same evidence the class itself comes from.
    """
    grouped: dict[str, list[ScoredRun]] = {}
    for trace in traces:
        run_id = str(trace.get("run_id") or "")
        score_path = scores.get(run_id)
        if not run_id or not score_path:
            continue
        derived = derive(trace)
        if derived is None:
            continue
        key = derived[0]
        grouped.setdefault(key, []).append(
            ScoredRun(
                run_id=run_id,
                task_class=key,
                score_path=score_path,
                timestamp=str(trace.get("timestamp") or ""),
            )
        )
    return {
        key: tuple(sorted(runs, key=lambda run: (run.timestamp, run.run_id)))
        for key, runs in grouped.items()
    }
