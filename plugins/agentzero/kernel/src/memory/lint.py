"""EVAL L2 structure lint: is this workspace's content healthy?

Three settled decisions terminate here. #55 makes this where a mechanical
learning lands instead of becoming prose. #56 has it compute consolidation
candidates so System rule 9 surfaces something measured rather than something
the model felt. #53 replaced the soft Review reminder with detection.

It reports and changes nothing; `memory review` is what acts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from memory.graph import parse_graph
from memory.host import command
from memory.lifecycle import parse_entry, parse_episode, select_facts_as_of
from memory.taskclass import TaskClass, detect
from memory.text import RESEMBLES, resemblance, sentence_key

Group = Literal["hygiene", "consolidation", "detection"]

PLACEHOLDER_ROLE = "General project assistant for this workspace. No specialty lens."
DEFAULT_RECENT_RUNS = 5
STALE_PROPOSAL_DAYS = 14


@dataclass(frozen=True)
class Finding:
    group: Group
    code: str
    subject: str
    detail: str
    fix: str

    def line(self) -> str:
        return f"  {self.code}  {self.subject}\n      {self.detail}\n      fix: {self.fix}"


@dataclass(frozen=True)
class LintReport:
    workspace: Path
    findings: tuple[Finding, ...]
    notes: tuple[str, ...] = ()
    task_classes: tuple[TaskClass, ...] = ()

    def of(self, group: Group) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.group == group)

    @property
    def has_hygiene(self) -> bool:
        return bool(self.of("hygiene"))

    def render(self) -> str:
        lines = [f"lint {self.workspace}"]
        for group, heading in (
            ("hygiene", "Wrong — these are defects"),
            ("consolidation", "Stale — these may have stopped earning their place"),
            ("detection", "Repeated — a task class came back"),
        ):
            items = self.of(group)  # type: ignore[arg-type]
            lines.append("")
            lines.append(f"{heading} ({len(items)})")
            if not items:
                lines.append("  (none)")
                continue
            lines.extend(item.line() for item in items)
        if self.notes:
            lines.append("")
            lines.append("Notes")
            lines.extend(f"  {note}" for note in self.notes)
        return "\n".join(lines) + "\n"


def lint_workspace(
    workspace: Path, *, recent_runs: int = DEFAULT_RECENT_RUNS, now: datetime | None = None
) -> LintReport:
    """Every L2 finding this workspace's own files can support."""
    workspace = workspace.resolve()
    memory_dir = workspace / "memory"
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"no memory/ directory under {workspace}")

    facts = _load_facts(memory_dir)
    episodes = _load_episodes(memory_dir / "episodes")
    graph_path = memory_dir / "graph.yaml"
    graph = parse_graph(graph_path) if graph_path.is_file() else None
    skills = _load_skills(workspace / "skills")
    all_traces = _load_traces(memory_dir / "traces", limit=10_000)
    scores = _load_scores(memory_dir / "scores")

    findings: list[Finding] = []
    notes: list[str] = []

    findings.extend(
        _check_skill_references(
            skills,
            facts,
            traces_all=_trace_ids(memory_dir),
            scores=scores,
            workspace=workspace,
            episode_ids={episode.id for _path, episode in episodes},
        )
    )
    findings.extend(_check_graph_references(graph, facts))
    findings.extend(_check_episode_promotions(episodes, facts))
    findings.extend(_check_status_discipline(facts, episodes, graph))
    findings.extend(_check_skill_routability(skills))
    findings.extend(_check_skill_assets(skills))
    findings.extend(_check_fact_overlap(memory_dir))
    findings.extend(_check_role(workspace))
    findings.extend(_check_knowledge(workspace))
    findings.extend(_check_scores_have_traces(scores, memory_dir / "traces"))

    if all_traces:
        findings.extend(_check_unused(facts, skills, episodes, all_traces, recent_runs))
    else:
        notes.append(
            "no Traces under memory/traces, so nothing is reported as unused — "
            "absence of evidence is not evidence of staleness"
        )
    findings.extend(_check_fact_count(facts))
    findings.extend(_check_duplicate_facts(facts))
    findings.extend(_check_resembling_facts(facts))
    findings.extend(_check_stale_proposals(facts, now or datetime.now().astimezone()))

    classes = detect(all_traces)
    findings.extend(_check_repeated_classes(classes, skills))
    if all_traces and not classes:
        notes.append(
            "no run called an MCP tool beyond the agent app's own controls, so no task "
            "class is derivable (classes come from MCP calls, #59) — a workspace "
            "with no repeating head correctly stays at T2 (SETTLED #53)"
        )

    return LintReport(
        workspace=workspace,
        findings=tuple(findings),
        notes=tuple(notes),
        task_classes=classes,
    )


