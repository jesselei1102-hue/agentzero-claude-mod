"""`skills run`: the only way a Skill's script runs (#72, ADR 0008).

The command, not the agent's goodwill, holds the line (#69): the hashes are the
version the operator confirmed, the default is a plan, `--apply` needs an
active Skill, and a Skill formed from one run needs the agent's one-sentence
check that this batch still fits (`--reviewed`) — a check that can stop a run
but never promote a Skill (#46). `--apply` writes its own use record, so a
script-backed Skill counts as used on harnesses with no hooks and no MCP.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from memory.host import command
from skills.assets import ENTRY, SCRIPTS_DIRNAME, mismatches
from skills.lifecycle import Skill, parse_skill, project_skill_paths

USE_RECORD_KIND = "skill-run"


@dataclass(frozen=True)
class RunRequest:
    skill_id: str
    template: bool = False
    input: Path | None = None
    output: Path | None = None
    append_to: Path | None = None
    reviewed: str | None = None
    apply: bool = False
    in_place: tuple[Path, ...] = ()
    """Folders whose files the script may rename where they are (#76)."""


class RefusedError(Exception):
    """The run cannot go ahead; the message says what to do instead."""


def run(workspace: Path, request: RunRequest, *, now: datetime | None = None) -> str:
    """Run the Skill's script and return what to print. Raises RefusedError."""
    path, skill = _find(workspace, request.skill_id)
    skill_dir = path.parent
    if not skill.assets:
        raise RefusedError(f"skill:{skill.id} has no script; follow its procedure instead")
    if skill.status == "retired":
        raise RefusedError(f"skill:{skill.id} is retired and is not run")
    changed = mismatches(skill_dir, skill.assets)
    if changed:
        raise RefusedError(
            f"{', '.join(changed)} changed since the operator confirmed skill:{skill.id}; "
            "it will not run. Copy the script into work/ for this run, and offer the "
            "change as a new version with `skills draft --supersedes`"
        )
    entry = skill_dir / SCRIPTS_DIRNAME / ENTRY
    if request.template:
        header = _script(workspace, entry, ["template"])
        return (
            header.rstrip()
            + "\n\n→ fill one row per source file in this format, then run "
            + command(f"skills run {skill.id} --input <records.csv>")
            + "\n"
        )

    if request.input is None or not request.input.is_file():
        raise RefusedError(
            "name the filled hand-off with --input <records.csv>; "
            + command(f"skills run {skill.id} --template")
            + " prints its columns"
        )
    if request.apply and skill.status != "active":
        raise RefusedError(
            f"skill:{skill.id} is {skill.status}; show the operator this plan and ask. "
            f"On yes: {command(f'memory review --confirm skill:{skill.id}')}, then --apply"
        )
    runs_on_record = len(skill.source_runs) + _applied_uses(workspace, skill)
    reviewed = (request.reviewed or "").strip()
    if runs_on_record < 2 and not reviewed:
        raise RefusedError(
            f"skill:{skill.id} was formed from one run. Before running it, check that this "
            "request and a few of this batch's inputs still fit what it was made for "
            "(same kind of document, same fields, same goal), then pass your conclusion "
            'in one sentence: --reviewed "<conclusion>". If they do not fit, do not run it: '
            "tell the operator what differs"
        )

    now = now or datetime.now().astimezone()
    output = request.output or workspace / "work" / skill.id / now.strftime("%Y-%m-%d")
    arguments = ["apply" if request.apply else "plan", "--input", str(request.input)]
    arguments += ["--output", str(output)]
    if request.append_to is not None:
        arguments += ["--append-to", str(request.append_to)]
    for folder in request.in_place:
        arguments += ["--in-place", str(folder)]
    watched = _watched_folders(workspace, request.input, request.in_place, output)
    before = _snapshot(watched) if request.apply else {}
    produced = _script(workspace, entry, arguments)

    lines: list[str] = []
    if reviewed:
        lines.append(f"Reviewed: {reviewed}")
        lines.append("")
    if request.in_place:
        folders = ", ".join(str(folder) for folder in request.in_place)
        lines.append(
            f"In place: files under {folders} will be renamed, not copied; "
            "skills run writes a map that undoes every rename"
        )
        lines.append("")
    lines.append(produced.rstrip())
    lines.append("")
    if request.apply:
        moved, missing = _compare(before, _snapshot(watched))
        map_path = _write_map(output, moved) if moved or request.in_place else None
        record = _write_use_record(
            workspace, skill, request, output, reviewed, now, map_path=map_path
        )
        outside = [
            old for old, _new in moved
            if not any(folder == old.parent or folder in old.parents for folder in request.in_place)
        ]
        if outside or missing:
            raise RefusedError(
                "the script moved or changed a source file without --in-place"
                + (f" ({', '.join(str(path) for path in outside[:5])})" if outside else "")
                + (f"; gone: {', '.join(str(path) for path in missing[:5])}" if missing else "")
                + f". The map to undo it is {map_path}; tell the operator, and return "
                f"skill:{skill.id} to proposed if the script did it: "
                + command(f"memory review --reject skill:{skill.id}")
            )
        lines.append(f"recorded: {record.relative_to(workspace)}")
        if map_path is not None:
            lines.append(f"renamed in place: {len(moved)}; to undo, rename back from {map_path}")
        lines.append(
            f"→ tell the operator what was written to {output} and what needs their review; "
            "if the result is wrong because of the script, the Skill goes back to proposed"
        )
    else:
        again = [f"skills run {skill.id}", f"--input {request.input}", f"--output {output}"]
        if request.append_to is not None:
            again.append(f"--append-to {request.append_to}")
        again.extend(f"--in-place {folder}" for folder in request.in_place)
        if reviewed:
            again.append(f'--reviewed "{reviewed}"')
        again.append("--apply")
        lines.append(
            "→ nothing was written. Show the operator this plan; on yes run "
            + command(" ".join(again))
        )
    return "\n".join(lines) + "\n"


def _find(workspace: Path, skill_id: str) -> tuple[Path, Skill]:
    for path in project_skill_paths(workspace / "skills"):
        skill = parse_skill(path)
        if skill.id == skill_id:
            return path, skill
    raise RefusedError(f"no Skill with id {skill_id!r}; {command('skills list')} shows them")


def _script(workspace: Path, entry: Path, arguments: list[str]) -> str:
    # The interpreter `./a0` chose: Python 3.11+ with PyYAML, which is what a script may use.
    completed = subprocess.run(
        [sys.executable, str(entry), *arguments],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip() or f"exit {completed.returncode}"
        hint = missing_module_hint(message)
        raise RefusedError(f"the script stopped: {message}" + (f"\n{hint}" if hint else ""))
    return completed.stdout


def missing_module_hint(message: str) -> str | None:
    """openpyxl is allowed but not guaranteed (#76): say how to add it to ./a0's Python."""
    found = re.search(r"No module named '([A-Za-z0-9_]+)", message)
    if not found:
        return None
    return (
        f"→ {found.group(1)} is not installed for the Python ./a0 uses; ask the operator to "
        f"run: {sys.executable} -m pip install {found.group(1)}"
    )


_NOT_OURS = frozenset({"node_modules", "__pycache__", ".git", ".venv"})


def _watched_folders(
    workspace: Path, records: Path, in_place: tuple[Path, ...], output: Path
) -> list[Path]:
    """The in-place folders and every folder holding a source the hand-off names.

    The framework does not know the hand-off's columns (#72), so any cell that names
    an existing file counts as a source.
    """
    folders = list(in_place)
    output = output.resolve()
    for cell in _cells(records):
        path = Path(cell).expanduser()
        path = path if path.is_absolute() else (workspace / path)
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if not is_file:
            continue
        folder = path.resolve().parent
        if folder == output or output in folder.parents or folder in folders:
            continue
        folders.append(folder)
    return folders


def _cells(records: Path) -> list[str]:
    text = records.read_text(encoding="utf-8", errors="replace")
    if records.suffix.lower() == ".json":
        found: list[str] = []

        def walk(value: object) -> None:
            if isinstance(value, str):
                found.append(value)
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        try:
            walk(json.loads(text))
        except json.JSONDecodeError:
            return []
        return found
    return [cell for row in csv.reader(text.splitlines()) for cell in row if cell.strip()]


def _snapshot(folders: list[Path]) -> dict[Path, str]:
    files: dict[Path, str] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and not _NOT_OURS & set(path.relative_to(folder).parts):
                files[path.resolve()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _compare(
    before: dict[Path, str], after: dict[Path, str]
) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """(old, new) for each file that moved, by content; and files that are gone or changed."""
    appeared: dict[str, list[Path]] = {}
    for path, digest in after.items():
        if path not in before:
            appeared.setdefault(digest, []).append(path)
    moved: list[tuple[Path, Path]] = []
    missing: list[Path] = []
    for path, digest in sorted(before.items()):
        if after.get(path) == digest:
            continue
        candidates = appeared.get(digest) or []
        if candidates:
            moved.append((path, candidates.pop(0)))
        else:
            missing.append(path)
    return moved, missing


def _write_map(output: Path, moved: list[tuple[Path, Path]]) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "in-place-map.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["old", "new"])
        writer.writerows([str(old), str(new)] for old, new in moved)
    return path


def _applied_uses(workspace: Path, skill: Skill) -> int:
    """Applied runs of this very version: a changed script starts from zero."""
    count = 0
    for record in _use_records(workspace):
        detail = record.get("skill_run") or {}
        if detail.get("skill") == skill.id and detail.get("assets") == dict(skill.assets):
            count += 1
    return count


def _use_records(workspace: Path) -> list[dict[str, Any]]:
    traces = workspace / "memory" / "traces"
    if not traces.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(traces.glob("skillrun-*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("kind") == USE_RECORD_KIND:
            records.append(payload)
    return records


def _write_use_record(
    workspace: Path,
    skill: Skill,
    request: RunRequest,
    output: Path,
    reviewed: str,
    now: datetime,
    *,
    map_path: Path | None = None,
) -> Path:
    traces = workspace / "memory" / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    stem = f"skillrun-{now.strftime('%Y%m%dT%H%M%S')}-{skill.id}"
    destination = traces / f"{stem}.yaml"
    suffix = 2
    while destination.exists():
        destination = traces / f"{stem}-{suffix}.yaml"
        suffix += 1
    # Trace-shaped, so lint's "used since intake" reads it like any run; it has no
    # tool calls, so it derives no task class (#59) and is not a scored run.
    payload: dict[str, Any] = {
        "run_id": destination.stem,
        "kind": USE_RECORD_KIND,
        "timestamp": now.isoformat(timespec="seconds"),
        "task_as_asked": "",
        "connected_mcps": [],
        "tool_calls": [],
        "loaded_skill_ids": [skill.id],
        "loaded_memory_ids": [],
        "output_yaml": {"path": "", "hash": ""},
        "skill_run": {
            "skill": skill.id,
            "assets": dict(skill.assets),
            "input": str(request.input),
            "output": str(output),
            "append_to": None if request.append_to is None else str(request.append_to),
            "reviewed": reviewed or None,
            "in_place": [str(folder) for folder in request.in_place],
            "in_place_map": None if map_path is None else str(map_path),
        },
    }
    destination.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return destination
