"""CLI: python -m knowledge list | add | forget — what reference material a run can use (rule 2)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from knowledge.sources import (
    TYPES,
    add_source,
    forget_source,
    is_plain_text,
    load_sources,
    reach,
)
from memory.host import command, relay, reminder, warn_if_foreign_runtime
from memory.runstate import hot_set_reminder


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    warn_if_foreign_runtime(args.workspace, "knowledge")
    if args.command == "add":
        return _add(args)
    if args.command == "forget":
        return _forget(args)
    return _list(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m knowledge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="declared sources, and whether each is reachable here")
    listing.add_argument("--workspace", type=Path, default=Path("."))
    listing.add_argument("--format", choices=("text", "yaml"), default="text")

    add = sub.add_parser(
        "add",
        help="declare reference material the operator handed over, so later runs can use it",
    )
    add.add_argument(
        "path", nargs="?", default=None, help="file or folder; may be omitted for an index"
    )
    add.add_argument("--type", required=True, choices=TYPES)
    add.add_argument("--name", required=True, help="what it is, in plain words")
    add.add_argument("--id", default=None, help="default: derived from --name")
    add.add_argument(
        "--query", default=None, metavar="COMMAND", help="index only: how a run searches it"
    )
    add.add_argument(
        "--prerequisite", action="append", default=[], help="what must be running; repeatable"
    )
    add.add_argument(
        "--from",
        dest="derived_from",
        default=None,
        metavar="ID",
        help="the raw source this was prepared from",
    )
    add.add_argument(
        "--in-place",
        action="store_true",
        help="declare a path outside the workspace where it is, instead of copying it in",
    )
    add.add_argument("--notes", default=None)
    add.add_argument("--workspace", type=Path, default=Path("."))

    forget = sub.add_parser(
        "forget",
        help="retire a source declared by mistake or withdrawn; nothing is deleted",
    )
    forget.add_argument("id", help="the source id, as `knowledge list` shows it")
    forget.add_argument("--workspace", type=Path, default=Path("."))
    return parser


def _forget(args: argparse.Namespace) -> int:
    try:
        source = forget_source(args.workspace, args.id)
    except ValueError as exc:
        sys.stderr.write(f"forget failed: {exc}\n")
        return 1
    sys.stdout.write(
        f"retired: {source.id} ({source.type}) — {source.name}; kept in knowledge.yaml "
        "and on disk, no longer read by any run\n"
    )
    sys.stdout.write(relay(f'"{source.name}" is no longer used as Knowledge'))
    return 0


def _add(args: argparse.Namespace) -> int:
    try:
        added = add_source(
            args.workspace,
            args.path,
            type=args.type,
            name=args.name,
            id=args.id,
            query=args.query,
            prerequisites=args.prerequisite,
            derived_from=args.derived_from,
            notes=args.notes,
            in_place=args.in_place,
        )
    except ValueError as exc:
        sys.stderr.write(f"add failed: {exc}\n")
        return 1
    source = added.source
    where = source.path or "(queried by command)"
    if added.existing:
        sys.stdout.write(f"already declared: {source.id} ({source.type}) — {where}\n")
        return 0
    sys.stdout.write(f"declared: {source.id} ({source.type}) — {source.name} — {where}\n")
    if source.type == "raw":
        # Codex and Cursor asked "shall I extract it and make Markdown?" after the operator
        # had said "make it md notes": "unless the operator already said how" read as
        # "unless they named the method", and a line asking for a sample first did the rest.
        sys.stdout.write(
            "raw: prepare it into knowledge/<name>/ (not work/, not /tmp), then declare "
            "that folder: "
            + command(f"knowledge add knowledge/<name> --type docs --from {source.id}")
            + " --name ...\n"
            "  if the operator named the result (\"make it md notes\"), that is their yes: "
            "go ahead. Only when they asked for nothing, propose how and wait\n"
            # Kit 2: three of four agents declared a batch of reports they were asked to
            # tabulate and file, and two wrote that step into the Skill they learned.
            "  files handed over to be processed (a batch to tabulate, rename or file) are "
            "input, not Knowledge: if that is what this is, "
            + command(f"knowledge forget {source.id}")
            + "\n"
        )
    if source.path and not is_plain_text(_resolve_for_output(args.workspace, source.path)):
        sys.stdout.write(
            "not plain text: extract its text with a tool this machine has (e.g. textutil, "
            "pandoc, pypdf) straight into knowledge/<name>/; show a sample in your reply, and "
            "never write a clause you did not extract\n"
        )
    if args.in_place and source.path and Path(source.path).expanduser().is_absolute():
        sys.stdout.write(
            f"in place: nothing was copied; if {source.path} moves or is deleted, no run can "
            "read this source. Without --in-place it is copied into knowledge/\n"
        )
    sys.stdout.write(relay(f'declared "{source.name}" as {source.type} Knowledge'))
    sys.stdout.write(reminder(hot_set_reminder(args.workspace)))
    return 0


def _resolve_for_output(workspace: Path, path: str) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else workspace / candidate


def _list(args: argparse.Namespace) -> int:
    try:
        sources = load_sources(args.workspace)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    rows = [(source, reach(args.workspace, source)) for source in sources]
    if args.format == "yaml":
        sys.stdout.write(
            yaml.safe_dump(
                [
                    {
                        "id": source.id,
                        "type": source.type,
                        "name": source.name,
                        "path": source.path,
                        "reachable": state.ok,
                        "detail": state.detail,
                    }
                    for source, state in rows
                ],
                sort_keys=False,
                allow_unicode=True,
            )
        )
        return 0
    if not rows:
        sys.stdout.write(
            "No Knowledge declared.\n\n"
            "That is valid: without it the agent studies the Role itself and marks what it\n"
            "concludes as proposed. Reference material the operator hands over is added with\n"
            "`knowledge add`.\n"
        )
        return 0
    lines = [f"{len(rows)} Knowledge source(s)", ""]
    for source, state in rows:
        mark = "ok  " if state.ok else "MISS"
        lines.append(f"  [{mark}] {source.id} ({source.type}) — {source.name}")
        lines.append(f"         {source.path or '(no path)'} · {state.detail}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
