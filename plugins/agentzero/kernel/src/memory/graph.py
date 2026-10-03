"""Memory graph index: entities, edges, activation, query, markdown export (ADR 0006)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from math import sqrt
from pathlib import Path
from typing import Any, Literal

import yaml

from memory.text import legacy_slug, sentence_key, slug

_AUTHORS = frozenset({"human", "agent"})
_STATUSES = frozenset({"proposed", "active", "retired"})
_ENTITY_FIELDS = ("id", "label", "status", "created_at", "author")
_EDGE_FIELDS = ("id", "from", "to", "rel", "status", "created_at", "author")
GraphKind = Literal["entity", "edge"]
_DEFAULT_HOPS = 2
_DEFAULT_DECAY = 0.5
# A hint is direct task evidence; a link to a loaded Fact is weak evidence, since
# every in-scope Fact is in the hot set. Equal weights made every linked entity a
# direct match and flattened the ranking.
_HINT_WEIGHT = 1.0
_FACT_LINK_WEIGHT = 0.25


@dataclass(frozen=True)
class GraphEntity:
    id: str
    label: str
    status: str
    created_at: str
    author: str
    tags: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphEdge:
    id: str
    from_id: str
    to_id: str
    rel: str
    status: str
    created_at: str
    author: str
    note: str | None = None


@dataclass(frozen=True)
class MemoryGraph:
    entities: tuple[GraphEntity, ...] = ()
    edges: tuple[GraphEdge, ...] = ()

    def entity(self, entity_id: str) -> GraphEntity | None:
        for item in self.entities:
            if item.id == entity_id:
                return item
        return None

    def edge(self, edge_id: str) -> GraphEdge | None:
        for item in self.edges:
            if item.id == edge_id:
                return item
        return None


@dataclass(frozen=True)
class GraphIndexLine:
    entity_id: str
    line: str
    score: float = 0.0
    hops: int = 0


@dataclass(frozen=True)
class GraphActivation:
    lines: tuple[GraphIndexLine, ...] = ()
    entities: tuple[GraphEntity, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    truncated: bool = False
    warning: str | None = None


def parse_graph(path: Path) -> MemoryGraph:
    """Parse memory/graph.yaml. Missing file is not valid here; callers check exists."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded in (None, ""):
        return MemoryGraph()
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    entities_raw = loaded.get("entities") or []
    edges_raw = loaded.get("edges") or []
    if not isinstance(entities_raw, list) or not isinstance(edges_raw, list):
        raise ValueError("graph entities and edges must be lists")
    return MemoryGraph(
        entities=tuple(_entity_from_mapping(item) for item in entities_raw),
        edges=tuple(_edge_from_mapping(item) for item in edges_raw),
    )


def record_entity(
    graph_path: Path,
    *,
    id: str,
    label: str,
    author: str,
    created_at: str,
    tags: Sequence[str] = (),
    fact_ids: Sequence[str] = (),
) -> GraphEntity:
    """Append or replace an entity. Human → active; agent → proposed."""
    graph = _read_or_empty(graph_path)
    status = "active" if author == "human" else "proposed"
    entity = _entity_from_mapping(
        {
            "id": id,
            "label": label,
            "author": author,
            "status": status,
            "created_at": created_at,
            "tags": list(tags),
            "fact_ids": list(fact_ids),
        }
    )
    others = tuple(item for item in graph.entities if item.id != id)
    _write_graph(graph_path, MemoryGraph(entities=(*others, entity), edges=graph.edges))
    return entity


def record_edge(
    graph_path: Path,
    *,
    id: str,
    from_id: str,
    to_id: str,
    rel: str,
    author: str,
    created_at: str,
    note: str | None = None,
) -> GraphEdge:
    """Append or replace an edge. Human → active; agent → proposed."""
    graph = _read_or_empty(graph_path)
    status = "active" if author == "human" else "proposed"
    payload: dict[str, Any] = {
        "id": id,
        "from": from_id,
        "to": to_id,
        "rel": rel,
        "author": author,
        "status": status,
        "created_at": created_at,
    }
    if note is not None:
        payload["note"] = note
    edge = _edge_from_mapping(payload)
    others = tuple(item for item in graph.edges if item.id != id)
    _write_graph(graph_path, MemoryGraph(entities=graph.entities, edges=(*others, edge)))
    return edge


