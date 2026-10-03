"""Memory entry schema and lifecycle for the convention layer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from memory.graph import GraphActivation, activate_graph, parse_graph, repoint_fact_ids
from memory.text import RESEMBLES, resemblance, sentence_key, slug

_FIELDS = ("id", "rule", "scope", "author", "status", "created_at", "source_run")
_OPTIONAL_FIELDS = ("fact_key", "effective_from", "effective_to", "tags", "said")
_SCOPES = frozenset({"task", "project"})
_AUTHORS = frozenset({"human", "agent"})
_STATUSES = frozenset({"proposed", "active", "retired"})
_SCOPE_WIDTH = {"task": 0, "project": 1}


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    rule: str
    scope: str
    author: str
    status: str
    created_at: str
    source_run: str
    fact_key: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    tags: tuple[str, ...] = ()
    said: str | None = None
    """The operator's own words an operator-stated Fact was recorded from (`remember --said`)."""

    @property
    def effective_fact_key(self) -> str:
        """Logical fact family; defaults to id when fact_key is omitted (ADR 0005)."""
        return self.fact_key if self.fact_key else self.id


def parse_entry(path: Path) -> MemoryEntry:
    """Parse a Memory entry YAML file against the settled fields."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    return _from_mapping(loaded)


def record_entry(
    destination: Path,
    *,
    id: str,
    rule: str,
    scope: str,
    author: str,
    created_at: str,
    source_run: str,
    fact_key: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    tags: Sequence[str] | None = None,
    said: str | None = None,
) -> MemoryEntry:
    """Write a Memory entry. Human-authored facts enter active; agent-inferred stay proposed."""
    status = "active" if author == "human" else "proposed"
    payload: dict[str, Any] = {
        "id": id,
        "rule": rule,
        "scope": scope,
        "author": author,
        "status": status,
        "created_at": created_at,
        "source_run": source_run,
    }
    if fact_key is not None:
        payload["fact_key"] = fact_key
    if effective_from is not None:
        payload["effective_from"] = effective_from
    if effective_to is not None:
        payload["effective_to"] = effective_to
    if tags is not None:
        payload["tags"] = list(tags)
    if said is not None:
        payload["said"] = said
    entry = _from_mapping(payload)
    _write(destination, entry)
    return entry


@dataclass(frozen=True)
class Remembered:
    entry: MemoryEntry
    path: Path
    superseded: tuple[MemoryEntry, ...] = ()
    existing: bool = False
    """The same sentence was already on record, so nothing was written."""
    resembling: tuple[MemoryEntry, ...] = ()
    """Active Facts that may say the same thing at another time, left as they were."""


def remember_fact(
    memory_dir: Path,
    *,
    rule: str,
    scope: str = "project",
    fact_key: str | None = None,
    tags: Sequence[str] | None = None,
    source_run: str = "operator-stated",
    now: datetime | None = None,
    said: str | None = None,
) -> Remembered:
    """Record something the operator said, active at once (SETTLED #26).

    The write side of what `hot-set` reads: without a command, an agent told an
    operator-stated fact is already active had no step that made it one. With a
    `fact_key`, the active Facts already holding that key are retired so the new
    statement replaces them instead of leaving overlapping Facts for the hot set
    to warn about. Nothing is deleted. `said` keeps the operator's own words beside it.
    """
    return _write_fact(
        memory_dir,
        author="human",
        blocking=frozenset({"active"}),
        rule=rule,
        scope=scope,
        fact_key=fact_key,
        tags=tags,
        source_run=source_run,
        now=now,
        said=said,
    )


def propose_fact(
    memory_dir: Path,
    *,
    rule: str,
    scope: str = "project",
    fact_key: str | None = None,
    tags: Sequence[str] | None = None,
    source_run: str = "agent-inferred",
    now: datetime | None = None,
    said: str | None = None,
) -> Remembered:
    """Record something the agent inferred. It stays `proposed` until the operator confirms.

    `said` is the operator's words the agent concluded it from, when there were any:
    the operator confirming it reads what they said beside what was made of it.

    The counterpart of `remember_fact`: the verb, not a flag, says who spoke, so an
    agent that means "I noticed" cannot write `active` by omitting an argument. A
    sentence the operator already rejected is not proposed again; a rejection that
    changed nothing would make the confirm gate noise.
    """
    return _write_fact(
        memory_dir,
        author="agent",
        blocking=frozenset({"active", "proposed", "retired"}),
        rule=rule,
        scope=scope,
        fact_key=fact_key,
        tags=tags,
        source_run=source_run,
        now=now,
        said=said,
    )


def supersede_fact_key(
    memory_dir: Path, fact_key: str, *, keep_id: str | None = None
) -> tuple[MemoryEntry, ...]:
    """Retire every active Fact holding `fact_key`, except `keep_id`. Nothing is deleted."""
    retired: list[MemoryEntry] = []
    for path, current in _facts(memory_dir):
        if (
            current.id != keep_id
            and current.status == "active"
            and current.effective_fact_key == fact_key
        ):
            retired.append(retire_entry(path))
    if retired:
        # An entity links Facts by id, so a replaced Fact must not orphan the link.
        repoint_fact_ids(memory_dir / "graph.yaml", {old.id: keep_id for old in retired})
    return tuple(retired)


def _write_fact(
    memory_dir: Path,
    *,
    author: str,
    blocking: frozenset[str],
    rule: str,
    scope: str,
    fact_key: str | None,
    tags: Sequence[str] | None,
    source_run: str,
    now: datetime | None,
    said: str | None = None,
) -> Remembered:
    rule = rule.strip()
    if not rule:
        raise ValueError("a Fact needs a sentence")
    fact_key = (fact_key or "").strip() or None
    clock = now or datetime.now().astimezone()
    facts = _facts(memory_dir)

    wanted = sentence_key(rule)
    for path, current in facts:
        if (
            current.status in blocking
            and current.scope == scope
            and sentence_key(current.rule) == wanted
        ):
            return Remembered(entry=current, path=path, existing=True)

    identifier = _new_fact_id(memory_dir, {entry.id for _, entry in facts}, fact_key, clock, rule)
    destination = memory_dir / f"{identifier}.yaml"
    entry = record_entry(
        destination,
        id=identifier,
        rule=rule,
        scope=scope,
        author=author,
        # Milliseconds: two Facts said in one second must still say which came first.
        created_at=clock.isoformat(timespec="milliseconds"),
        source_run=source_run,
        fact_key=fact_key,
        tags=tags or None,
        said=(said or "").strip() or None,
    )
    superseded: tuple[MemoryEntry, ...] = ()
    if fact_key and entry.status == "active":
        superseded = supersede_fact_key(memory_dir, fact_key, keep_id=identifier)
    replaced = {old.id for old in superseded}
    # A Devin run remembered "30 minutes a day this week", then "one hour a day
    # from next week", without a fact-key: both stayed active and contradicted.
    resembling = tuple(
        current for _, current in facts
        if current.status == "active"
        and current.scope == scope
        and current.id not in replaced
        and not (fact_key and current.fact_key == fact_key)
        and resemblance(current.rule, rule) >= RESEMBLES
    )
    return Remembered(
        entry=entry, path=destination, superseded=superseded, resembling=resembling
    )


def live_fact_ids(memory_dir: Path) -> set[str]:
    """Ids of Facts that are not retired — what an entity may link to."""
    return {entry.id for _, entry in _facts(memory_dir) if entry.status != "retired"}


def _facts(memory_dir: Path) -> list[tuple[Path, MemoryEntry]]:
    return [
        (path, parse_entry(path))
        for path in sorted(memory_dir.glob("*.yaml"))
        if path.name != "graph.yaml"
    ]


_SENTENCE_ID_MAX = 32
"""Characters of the sentence an id without a fact-key starts with."""


def _opening(slugged: str) -> str:
    """The first words of a slugged sentence, cut at a word boundary where there is one."""
    if len(slugged) <= _SENTENCE_ID_MAX:
        return slugged
    cut = slugged[:_SENTENCE_ID_MAX]
    if slugged[_SENTENCE_ID_MAX] != "-" and "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.rstrip("-")


def _new_fact_id(
    memory_dir: Path, taken: set[str], fact_key: str | None, clock: datetime, rule: str
) -> str:
    # The key is agent-supplied and becomes a file name: slug it, never trust it as a path.
    # Without one the id opens with the sentence: "fact-20260928-002248" named nothing.
    name = slug(fact_key) if fact_key else _opening(slug(rule))
    base = f"{name or 'fact'}-{clock.strftime('%Y%m%d-%H%M%S')}"
    identifier, suffix = base, 1
    while identifier in taken or (memory_dir / f"{identifier}.yaml").exists():
        suffix += 1
        identifier = f"{base}-{suffix}"
    return identifier


def confirm_entry(path: Path) -> MemoryEntry:
    """Operator confirmation: update the status field from proposed to active."""
    current = parse_entry(path)
    if current.status == "retired":
        raise ValueError("retired Memory entries cannot become active")
    if current.status == "active":
        return current
    confirmed = replace(current, status="active")
    _write(path, confirmed)
    return confirmed


def winning_entry(entries: Sequence[MemoryEntry]) -> MemoryEntry:
    """Among conflicting entries, narrower scope wins, then newer created_at."""
    return min(entries, key=_conflict_key)


def _conflict_key(entry: MemoryEntry) -> tuple[int, float]:
    return (_SCOPE_WIDTH[entry.scope], -datetime.fromisoformat(entry.created_at).timestamp())


def load_set(entries_dir: Path, *, run_scope: str) -> list[MemoryEntry]:
    """Return active entries in scope: project always, plus task-scoped on a task run."""
    if run_scope not in _SCOPES:
        raise ValueError(f"run_scope must be task or project, got {run_scope!r}")
    allowed_scopes = {"project"} if run_scope == "project" else {"task", "project"}
    loaded: list[MemoryEntry] = []
    for path in sorted(entries_dir.glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        entry = parse_entry(path)
        if entry.status == "active" and entry.scope in allowed_scopes:
            loaded.append(entry)
    return loaded


@dataclass(frozen=True)
class AsOfSelection:
    facts: tuple[MemoryEntry, ...]
    overlap_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HotSet:
    facts: tuple[MemoryEntry, ...]
    overlap_warnings: tuple[str, ...] = ()
    fact_count_warning: str | None = None
    graph_activation: GraphActivation | None = None


@dataclass(frozen=True)
class Episode:
    id: str
    rule: str
    observed_at: str
    source_run: str
    author: str
    status: str
    promoted_to: str | None = None


_EPISODE_FIELDS = ("id", "rule", "observed_at", "source_run", "author", "status")


def select_facts_as_of(
    entries_dir: Path,
    *,
    run_scope: str,
    as_of: str | datetime | None = None,
) -> AsOfSelection:
    """Pick one active Fact per fact_key valid at as_of (ADR 0005)."""
    if run_scope not in _SCOPES:
        raise ValueError(f"run_scope must be task or project, got {run_scope!r}")
    clock = _coerce_as_of(as_of)
    allowed_scopes = {"project"} if run_scope == "project" else {"task", "project"}
    candidates: list[MemoryEntry] = []
    for path in sorted(entries_dir.glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        entry = parse_entry(path)
        if entry.status != "active" or entry.scope not in allowed_scopes:
            continue
        if _effective_contains(entry, clock):
            candidates.append(entry)

    by_key: dict[str, list[MemoryEntry]] = {}
    for entry in candidates:
        by_key.setdefault(entry.effective_fact_key, []).append(entry)

    selected: list[MemoryEntry] = []
    warnings: list[str] = []
    for key, group in sorted(by_key.items()):
        if len(group) > 1:
            warnings.append(
                f"overlapping active Facts for fact_key={key!r}: "
                f"{', '.join(sorted(entry.id for entry in group))}"
            )
        selected.append(winning_entry(group))
    return AsOfSelection(facts=tuple(selected), overlap_warnings=tuple(warnings))


def load_hot_set(
    facts_dir: Path,
    *,
    run_scope: str,
    as_of: str | datetime | None = None,
    fact_warn_above: int = 50,
    graph_path: Path | None = None,
    task_hints: Sequence[str] = (),
    graph_k: int = 20,
    graph_hops: int = 2,
    graph_decay: float = 0.5,
) -> HotSet:
    """Facts valid at as_of plus a graph activation (ADR 0005 / 0006, amended by #61).

    There is no Timeline slot. Run summaries were retracted rather than left
    unimplemented: a prose account of a run is not independently checkable, and
    unlike a Fact nothing cross-checks it — the lint has no reference to follow.
    """
    selection = select_facts_as_of(facts_dir, run_scope=run_scope, as_of=as_of)
    count_warning = None
    if len(selection.facts) >= fact_warn_above:
        count_warning = (
            f"hot set Fact count is {len(selection.facts)} "
            f"(warn_above={fact_warn_above}); consider retiring or querying by tags"
        )
    resolved_graph = graph_path if graph_path is not None else facts_dir / "graph.yaml"
    graph_activation = None
    # The graph is built only when the operator asks for one (SETTLED #82); an empty one
    # adds nothing to a run, so the hot set says nothing about it.
    graph = parse_graph(resolved_graph) if resolved_graph.is_file() else None
    if graph is not None and any(entity.status == "active" for entity in graph.entities):
        graph_activation = activate_graph(
            graph,
            task_hints=task_hints,
            fact_ids=tuple(entry.id for entry in selection.facts),
            k=graph_k,
            hops=graph_hops,
            decay=graph_decay,
        )
    return HotSet(
        facts=selection.facts,
        overlap_warnings=selection.overlap_warnings,
        fact_count_warning=count_warning,
        graph_activation=graph_activation,
    )


def query_facts(
    facts_dir: Path,
    *,
    tags: Sequence[str] | None = None,
    text: str | None = None,
) -> tuple[MemoryEntry, ...]:
    """On-demand Facts filtered by optional tags and/or substring match on rule."""
    wanted_tags = set(tags) if tags else None
    needle = text.casefold() if text else None
    matched: list[MemoryEntry] = []
    for path in sorted(facts_dir.glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        entry = parse_entry(path)
        if wanted_tags is not None and wanted_tags.isdisjoint(entry.tags):
            continue
        if needle is not None and needle not in entry.rule.casefold():
            continue
        matched.append(entry)
    return tuple(matched)


@dataclass(frozen=True)
class TimelineQuery:
    episodes: tuple[Episode, ...]


def query_timeline(
    *,
    episodes_dir: Path | None = None,
    since: str | datetime | None = None,
    run_id: str | None = None,
) -> TimelineQuery:
    """On-demand Timeline: Episodes, optionally filtered by since/run_id.

    The prose `summary` half of ADR 0005's Timeline is retired (#61); what
    remains is the evidence axis — Episodes here, and Trace / Score / run YAML
    read directly from their own directories.
    """
    since_clock = _coerce_as_of(since) if since is not None else None
    episodes: list[Episode] = []
    if episodes_dir is not None and episodes_dir.exists():
        for path in sorted(episodes_dir.glob("*.yaml")):
            episode = parse_episode(path)
            if run_id is not None and episode.source_run != run_id:
                continue
            if since_clock is not None:
                observed = datetime.fromisoformat(episode.observed_at)
                if observed.tzinfo is None and since_clock.tzinfo is not None:
                    observed = observed.replace(tzinfo=since_clock.tzinfo)
                if observed < since_clock:
                    continue
            episodes.append(episode)
    return TimelineQuery(episodes=tuple(episodes))


def retire_entry(path: Path) -> MemoryEntry:
    """Mark a Fact as retired (Archive semantics)."""
    current = parse_entry(path)
    if current.status == "retired":
        return current
    retired = replace(current, status="retired")
    _write(path, retired)
    return retired


def archive_move(path: Path, *, archive_dir: Path) -> Path:
    """Physically move a retired Fact YAML into memory/archive/."""
    current = parse_entry(path)
    if current.status != "retired":
        raise ValueError("only retired Memory entries can be archive-moved")
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / path.name
    path.replace(destination)
    return destination


def _coerce_as_of(as_of: str | datetime | None) -> datetime:
    if as_of is None:
        return datetime.now().astimezone()
    if isinstance(as_of, datetime):
        return as_of if as_of.tzinfo else as_of.astimezone()
    try:
        parsed = datetime.fromisoformat(as_of)
    except ValueError as exc:
        raise ValueError(f"as_of must be an ISO timestamp, got {as_of!r}") from exc
    return parsed


def _effective_contains(entry: MemoryEntry, clock: datetime) -> bool:
    if entry.effective_from:
        start = datetime.fromisoformat(entry.effective_from)
        if start.tzinfo is None and clock.tzinfo is not None:
            start = start.replace(tzinfo=clock.tzinfo)
        if clock < start:
            return False
    if entry.effective_to:
        end = datetime.fromisoformat(entry.effective_to)
        if end.tzinfo is None and clock.tzinfo is not None:
            end = end.replace(tzinfo=clock.tzinfo)
        if clock > end:
            return False
    return True


def parse_episode(path: Path) -> Episode:
    """Parse an Episode YAML under memory/episodes/."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    return _episode_from_mapping(loaded)


def record_episode(
    destination: Path,
    *,
    id: str,
    rule: str,
    observed_at: str,
    source_run: str,
    author: str,
) -> Episode:
    """Write an Episode. Agent-authored episodes enter proposed; human enter active."""
    status = "active" if author == "human" else "proposed"
    episode = _episode_from_mapping(
        {
            "id": id,
            "rule": rule,
            "observed_at": observed_at,
            "source_run": source_run,
            "author": author,
            "status": status,
        }
    )
    _write_episode(destination, episode)
    return episode


def confirm_episode(path: Path) -> Episode:
    """Operator confirmation: update an Episode from proposed to active."""
    current = parse_episode(path)
    if current.status == "retired":
        raise ValueError("retired Episodes cannot become active")
    if current.status == "active":
        return current
    confirmed = replace(current, status="active")
    _write_episode(path, confirmed)
    return confirmed


def retire_episode(path: Path) -> Episode:
    """Mark an Episode as retired. Rejecting a proposal retires it; it is never deleted."""
    current = parse_episode(path)
    if current.status == "retired":
        return current
    retired = replace(current, status="retired")
    _write_episode(path, retired)
    return retired


@dataclass(frozen=True)
class Noted:
    episode: Episode
    path: Path
    existing: bool = False


def propose_episode(
    memory_dir: Path,
    *,
    rule: str,
    observed_at: str | None = None,
    source_run: str = "agent-inferred",
    now: datetime | None = None,
) -> Noted:
    """Note something that happened, `proposed`. An Episode is a staging post, not Memory (#61)."""
    rule = rule.strip()
    if not rule:
        raise ValueError("an Episode needs a sentence")
    clock = now or datetime.now().astimezone()
    directory = memory_dir / "episodes"
    known = [(path, parse_episode(path)) for path in sorted(directory.glob("*.yaml"))]
    wanted = sentence_key(rule)
    for path, current in known:
        if sentence_key(current.rule) == wanted:
            return Noted(current, path, existing=True)
    base = f"episode-{clock.strftime('%Y%m%d-%H%M%S')}"
    taken = {current.id for _, current in known}
    identifier, suffix = base, 1
    while identifier in taken or (directory / f"{identifier}.yaml").exists():
        suffix += 1
        identifier = f"{base}-{suffix}"
    destination = directory / f"{identifier}.yaml"
    episode = record_episode(
        destination,
        id=identifier,
        rule=rule,
        observed_at=observed_at or clock.isoformat(timespec="seconds"),
        source_run=source_run,
        author="agent",
    )
    return Noted(episode, destination)


def promote_episode(
    memory_dir: Path,
    episode_id: str,
    *,
    rule: str,
    scope: str = "project",
    fact_key: str | None = None,
    tags: Sequence[str] | None = None,
    now: datetime | None = None,
) -> Remembered:
    """Turn an Episode into a `proposed` Fact — the only way an Episode is ever remembered."""
    rule = rule.strip()
    if not rule:
        raise ValueError("a Fact needs a sentence")
    episode_id = episode_id.removeprefix("episode:")
    matches = [
        candidate
        for candidate in sorted((memory_dir / "episodes").glob("*.yaml"))
        if parse_episode(candidate).id == episode_id
    ]
    if not matches:
        raise ValueError(f"Episode not found: {episode_id}")
    path = matches[0]
    episode = parse_episode(path)
    if episode.status == "retired":
        raise ValueError(f"Episode {episode_id} is retired, so it cannot be promoted")
    if episode.promoted_to:
        raise ValueError(f"Episode {episode_id} was already promoted to {episode.promoted_to}")
    facts = _facts(memory_dir)
    wanted = sentence_key(rule)
    for fact_path, current in facts:
        if current.scope == scope and sentence_key(current.rule) == wanted:
            return Remembered(entry=current, path=fact_path, existing=True)
    clock = now or datetime.now().astimezone()
    fact_key = (fact_key or "").strip() or None
    identifier = _new_fact_id(memory_dir, {entry.id for _, entry in facts}, fact_key, clock, rule)
    entry = propose_fact_from_episode(
        path,
        fact_destination=memory_dir / f"{identifier}.yaml",
        fact_id=identifier,
        rule=rule,
        scope=scope,
        fact_key=fact_key,
        tags=tags,
    )
    return Remembered(entry=entry, path=memory_dir / f"{identifier}.yaml")


def propose_fact_from_episode(
    episode_path: Path,
    *,
    fact_destination: Path,
    fact_id: str,
    rule: str,
    scope: str,
    fact_key: str | None = None,
    tags: Sequence[str] | None = None,
) -> MemoryEntry:
    """Promote an Episode into a proposed Fact; observed_at becomes effective_from."""
    episode = parse_episode(episode_path)
    fact = record_entry(
        fact_destination,
        id=fact_id,
        rule=rule,
        scope=scope,
        author="agent",
        created_at=datetime.now().astimezone().isoformat(),
        source_run=episode.source_run,
        fact_key=fact_key,
        effective_from=episode.observed_at,
        tags=tags,
    )
    updated = replace(episode, promoted_to=fact_id)
    _write_episode(episode_path, updated)
    return fact


def _episode_from_mapping(payload: dict[str, Any]) -> Episode:
    missing = [
        name for name in _EPISODE_FIELDS if name not in payload or payload[name] in (None, "")
    ]
    if missing:
        raise ValueError(f"Episode missing fields: {', '.join(missing)}")
    author = str(payload["author"])
    status = str(payload["status"])
    if author not in _AUTHORS:
        raise ValueError(f"Episode author must be human or agent, got {author!r}")
    if status not in _STATUSES:
        raise ValueError(f"Episode status must be proposed, active, or retired, got {status!r}")
    observed_at = _parse_optional_timestamp(payload["observed_at"], field="observed_at")
    if observed_at is None:
        raise ValueError("Episode observed_at must be an ISO timestamp")
    promoted_raw = payload.get("promoted_to")
    promoted_to = None if promoted_raw in (None, "") else str(promoted_raw)
    return Episode(
        id=str(payload["id"]),
        rule=str(payload["rule"]),
        observed_at=observed_at,
        source_run=str(payload["source_run"]),
        author=author,
        status=status,
        promoted_to=promoted_to,
    )


def _write_episode(path: Path, episode: Episode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(episode)
    if payload.get("promoted_to") in (None, ""):
        payload.pop("promoted_to", None)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _parse_optional_timestamp(value: Any, *, field: str) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value)
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Memory entry {field} must be an ISO timestamp, got {text!r}") from exc
    return text


def _from_mapping(payload: dict[str, Any]) -> MemoryEntry:
    missing = [name for name in _FIELDS if name not in payload or payload[name] in (None, "")]
    if missing:
        raise ValueError(f"Memory entry missing fields: {', '.join(missing)}")
    scope = str(payload["scope"])
    author = str(payload["author"])
    status = str(payload["status"])
    if scope not in _SCOPES:
        raise ValueError(f"Memory entry scope must be task or project, got {scope!r}")
    if author not in _AUTHORS:
        raise ValueError(f"Memory entry author must be human or agent, got {author!r}")
    if status not in _STATUSES:
        raise ValueError(
            f"Memory entry status must be proposed, active, or retired, got {status!r}"
        )
    created_at = payload["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    else:
        created_at = str(created_at)
        try:
            datetime.fromisoformat(created_at)
        except ValueError as exc:
            raise ValueError(
                f"Memory entry created_at must be an ISO timestamp, got {created_at!r}"
            ) from exc

    fact_key_raw = payload.get("fact_key")
    fact_key = None if fact_key_raw in (None, "") else str(fact_key_raw)
    tags_raw = payload.get("tags")
    if tags_raw in (None, ""):
        tags: tuple[str, ...] = ()
    elif isinstance(tags_raw, list):
        tags = tuple(str(tag) for tag in tags_raw)
    else:
        raise ValueError("Memory entry tags must be a list of strings when present")

    return MemoryEntry(
        id=str(payload["id"]),
        rule=str(payload["rule"]),
        scope=scope,
        author=author,
        status=status,
        created_at=str(created_at),
        source_run=str(payload["source_run"]),
        fact_key=fact_key,
        effective_from=_parse_optional_timestamp(
            payload.get("effective_from"), field="effective_from"
        ),
        effective_to=_parse_optional_timestamp(payload.get("effective_to"), field="effective_to"),
        tags=tags,
        said=None if payload.get("said") in (None, "") else str(payload["said"]),
    )


def _write(path: Path, entry: MemoryEntry) -> None:
    payload = asdict(entry)
    for name in _OPTIONAL_FIELDS:
        if payload.get(name) in (None, (), []):
            payload.pop(name, None)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
