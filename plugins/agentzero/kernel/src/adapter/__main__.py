"""python -m adapter init DEST | materialize [DIR] | preflight [DIR] | sync-template"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adapter.claude import materialize_claude
from adapter.codex import materialize_codex
from adapter.cursor import materialize_cursor
from adapter.init import init_workspace
from adapter.preflight import run_preflight
from adapter.vendor import (
    apply_conventions,
    apply_upgrade,
    plan_conventions,
    plan_upgrade,
    sync_template,
)

FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adapter")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="copy the portable template and materialize harness files")
    init_p.add_argument("dest", type=Path)
    init_p.add_argument(
        "--harness",
        choices=("cursor", "codex", "claude"),
        default="cursor",
        help="which harness adapter to materialize (default: cursor)",
    )

    mat = sub.add_parser(
        "materialize",
        help="write harness artifacts from System.md, keep the runtime current, then preflight",
    )
    mat.add_argument("workspace", nargs="?", type=Path, default=Path("."))
    mat.add_argument(
        "--harness",
        choices=("cursor", "codex", "claude", "all"),
        default="cursor",
        help="which harness adapter to run (default: cursor)",
    )
    mat.add_argument(
        "--force",
        action="store_true",
        help="overwrite a vendored runtime or framework file that was edited in place",
    )
    mat.add_argument("--strict", action="store_true", help="treat preflight warnings as failures")

    pre = sub.add_parser("preflight", help="check that a workspace can actually run")
    pre.add_argument("workspace", nargs="?", type=Path, default=Path("."))
    pre.add_argument("--strict", action="store_true", help="treat warnings as failures")

    sync = sub.add_parser(
        "sync-template",
        help="regenerate template/src from the framework's own src/",
    )
    sync.add_argument("framework", nargs="?", type=Path, default=Path("."))

    args = parser.parse_args(argv)

    if args.command == "sync-template":
        written = sync_template(args.framework.resolve())
        sys.stdout.write(f"synced template/src: {', '.join(written)}\n")
        return 0

    if args.command == "init":
        init_workspace(args.dest, harness=args.harness)
        return 0

    if args.command == "preflight":
        report = run_preflight(
            args.workspace.resolve(), framework_root=FRAMEWORK_ROOT, strict=args.strict
        )
        sys.stdout.write(report.render())
        return 1 if report.failed else 0

    workspace = args.workspace.resolve()
    if not _upgrade_runtime(workspace, force=args.force):
        return 1
    if not _upgrade_conventions(workspace, force=args.force):
        return 1
    if args.harness in {"cursor", "all"}:
        materialize_cursor(workspace)
    if args.harness in {"codex", "all"}:
        materialize_codex(workspace)
    if args.harness in {"claude", "all"}:
        materialize_claude(workspace)
    report = run_preflight(workspace, framework_root=FRAMEWORK_ROOT, strict=args.strict)
    sys.stdout.write(report.render())
    return 1 if report.failed else 0


def _upgrade_runtime(workspace: Path, *, force: bool) -> bool:
    """Keep the workspace's vendored runtime current. False means stop."""
    if workspace == FRAMEWORK_ROOT:
        # The framework checkout is the source; there is nothing to vendor into it.
        return True
    decision = plan_upgrade(workspace, framework_root=FRAMEWORK_ROOT)
    if decision.blocks and not force:
        sys.stderr.write(f"refusing to overwrite the vendored runtime: {decision.detail}\n")
        for name in decision.changed_files[:10]:
            sys.stderr.write(f"  differs from framework: src/{name}\n")
        if len(decision.changed_files) > 10:
            sys.stderr.write(f"  … and {len(decision.changed_files) - 10} more\n")
        sys.stderr.write("re-run with --force to replace it\n")
        return False
    if decision.action in {"install", "upgrade"} or (decision.blocks and force):
        apply_upgrade(workspace, framework_root=FRAMEWORK_ROOT)
        sys.stdout.write(f"vendored runtime: {decision.action} ({decision.detail})\n")
    return True


def _upgrade_conventions(workspace: Path, *, force: bool) -> bool:
    """Bring System.md and the other framework-owned files forward. False means stop.

    Runs before the harness files are written, since they are generated from System.md:
    an upgrade that skipped it re-emitted the old rules into fresh harness files.
    """
    if workspace == FRAMEWORK_ROOT:
        return True
    plan = plan_conventions(workspace, framework_root=FRAMEWORK_ROOT)
    if plan.edited and not force:
        sys.stderr.write("refusing to overwrite framework files edited in this workspace:\n")
        for name in plan.edited:
            sys.stderr.write(f"  {name} (compare with {FRAMEWORK_ROOT / 'template' / name})\n")
        sys.stderr.write(
            "move what you changed into Role.md or Memory, or re-run with --force to "
            "replace them with the framework's copy\n"
        )
        return False
    written = apply_conventions(workspace, framework_root=FRAMEWORK_ROOT, plan=plan, force=force)
    if written:
        sys.stdout.write(f"framework files: {', '.join(written)}\n")
    return True


if __name__ == "__main__":
    sys.exit(main())
