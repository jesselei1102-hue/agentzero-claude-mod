"""The confirmation surface: what the agent proposed, and the operator's yes or no.

Five stores carry `proposed → active`, and until now the only way to answer that
gate was to open a YAML file and edit `status:` — which USER_JOURNEY says the
operator never does. SETTLED #53 made T2 the terminal state for a long-tail
workspace, so for most workspaces this *is* the product's main interaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from memory.graph import (
    confirm_graph_item,
    edge_sentence,
    parse_graph,
    repoint_fact_ids,
    retire_graph_item,
)
from memory.host import command
from memory.lifecycle import (
    MemoryEntry,
    confirm_entry,
    confirm_episode,
    parse_entry,
    parse_episode,
    retire_entry,
    retire_episode,
    supersede_fact_key,
)

Kind = Literal["fact", "episode", "entity", "edge", "skill"]
_T = TypeVar("_T", "Pending", "Item")
KINDS: tuple[Kind, ...] = ("fact", "episode", "entity", "edge", "skill")

_HEADINGS = {
    "fact": "Facts — one-sentence project facts",
    "episode": "Episodes — time-stamped things that happened",
    "entity": "Graph entities — things this project talks about",
    "edge": "Graph edges — how those things relate",
    "skill": "Skills — procedures for a kind of task",
}


@dataclass(frozen=True)
class Pending:
    """One proposed item, described the way the operator has to judge it."""

    kind: Kind
    id: str
    sentence: str
    provenance: str
    sort_key: str

    @property
    def qualified_id(self) -> str:
        return f"{self.kind}:{self.id}"


def collect_pending(workspace: Path) -> tuple[Pending, ...]:
    """Every `proposed` item across Facts, Episodes, graph entities/edges and Skills."""
    memory_dir = workspace / "memory"
    found: list[Pending] = []
    found.extend(_pending_facts(memory_dir))
    found.extend(_pending_episodes(memory_dir / "episodes"))
    found.extend(_pending_graph(memory_dir / "graph.yaml"))
    found.extend(_pending_skills(workspace / "skills"))
    ordered: list[Pending] = []
    for kind in KINDS:
        group = [item for item in found if item.kind == kind]
        group.sort(key=lambda item: item.sort_key, reverse=True)
        ordered.extend(group)
    return tuple(ordered)


def resolve(workspace: Path, raw: str) -> Pending:
    """Find one pending item. A bare id must be unambiguous — never guess."""
    return _pick(collect_pending(workspace), raw, "no item waiting for confirmation")


@dataclass(frozen=True)
class Item:
    """Something on record, in any status — what `forget` looks up."""

    kind: Kind
    id: str
    sentence: str
    status: str

    @property
    def qualified_id(self) -> str:
        return f"{self.kind}:{self.id}"


def find(workspace: Path, raw: str) -> Item:
    """Find one item of any status. Same `kind:id` rules as `resolve`; never guess."""
    return _pick(_everything(workspace), raw, "nothing on record")


def _pick(items: Sequence[_T], raw: str, missing: str) -> _T:
    if ":" in raw:
        prefix, _, identifier = raw.partition(":")
        if prefix not in KINDS:
            raise ValueError(f"unknown kind {prefix!r}; expected one of {', '.join(KINDS)}")
        for item in items:
            if item.kind == prefix and item.id == identifier:
                return item
        raise ValueError(f"{missing} with id {raw!r}")

    matches = [item for item in items if item.id == raw]
    if not matches:
        raise ValueError(f"{missing} with id {raw!r}")
    if len(matches) > 1:
        candidates = ", ".join(item.qualified_id for item in matches)
        raise ValueError(f"{raw!r} is ambiguous; name one of: {candidates}")
    return matches[0]


def _everything(workspace: Path) -> list[Item]:
    from skills import parse_skill, project_skill_paths

    memory_dir = workspace / "memory"
    found: list[Item] = []
    for path in sorted(memory_dir.glob("*.yaml")):
        if path.name != "graph.yaml":
            fact = parse_entry(path)
            found.append(Item("fact", fact.id, fact.rule, fact.status))
    for path in sorted((memory_dir / "episodes").glob("*.yaml")):
        episode = parse_episode(path)
        found.append(Item("episode", episode.id, episode.rule, episode.status))
    graph_path = memory_dir / "graph.yaml"
    if graph_path.is_file():
        graph = parse_graph(graph_path)
        for entity in graph.entities:
            found.append(Item("entity", entity.id, entity.label, entity.status))
        for edge in graph.edges:
            found.append(Item("edge", edge.id, edge_sentence(graph, edge), edge.status))
    for path in project_skill_paths(workspace / "skills"):
        skill = parse_skill(path)
        found.append(Item("skill", skill.id, _skill_heading(skill), skill.status))
    return found


def confirm(workspace: Path, item: Pending) -> tuple[MemoryEntry, ...]:
    """proposed → active. Returns the Facts a confirmed Fact replaced, if any."""
    if item.kind == "fact":
        entry = confirm_entry(_fact_path(workspace, item.id))
        if entry.fact_key:
            return supersede_fact_key(workspace / "memory", entry.fact_key, keep_id=entry.id)
    elif item.kind == "episode":
        confirm_episode(_episode_path(workspace, item.id))
    elif item.kind == "entity" or item.kind == "edge":
        confirm_graph_item(workspace / "memory" / "graph.yaml", kind=item.kind, id=item.id)
    elif item.kind == "skill":
        from skills import confirm_skill

        skill = confirm_skill(_skill_path(workspace, item.id))
        # A new version replaces the confirmed one only now, not when drafted (#72).
        if skill.supersedes:
            retire(workspace, "skill", skill.supersedes)
    else:  # pragma: no cover - KINDS is closed
        raise ValueError(f"unknown kind {item.kind!r}")
    return ()


def reject(workspace: Path, item: Pending) -> None:
    """proposed → retired. A rejected proposal is evidence, so it is never deleted."""
    retire(workspace, item.kind, item.id)


def retire(workspace: Path, kind: Kind, identifier: str) -> None:
    """Any status → retired. Nothing is deleted: retiring is a learning outcome (#56)."""
    if kind == "fact":
        retire_entry(_fact_path(workspace, identifier))
        # A retired Fact leaves the hot set, so an entity must stop pointing at it.
        repoint_fact_ids(workspace / "memory" / "graph.yaml", {identifier: None})
    elif kind == "episode":
        retire_episode(_episode_path(workspace, identifier))
    elif kind == "entity" or kind == "edge":
        retire_graph_item(workspace / "memory" / "graph.yaml", kind=kind, id=identifier)
    elif kind == "skill":
        from skills import retire_skill

        retire_skill(_skill_path(workspace, identifier))
    else:  # pragma: no cover - KINDS is closed
        raise ValueError(f"unknown kind {kind!r}")


def render(pending: tuple[Pending, ...]) -> str:
    """Plain language, leading with the sentence to judge, ending with the command."""
    if not pending:
        return (
            "Nothing is waiting for you.\n\n"
            "That is a normal state: the agent only proposes something when it has\n"
            "a reason to, and a workspace can go a long time without one.\n"
        )

    count = len(pending)
    noun = "item is" if count == 1 else "items are"
    lines = [f"{count} {noun} waiting for you.", ""]
    for kind in KINDS:
        group = [item for item in pending if item.kind == kind]
        if not group:
            continue
        lines.append(_HEADINGS[kind])
        for item in group:
            lines.append(f"  {item.qualified_id}")
            lines.append(f"      {item.sentence}")
            lines.append(f"      {item.provenance}")
        lines.append("")
    first = pending[0].qualified_id
    # Hermes ran `review` in its last turn, saw the item it had proposed, and neither
    # asked nor confirmed: the list said what could be done, not what to do.
    lines.append(
        "  → ask the operator about each, one at a time, in their language; "
        "then run exactly what they answered:"
    )
    lines.append(f"  Confirm:  {command(f'memory review --confirm {first}')}")
    lines.append(f"  Reject:   {command(f'memory review --reject {first}')}")
    lines.append("")
    lines.append("  Confirming keeps it. Rejecting retires it — nothing is deleted.")
    return "\n".join(lines) + "\n"


def _fact_path(workspace: Path, identifier: str) -> Path:
    for path in sorted((workspace / "memory").glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        if parse_entry(path).id == identifier:
            return path
    raise ValueError(f"Fact not found: {identifier}")


def _episode_path(workspace: Path, identifier: str) -> Path:
    for path in sorted((workspace / "memory" / "episodes").glob("*.yaml")):
        if parse_episode(path).id == identifier:
            return path
    raise ValueError(f"Episode not found: {identifier}")


def _skill_path(workspace: Path, identifier: str) -> Path:
    from skills import parse_skill, project_skill_paths

    for path in project_skill_paths(workspace / "skills"):
        if parse_skill(path).id == identifier:
            return path
    raise ValueError(f"Skill not found: {identifier}")


def _pending_facts(memory_dir: Path) -> list[Pending]:
    items: list[Pending] = []
    if not memory_dir.is_dir():
        return items
    for path in sorted(memory_dir.glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        entry = parse_entry(path)
        if entry.status != "proposed":
            continue
        items.append(
            Pending(
                kind="fact",
                id=entry.id,
                sentence=entry.rule,
                provenance=_fact_provenance(entry),
                sort_key=entry.created_at,
            )
        )
    return items


def _pending_episodes(episodes_dir: Path) -> list[Pending]:
    items: list[Pending] = []
    if not episodes_dir.is_dir():
        return items
    for path in sorted(episodes_dir.glob("*.yaml")):
        episode = parse_episode(path)
        if episode.status != "proposed":
            continue
        items.append(
            Pending(
                kind="episode",
                id=episode.id,
                sentence=episode.rule,
                provenance=f"observed {episode.observed_at} during run {episode.source_run}",
                sort_key=episode.observed_at,
            )
        )
    return items


def _pending_graph(graph_path: Path) -> list[Pending]:
    items: list[Pending] = []
    if not graph_path.is_file():
        return items
    graph = parse_graph(graph_path)
    for entity in graph.entities:
        if entity.status != "proposed":
            continue
        linked = ", ".join(entity.fact_ids) if entity.fact_ids else "no Facts yet"
        items.append(
            Pending(
                kind="entity",
                id=entity.id,
                sentence=entity.label,
                provenance=f"{entity.author} proposed it; linked to {linked}",
                sort_key=entity.created_at,
            )
        )
    for edge in graph.edges:
        if edge.status != "proposed":
            continue
        items.append(
            Pending(
                kind="edge",
                id=edge.id,
                sentence=edge_sentence(graph, edge),
                provenance=f"{edge.author} proposed it",
                sort_key=edge.created_at,
            )
        )
    return items


def _pending_skills(skills_dir: Path) -> list[Pending]:
    from skills import parse_skill, project_skill_paths

    items: list[Pending] = []
    for path in project_skill_paths(skills_dir):
        skill = parse_skill(path)
        if skill.status not in {"proposed", "draft"}:
            continue
        heading = _skill_heading(skill)
        items.append(
            Pending(
                kind="skill",
                id=skill.id,
                sentence=heading,
                provenance=f"{skill.status} from runs {', '.join(skill.source_runs)}",
                sort_key=skill.id,
            )
        )
    return items


_NO_RUN = {"agent-inferred", "operator-stated"}
"""`propose` / `remember` defaults when the run has no id worth citing."""


def _fact_provenance(entry: MemoryEntry) -> str:
    if entry.source_run in _NO_RUN:
        return f"{entry.author} proposed it"
    return f"{entry.author} proposed it during run {entry.source_run}"


def _skill_heading(skill: Any) -> str:
    heading: str = next(
        (
            line.lstrip("# ").strip()
            for line in skill.procedure.splitlines()
            if line.startswith("#")
        ),
        skill.id,
    )
    return heading