def _check_repeated_classes(
    classes: tuple[TaskClass, ...], skills: list[tuple[Path, Any]]
) -> list[Finding]:
    """Detection replaces the soft Review reminder (SETTLED #53).

    Evidence drives the offer. Reporting a recurrence is not proposing a Skill:
    the operator still confirms, and nothing here writes.
    """
    # Any Skill naming the class means it has been considered — a draft is the
    # offer already made, and a retired one is the operator having said no.
    # Re-reporting either is the nagging #53 removed the reminder to avoid.
    served = {skill.task_class for _path, skill in skills if skill.task_class}
    findings: list[Finding] = []
    for item in classes:
        if not item.recurred or item.key in served:
            continue
        findings.append(
            Finding(
                "detection",
                "task-class-repeated-without-skill",
                f"{item.key}  {item.label}",
                f"{len(item.run_ids)} runs did the same thing: {', '.join(item.run_ids)}",
                "offer a Skill draft citing those runs, with task_class: "
                f"{item.key} — the operator confirms it",
            )
        )
    return findings


# --- hygiene --------------------------------------------------------------


def _check_skill_references(
    skills: list[tuple[Path, Any]],
    facts: dict[str, Any],
    *,
    traces_all: set[str],
    scores: dict[str, Any],
    workspace: Path,
    episode_ids: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    for path, skill in skills:
        if skill.status == "retired":
            continue
        for fact_id in skill.memory_ids:
            entry = facts.get(fact_id)
            if entry is None:
                findings.append(
                    Finding(
                        "hygiene",
                        "skill-dangling-memory-id",
                        f"{_skill_name(path)} → {fact_id}",
                        "the Skill cites a Fact that does not exist",
                        "remove the id, or restore the Fact",
                    )
                )
            elif entry.status == "retired" and skill.status == "active":
                findings.append(
                    Finding(
                        "hygiene",
                        "active-skill-cites-retired-fact",
                        f"{_skill_name(path)} → {fact_id}",
                        "an active Skill rests on a Fact that was retired; "
                        "reuse can no longer be assumed not to degrade (ADR 0004)",
                        f"review the Skill, or confirm a replacement Fact for {fact_id}",
                    )
                )
        known_runs = traces_all | set(scores)
        if known_runs:
            unknown = [run for run in skill.source_runs if run not in known_runs]
            # Layer 1 builtins cite a product sentinel rather than a run.
            unknown = [run for run in unknown if not run.startswith("product:")]
            # A run with no MCP leaves no Trace; what it left under work/, or an
            # Episode, is the evidence read back from disk (#57, #72).
            unknown = [
                run
                for run in unknown
                if run not in episode_ids and not _inside_workspace(workspace, run)
            ]
            if unknown:
                findings.append(
                    Finding(
                        "hygiene",
                        "skill-unsourced",
                        f"{_skill_name(path)} → {', '.join(unknown)}",
                        "source_runs cite no Trace and no Score; the offer was unsourced (#57)",
                        "cite runs that left evidence on disk, or record why they did not",
                    )
                )
    return findings


def _inside_workspace(workspace: Path, run: str) -> bool:
    candidate = (workspace / run).resolve()
    return candidate != workspace and workspace in candidate.parents and candidate.exists()


def _check_skill_routability(skills: list[tuple[Path, Any]]) -> list[Finding]:
    """System rule 5 matches on the description; without one the Skill is unreachable."""
    findings: list[Finding] = []
    for path, skill in skills:
        if skill.status not in {"proposed", "active"} or skill.description:
            continue
        findings.append(
            Finding(
                "hygiene",
                "skill-missing-description",
                f"{path.name} ({skill.id})",
                "no description, so System rule 5 has nothing to match and the Skill "
                "will never be selected",
                "add one sentence saying when to use it",
            )
        )
    return findings


def _check_graph_references(graph: Any, facts: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    if graph is None:
        return findings
    live = {item.id for item in graph.entities if item.status != "retired"}
    for entity in graph.entities:
        if entity.status == "retired":
            continue
        for fact_id in entity.fact_ids:
            if fact_id not in facts:
                findings.append(
                    Finding(
                        "hygiene",
                        "entity-dangling-fact-id",
                        f"{entity.id} → {fact_id}",
                        "the entity links to a Fact that does not exist",
                        "remove the link in memory/graph.yaml, or restore the Fact",
                    )
                )
    for entity in graph.entities:
        if entity.status == "retired":
            continue
        for fact_id in entity.fact_ids:
            if fact_id in facts and facts[fact_id].status == "retired":
                findings.append(
                    Finding(
                        "hygiene",
                        "entity-links-retired-fact",
                        f"{entity.id} → {fact_id}",
                        "the Fact was retired, so this link points at something no run loads",
                        "link the entity to the Fact that replaced it, or drop the link",
                    )
                )
    for edge in graph.edges:
        if edge.status == "retired":
            continue
        for side, target in (("from", edge.from_id), ("to", edge.to_id)):
            if target not in live:
                findings.append(
                    Finding(
                        "hygiene",
                        "edge-dangling-endpoint",
                        f"{edge.id} ({side}: {target})",
                        "the edge points at an entity that is missing or retired, "
                        "so it silently drops out of every activation",
                        "retire the edge, or restore the entity",
                    )
                )
    return findings


def _check_episode_promotions(
    episodes: list[tuple[Path, Any]], facts: dict[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    for path, episode in episodes:
        if episode.promoted_to and episode.promoted_to not in facts:
            findings.append(
                Finding(
                    "hygiene",
                    "episode-dangling-promotion",
                    f"{path.name} → {episode.promoted_to}",
                    "the Episode was promoted to a Fact that does not exist",
                    "clear promoted_to, or restore the Fact",
                )
            )
    return findings


def _check_status_discipline(
    facts: dict[str, Any], episodes: list[tuple[Path, Any]], graph: Any
) -> list[Finding]:
    findings: list[Finding] = []
    for entry in facts.values():
        if entry.author == "human" and entry.status == "proposed":
            findings.append(
                Finding(
                    "hygiene",
                    "human-fact-left-proposed",
                    entry.id,
                    "the operator stated it, so it should have entered active (#26)",
                    command(f"memory review --confirm fact:{entry.id}"),
                )
            )
    for _path, episode in episodes:
        if episode.author == "human" and episode.status == "proposed":
            findings.append(
                Finding(
                    "hygiene",
                    "human-episode-left-proposed",
                    episode.id,
                    "the operator stated it, so it should have entered active (#26)",
                    command(f"memory review --confirm episode:{episode.id}"),
                )
            )
    if graph is not None:
        for entity in graph.entities:
            if entity.author == "human" and entity.status == "proposed":
                findings.append(
                    Finding(
                        "hygiene",
                        "human-entity-left-proposed",
                        entity.id,
                        "the operator stated it, so it should have entered active (#26)",
                        command(f"memory review --confirm entity:{entity.id}"),
                    )
                )
    return findings


def _check_fact_overlap(memory_dir: Path) -> list[Finding]:
    selection = select_facts_as_of(memory_dir, run_scope="task")
    return [
        Finding(
            "hygiene",
            "fact-key-overlap",
            warning.split(":", 1)[0].removeprefix("overlapping active Facts for "),
            warning,
            "tighten effective_from / effective_to, or retire the older version",
        )
        for warning in selection.overlap_warnings
    ]


def _check_role(workspace: Path) -> list[Finding]:
    role = workspace / "Role.md"
    if not role.is_file():
        return [
            Finding(
                "hygiene",
                "role-missing",
                "Role.md",
                "every workspace has a Role file, even when the Role is general",
                command("adapter materialize") + " from a framework checkout",
            )
        ]
    return []


def _check_knowledge(workspace: Path) -> list[Finding]:
    from knowledge import load_sources, reach

    try:
        sources = load_sources(workspace)
    except ValueError as exc:
        return [
            Finding(
                "hygiene",
                "knowledge-malformed",
                "knowledge.yaml",
                f"{exc}; no run can read any source while this stands",
                "fix knowledge.yaml, then check with " + command("knowledge list"),
            )
        ]
    findings: list[Finding] = []
    declared = {source.id for source in sources}
    for source in sources:
        if source.type != "index":
            state = reach(workspace, source)
            if not state.ok:
                findings.append(
                    Finding(
                        "hygiene",
                        "knowledge-source-unreachable",
                        source.id,
                        f"{state.detail}, so every run silently reads nothing from it",
                        "restore it, or correct its path in knowledge.yaml",
                    )
                )
        parent = source.raw.get("derived_from")
        if parent and parent not in declared:
            findings.append(
                Finding(
                    "hygiene",
                    "knowledge-dangling-derived-from",
                    f"{source.id} → {parent}",
                    "it names a raw source that is no longer declared",
                    "restore that source, or drop derived_from",
                )
            )
    # A retired source's folder is kept on purpose (nothing is deleted), so it counts
    # as declared here even though no run reads it.
    findings.extend(
        _check_undeclared_knowledge(workspace, load_sources(workspace, include_retired=True))
    )
    return findings


def _check_undeclared_knowledge(workspace: Path, sources: Sequence[Any]) -> list[Finding]:
    """A folder under knowledge/ that no source names is read by no run.

    Found in a real run: the agent converted a regulation straight into
    knowledge/<name>/ with shell tools and never ran `knowledge add`; lint
    reported nothing, and the next session did not know the material existed.
    """
    root = workspace / "knowledge"
    if not root.is_dir():
        return []
    declared: list[Path] = []
    for source in sources:
        if source.path:
            candidate = Path(source.path).expanduser()
            target = candidate if candidate.is_absolute() else workspace / candidate
            declared.append(target.resolve())
    findings: list[Finding] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or entry.name == "README.md":
            continue
        resolved = entry.resolve()
        if any(path == resolved or resolved in path.parents for path in declared):
            continue
        findings.append(
            Finding(
                "hygiene",
                "knowledge-undeclared",
                f"knowledge/{entry.name}",
                "no source in knowledge.yaml names it, so no run knows it exists",
                "declare it with " + command("knowledge add") + f" knowledge/{entry.name} "
                "--type docs|raw --name ..., or remove it",
            )
        )
    return findings


def _check_scores_have_traces(scores: dict[str, Any], traces_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for run_id in sorted(scores):
        if not (traces_dir / f"{run_id}.yaml").is_file():
            findings.append(
                Finding(
                    "hygiene",
                    "scored-run-without-trace",
                    run_id,
                    "a Score exists for a run that left no Trace, so it was not a formal run (#25)",
                    f"re-run with hooks wired ({command('adapter preflight')}), "
                    "or mark the Score degraded",
                )
            )
    return findings


# --- consolidation --------------------------------------------------------


def _check_unused(
    facts: dict[str, Any],
    skills: list[tuple[Path, Any]],
    episodes: list[tuple[Path, Any]],
    traces: list[dict[str, Any]],
    recent_runs: int,
) -> list[Finding]:
    """Nominate only what a fair sample of later runs passed over.

    An item is judged by the runs after it arrived, and only once `recent_runs` of them
    exist: runs from before it could not have loaded it, and one run is not a sample.
    """
    # A Skill's use record (#72) says a script ran, not that a run loaded Memory,
    # so it counts toward Skills only.
    runs = [trace for trace in traces if trace.get("kind") != "skill-run"]
    findings: list[Finding] = []
    for entry in facts.values():
        if entry.status == "active" and _passed_over(
            entry.id, entry.created_at, runs, "loaded_memory_ids", recent_runs
        ):
            findings.append(
                Finding(
                    "consolidation",
                    "fact-not-loaded-recently",
                    entry.id,
                    f"none of the last {recent_runs} runs since it was recorded loaded it",
                    command(f"memory review --reject fact:{entry.id}")
                    + " (if it no longer applies)",
                )
            )
    for path, skill in skills:
        if skill.status == "active" and _passed_over(
            skill.id, skill.confirmed_at, traces, "loaded_skill_ids", recent_runs
        ):
            findings.append(
                Finding(
                    "consolidation",
                    "skill-not-used-since-intake",
                    f"{_skill_name(path)} ({skill.id})",
                    f"none of the last {recent_runs} runs since it was confirmed loaded it",
                    command(f"memory review --reject skill:{skill.id}")
                    + " (if it no longer applies)",
                )
            )
    for _path, episode in episodes:
        if episode.status == "proposed" and not episode.promoted_to:
            findings.append(
                Finding(
                    "consolidation",
                    "episode-neither-promoted-nor-retired",
                    episode.id,
                    "still proposed and never promoted to a Fact",
                    "promote it, or " + command(f"memory review --reject episode:{episode.id}"),
                )
            )
    return findings


def _passed_over(
    item_id: str, since: str | None, traces: list[dict[str, Any]], key: str, window: int
) -> bool:
    """True when the `window` newest runs after `since` exist and none loaded the item.

    `traces` is newest first. A Skill confirmed before `confirmed_at` was recorded has no
    `since`, so every run counts, as it did before.
    """
    start = _moment(since) if since else None
    later: list[dict[str, Any]] = []
    for trace in traces:
        at = _moment(trace.get("timestamp"))
        if start is not None and (at is None or at <= start):
            continue
        later.append(trace)
        if len(later) == window:
            break
    if len(later) < window:
        return False
    return all(item_id not in [str(item) for item in trace.get(key) or []] for trace in later)


_OLDEST = datetime.min.replace(tzinfo=UTC)


def _moment(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.astimezone()
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _check_fact_count(facts: dict[str, Any], warn_above: int = 50) -> list[Finding]:
    active = [entry for entry in facts.values() if entry.status == "active"]
    if len(active) < warn_above:
        return []
    return [
        Finding(
            "consolidation",
            "hot-set-fact-count",
            f"{len(active)} active Facts",
            f"at or above the hot-set warning line ({warn_above}); every run carries all of them",
            "retire what no longer applies, or narrow scope with tags",
        )
    ]


def _check_duplicate_facts(facts: dict[str, Any]) -> list[Finding]:
    groups: dict[tuple[str, str], list[Any]] = {}
    for entry in facts.values():
        if entry.status == "active":
            groups.setdefault((entry.scope, sentence_key(entry.rule)), []).append(entry)
    findings: list[Finding] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: item.created_at)
        extras = ordered[1:]
        findings.append(
            Finding(
                "consolidation",
                "duplicate-active-fact",
                ", ".join(item.id for item in ordered),
                f"{len(ordered)} active Facts say the same thing: {ordered[0].rule}",
                "; ".join(command(f"memory forget fact:{item.id}") for item in extras),
            )
        )
    return findings


def _check_resembling_facts(facts: dict[str, Any]) -> list[Finding]:
    """Two active Facts that seem to say the same thing, each true at a different time.

    `duplicate-active-fact` catches the same sentence twice; this catches "30 minutes a
    day this week" beside "one hour a day from next week", left active together because
    neither was recorded with a fact-key. A candidate, not a defect: it is a heuristic.
    """
    active = sorted(
        (entry for entry in facts.values() if entry.status == "active"),
        # By moment; created_at has milliseconds now. Two older ones written in the same
        # second: the later one got the "-2" id suffix.
        key=lambda item: (_moment(item.created_at) or _OLDEST, len(item.id), item.id),
    )
    findings: list[Finding] = []
    for index, earlier in enumerate(active):
        for later in active[index + 1:]:
            if (
                earlier.scope != later.scope
                or earlier.effective_fact_key == later.effective_fact_key
                or sentence_key(earlier.rule) == sentence_key(later.rule)
                or resemblance(earlier.rule, later.rule) < RESEMBLES
            ):
                continue
            findings.append(
                Finding(
                    "consolidation",
                    "resembling-active-facts",
                    f"{earlier.id}, {later.id}",
                    f"both active, and they may describe the same thing: "
                    f"{earlier.rule!r} / {later.rule!r}",
                    "if the later replaces the earlier: "
                    + command(f"memory forget fact:{earlier.id}"),
                )
            )
    return findings


def _check_stale_proposals(facts: dict[str, Any], now: datetime) -> list[Finding]:
    findings: list[Finding] = []
    for entry in facts.values():
        if entry.status != "proposed":
            continue
        age = (now - datetime.fromisoformat(entry.created_at)).days
        if age <= STALE_PROPOSAL_DAYS:
            continue
        findings.append(
            Finding(
                "consolidation",
                "stale-proposal",
                entry.id,
                f"proposed {age} days ago and never answered: {entry.rule}",
                command(f"memory review --confirm fact:{entry.id}")
                + " or "
                + command(f"memory review --reject fact:{entry.id}"),
            )
        )
    return findings


def _check_skill_assets(skills: list[tuple[Path, Any]]) -> list[Finding]:
    """A script is confirmed as a version, and may only do what #72 allows."""
    from skills.assets import mismatches, violations

    findings: list[Finding] = []
    for path, skill in skills:
        if not skill.assets or skill.status == "retired":
            continue
        name = f"{_skill_name(path)} ({skill.id})"
        changed = mismatches(path.parent, skill.assets)
        if changed:
            findings.append(
                Finding(
                    "hygiene",
                    "asset-hash-mismatch",
                    name,
                    f"{', '.join(changed)} is not the version the operator confirmed, "
                    "so `skills run` refuses it",
                    "offer the change as a new version: "
                    + command(f"skills draft --supersedes {skill.id} --script <file> …"),
                )
            )
        for asset, _digest in skill.assets:
            script = path.parent / asset
            if asset in changed or script.suffix != ".py":
                continue
            found = violations(script.read_text(encoding="utf-8"))
            if found:
                findings.append(
                    Finding(
                        "hygiene",
                        "script-import-not-allowed",
                        name,
                        f"{asset}: {'; '.join(found)}",
                        "a Skill's script deletes nothing and launches nothing, and imports "
                        "only the standard library, PyYAML and openpyxl; retire it or draft "
                        "a version that does",
                    )
                )
    return findings


def _skill_name(path: Path) -> str:
    return f"{path.parent.name}/{path.name}" if path.name == "SKILL.md" else path.name


# --- loading --------------------------------------------------------------


def _load_facts(memory_dir: Path) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for path in sorted(memory_dir.glob("*.yaml")):
        if path.name == "graph.yaml":
            continue
        entry = parse_entry(path)
        facts[entry.id] = entry
    return facts


def _load_episodes(episodes_dir: Path) -> list[tuple[Path, Any]]:
    if not episodes_dir.is_dir():
        return []
    return [(path, parse_episode(path)) for path in sorted(episodes_dir.glob("*.yaml"))]


def _load_skills(skills_dir: Path) -> list[tuple[Path, Any]]:
    """Learned Skills only. Builtins are product defaults, not learned intake (#47)."""
    from skills import parse_skill, project_skill_paths

    return [(path, parse_skill(path)) for path in project_skill_paths(skills_dir)]


def _trace_ids(memory_dir: Path) -> set[str]:
    traces = memory_dir / "traces"
    if not traces.is_dir():
        return set()
    return {path.stem for path in traces.glob("*.yaml")}


def _load_traces(traces_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    if not traces_dir.is_dir():
        return []
    # Hook Traces carry UTC and use records local time, so order by the moment, not the text.
    loaded: list[tuple[datetime, dict[str, Any]]] = []
    for path in sorted(traces_dir.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            loaded.append((_moment(payload.get("timestamp")) or _OLDEST, payload))
    loaded.sort(key=lambda item: item[0], reverse=True)
    return [payload for _key, payload in loaded[:limit]]


def _load_scores(scores_dir: Path) -> dict[str, Any]:
    if not scores_dir.is_dir():
        return {}
    scores: dict[str, Any] = {}
    for path in sorted(scores_dir.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("run_id"):
            scores[str(payload["run_id"])] = payload
    return scores