@dataclass(frozen=True)
class EntityWritten:
    entity: GraphEntity
    created: bool = False
    existing: bool = False
    """It was already on record in a state the writer would not change."""


@dataclass(frozen=True)
class LinkWritten:
    edge: GraphEdge
    created_entities: tuple[GraphEntity, ...] = ()
    existing: bool = False


def edge_sentence(graph: MemoryGraph, edge: GraphEdge) -> str:
    """"Acme owns Riverside model" — the labels a person reads, not the ids the file keys on."""
    ends = {item.id: item.label for item in graph.entities}
    return f"{ends.get(edge.from_id, edge.from_id)} {edge.rel} {ends.get(edge.to_id, edge.to_id)}"


def resolve_entity(graph: MemoryGraph, ref: str) -> GraphEntity | None:
    """An entity by id, or by label ignoring case and spacing; a live one beats a retired one."""
    wanted = ref.strip()
    key = sentence_key(ref)
    matches = [
        item for item in graph.entities if item.id == wanted or sentence_key(item.label) == key
    ]
    matches.sort(key=lambda item: item.status == "retired")
    return matches[0] if matches else None


def write_entity(
    graph_path: Path,
    label: str,
    *,
    author: str,
    now: datetime | None = None,
    tags: Sequence[str] = (),
    fact_ids: Sequence[str] = (),
) -> EntityWritten:
    """Add an entity by label. The operator's word is active; the agent's is proposed.

    The agent never changes something already on record, and never re-proposes what the
    operator rejected. The operator's word promotes a proposed or retired entity to active,
    keeping the tags and Fact links it already had.
    """
    label = label.strip()
    if not label:
        raise ValueError("an entity needs a label")
    graph = _read_or_empty(graph_path)
    clock = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    found = resolve_entity(graph, label)
    if found is not None:
        if author == "agent" or found.status == "active":
            return EntityWritten(found, existing=True)
        entity = record_entity(
            graph_path,
            id=found.id,
            label=found.label,
            author="human",
            created_at=clock,
            tags=found.tags,
            fact_ids=found.fact_ids,
        )
        return EntityWritten(entity)
    taken = {item.id for item in graph.entities}
    base, identifier, suffix = slug(label), slug(label), 1
    while identifier in taken:
        suffix += 1
        identifier = f"{base}-{suffix}"
    entity = record_entity(
        graph_path,
        id=identifier,
        label=label,
        author=author,
        created_at=clock,
        tags=tags,
        fact_ids=fact_ids,
    )
    return EntityWritten(entity, created=True)


def write_link(
    graph_path: Path,
    from_ref: str,
    rel: str,
    to_ref: str,
    *,
    author: str,
    now: datetime | None = None,
    note: str | None = None,
) -> LinkWritten:
    """Relate two things by name, creating whichever entity is missing.

    Same authorship rule as `write_entity`: the operator's word is active, the agent's is
    proposed and is never written over anything already on record.
    """
    rel = rel.strip()
    if not rel:
        raise ValueError("an edge needs a relationship")
    created: list[GraphEntity] = []
    ends: list[GraphEntity] = []
    for ref in (from_ref, to_ref):
        written = write_entity(graph_path, ref, author=author, now=now)
        ends.append(written.entity)
        if written.created:
            created.append(written.entity)
    source, target = ends
    if source.id == target.id:
        raise ValueError("an edge needs two different things")
    identifier = f"{source.id}--{slug(rel)}--{target.id}"
    graph = _read_or_empty(graph_path)
    # An edge written before ids kept non-ASCII letters is under its old id.
    found = graph.edge(identifier) or graph.edge(f"{source.id}--{legacy_slug(rel)}--{target.id}")
    if found is not None and (author == "agent" or found.status == "active"):
        return LinkWritten(found, tuple(created), existing=True)
    edge = record_edge(
        graph_path,
        id=identifier,
        from_id=source.id,
        to_id=target.id,
        rel=rel,
        author=author,
        created_at=(now or datetime.now().astimezone()).isoformat(timespec="seconds"),
        note=note,
    )
    return LinkWritten(edge, tuple(created))


