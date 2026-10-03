"""Declared Knowledge sources, and the one way to add one.

Rule 2 told the agent to *read* `knowledge.yaml` and nothing told it to *write*
there, so reference material an operator handed over was read once and was gone
the next run — the same gap Memory had before `remember` (#64). A source is only
a pointer: its form is `docs`, `index` or `raw` (#19); the framework guarantees
the place, not the format, and ships no ingest pipeline.
"""

from __future__ import annotations

import filecmp
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from memory.text import slug

TYPES: tuple[str, ...] = ("docs", "index", "raw")
FILE_NAME = "knowledge.yaml"
HEADER = (
    "# Knowledge is optional. Each source is docs, index, or raw.\n"
    "# Do not embed project facts (Memory) or procedures (Skills) here.\n"
    "# Add sources with: ./a0 knowledge add <path> --type docs|index|raw --name ...\n"
)
_NOT_KNOWLEDGE = ("memory", "skills")
"""Workspace stores that already have a meaning; a path inside them is not reference material."""


@dataclass(frozen=True)
class Source:
    id: str
    type: str
    name: str
    path: str | None
    raw: dict[str, Any]
    """Every field as written, so fields this code does not know survive a rewrite."""

    @property
    def retired(self) -> bool:
        return self.raw.get("status") == "retired"


@dataclass(frozen=True)
class Added:
    source: Source
    existing: bool = False


@dataclass(frozen=True)
class Reach:
    ok: bool
    detail: str


def load_sources(workspace: Path, *, include_retired: bool = False) -> tuple[Source, ...]:
    """Every declared source. A missing file is an empty declaration (Knowledge is optional).

    A retired source stays in the file — nothing is deleted — but no run reads it, so it is
    left out unless the caller asks for the whole record.
    """
    path = workspace / FILE_NAME
    if not path.is_file():
        return ()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded in (None, ""):
        return ()
    if not isinstance(loaded, dict):
        raise ValueError(f"{FILE_NAME} must be a YAML mapping with a `sources` list")
    raw_sources = loaded.get("sources") or []
    if not isinstance(raw_sources, list):
        raise ValueError(f"{FILE_NAME}: `sources` must be a list")
    sources: list[Source] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_sources):
        source = _from_mapping(item, where=f"sources[{index}]")
        if source.id in seen:
            raise ValueError(f"{FILE_NAME}: source id {source.id!r} is declared twice")
        seen.add(source.id)
        sources.append(source)
    return tuple(source for source in sources if include_retired or not source.retired)


def reach(workspace: Path, source: Source) -> Reach:
    """Can a run actually get at this source from here?"""
    if source.path is None:
        if source.type == "index" and source.raw.get("query"):
            return Reach(True, "queried by command")
        return Reach(False, "no path, and no query command")
    target = _resolve(workspace, source.path)
    if not target.exists():
        return Reach(False, f"{source.path} does not exist on this machine")
    if target.is_dir():
        count = sum(1 for item in target.rglob("*") if item.is_file() and item.name != ".gitkeep")
        return Reach(count > 0, f"{count} file(s)" if count else "folder is empty")
    return Reach(True, "file")


