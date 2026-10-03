"""What Skills exist, and when each applies — the lookup System rule 5 needs.

Rule 5 is "Role lens → matching project `active` Skill → else a Layer 1
builtin", and with more than one learned Skill that meant reading every body on
every run. This answers it in one call, in the rule's own precedence order.

Not a generated `skills/_index.md`: a committed copy has drifted from its source
twice in this repository already. A command reads the files that are there.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory.host import command
from skills.lifecycle import Skill, parse_skill, project_skill_paths

BUILTIN_DIRNAME = "builtin"


@dataclass(frozen=True)
class Listed:
    layer: str  # "project" | "builtin"
    skill: Skill
    path: Path

    @property
    def routable(self) -> bool:
        return bool(self.skill.description) and self.skill.status in {"proposed", "active"}


def list_skills(workspace: Path, *, include_retired: bool = False) -> tuple[Listed, ...]:
    """Project Skills first, then Layer 1 builtins — rule 5's precedence."""
    skills_dir = workspace / "skills"
    found: list[Listed] = []
    builtin_dir = skills_dir / BUILTIN_DIRNAME
    builtins = (
        # `_shared.md` and `_routing.md` are reference docs, not Skills:
        # they carry no frontmatter and parse_skill does not apply (#47).
        [path for path in sorted(builtin_dir.glob("*.md")) if not path.name.startswith("_")]
        if builtin_dir.is_dir()
        else []
    )
    for layer, paths in (("project", project_skill_paths(skills_dir)), ("builtin", builtins)):
        for path in paths:
            skill = parse_skill(path)
            if skill.status == "retired" and not include_retired:
                continue
            found.append(Listed(layer=layer, skill=skill, path=path))
    return tuple(found)


def render(listed: tuple[Listed, ...]) -> str:
    if not listed:
        return (
            "No Skills in this workspace yet.\n\n"
            "That is a normal state: a Skill is only kept after the same kind of work\n"
            "has come back and you confirmed a draft.\n"
        )
    lines: list[str] = []
    for layer, heading in (
        ("project", "Project Skills — confirmed for this work, tried first"),
        ("builtin", "Layer 1 builtins — product defaults, used when no project Skill matches"),
    ):
        group = [item for item in listed if item.layer == layer]
        if not group:
            continue
        lines.append(heading)
        for item in group:
            status = "" if item.skill.status == "active" else f"  ({item.skill.status})"
            lines.append(f"  {item.skill.id}{status}")
            sentence = item.skill.description or "(no description — cannot be routed to)"
            lines.append(f"      {sentence}")
            if item.skill.task_class:
                lines.append(f"      task_class: {item.skill.task_class}")
            if item.skill.assets:
                lines.append(f"      runs a script: {command(f'skills run {item.skill.id}')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
