"""CLI: python -m skills list | draft | run (System rules 5, 8; #72).

What exists, when each applies, and the only way a Skill's script runs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

from memory.host import ask, command, warn_if_foreign_runtime
from skills.assets import CONTRACT, ENTRY, SCRIPTS_DIRNAME, hash_all, violations
from skills.lifecycle import SKILL_FILENAME, draft_skill
from skills.registry import list_skills, render
from skills.runner import RefusedError, RunRequest, run

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skills")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="Skills and builtins, in rule 5 precedence order")
    listing.add_argument("--workspace", type=Path, default=Path("."))
    listing.add_argument("--format", choices=("text", "yaml"), default="text")
    listing.add_argument(
        "--include-retired",
        action="store_true",
        help="also show retired Skills, which are never routed to",
    )
    draft = sub.add_parser(
        "draft",
        help="write a Skill draft; it stays a draft until the operator confirms it",
        epilog=CONTRACT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    draft.add_argument("--id", required=True, help="letters, digits, - and _ only")
    draft.add_argument(
        "--description", required=True, help="one sentence saying when to use this Skill"
    )
    draft.add_argument(
        "--runs",
        nargs="+",
        required=True,
        metavar="RUN",
        help="the runs it was learned from: Trace or Score ids, or with no Trace, "
        "what the run left under work/ (a path) or an Episode id",
    )
    draft.add_argument(
        "--procedure-file",
        required=True,
        metavar="FILE",
        help="the procedure as Markdown, or - for stdin",
    )
    draft.add_argument("--memory-id", action="append", default=[], help="repeatable")
    draft.add_argument("--task-class", default=None, help="the key `memory lint` derived")
    draft.add_argument(
        "--script",
        action="append",
        default=[],
        type=Path,
        metavar="FILE",
        help=f"repeatable; the entry must be {ENTRY}, taking template | plan | apply",
    )
    draft.add_argument(
        "--supersedes",
        default=None,
        metavar="ID",
        help="the Skill this version replaces once the operator confirms it",
    )
    draft.add_argument("--workspace", type=Path, default=Path("."))
    runner = sub.add_parser(
        "run",
        help="run a Skill's script: a plan by default, --apply to execute",
        epilog=CONTRACT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    runner.add_argument("id")
    runner.add_argument("--template", action="store_true", help="print the hand-off columns")
    runner.add_argument("--input", type=Path, metavar="RECORDS", help="the filled hand-off file")
    runner.add_argument("--output", type=Path, help="default work/<id>/<date>/")
    runner.add_argument(
        "--append-to", type=Path, metavar="TABLE", help="a table kept across batches"
    )
    runner.add_argument(
        "--reviewed", metavar="SENTENCE", help="your check that this batch fits the Skill"
    )
    runner.add_argument("--apply", action="store_true", help="execute the plan")
    runner.add_argument(
        "--in-place",
        action="append",
        default=[],
        type=Path,
        metavar="FOLDER",
        help="let the script rename files where they are in FOLDER (repeatable); "
        "skills run writes a map that undoes it",
    )
    runner.add_argument("--workspace", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    warn_if_foreign_runtime(args.workspace, "skills")

    if args.command == "draft":
        return _draft(args)
    if args.command == "run":
        return _run(args)

    listed = list_skills(args.workspace, include_retired=args.include_retired)
    if args.format == "yaml":
        sys.stdout.write(
            yaml.safe_dump(
                [
                    {
                        "layer": item.layer,
                        "id": item.skill.id,
                        "status": item.skill.status,
                        "description": item.skill.description,
                        "task_class": item.skill.task_class,
                        "path": str(item.path),
                    }
                    for item in listed
                ],
                sort_keys=False,
                allow_unicode=True,
            )
        )
    else:
        sys.stdout.write(render(listed))
    return 0


def _draft(args: argparse.Namespace) -> int:
    if not _SAFE_ID.match(args.id):
        sys.stderr.write(f"draft failed: id must be letters, digits, - and _, got {args.id!r}\n")
        return 1
    directory: Path = args.workspace / "skills"
    scripts: list[Path] = args.script
    destination = (
        directory / args.id / SKILL_FILENAME if scripts else directory / f"{args.id}.md"
    )
    if (directory / f"{args.id}.md").exists() or (directory / args.id).exists():
        sys.stderr.write(f"draft failed: skill {args.id} exists; retire it or pick a new id\n")
        return 1
    problem = _script_problem(scripts)
    if problem:
        sys.stderr.write(f"draft failed: {problem}\n")
        return 1
    try:
        procedure = (
            sys.stdin.read()
            if args.procedure_file == "-"
            else Path(args.procedure_file).read_text(encoding="utf-8")
        )
        referenced = [] if scripts else _source_run_scripts(args.workspace, args.runs, procedure)
        if referenced:
            procedure = procedure.rstrip() + "\n\n" + _scripts_section(referenced)
        destination.parent.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        for script in scripts:
            target = destination.parent / SCRIPTS_DIRNAME / script.name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(script, target)
            names.append(f"{SCRIPTS_DIRNAME}/{script.name}")
        skill = draft_skill(
            destination,
            id=args.id,
            source_runs=args.runs,
            procedure=procedure,
            memory_ids=args.memory_id,
            task_class=args.task_class,
            description=args.description,
            assets=hash_all(destination.parent, names),
            supersedes=args.supersedes,
        )
    except (OSError, ValueError) as exc:
        if scripts and destination.parent.exists():
            shutil.rmtree(destination.parent)
        sys.stderr.write(f"draft failed: {exc}\n")
        return 1
    sys.stdout.write(f"drafted: skill:{skill.id} — {skill.description}\n")
    sys.stdout.write("waiting for the operator: it is a draft until confirmed\n")
    if skill.assets:
        sys.stdout.write(
            "  its script is confirmed by what it does: show the operator a plan from "
            f"{command(f'skills run {skill.id} --input <records.csv>')}, or the result of "
            "the run it came from, whichever they prefer\n"
        )
    else:
        sys.stdout.write(_no_script_hint(args.workspace))
        if referenced:
            sys.stdout.write(
                f"  listed in the Skill as references to adapt: {', '.join(referenced)}\n"
            )
    if skill.supersedes:
        sys.stdout.write(
            f"  confirming it retires skill:{skill.supersedes}; "
            "until then that one stays in use\n"
        )
    sys.stdout.write(ask(skill.description or skill.id, f"skill:{skill.id}"))
    return 0


_CODE_SUFFIXES = frozenset({".py", ".mjs", ".js", ".cjs", ".ts", ".sh", ".ps1", ".r", ".R"})
_NOT_OURS = frozenset({"node_modules", "__pycache__", ".venv", "venv", ".git"})


def _source_run_scripts(workspace: Path, runs: list[str], procedure: str) -> list[str]:
    """Code files the source runs left, which the procedure does not name.

    Turn-by-turn test (2026-09-27): Codex drafted a prose Skill beside the scripts it had
    written, and the next run rewrote them from scratch. Without a confirmed script the
    Skill can still say where the last run's code is (operator, 2026-09-27).

    A cited path's folder is searched, except `work/` itself: it pools every task's
    output, and the Lab (2026-10-05) listed another task's sensor scripts in a Skill for
    turning a form into JSON. A run's own Trace names what it wrote, so the code in the
    `work_files` of a cited Trace, or of a Trace naming a cited path, is listed too.
    """
    root = workspace.resolve()
    pooled = (workspace / "work").resolve()
    traces = _traces_work_files(workspace)
    folders: list[Path] = []
    written: list[str] = []
    for cited in runs:
        by_run = [traces[cited]] if cited in traces else []
        by_run += [files for files in traces.values() if cited in files]
        for files in by_run:
            written.extend(name for name in files if name not in written)
        path = (workspace / cited).resolve()
        if path == root or root not in path.parents or not path.exists():
            continue  # a Trace or Score id, not a path the run left
        folder = path if path.is_dir() else path.parent
        if folder not in (root, pooled) and folder not in folders:
            folders.append(folder)
    found: list[str] = []
    for name in written:
        path = workspace / name
        if path.is_file() and path.suffix in _CODE_SUFFIXES and name not in procedure:
            found.append(name)
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix not in _CODE_SUFFIXES:
                continue
            if _NOT_OURS & set(path.relative_to(folder).parts):
                continue
            name = path.relative_to(root).as_posix()
            if name not in found and name not in procedure:
                found.append(name)
    return found[:20]


def _traces_work_files(workspace: Path) -> dict[str, list[str]]:
    """Run id → the `work_files` its Trace names; unreadable Traces are skipped."""
    traces_dir = workspace / "memory" / "traces"
    out: dict[str, list[str]] = {}
    for path in sorted(traces_dir.glob("*.yaml")) if traces_dir.is_dir() else []:
        try:
            trace = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(trace, dict):
            files = trace.get("work_files") or []
            out[str(trace.get("run_id") or path.stem)] = [str(name) for name in files]
    return out


def _scripts_section(names: list[str]) -> str:
    lines = [
        "## Scripts from the source run",
        "",
        "Code the run this Skill came from left behind. Not confirmed, not hashed and not "
        "run by `./a0 skills run`: read it and adapt it next time instead of writing the "
        "processing from scratch.",
        "",
    ]
    lines.extend(f"- `{name}`" for name in names)
    return "\n".join(lines) + "\n"


def _no_script_hint(workspace: Path) -> str:
    """Kit 2: WorkBuddy drafted without the scripts it had written, Qoder kept none.

    Both then redid the processing by hand next run; a script-backed Skill is what
    lets that run reuse it (#72).
    """
    work = workspace / "work"
    found = sorted(
        str(path.relative_to(workspace))
        for path in (work.rglob("*.py") if work.is_dir() else [])
        if not {"node_modules", "__pycache__"} & set(path.parts)
    )
    if found:
        listed = ", ".join(found[:5]) + (" …" if len(found) > 5 else "")
        return (
            f"  no script attached, but work/ holds {listed}. If one of them did the "
            "processing (validate, copy, rename, tabulate), draft again with "
            f"--script <file> so the next run reuses it instead of rewriting it\n"
        )
    return (
        "  no script attached. If code did the processing, save it as a file under work/ "
        "and draft again with --script <file>, so the next run reuses it\n"
    )


def _script_problem(scripts: list[Path]) -> str | None:
    if not scripts:
        return None
    names = [script.name for script in scripts]
    if ENTRY not in names:
        return (
            f"one script must be named {ENTRY}: "
            "`skills run` calls it with template | plan | apply"
        )
    if len(set(names)) != len(names):
        return "two scripts share a file name"
    for script in scripts:
        if not script.is_file():
            return f"{script} does not exist"
        if script.suffix != ".py":
            return f"{script} is not a Python file"
        found = violations(script.read_text(encoding="utf-8"))
        if found:
            return (
                f"{script.name} may not do this in a Skill: {'; '.join(found)}\n{CONTRACT}"
            )
    return None


def _run(args: argparse.Namespace) -> int:
    request = RunRequest(
        skill_id=args.id,
        template=args.template,
        # The script runs from the workspace root, so relative paths are fixed here.
        input=None if args.input is None else args.input.resolve(),
        output=None if args.output is None else args.output.resolve(),
        append_to=None if args.append_to is None else args.append_to.resolve(),
        in_place=tuple(folder.resolve() for folder in args.in_place),
        reviewed=args.reviewed,
        apply=args.apply,
    )
    try:
        sys.stdout.write(run(args.workspace.resolve(), request))
    except RefusedError as exc:
        sys.stderr.write(f"run refused: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
