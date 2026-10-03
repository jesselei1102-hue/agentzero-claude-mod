"""CLI: python -m memory hot-set, remember, propose, link, promote, forget, review, lint.

`hot-set` is the run-start seam System rule 3 names: it computes the injection
block (as-of Facts + activated graph index) so the
selection rules of ADR 0005 / 0006 actually run, instead of being re-derived by
hand from the file tree.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge import Reach, Source, load_sources, reach
from memory.graph import (
    edge_sentence,
    export_graph_markdown,
    parse_graph,
    write_entity,
    write_link,
)
from memory.host import ask, command, relay, reminder, warn_if_foreign_runtime
from memory.lifecycle import (
    HotSet,
    live_fact_ids,
    load_hot_set,
    promote_episode,
    propose_episode,
    propose_fact,
    remember_fact,
    supersede_fact_key,
)
from memory.lint import DEFAULT_RECENT_RUNS, lint_workspace
from memory.review import Pending, collect_pending, confirm, find, reject, render, resolve, retire
from memory.runstate import hot_set_reminder, note_hot_set
from memory.text import is_request, is_standing, supported_by
from skills import Listed, list_skills


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not args:
        parser.print_help(sys.stdout)
        return 2
    parsed = parser.parse_args(args)
    workspace = getattr(parsed, "workspace", None)
    if workspace is None and getattr(parsed, "memory_dir", None) is not None:
        workspace = parsed.memory_dir.parent
    warn_if_foreign_runtime(Path(workspace or "."), "memory")
    if parsed.command == "export-graph":
        return _export_graph(parsed)
    if parsed.command == "remember":
        return _remember(parsed)
    if parsed.command == "propose":
        return _propose(parsed)
    if parsed.command == "link":
        return _link(parsed)
    if parsed.command == "promote":
        return _promote(parsed)
    if parsed.command == "forget":
        return _forget(parsed)
    if parsed.command == "review":
        return _review(parsed)
    if parsed.command == "lint":
        return _lint(parsed)
    return _hot_set(parsed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m memory", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    hot = sub.add_parser(
        "hot-set",
        help="print the run-start Memory injection block (ADR 0005 / 0006)",
    )
    hot.add_argument("--memory-dir", type=Path, default=Path("memory"))
    hot.add_argument("--scope", choices=("task", "project"), default="project")
    hot.add_argument(
        "--hints",
        action="append",
        default=[],
        help="task keywords steering graph activation; repeatable or comma-separated",
    )
    hot.add_argument("--k", type=int, default=20, help="graph index line cap (default 20)")
    hot.add_argument("--as-of", default=None, help="ISO timestamp; default now")
    hot.add_argument("--hops", type=int, default=2, help="graph spreading hops (default 2)")
    hot.add_argument("--decay", type=float, default=0.5, help="per-hop decay (default 0.5)")
    hot.add_argument("--format", choices=("text", "yaml"), default="text")
    hot.add_argument(
        "--explain",
        action="store_true",
        help="show activation score and hop distance per graph line",
    )

    remember = sub.add_parser(
        "remember",
        help="record something the operator just said as an active Fact",
    )
    remember.add_argument(
        "sentence", help="the Fact, in one plain sentence, as the operator said it"
    )
    remember.add_argument(
        "--said",
        required=True,
        metavar="WORDS",
        help="the operator's own words this comes from, quoted as they said them",
    )
    remember.add_argument("--workspace", type=Path, default=Path("."))
    remember.add_argument("--scope", choices=("task", "project"), default="project")
    remember.add_argument(
        "--fact-key",
        default=None,
        metavar="KEY",
        help="stable name for state that changes (progress, a current choice); "
        "a newer statement with the same key retires the older one",
    )
    remember.add_argument("--tag", action="append", default=[], help="repeatable")
    remember.add_argument(
        "--source-run", default="operator-stated", help="run id, when the run has one"
    )

    propose = sub.add_parser(
        "propose",
        help="record something the agent inferred; it waits for the operator's yes",
    )
    kinds = propose.add_subparsers(dest="kind", required=True)
    fact = kinds.add_parser("fact", help="a one-sentence Fact, proposed")
    fact.add_argument("sentence", help="the Fact, in one plain sentence")
    fact.add_argument("--workspace", type=Path, default=Path("."))
    fact.add_argument("--scope", choices=("task", "project"), default="project")
    fact.add_argument(
        "--fact-key",
        default=None,
        metavar="KEY",
        help="stable name for state that changes; confirming replaces the older Fact",
    )
    fact.add_argument("--tag", action="append", default=[], help="repeatable")
    fact.add_argument(
        "--source-run", default="agent-inferred", help="run id, when the run has one"
    )

    entity = kinds.add_parser("entity", help="a thing this project talks about, proposed")
    entity.add_argument("label", help="what people call it, e.g. a client or a model")
    entity.add_argument("--workspace", type=Path, default=Path("."))
    entity.add_argument(
        "--fact", action="append", default=[], metavar="ID", help="link a Fact; repeatable"
    )
    entity.add_argument("--tag", action="append", default=[], help="repeatable")

    edge = kinds.add_parser("edge", help="how two things relate, proposed")
    edge.add_argument("source", metavar="from", help="an entity's label or id")
    edge.add_argument("rel", help="the relationship, e.g. owns")
    edge.add_argument("target", metavar="to", help="an entity's label or id")
    edge.add_argument("--note", default=None)
    edge.add_argument("--workspace", type=Path, default=Path("."))

    episode = kinds.add_parser("episode", help="something that happened, proposed")
    episode.add_argument("sentence", help="what happened, in one plain sentence")
    episode.add_argument("--at", default=None, metavar="ISO", help="when; default now")
    episode.add_argument("--source-run", default="agent-inferred")
    episode.add_argument("--workspace", type=Path, default=Path("."))

    link = sub.add_parser(
        "link",
        help="record how two things relate because the operator said so (active)",
    )
    link.add_argument("source", metavar="from", help="an entity's label or id; created if new")
    link.add_argument("rel", help="the relationship, e.g. owns")
    link.add_argument("target", metavar="to", help="an entity's label or id; created if new")
    link.add_argument("--note", default=None)
    link.add_argument("--workspace", type=Path, default=Path("."))

    promote = sub.add_parser(
        "promote",
        help="turn an Episode into a proposed Fact — the only way an Episode is remembered",
    )
    promote.add_argument("episode", help="an Episode id, e.g. episode:episode-20260921-101500")
    promote.add_argument("sentence", help="the Fact, in one plain sentence")
    promote.add_argument("--workspace", type=Path, default=Path("."))
    promote.add_argument("--scope", choices=("task", "project"), default="project")
    promote.add_argument("--fact-key", default=None, metavar="KEY")
    promote.add_argument("--tag", action="append", default=[], help="repeatable")

    forget = sub.add_parser(
        "forget",
        help="retire something on record because the operator withdrew it; nothing is deleted",
    )
    forget.add_argument(
        "target", nargs="?", default=None, help="kind:id (fact, episode, entity, edge, skill)"
    )
    forget.add_argument(
        "--fact-key", default=None, metavar="KEY", help="retire the active Fact holding this key"
    )
    forget.add_argument("--workspace", type=Path, default=Path("."))

    review = sub.add_parser(
        "review",
        help="see what the agent proposed, and confirm or reject it",
    )
    review.add_argument("--workspace", type=Path, default=Path("."))
    review.add_argument(
        "--confirm", nargs="+", metavar="ID", default=[], help="proposed → active"
    )
    review.add_argument(
        "--reject", nargs="+", metavar="ID", default=[], help="proposed → retired"
    )
    review.add_argument("--format", choices=("text", "yaml"), default="text")

    lint = sub.add_parser(
        "lint",
        help="EVAL L2 structure lint: dangling references and consolidation candidates",
    )
    lint.add_argument("--workspace", type=Path, default=Path("."))
    lint.add_argument("--format", choices=("text", "yaml"), default="text")
    lint.add_argument(
        "--recent-runs",
        type=int,
        default=DEFAULT_RECENT_RUNS,
        help=f"how many Traces count as recent (default {DEFAULT_RECENT_RUNS})",
    )
    lint.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on hygiene findings; consolidation candidates never fail",
    )

    export = sub.add_parser("export-graph", help="regenerate the read-only Mermaid graph view")
    export.add_argument("graph_path", nargs="?", type=Path, default=Path("memory/graph.yaml"))
    export.add_argument("destination", nargs="?", type=Path, default=None)
    return parser


def _lint(parsed: argparse.Namespace) -> int:
    try:
        report = lint_workspace(parsed.workspace, recent_runs=parsed.recent_runs)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"lint failed: {exc}\n")
        return 1
    if parsed.format == "yaml":
        sys.stdout.write(
            yaml.safe_dump(
                {
                    "workspace": str(report.workspace),
                    "findings": [
                        {
                            "group": item.group,
                            "code": item.code,
                            "subject": item.subject,
                            "detail": item.detail,
                            "fix": item.fix,
                        }
                        for item in report.findings
                    ],
                    "notes": list(report.notes),
                },
                sort_keys=False,
                allow_unicode=True,
            )
        )
    else:
        sys.stdout.write(report.render())
    # Consolidation is a judgement the operator makes; only defects gate a build.
    return 1 if (parsed.strict and report.has_hygiene) else 0


def _remember(parsed: argparse.Namespace) -> int:
    memory_dir: Path = parsed.workspace / "memory"
    if not memory_dir.is_dir():
        sys.stderr.write(f"no memory/ directory under {parsed.workspace}\n")
        return 1
    refusal = _not_the_operators_word(parsed.sentence, parsed.said)
    if refusal:
        sys.stderr.write(f"remember refused: {refusal}\n")
        return 1
    if not supported_by(parsed.sentence, parsed.said.strip()):
        return _proposed_instead(parsed, memory_dir)
    try:
        result = remember_fact(
            memory_dir,
            rule=parsed.sentence,
            scope=parsed.scope,
            fact_key=parsed.fact_key,
            tags=parsed.tag,
            source_run=parsed.source_run,
            said=parsed.said,
        )
    except ValueError as exc:
        sys.stderr.write(f"remember failed: {exc}\n")
        return 1
    if result.existing:
        sys.stdout.write(f"already remembered: {result.entry.id} — {result.entry.rule}\n")
        sys.stdout.write(relay(f'already on record: "{result.entry.rule}"'))
        return 0
    sys.stdout.write(f"remembered: {result.entry.id} — {result.entry.rule}\n")
    for old in result.superseded:
        sys.stdout.write(f"replaced:   {old.id} — {old.rule}\n")
    sys.stdout.write(_cited_by_skills(parsed.workspace, [o.id for o in result.superseded]))
    for other in result.resembling:
        sys.stdout.write(f"similar:    {other.id} — {other.rule}\n")
    if result.resembling:
        sys.stdout.write(
            "  both are active now. If the new one replaces it: "
            + command(f"memory forget fact:{result.resembling[0].id}")
            + "; for state that changes, record it with --fact-key so the next one replaces it\n"
        )
    told = f'remembered "{result.entry.rule}"'
    if result.superseded:
        told += "; it replaces " + ", ".join(f'"{old.rule}"' for old in result.superseded)
    only_now = is_request(parsed.said) and not is_standing(parsed.said)
    if only_now:
        told += " — kept for later runs too; if it was meant for this task only, say so"
    sys.stdout.write(relay(told))
    if only_now:
        sys.stdout.write(
            "  if it was for this task only: "
            + command(f"memory forget fact:{result.entry.id}")
            + "\n"
        )
    if is_standing(parsed.said):
        sys.stdout.write(_RECURRING)
    sys.stdout.write(reminder(hot_set_reminder(parsed.workspace)))
    return 0


_RECURRING = (
    "→ if this says a kind of work is to be done this way each time it comes back (not how "
    "to talk), the operator said it will recur: ask them, in their language, whether to keep "
    "how it was done as a Skill, and if yes: "
    + command(
        'skills draft --id <name> --description "<when to use it>" '
        "--runs <what this run left under work/> --procedure-file <file>"
    )
    + "\n"
)
"""Rule 8 at the moment it applies (SETTLED #91). "以后每个课程模块都要这样做笔记" was
recorded as a Fact and nothing more: the rule was prose, and no command spoke."""


def _not_the_operators_word(sentence: str, said: str) -> str | None:
    """Why `sentence` may not be recorded as the operator's word, or None if it may.

    In the test kit WorkBuddy, Hermes and Devin each recorded "the operator studied
    lesson 2" as operator-stated, and Hermes replaced a correct Fact with it. The
    operator had said only "here is last week's lecture, make it md notes".

    Words that ask for something are not refused (SETTLED #85): refusing "你不要一次过
    给我太多内容" made the agent cut the operator's words until they passed.
    `_remember` keeps it and has the operator told instead. Nor is a sentence that says
    more than the words (SETTLED #88): it becomes a proposal, see `_proposed_instead`.
    """
    if not said.strip():
        propose = command('memory propose fact "<what you concluded>"')
        return "--said needs the operator's own words; with none, it is yours: " + propose
    return None


def _proposed_instead(parsed: argparse.Namespace, memory_dir: Path) -> int:
    """A sentence that says more than the operator's words waits for them, as a proposal.

    Refused, it was rewritten until it passed: "Lesson 0 paused at reshape; start there
    next time", from the operator's "先到这里", became "用户本次先暂停", which kept the
    words and lost where the lesson stopped. What the agent added is its conclusion, so
    the operator is asked; nothing the operator did not say becomes active unconfirmed,
    which is what the refusal was for.
    """
    try:
        result = propose_fact(
            memory_dir,
            rule=parsed.sentence,
            scope=parsed.scope,
            fact_key=parsed.fact_key,
            tags=parsed.tag,
            source_run=parsed.source_run,
            said=parsed.said,
        )
    except ValueError as exc:
        sys.stderr.write(f"remember failed: {exc}\n")
        return 1
    if result.existing:
        sys.stdout.write(
            f"already on record ({result.entry.status}): {result.entry.id} — {result.entry.rule}\n"
        )
        return 0
    sys.stdout.write(f"proposed: {result.entry.id} — {result.entry.rule}\n")
    sys.stdout.write(
        f'  it says more than the operator\'s words ("{parsed.said.strip()}"), so it is '
        "your conclusion, not theirs yet\n"
    )
    sys.stdout.write(_WAITING)
    sys.stdout.write(ask(result.entry.rule, f"fact:{result.entry.id}"))
    sys.stdout.write(reminder(hot_set_reminder(parsed.workspace)))
    return 0


_WAITING = "waiting for the operator: it is not remembered until confirmed\n"


def _propose(parsed: argparse.Namespace) -> int:
    memory_dir: Path = parsed.workspace / "memory"
    if not memory_dir.is_dir():
        sys.stderr.write(f"no memory/ directory under {parsed.workspace}\n")
        return 1
    if parsed.kind != "fact":
        return _propose_other(parsed, memory_dir)
    try:
        result = propose_fact(
            memory_dir,
            rule=parsed.sentence,
            scope=parsed.scope,
            fact_key=parsed.fact_key,
            tags=parsed.tag,
            source_run=parsed.source_run,
        )
    except ValueError as exc:
        sys.stderr.write(f"propose failed: {exc}\n")
        return 1
    if result.existing:
        sys.stdout.write(
            f"already on record ({result.entry.status}): {result.entry.id} — {result.entry.rule}\n"
        )
        return 0
    sys.stdout.write(f"proposed: {result.entry.id} — {result.entry.rule}\n")
    sys.stdout.write(_WAITING)
    sys.stdout.write(ask(result.entry.rule, f"fact:{result.entry.id}"))
    sys.stdout.write(reminder(hot_set_reminder(parsed.workspace)))
    return 0


def _propose_other(parsed: argparse.Namespace, memory_dir: Path) -> int:
    graph = memory_dir / "graph.yaml"
    asked: tuple[str, str]
    try:
        if parsed.kind == "episode":
            noted = propose_episode(
                memory_dir,
                rule=parsed.sentence,
                observed_at=parsed.at,
                source_run=parsed.source_run,
            )
            if noted.existing:
                sys.stdout.write(
                    f"already on record ({noted.episode.status}): "
                    f"episode:{noted.episode.id} — {noted.episode.rule}\n"
                )
                return 0
            sys.stdout.write(f"proposed: episode:{noted.episode.id} — {noted.episode.rule}\n")
            asked = (noted.episode.rule, f"episode:{noted.episode.id}")
        elif parsed.kind == "entity":
            unknown = sorted(set(parsed.fact) - live_fact_ids(memory_dir))
            if unknown:
                raise ValueError(f"no such Fact to link: {', '.join(unknown)}")
            written = write_entity(
                graph, parsed.label, author="agent", tags=parsed.tag, fact_ids=parsed.fact
            )
            if written.existing:
                sys.stdout.write(
                    f"already on record ({written.entity.status}): "
                    f"entity:{written.entity.id} — {written.entity.label}\n"
                )
                return 0
            sys.stdout.write(f"proposed: entity:{written.entity.id} — {written.entity.label}\n")
            asked = (written.entity.label, f"entity:{written.entity.id}")
        else:
            linked = write_link(
                graph, parsed.source, parsed.rel, parsed.target, author="agent", note=parsed.note
            )
            edge = linked.edge
            sentence = edge_sentence(parse_graph(graph), edge)
            if linked.existing:
                sys.stdout.write(
                    f"already on record ({edge.status}): edge:{edge.id} — {sentence}\n"
                )
                return 0
            sys.stdout.write(f"proposed: edge:{edge.id} — {sentence}\n")
            for made in linked.created_entities:
                sys.stdout.write(f"proposed: entity:{made.id} — {made.label}\n")
            asked = (sentence, f"edge:{edge.id}")
    except ValueError as exc:
        sys.stderr.write(f"propose failed: {exc}\n")
        return 1
    sys.stdout.write(_WAITING)
    sys.stdout.write(ask(*asked))
    sys.stdout.write(reminder(hot_set_reminder(parsed.workspace)))
    return 0


def _link(parsed: argparse.Namespace) -> int:
    memory_dir: Path = parsed.workspace / "memory"
    if not memory_dir.is_dir():
        sys.stderr.write(f"no memory/ directory under {parsed.workspace}\n")
        return 1
    try:
        linked = write_link(
            memory_dir / "graph.yaml",
            parsed.source,
            parsed.rel,
            parsed.target,
            author="human",
            note=parsed.note,
        )
    except ValueError as exc:
        sys.stderr.write(f"link failed: {exc}\n")
        return 1
    edge = linked.edge
    sentence = edge_sentence(parse_graph(memory_dir / "graph.yaml"), edge)
    if linked.existing:
        sys.stdout.write(f"already linked: edge:{edge.id} — {sentence}\n")
        return 0
    sys.stdout.write(f"linked: edge:{edge.id} — {sentence}\n")
    for made in linked.created_entities:
        sys.stdout.write(f"created: entity:{made.id} — {made.label}\n")
    sys.stdout.write(relay(f'recorded "{sentence}"'))
    sys.stdout.write(reminder(hot_set_reminder(parsed.workspace)))
    return 0


def _promote(parsed: argparse.Namespace) -> int:
    memory_dir: Path = parsed.workspace / "memory"
    if not memory_dir.is_dir():
        sys.stderr.write(f"no memory/ directory under {parsed.workspace}\n")
        return 1
    try:
        result = promote_episode(
            memory_dir,
            parsed.episode,
            rule=parsed.sentence,
            scope=parsed.scope,
            fact_key=parsed.fact_key,
            tags=parsed.tag,
        )
    except ValueError as exc:
        sys.stderr.write(f"promote failed: {exc}\n")
        return 1
    if result.existing:
        sys.stdout.write(
            f"already on record ({result.entry.status}): {result.entry.id} — {result.entry.rule}\n"
        )
        return 0
    sys.stdout.write(f"proposed: {result.entry.id} — {result.entry.rule}\n")
    sys.stdout.write(f"from {parsed.episode}; " + _WAITING)
    sys.stdout.write(ask(result.entry.rule, f"fact:{result.entry.id}"))
    return 0


def _cited_by_skills(workspace: Path, fact_ids: Sequence[str]) -> str:
    """Name each live Skill that cites a Fact being retired, and the way out.

    Kit 2 (2026-09-26): Claude replaced a Fact its new Skill cited; lint then reported
    `active-skill-cites-retired-fact`, and only a new version cleared it. A Skill's
    content is what the operator confirmed, so it is not repointed silently (#72).
    """
    if not fact_ids:
        return ""
    from skills import parse_skill, project_skill_paths

    retired = set(fact_ids)
    lines: list[str] = []
    for path in project_skill_paths(workspace / "skills"):
        skill = parse_skill(path)
        cited = sorted(retired & set(skill.memory_ids))
        if skill.status == "retired" or not cited:
            continue
        lines.append(
            f"  skill:{skill.id} cites it (fact:{', fact:'.join(cited)}); lint reports that "
            "until a version cites the replacement: "
            + command(
                f"skills draft --id {skill.id}-v2 --supersedes {skill.id} --memory-id <new> …"
            )
            + "\n"
        )
    return "".join(lines)


def _forget(parsed: argparse.Namespace) -> int:
    workspace: Path = parsed.workspace
    if not (workspace / "memory").is_dir():
        sys.stderr.write(f"no memory/ directory under {workspace}\n")
        return 1
    if bool(parsed.target) == bool(parsed.fact_key):
        sys.stderr.write("forget needs exactly one of: kind:id, or --fact-key\n")
        return 1
    if parsed.fact_key:
        retired = supersede_fact_key(workspace / "memory", parsed.fact_key)
        if not retired:
            sys.stderr.write(f"no active Fact holds fact_key {parsed.fact_key!r}\n")
            return 1
        for entry in retired:
            sys.stdout.write(f"forgot: fact:{entry.id} — {entry.rule}\n")
        sys.stdout.write(_cited_by_skills(workspace, [entry.id for entry in retired]))
        sys.stdout.write(relay("no longer remembered: " + "; ".join(e.rule for e in retired)))
        return 0
    try:
        item = find(workspace, parsed.target)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    retire(workspace, item.kind, item.id)
    sys.stdout.write(f"forgot: {item.qualified_id} — {item.sentence}\n")
    if item.kind == "fact":
        sys.stdout.write(_cited_by_skills(workspace, [item.id]))
    sys.stdout.write(relay(f'no longer remembered: "{item.sentence}"'))
    return 0


def _review(parsed: argparse.Namespace) -> int:
    workspace: Path = parsed.workspace
    if not (workspace / "memory").is_dir():
        sys.stderr.write(f"no memory/ directory under {workspace}\n")
        return 1

    acted = False
    for raw, action, verb in (
        (parsed.confirm, confirm, "confirmed"),
        (parsed.reject, reject, "rejected"),
    ):
        for identifier in raw:
            try:
                item = resolve(workspace, identifier)
                replaced = action(workspace, item) or ()
            except ValueError as exc:
                sys.stderr.write(f"{exc}\n")
                return 1
            sys.stdout.write(f"{verb}: {item.qualified_id} — {item.sentence}\n")
            for old in replaced:
                sys.stdout.write(f"replaced:   fact:{old.id} — {old.rule}\n")
            sys.stdout.write(_cited_by_skills(workspace, [old.id for old in replaced]))
            told = "kept" if verb == "confirmed" else "dropped"
            sys.stdout.write(relay(f'{told} "{item.sentence}"'))
            acted = True
    if acted:
        return 0

    pending = collect_pending(workspace)
    if parsed.format == "yaml":
        sys.stdout.write(
            yaml.safe_dump(
                [
                    {
                        "id": item.qualified_id,
                        "kind": item.kind,
                        "sentence": item.sentence,
                        "provenance": item.provenance,
                    }
                    for item in pending
                ],
                sort_keys=False,
                allow_unicode=True,
            )
        )
    else:
        sys.stdout.write(render(pending))
    return 0


def _export_graph(parsed: argparse.Namespace) -> int:
    parse_graph(parsed.graph_path)
    written = export_graph_markdown(parsed.graph_path, destination=parsed.destination)
    sys.stdout.write(f"{written}\n")
    return 0


def _hot_set(parsed: argparse.Namespace) -> int:
    memory_dir: Path = parsed.memory_dir
    if not memory_dir.is_dir():
        sys.stderr.write(f"memory directory not found: {memory_dir}\n")
        return 1

    hints = _split_hints(parsed.hints)
    try:
        hot = load_hot_set(
            memory_dir,
            run_scope=parsed.scope,
            as_of=parsed.as_of,
            task_hints=hints,
            graph_k=parsed.k,
            graph_hops=parsed.hops,
            graph_decay=parsed.decay,
        )
    except ValueError as exc:
        sys.stderr.write(f"hot set failed: {exc}\n")
        return 1

    note_hot_set(memory_dir, hints, fact_ids=tuple(entry.id for entry in hot.facts))
    start = _run_start(memory_dir.parent)
    if parsed.format == "yaml":
        sys.stdout.write(_as_yaml(hot, scope=parsed.scope, hints=hints, start=start))
    else:
        sys.stdout.write(
            _as_text(hot, scope=parsed.scope, hints=hints, explain=parsed.explain, start=start)
        )
    return 0


_SHOWN_WAITING = 3
_ASK_WAITING = (
    "→ ask the operator about each, one at a time, in their language; then run exactly what "
    "they answered: " + command("memory review --confirm <id>") + " or --reject <id>"
)
_HAND_OVER = (
    "Material the operator hands you: `knowledge add <path> --type docs|index|raw --name ...` "
    "before discussing it. A PDF, RTF or Word file is not text: extract it with a tool this "
    "machine has (e.g. pypdf, textutil, pandoc) before relying on it."
)


@dataclass(frozen=True)
class _RunStart:
    """What else a run must know at its start, carried by the one command it always runs.

    In the dummy's sessions the agent ran `hot-set` every time and never ran `review` or
    `knowledge list`, which the rules also ask for at run start. So `hot-set` says it.
    """

    waiting: tuple[Pending, ...]
    knowledge: tuple[tuple[Source, Reach], ...]
    problem: str | None = None
    skills: tuple[Listed, ...] = ()
    """Rule 5 asks for `skills list` too, and a run that never ran it chose no Skill."""


def _run_start(workspace: Path) -> _RunStart:
    problems: list[str] = []
    waiting: tuple[Pending, ...] = ()
    knowledge: tuple[tuple[Source, Reach], ...] = ()
    try:
        waiting = collect_pending(workspace)
    except ValueError as exc:
        problems.append(f"waiting items unreadable: {exc}")
    try:
        knowledge = tuple((source, reach(workspace, source)) for source in load_sources(workspace))
    except ValueError as exc:
        problems.append(str(exc))
    skills: tuple[Listed, ...] = ()
    try:
        skills = tuple(item for item in list_skills(workspace) if item.routable)
    except (OSError, ValueError) as exc:
        problems.append(f"skills unreadable: {exc}")
    return _RunStart(waiting, knowledge, "; ".join(problems) or None, skills)


def _split_hints(raw: Sequence[str]) -> tuple[str, ...]:
    hints: list[str] = []
    for item in raw:
        hints.extend(part.strip() for part in item.split(",") if part.strip())
    return tuple(hints)


def _as_text(
    hot: HotSet, *, scope: str, hints: Sequence[str], explain: bool, start: _RunStart
) -> str:
    hint_text = ", ".join(hints) if hints else "(none)"
    lines = [
        "# Memory hot set",
        f"scope={scope} hints={hint_text}",
        "",
        f"## Facts ({len(hot.facts)})",
    ]
    if hot.facts:
        lines.extend(f"- {entry.id}: {entry.rule}" for entry in hot.facts)
    else:
        lines.append("- (none)")

    activation = hot.graph_activation
    if activation is not None:
        lines.append("")
        lines.append(f"## Graph activation ({len(activation.lines)} entities)")
        if activation.lines:
            for line in activation.lines:
                suffix = f"  [score={line.score} hops={line.hops}]" if explain else ""
                lines.append(f"- {line.line}{suffix}")
        else:
            lines.append("- (none)")
        if activation.edges:
            lines.append("")
            lines.append("### Edges among activated")
            lines.extend(
                f"- {edge.from_id} --{edge.rel}--> {edge.to_id}" for edge in activation.edges
            )

    lines.extend(
        [
            "",
            f"## Waiting for the operator ({len(start.waiting)})"
            " — not Memory: offer these, do not act on them",
        ]
    )
    if start.waiting:
        for item in start.waiting[:_SHOWN_WAITING]:
            lines.append(f"- {item.qualified_id}: {item.sentence}")
        if len(start.waiting) > _SHOWN_WAITING:
            lines.append(f"- … and {len(start.waiting) - _SHOWN_WAITING} more (`memory review`)")
        lines.append(_ASK_WAITING)
    else:
        lines.append("- (none)")

    lines.extend(["", f"## Knowledge ({len(start.knowledge)} declared)"])
    for source, state in start.knowledge:
        mark = "" if state.ok else "  [UNREACHABLE]"
        lines.append(f"- {source.id} ({source.type}): {source.name} — {state.detail}{mark}")
    lines.append(f"- {_HAND_OVER}")

    lines.extend(["", f"## Skills ({len(start.skills)}) — pick one for this task before starting"])
    for listed in start.skills:
        lines.append(f"- {listed.skill.id} ({listed.layer}): {listed.skill.description}")
    if not start.skills:
        lines.append("- (none)")

    warnings = _warnings(hot) + ([start.problem] if start.problem else [])
    lines.extend(["", f"## Warnings ({len(warnings)})"])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _as_yaml(hot: HotSet, *, scope: str, hints: Sequence[str], start: _RunStart) -> str:
    activation = hot.graph_activation
    payload = {
        "scope": scope,
        "hints": list(hints),
        "facts": [{"id": entry.id, "rule": entry.rule} for entry in hot.facts],
        "loaded_memory_ids": [entry.id for entry in hot.facts],
        "graph_activation": None
        if activation is None
        else {
            "lines": [
                {
                    "entity_id": line.entity_id,
                    "line": line.line,
                    "score": line.score,
                    "hops": line.hops,
                }
                for line in activation.lines
            ],
            "edges": [
                {"id": edge.id, "from": edge.from_id, "to": edge.to_id, "rel": edge.rel}
                for edge in activation.edges
            ],
            "truncated": activation.truncated,
        },
        "waiting": [
            {"id": item.qualified_id, "sentence": item.sentence} for item in start.waiting
        ],
        "knowledge": [
            {
                "id": source.id,
                "type": source.type,
                "name": source.name,
                "reachable": state.ok,
                "detail": state.detail,
            }
            for source, state in start.knowledge
        ],
        "hand_over": _HAND_OVER,
        "skills": [
            {"id": item.skill.id, "layer": item.layer, "when": item.skill.description}
            for item in start.skills
        ],
        "warnings": _warnings(hot) + ([start.problem] if start.problem else []),
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _warnings(hot: HotSet) -> list[str]:
    warnings = list(hot.overlap_warnings)
    if hot.fact_count_warning:
        warnings.append(hot.fact_count_warning)
    if hot.graph_activation is not None and hot.graph_activation.warning:
        warnings.append(hot.graph_activation.warning)
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