def repoint_fact_ids(graph_path: Path, mapping: dict[str, str | None]) -> int:
    """Move entity links off Facts that were replaced (→ the new id) or withdrawn (→ None).

    Entities link Facts by id, and a replaced Fact keeps its file but leaves the hot set, so
    without this the link would quietly point at nothing that is ever loaded.
    """
    if not graph_path.is_file():
        return 0
    graph = parse_graph(graph_path)
    changed = 0
    entities: list[GraphEntity] = []
    for item in graph.entities:
        linked: list[str] = []
        for fact_id in item.fact_ids:
            target = mapping.get(fact_id, fact_id)
            if target and target not in linked:
                linked.append(target)
        if tuple(linked) != item.fact_ids:
            item = replace(item, fact_ids=tuple(linked))
            changed += 1
        entities.append(item)
    if changed:
        _write_graph(graph_path, MemoryGraph(entities=tuple(entities), edges=graph.edges))
    return changed


def confirm_graph_item(
    graph_path: Path, *, kind: GraphKind, id: str
) -> GraphEntity | GraphEdge:
    """Operator confirmation: proposed → active for an entity or edge."""
    graph = parse_graph(graph_path)
    if kind == "entity":
        current = graph.entity(id)
        if current is None:
            raise ValueError(f"graph entity not found: {id}")
        if current.status == "retired":
            raise ValueError("retired graph items cannot become active")
        if current.status == "active":
            return current
        updated = replace(current, status="active")
        entities = tuple(updated if item.id == id else item for item in graph.entities)
        _write_graph(graph_path, MemoryGraph(entities=entities, edges=graph.edges))
        return updated
    if kind == "edge":
        current_edge = graph.edge(id)
        if current_edge is None:
            raise ValueError(f"graph edge not found: {id}")
        if current_edge.status == "retired":
            raise ValueError("retired graph items cannot become active")
        if current_edge.status == "active":
            return current_edge
        updated_edge = replace(current_edge, status="active")
        edges = tuple(updated_edge if item.id == id else item for item in graph.edges)
        _write_graph(graph_path, MemoryGraph(entities=graph.entities, edges=edges))
        return updated_edge
    raise ValueError(f"kind must be entity or edge, got {kind!r}")


def retire_graph_item(
    graph_path: Path, *, kind: GraphKind, id: str
) -> GraphEntity | GraphEdge:
    """Retire an entity or edge. It leaves activation but stays readable as history."""
    graph = parse_graph(graph_path)
    if kind == "entity":
        current = graph.entity(id)
        if current is None:
            raise ValueError(f"graph entity not found: {id}")
        if current.status == "retired":
            return current
        updated = replace(current, status="retired")
        entities = tuple(updated if item.id == id else item for item in graph.entities)
        _write_graph(graph_path, MemoryGraph(entities=entities, edges=graph.edges))
        return updated
    if kind == "edge":
        current_edge = graph.edge(id)
        if current_edge is None:
            raise ValueError(f"graph edge not found: {id}")
        if current_edge.status == "retired":
            return current_edge
        updated_edge = replace(current_edge, status="retired")
        edges = tuple(updated_edge if item.id == id else item for item in graph.edges)
        _write_graph(graph_path, MemoryGraph(entities=graph.entities, edges=edges))
        return updated_edge
    raise ValueError(f"kind must be entity or edge, got {kind!r}")


