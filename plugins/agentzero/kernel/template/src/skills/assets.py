"""A Skill's confirmed scripts: their hashes, and what a script may do (#72).

The script owns only the deterministic tail of the work — validate, copy,
rename, file, tabulate. Reading and understanding the inputs stay with the
agent. What a script may do is a mechanical rule, so it is a check (#55): the
imports on an allow-list, and none of the calls that delete or launch.
Renaming is allowed (#76): `skills run` maps every file it moves, and a source
moved without `--in-place` is reported with that map.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable
from pathlib import Path

SCRIPTS_DIRNAME = "scripts"
ENTRY = "run.py"
"""`skills run` calls scripts/run.py with `template`, `plan` or `apply`."""

ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "argparse",
        "collections",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "hashlib",
        "itertools",
        "json",
        "math",
        "openpyxl",
        "os",
        "pathlib",
        "re",
        "shutil",
        "string",
        "sys",
        "textwrap",
        "typing",
        "unicodedata",
        "yaml",
    }
)
"""The standard library a processing step needs, PyYAML, which `./a0` guarantees, and
openpyxl, because the table operators ask for is a workbook (#76); `skills run` says how
to install it where it is missing."""

FORBIDDEN_CALLS = frozenset(
    {
        # Nothing is deleted. Renaming and moving are allowed and mapped by `skills run`.
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "rmtree",
        # Nothing is launched or evaluated.
        "system",
        "popen",
        "execv",
        "execve",
        "execvp",
        "execl",
        "spawnv",
        "spawnl",
        "startfile",
        "kill",
        "eval",
        "exec",
        "compile",
        "__import__",
    }
)


CONTRACT = """\
A Skill's script (--script) runs only through `./a0 skills run <id>`. The entry is
scripts/run.py, called as:
  run.py template                  print the hand-off header: the columns the agent fills
  run.py plan  --input RECORDS --output DIR [--append-to TABLE] [--in-place FOLDER ...]
  run.py apply (same arguments)    plan changes nothing; apply does what plan printed
RECORDS is the hand-off the agent fills, CSV or JSON, one row per input file; the
script checks its columns and refuses, saying which, when they are missing. DIR is
where it writes. --append-to is a table kept across batches. --in-place lets it rename
files where they are; skills run maps every rename so it can be undone.
Imports: the standard library, PyYAML and openpyxl. It deletes nothing and launches
nothing. Paths and values come from RECORDS and the arguments, not constants, so the
next batch runs unchanged.
"""
"""Printed by `skills draft --help` and `skills run --help`: az5 (2026-09-27) read the
runner's source to learn this after both help texts said nothing."""


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_all(skill_dir: Path, relative: Iterable[str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((name, file_hash(skill_dir / name)) for name in relative))


def mismatches(skill_dir: Path, assets: Iterable[tuple[str, str]]) -> list[str]:
    """Asset paths that are missing or no longer hash to what was confirmed."""
    changed: list[str] = []
    for name, digest in assets:
        path = skill_dir / name
        if not path.is_file() or file_hash(path) != digest:
            changed.append(name)
    return changed


def violations(source: str) -> list[str]:
    """What this script does that a Skill's script may not. Empty means allowed."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"does not parse: {exc.msg} (line {exc.lineno})"]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, node.lineno, found)
        elif isinstance(node, ast.ImportFrom):
            _check_module(node.module or "", node.lineno, found)
            for alias in node.names:
                if alias.name in FORBIDDEN_CALLS:
                    found.append(f"line {node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.Call):
            name = _called_name(node.func)
            if name in FORBIDDEN_CALLS:
                found.append(f"line {node.lineno}: calls {name}()")
    return found


def _check_module(module: str, lineno: int, found: list[str]) -> None:
    root = module.split(".")[0]
    if root not in ALLOWED_IMPORTS:
        found.append(f"line {lineno}: imports {module or '(relative)'}, not on the allow-list")


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
