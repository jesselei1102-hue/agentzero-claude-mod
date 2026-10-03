"""Stand a portable workspace from the extracted template."""

from __future__ import annotations

import shutil
from pathlib import Path

from adapter.claude import materialize_claude
from adapter.codex import materialize_codex
from adapter.cursor import materialize_cursor
from adapter.vendor import write_stamp

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO / "template"
_MATERIALIZERS = {
    "cursor": materialize_cursor,
    "codex": materialize_codex,
    "claude": materialize_claude,
}


def init_workspace(dest: Path, *, template: Path | None = None, harness: str = "cursor") -> None:
    """Copy the portable template into dest and materialize the specified harness adapter."""
    if harness not in _MATERIALIZERS:
        # Falling back to Cursor stood the wrong workspace without a word.
        expected = ", ".join(_MATERIALIZERS)
        raise ValueError(f"unknown harness {harness!r}; expected one of {expected}")
    dest = dest.resolve()
    if (dest / "Role.md").is_file():
        raise FileExistsError(dest / "Role.md")
    source = (template or _TEMPLATE).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    common = shutil.ignore_patterns("__pycache__", ".DS_Store")

    def ignore(folder: str, names: list[str]) -> set[str]:
        # memory/traces/ holds run state. A hook run with its cwd inside template/ took
        # it for a workspace and staged a run there, which init then copied into every
        # new workspace; only the placeholder belongs to the template.
        if Path(folder).parts[-2:] == ("memory", "traces"):
            return {name for name in names if name != ".gitkeep"}
        return set(common(folder, names))

    for item in source.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(item, target)

    # The template carries the runtime packages verbatim; only the provenance of
    # this particular copy has to be recorded here.
    if (dest / "src").is_dir():
        write_stamp(dest, framework_root=source.parent)

    _MATERIALIZERS[harness](dest)