def activate_graph(
    graph: MemoryGraph | Path,
    *,
    task_hints: Sequence[str] = (),
    fact_ids: Sequence[str] = (),
    k: int = 20,
    hops: int = _DEFAULT_HOPS,
    decay: float = _DEFAULT_DECAY,
) -> GraphActivation:
    """Task-relevant active entities as index lines, capped at K (ADR 0006).

    Seeds come from direct hint/fact matches, then spread along active edges for
    `hops` rounds with `decay` per hop. Each hop is normalized by the degree of
    both endpoints, so a link between two hubs carries less evidence than a link
    between two specific entities. Direct matches always outrank spread-only
    neighbours at equal evidence.
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if hops < 0:
        raise ValueError(f"hops must be >= 0, got {hops}")
    if not 0 < decay <= 1:
        raise ValueError(f"decay must be in (0, 1], got {decay}")
    loaded = parse_graph(graph) if isinstance(graph, Path) else graph
    active = [item for item in loaded.entities if item.status == "active"]
    active_ids = {item.id for item in active}
    hints = tuple(hint.casefold() for hint in task_hints if hint.strip())
    wanted_facts = set(fact_ids)

    usable_edges = [
        edge
        for edge in loaded.edges
        if edge.status == "active" and edge.from_id in active_ids and edge.to_id in active_ids
    ]
    dangling = [
        edge.id
        for edge in loaded.edges
        if edge.status == "active"
        and (edge.from_id not in active_ids or edge.to_id not in active_ids)
    ]

    seeds = {
        entity.id: _relevance_score(entity, hints=hints, fact_ids=wanted_facts)
        for entity in active
    }
    totals, hop_of = _spread(seeds, usable_edges, hops=hops, decay=decay)

    scored = [(totals.get(entity.id, 0.0), entity.created_at, entity) for entity in active]
    relevant = [item for item in scored if item[0] > 0]
    warnings: list[str] = []
    if relevant:
        ranked = relevant
    else:
        ranked = scored
        if hints or wanted_facts:
            warnings.append(
                "no graph entities matched task hints; falling back to most recent active entities"
            )

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    chosen = [item[2] for item in ranked[:k]]
    truncated = len(ranked) > k
    if truncated:
        warnings.append(f"graph activation truncated to k={k} of {len(ranked)} candidates")
    if dangling:
        warnings.append(
            "active edges skipped because an endpoint is missing or not active: "
            + ", ".join(sorted(dangling))
        )

    chosen_ids = {entity.id for entity in chosen}
    lines = tuple(
        GraphIndexLine(
            entity_id=entity.id,
            line=_index_line(entity),
            score=round(totals.get(entity.id, 0.0), 4),
            hops=hop_of.get(entity.id, 0),
        )
        for entity in chosen
    )
    incident = tuple(
        edge for edge in usable_edges if edge.from_id in chosen_ids and edge.to_id in chosen_ids
    )
    return GraphActivation(
        lines=lines,
        entities=tuple(chosen),
        edges=incident,
        truncated=truncated,
        warning="; ".join(warnings) if warnings else None,
    )


def _spread(
    seeds: dict[str, float],
    edges: Sequence[GraphEdge],
    *,
    hops: int,
    decay: float,
) -> tuple[dict[str, float], dict[str, int]]:
    """Spreading activation over an undirected view of the active edges.

    Contribution along an edge is divided by sqrt(degree(source) * degree(target)):
    hubs neither broadcast nor absorb their way into every activation set.
    """
    totals = {node: value for node, value in seeds.items() if value > 0}
    hop_of = dict.fromkeys(totals, 0)
    if hops == 0 or not edges or not totals:
        return totals, hop_of

    neighbours: dict[str, list[str]] = {}
    for edge in edges:
        if edge.from_id == edge.to_id:
            continue
        neighbours.setdefault(edge.from_id, []).append(edge.to_id)
        neighbours.setdefault(edge.to_id, []).append(edge.from_id)
    degree = {node: max(len(items), 1) for node, items in neighbours.items()}

    frontier = dict(totals)
    for hop in range(1, hops + 1):
        nxt: dict[str, float] = {}
        for source, value in frontier.items():
            for target in neighbours.get(source, ()):
                damping = sqrt(degree.get(source, 1) * degree.get(target, 1))
                nxt[target] = nxt.get(target, 0.0) + value * decay / damping
        if not nxt:
            break
        for node, value in nxt.items():
            totals[node] = totals.get(node, 0.0) + value
            hop_of.setdefault(node, hop)
        frontier = nxt
    return totals, hop_of


def _relevance_score(
    entity: GraphEntity, *, hints: Sequence[str], fact_ids: set[str]
) -> float:
    haystack = " ".join(
        (entity.id, entity.label, *entity.tags, *entity.fact_ids)
    ).casefold()
    score = 0.0
    for hint in hints:
        if hint in haystack:
            score += _HINT_WEIGHT
    score += _FACT_LINK_WEIGHT * sum(1 for fact_id in entity.fact_ids if fact_id in fact_ids)
    return score


def _index_line(entity: GraphEntity) -> str:
    parts = [f"{entity.id} — {entity.label}"]
    if entity.tags:
        parts.append("[" + ", ".join(entity.tags) + "]")
    if entity.fact_ids:
        parts.append("facts: " + ", ".join(entity.fact_ids))
    return " ".join(parts)


def query_graph(
    graph: MemoryGraph | Path,
    *,
    tag: str | None = None,
    fact_id: str | None = None,
    rel: str | None = None,
    entity_id: str | None = None,
    include_retired: bool = False,
) -> MemoryGraph:
    """On-demand subgraph by tag, fact_id, rel, or neighborhood (ADR 0006)."""
    loaded = parse_graph(graph) if isinstance(graph, Path) else graph

    def visible_entity(item: GraphEntity) -> bool:
        if include_retired:
            return True
        return item.status == "active"

    def visible_edge(item: GraphEdge) -> bool:
        if include_retired:
            return True
        return item.status == "active"

    entities = [item for item in loaded.entities if visible_entity(item)]
    edges = [item for item in loaded.edges if visible_edge(item)]
    selected_entities: list[GraphEntity]
    selected_edges: list[GraphEdge]

    if entity_id is not None:
        center = next((item for item in entities if item.id == entity_id), None)
        if center is None:
            return MemoryGraph()
        neighbor_ids = {entity_id}
        selected_edges = []
        for edge in edges:
            if edge.from_id == entity_id:
                neighbor_ids.add(edge.to_id)
                selected_edges.append(edge)
            elif edge.to_id == entity_id:
                neighbor_ids.add(edge.from_id)
                selected_edges.append(edge)
        selected_entities = [item for item in entities if item.id in neighbor_ids]
    elif rel is not None:
        selected_edges = [edge for edge in edges if edge.rel == rel]
        ids = {edge.from_id for edge in selected_edges} | {edge.to_id for edge in selected_edges}
        selected_entities = [item for item in entities if item.id in ids]
    else:
        selected_entities = list(entities)
        if tag is not None:
            needle = tag.casefold()
            selected_entities = [
                item for item in selected_entities if needle in {t.casefold() for t in item.tags}
            ]
        if fact_id is not None:
            selected_entities = [
                item for item in selected_entities if fact_id in item.fact_ids
            ]
        ids = {item.id for item in selected_entities}
        selected_edges = [
            edge for edge in edges if edge.from_id in ids and edge.to_id in ids
        ]

    return MemoryGraph(entities=tuple(selected_entities), edges=tuple(selected_edges))


def export_graph_markdown(graph_path: Path, *, destination: Path | None = None) -> Path:
    """Regenerate a read-only Mermaid view from graph.yaml. Never a second source of truth."""
    graph = parse_graph(graph_path)
    target = destination if destination is not None else graph_path.with_name("graph.md")
    lines = [
        "<!-- generated from memory/graph.yaml; do not edit as truth -->",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for entity in graph.entities:
        label = entity.label.replace('"', "'")
        suffix = "" if entity.status == "active" else f" ({entity.status})"
        lines.append(f'  {entity.id}["{label}{suffix}"]')
    for edge in graph.edges:
        rel = edge.rel.replace("|", "/")
        lines.append(f"  {edge.from_id} -->|{rel}| {edge.to_id}")
    lines.append("```")
    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _read_or_empty(path: Path) -> MemoryGraph:
    if not path.exists():
        return MemoryGraph()
    return parse_graph(path)


def _parse_timestamp(value: Any, *, field: str) -> str:
    if value in (None, ""):
        raise ValueError(f"graph {field} must be an ISO timestamp")
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value)
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"graph {field} must be an ISO timestamp, got {text!r}") from exc
    return text


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ValueError(f"graph {field} must be a list of strings when present")
    return tuple(str(item) for item in value)


def _entity_from_mapping(payload: Any) -> GraphEntity:
    if not isinstance(payload, dict):
        raise ValueError("graph entity must be a YAML mapping")
    missing = [
        name for name in _ENTITY_FIELDS if name not in payload or payload[name] in (None, "")
    ]
    if missing:
        raise ValueError(f"graph entity missing fields: {', '.join(missing)}")
    author = str(payload["author"])
    status = str(payload["status"])
    if author not in _AUTHORS:
        raise ValueError(f"graph author must be human or agent, got {author!r}")
    if status not in _STATUSES:
        raise ValueError(f"graph status must be proposed, active, or retired, got {status!r}")
    return GraphEntity(
        id=str(payload["id"]),
        label=str(payload["label"]),
        status=status,
        created_at=_parse_timestamp(payload["created_at"], field="created_at"),
        author=author,
        tags=_string_tuple(payload.get("tags"), field="tags"),
        fact_ids=_string_tuple(payload.get("fact_ids"), field="fact_ids"),
    )


def _edge_from_mapping(payload: Any) -> GraphEdge:
    if not isinstance(payload, dict):
        raise ValueError("graph edge must be a YAML mapping")
    missing = [name for name in _EDGE_FIELDS if name not in payload or payload[name] in (None, "")]
    if missing:
        raise ValueError(f"graph edge missing fields: {', '.join(missing)}")
    author = str(payload["author"])
    status = str(payload["status"])
    if author not in _AUTHORS:
        raise ValueError(f"graph author must be human or agent, got {author!r}")
    if status not in _STATUSES:
        raise ValueError(f"graph status must be proposed, active, or retired, got {status!r}")
    note_raw = payload.get("note")
    note = None if note_raw in (None, "") else str(note_raw)
    return GraphEdge(
        id=str(payload["id"]),
        from_id=str(payload["from"]),
        to_id=str(payload["to"]),
        rel=str(payload["rel"]),
        status=status,
        created_at=_parse_timestamp(payload["created_at"], field="created_at"),
        author=author,
        note=note,
    )


def _entity_to_mapping(entity: GraphEntity) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": entity.id,
        "label": entity.label,
        "tags": list(entity.tags),
        "status": entity.status,
        "fact_ids": list(entity.fact_ids),
        "author": entity.author,
        "created_at": entity.created_at,
    }
    return payload


def _edge_to_mapping(edge: GraphEdge) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": edge.id,
        "from": edge.from_id,
        "to": edge.to_id,
        "rel": edge.rel,
        "status": edge.status,
        "author": edge.author,
        "created_at": edge.created_at,
    }
    if edge.note:
        payload["note"] = edge.note
    return payload


def _write_graph(path: Path, graph: MemoryGraph) -> None:
    payload = {
        "entities": [_entity_to_mapping(item) for item in graph.entities],
        "edges": [_edge_to_mapping(item) for item in graph.edges],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