def add_source(
    workspace: Path,
    path: str | None,
    *,
    type: str,
    name: str,
    id: str | None = None,
    query: str | None = None,
    prerequisites: Sequence[str] = (),
    derived_from: str | None = None,
    notes: str | None = None,
    in_place: bool = False,
) -> Added:
    """Declare a source. Refuses anything a later run could not use; never rewrites a source.

    A file outside the workspace is copied into `knowledge/<id>/` and the copy declared:
    a chat attachment or a download may not be there next week. This is the default, not a
    flag, because the flag was the one step the agent left out. `in_place` points at it
    where it is — for an index or a shared drive the operator keeps up.
    """
    if type not in TYPES:
        raise ValueError(f"type must be one of {', '.join(TYPES)}, got {type!r}")
    name = name.strip()
    if not name:
        raise ValueError("a source needs a name saying what it is")
    record = load_sources(workspace, include_retired=True)
    sources = tuple(current for current in record if not current.retired)

    stored: str | None = None
    copied_from: str | None = None
    if path:
        target = _resolve(workspace, path)
        if not target.exists():
            raise ValueError(f"{path} does not exist; a source nobody can open is not Knowledge")
        if type == "docs" and target.is_file() and not is_plain_text(target):
            # Three of eight agents declared an .rtf lecture as docs and put their notes
            # under work/: a run then "reads" markup it cannot read, and the notes are
            # no one's Knowledge. The command says so instead of the rule alone.
            raise ValueError(
                f"{path} is not plain text, so a run cannot read it as docs. Declare it "
                "--type raw, extract its text into knowledge/<name>/, then declare that "
                "folder --type docs --from <raw-id>"
            )
        if not in_place and _relative(workspace, target) is None:
            home = (workspace / "knowledge").resolve()
            for current in sources:
                if current.path and _same_content(_resolve(workspace, current.path), target):
                    return Added(current, existing=True)
            identifier = _new_id(record, id=id, name=name)
            destination = home / identifier / target.name
            if destination.parent.exists():
                raise ValueError(f"knowledge/{identifier}/ already exists; pass a different --id")
            destination.parent.mkdir(parents=True)
            if target.is_dir():
                shutil.copytree(target, destination)
            else:
                shutil.copy2(target, destination)
            copied_from = str(target)
            target, path, id = destination, str(destination), identifier
        stored = _stored_path(workspace, target, given=path)
        inside = _relative(workspace, target)
        if inside is not None and inside.parts and inside.parts[0] in _NOT_KNOWLEDGE:
            raise ValueError(
                f"{stored} is inside {inside.parts[0]}/, which holds "
                f"{'Facts' if inside.parts[0] == 'memory' else 'Skills'}, not reference material"
            )
        for current in sources:
            if current.path and _resolve(workspace, current.path) == target:
                return Added(current, existing=True)
    elif type != "index":
        raise ValueError(f"a {type} source needs a path")
    if type == "index" and not (query or "").strip():
        raise ValueError("an index source needs --query: the command a run uses to search it")

    if derived_from and derived_from not in {current.id for current in sources}:
        raise ValueError(f"--from names no declared source: {derived_from!r}")

    identifier = _new_id(record, id=id, name=name)

    payload: dict[str, Any] = {"id": identifier, "type": type, "name": name}
    if stored is not None:
        payload["path"] = stored
    if query:
        payload["query"] = {"command": query.strip()}
    if prerequisites:
        payload["prerequisites"] = [item for item in prerequisites if item.strip()]
    if derived_from:
        payload["derived_from"] = derived_from
    if notes:
        payload["notes"] = notes.strip()
    # Where it came from and when: `knowledge.yaml` could not say whether a source was
    # the operator's, and a self-check had to answer "unknown".
    payload["added_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if copied_from:
        payload["copied_from"] = copied_from
    source = _from_mapping(payload, where="new source")
    _write(workspace, [*(item.raw for item in record), payload])
    return Added(source)


def forget_source(workspace: Path, source_id: str) -> Source:
    """Retire a declared source: it stays in the file and on disk, and no run reads it.

    The counterpart of `memory forget`. Before it, a source declared by mistake could only
    be removed by hand-editing `knowledge.yaml`, which the rules forbid.
    """
    record = load_sources(workspace, include_retired=True)
    match = next((current for current in record if current.id == source_id), None)
    if match is None:
        raise ValueError(f"no declared source {source_id!r}; see `knowledge list`")
    if match.retired:
        raise ValueError(f"{source_id!r} is already retired")
    children = [
        current.id for current in record
        if not current.retired and current.raw.get("derived_from") == source_id
    ]
    if children:
        # Devin tried to retire the raw lecture after declaring its notes, was refused with
        # "forget that first", and retired the good notes instead.
        raise ValueError(
            f"{source_id!r} is the original that {', '.join(children)} was prepared from. "
            "Keeping both declared is right: there is nothing to forget. Only if the operator "
            f"withdrew the material itself, forget {', '.join(children)} first"
        )
    rewritten = []
    for current in record:
        raw = dict(current.raw)
        if current.id == source_id:
            raw["status"] = "retired"
            raw["retired_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        rewritten.append(raw)
    _write(workspace, rewritten)
    return _from_mapping(rewritten[record.index(match)], where="retired source")


_NOT_TEXT = frozenset({".pdf", ".rtf", ".doc", ".docx", ".odt", ".pages", ".xls", ".xlsx"})
"""Decodes as text or not, a run cannot read these as they are. RTF is ASCII markup."""


def is_plain_text(path: Path) -> bool:
    """Can a run read this file as it is? A PDF or scan cannot, and must be extracted first."""
    if path.is_dir():
        return True
    if path.suffix.lower() in _NOT_TEXT:
        return False
    try:
        path.read_bytes()[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _new_id(sources: Sequence[Source], *, id: str | None, name: str) -> str:
    identifier = slug(id) if id else slug(name)
    taken = {current.id for current in sources}
    if id and identifier in taken:
        raise ValueError(f"source id {identifier!r} is already declared")
    base, suffix = identifier, 1
    while identifier in taken:
        suffix += 1
        identifier = f"{base}-{suffix}"
    return identifier


def _same_content(declared: Path, candidate: Path) -> bool:
    """Is this file already declared, perhaps as a copy made earlier?"""
    if not declared.exists():
        return False
    if declared.is_dir() and candidate.is_file():
        inner = declared / candidate.name
        return inner.is_file() and filecmp.cmp(inner, candidate, shallow=False)
    if declared.is_file() and candidate.is_file():
        return filecmp.cmp(declared, candidate, shallow=False)
    return False


def _from_mapping(item: Any, *, where: str) -> Source:
    if not isinstance(item, dict):
        raise ValueError(f"{FILE_NAME}: {where} must be a mapping")
    missing = [key for key in ("id", "type", "name") if item.get(key) in (None, "")]
    if missing:
        raise ValueError(f"{FILE_NAME}: {where} is missing {', '.join(missing)}")
    kind = str(item["type"])
    if kind not in TYPES:
        raise ValueError(f"{FILE_NAME}: {where} type must be docs, index, or raw, got {kind!r}")
    path = item.get("path")
    return Source(
        id=str(item["id"]),
        type=kind,
        name=str(item["name"]),
        path=None if path in (None, "") else str(path),
        raw=dict(item),
    )


def _write(workspace: Path, sources: list[dict[str, Any]]) -> None:
    path = workspace / FILE_NAME
    header = HEADER
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = []
        for line in lines:
            if not line.startswith("#"):
                break
            kept.append(line)
        if kept:
            header = "".join(kept)
    body = yaml.safe_dump({"sources": sources}, sort_keys=False, allow_unicode=True)
    path.write_text(header + body, encoding="utf-8")


def _resolve(workspace: Path, path: str) -> Path:
    candidate = Path(path).expanduser()
    return (candidate if candidate.is_absolute() else workspace / candidate).resolve()


def _relative(workspace: Path, target: Path) -> Path | None:
    try:
        return target.relative_to(workspace.resolve())
    except ValueError:
        return None


def _stored_path(workspace: Path, target: Path, *, given: str) -> str:
    """Inside the workspace: relative, so it can move. Outside: as the operator gave it."""
    inside = _relative(workspace, target)
    if inside is None:
        return given
    return inside.as_posix() or "."
