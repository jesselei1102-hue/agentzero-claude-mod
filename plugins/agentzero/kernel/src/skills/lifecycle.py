"""Skill schema and lifecycle for the convention layer."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from score import Score, no_lower

_REQUIRED_FRONTMATTER = ("id", "status", "source_runs", "memory_ids")
_STATUSES = frozenset({"draft", "proposed", "active", "retired"})
_FORBIDDEN_FIELDS = frozenset(
    {"rule", "facts", "standards", "knowledge", "standard", "project_facts"}
)
_FORBIDDEN_HEADING = re.compile(
    r"^#{1,6}\s+(facts|project facts|standards?|knowledge)\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Skill:
    id: str
    status: str
    source_runs: tuple[str, ...]
    memory_ids: tuple[str, ...]
    procedure: str
    task_class: str | None = None
    """Derived key of the task class this Skill serves (memory.taskclass)."""

    description: str | None = None
    """One sentence: when to use this Skill. What System rule 5 matches on."""

    assets: tuple[tuple[str, str], ...] = ()
    """(path under the Skill directory, sha256) of each confirmed script (#72)."""

    supersedes: str | None = None
    """Id of the Skill this version replaces once confirmed (#72)."""

    confirmed_at: str | None = None
    """When the operator confirmed it: lint judges use only by runs after this."""


SKILL_FILENAME = "SKILL.md"
"""A Skill that carries scripts is a directory: skills/<id>/SKILL.md + scripts/."""


def project_skill_paths(skills_dir: Path) -> list[Path]:
    """Learned Skill files: skills/*.md and skills/<id>/SKILL.md, never builtins.

    `_shared.md` and `_routing.md` are reference docs, not Skills (#47).
    """
    if not skills_dir.is_dir():
        return []
    flat = [path for path in skills_dir.glob("*.md") if not path.name.startswith("_")]
    nested = [
        path
        for path in skills_dir.glob(f"*/{SKILL_FILENAME}")
        if path.parent.name != "builtin"
    ]
    return sorted(flat + nested)


def parse_skill(path: Path) -> Skill:
    """Parse a Skill markdown file against the settled fields."""
    text = path.read_text(encoding="utf-8")
    payload, procedure = _split_frontmatter(text)
    return _from_mapping(payload, procedure)


def draft_skill(
    destination: Path,
    *,
    id: str,
    source_runs: Sequence[str],
    procedure: str,
    memory_ids: Sequence[str] = (),
    task_class: str | None = None,
    description: str,
    assets: Sequence[tuple[str, str]] = (),
    supersedes: str | None = None,
) -> Skill:
    """Write a Skill draft. It stays draft until the operator confirms.

    `description` is required here though optional when parsing: a Skill written
    without one is unroutable from birth, while Skills that predate the field
    must keep loading.
    """
    if not description.strip():
        raise ValueError("a Skill needs one sentence saying when to use it")
    skill = _from_mapping(
        {
            "id": id,
            "status": "draft",
            "source_runs": list(source_runs),
            "memory_ids": list(memory_ids),
            "description": description.strip(),
            **({"task_class": task_class} if task_class else {}),
            **({"assets": dict(assets)} if assets else {}),
            **({"supersedes": supersedes} if supersedes else {}),
        },
        procedure,
    )
    _write(destination, skill)
    return skill


def confirm_skill(path: Path, *, now: datetime | None = None) -> Skill:
    """Operator confirmation: update the status field from draft or proposed to active."""
    current = parse_skill(path)
    if current.status == "retired":
        raise ValueError("retired Skills cannot become active")
    if current.status == "active":
        return current
    if current.assets:
        # The operator confirms a version, not whatever the file says later (#72).
        from skills.assets import mismatches

        changed = mismatches(path.parent, current.assets)
        if changed:
            raise ValueError(
                f"{', '.join(changed)} changed since it was drafted; "
                "draft it again so the operator confirms what will run"
            )
    clock = now or datetime.now().astimezone()
    confirmed = replace(
        current, status="active", confirmed_at=clock.isoformat(timespec="seconds")
    )
    _write(path, confirmed)
    return confirmed


def retire_skill(path: Path) -> Skill:
    """Retire a Skill. A rejected draft is kept as evidence, not deleted."""
    current = parse_skill(path)
    if current.status == "retired":
        return current
    retired = replace(current, status="retired")
    _write(path, retired)
    return retired


def evaluate_reuse(path: Path, *, later: Score, earlier: Score) -> Skill:
    """If an active Skill's reuse Score is lower than the prior run, return it to proposed."""
    current = parse_skill(path)
    if current.status != "active" or no_lower(later, earlier):
        return current
    demoted = replace(current, status="proposed")
    _write(path, demoted)
    return demoted


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("Skill must be markdown with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Skill frontmatter is not closed")
    loaded = yaml.safe_load(parts[1])
    if not isinstance(loaded, dict):
        raise ValueError("Skill frontmatter must be a YAML mapping")
    return loaded, parts[2].strip()


def _from_mapping(payload: dict[str, Any], procedure: str) -> Skill:
    forbidden = [name for name in payload if name in _FORBIDDEN_FIELDS]
    if forbidden:
        raise ValueError(
            f"Skill must not store project facts or standards "
            f"(forbidden fields: {', '.join(sorted(forbidden))})"
        )
    missing = [
        name
        for name in _REQUIRED_FRONTMATTER
        if name not in payload or payload[name] in (None, "")
    ]
    if missing:
        raise ValueError(f"Skill missing fields: {', '.join(missing)}")
    status = str(payload["status"])
    if status not in _STATUSES:
        raise ValueError(
            f"Skill status must be draft, proposed, active, or retired, got {status!r}"
        )
    source_runs = _id_list(payload["source_runs"], field="source_runs")
    if not source_runs:
        raise ValueError("Skill source_runs must cite at least one run")
    memory_ids = _id_list(payload["memory_ids"], field="memory_ids")
    if not procedure:
        raise ValueError("Skill procedure body must not be empty")
    if _FORBIDDEN_HEADING.search(procedure):
        raise ValueError("Skill must not dump project facts or standards into the procedure")
    raw_class = payload.get("task_class")
    raw_description = payload.get("description")
    raw_supersedes = payload.get("supersedes")
    raw_confirmed = payload.get("confirmed_at")
    return Skill(
        id=str(payload["id"]),
        status=status,
        source_runs=source_runs,
        memory_ids=memory_ids,
        procedure=procedure,
        task_class=None if raw_class in (None, "") else str(raw_class),
        description=None if raw_description in (None, "") else str(raw_description),
        assets=_assets(payload.get("assets")),
        supersedes=None if raw_supersedes in (None, "") else str(raw_supersedes),
        confirmed_at=None if raw_confirmed in (None, "") else str(raw_confirmed),
    )


def _assets(value: Any) -> tuple[tuple[str, str], ...]:
    if value in (None, {}):
        return ()
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(digest, str) and digest.startswith("sha256:")
        for key, digest in value.items()
    ):
        raise ValueError("Skill assets must map each script path to its sha256:<hex>")
    return tuple(sorted(value.items()))


def _id_list(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Skill {field} must be a list of ids")
    ids = tuple(str(item) for item in value if str(item).strip())
    if len(ids) != len(value):
        raise ValueError(f"Skill {field} must not contain empty ids")
    return ids


def _write(path: Path, skill: Skill) -> None:
    payload: dict[str, Any] = {
        "id": skill.id,
        "status": skill.status,
        "source_runs": list(skill.source_runs),
        "memory_ids": list(skill.memory_ids),
    }
    if skill.description:
        payload["description"] = skill.description
    if skill.task_class:
        payload["task_class"] = skill.task_class
    if skill.assets:
        payload["assets"] = dict(skill.assets)
    if skill.supersedes:
        payload["supersedes"] = skill.supersedes
    if skill.confirmed_at:
        payload["confirmed_at"] = skill.confirmed_at
    frontmatter = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{frontmatter}\n---\n\n{skill.procedure.rstrip()}\n", encoding="utf-8")
