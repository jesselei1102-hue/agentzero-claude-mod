"""Vendored runtime packages: sync into template/, hash them, stamp a workspace.

`template/` is everything the operator takes in order to use the agent, so the
packages a workspace needs to run are committed there and `init` stays a pure
copy. The boundary is host dependence: hook wiring is resolved per machine and
per harness (SETTLED #38) so it is generated; these packages are identical on
every machine so they are copied.
"""

from __future__ import annotations

import hashlib
import shutil
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from memory.host import command

VENDORED_PACKAGES: tuple[str, ...] = ("knowledge", "memory", "skills", "score", "traces")
"""`adapter` is deliberately absent: it creates and refreshes workspaces."""

MIRRORED_TREES: tuple[str, ...] = ("skills/builtin",)
"""Framework-owned trees that also exist in template/ and must not drift."""

LAUNCHERS: tuple[str, ...] = ("a0", "a0.cmd")
"""The workspace entry point (SETTLED #71); installed and refreshed with the runtime."""

MIRRORED_FILES: tuple[str, ...] = ("System.md", "OPERATOR.md", *LAUNCHERS)
"""Framework-owned files kept at the root and in template/.

Every operator-doc change for a release went into the root copy only, so each
freshly initialised workspace got the 0.1 checklist. Fourth committed copy to
drift, after template/src, template/skills/builtin and a workspace System.md.
"""

CONVENTION_FILES: tuple[str, ...] = ("System.md", "OPERATOR.md", ".gitignore")
CONVENTION_TREES: tuple[str, ...] = ("skills/builtin",)
"""Framework-owned files `init` copies into a workspace: replaced on upgrade when stale,
refused when the operator edited them (SETTLED #86). Role.md, knowledge.yaml, memory/,
work/, audit/ and learned Skills are the operator's and never written."""

SEEDED_FILES: tuple[str, ...] = ("memory/graph.yaml",)
"""Created when a workspace predates them, never replaced; so is every `.gitkeep`."""

STAMP_NAME = "VERSION.yaml"
SYNC_COMMAND = command("adapter sync-template")

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def framework_version(framework_root: Path) -> str:
    """Read [project].version from the framework's pyproject.toml."""
    payload = tomllib.loads((framework_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def tree_hash(src_root: Path, *, packages: Sequence[str] = VENDORED_PACKAGES) -> str:
    """Stable digest over the vendored `.py` contents, keyed by relative path."""
    digest = hashlib.sha256()
    for name in sorted(packages):
        package = src_root / name
        for path in sorted(package.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            digest.update(str(path.relative_to(src_root).as_posix()).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def sync_template(
    framework_root: Path, *, packages: Sequence[str] = VENDORED_PACKAGES
) -> list[str]:
    """Regenerate the framework-owned copies under `template/` from their sources.

    Two trees: the runtime packages under `src/`, and the Layer 1 builtins, which
    are equally framework-owned and had been drifting with nothing watching.
    """
    written: list[str] = []
    source_root = framework_root / "src"
    target_root = framework_root / "template" / "src"
    target_root.mkdir(parents=True, exist_ok=True)
    for name in packages:
        source = source_root / name
        if not source.is_dir():
            raise FileNotFoundError(f"framework package not found: {source}")
        target = target_root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=_IGNORE)
        written.append(f"src/{name}")
    for relative in MIRRORED_TREES:
        source = framework_root / relative
        if not source.is_dir():
            continue
        target = framework_root / "template" / relative
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=_IGNORE)
        written.append(relative)
    for relative in MIRRORED_FILES:
        source = framework_root / relative
        if source.is_file():
            shutil.copy2(source, framework_root / "template" / relative)
            written.append(relative)
    return written


def mirrored_drift(framework_root: Path) -> str | None:
    """None when every mirrored tree matches its source; otherwise what differs."""
    for relative in MIRRORED_TREES:
        source = framework_root / relative
        target = framework_root / "template" / relative
        if not source.is_dir():
            continue
        if not target.is_dir():
            return f"template/{relative} is missing; run `{SYNC_COMMAND}`"
        names = {p.name for p in source.glob("*")} | {p.name for p in target.glob("*")}
        for name in sorted(names):
            left, right = source / name, target / name
            if not left.is_file() or not right.is_file():
                return f"template/{relative}/{name} differs; run `{SYNC_COMMAND}`"
            if left.read_bytes() != right.read_bytes():
                return f"template/{relative}/{name} has drifted; run `{SYNC_COMMAND}`"
    for relative in MIRRORED_FILES:
        source, target = framework_root / relative, framework_root / "template" / relative
        drifted = not target.is_file() or source.read_bytes() != target.read_bytes()
        if source.is_file() and drifted:
            return f"template/{relative} has drifted from ./{relative}; run `{SYNC_COMMAND}`"
    return None


def template_drift(
    framework_root: Path, *, packages: Sequence[str] = VENDORED_PACKAGES
) -> str | None:
    """None when `template/src` matches `src`; otherwise a message naming the fix."""
    source_root = framework_root / "src"
    target_root = framework_root / "template" / "src"
    if not target_root.is_dir():
        return f"template/src is missing; run `{SYNC_COMMAND}`"
    expected = tree_hash(source_root, packages=packages)
    actual = tree_hash(target_root, packages=packages)
    if expected == actual:
        return None
    return (
        "template/src has drifted from src/ "
        f"(src={expected[:19]}…, template={actual[:19]}…); run `{SYNC_COMMAND}`"
    )


def convention_paths(template_root: Path) -> list[str]:
    """The framework-owned convention files the template carries, as relative paths."""
    paths = [name for name in CONVENTION_FILES if (template_root / name).is_file()]
    for tree in CONVENTION_TREES:
        root = template_root / tree
        if root.is_dir():
            paths.extend(
                path.relative_to(template_root).as_posix()
                for path in sorted(root.rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
            )
    return paths


def seeded_paths(template_root: Path) -> list[str]:
    paths = [name for name in SEEDED_FILES if (template_root / name).is_file()]
    paths.extend(
        path.relative_to(template_root).as_posix()
        for path in sorted(template_root.rglob(".gitkeep"))
        if "src" not in path.relative_to(template_root).parts[:1]
    )
    return paths


def file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def write_stamp(
    workspace: Path,
    *,
    framework_root: Path,
    packages: Sequence[str] = VENDORED_PACKAGES,
    now: datetime | None = None,
) -> Path:
    """Record what this workspace carries, so skew and local edits are detectable.

    Each convention file is hashed as it stands, which is as the framework wrote it:
    a later difference from that hash is the operator's edit, not the framework's move.
    """
    clock = now or datetime.now().astimezone()
    destination = workspace / "src" / STAMP_NAME
    payload = {
        "agentzero_version": framework_version(framework_root),
        "vendored_at": clock.isoformat(),
        "source": str(framework_root.resolve()),
        "packages": list(packages),
        "tree_hash": tree_hash(workspace / "src", packages=packages),
        "conventions": {
            name: file_hash(workspace / name)
            for name in convention_paths(framework_root / "template")
            if (workspace / name).is_file()
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return destination


def read_stamp(workspace: Path) -> dict[str, object] | None:
    """Parse `src/VERSION.yaml`; None when a workspace carries no stamp."""
    path = workspace / "src" / STAMP_NAME
    if not path.is_file():
        return None
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


@dataclass(frozen=True)
class UpgradeDecision:
    """What `materialize` should do about the workspace's vendored runtime."""

    action: str  # install | current | upgrade | refuse
    detail: str
    changed_files: tuple[str, ...] = ()

    @property
    def blocks(self) -> bool:
        return self.action == "refuse"


def _changed_against_framework(
    workspace: Path, framework_root: Path, *, packages: Sequence[str]
) -> tuple[str, ...]:
    """Relative paths whose bytes differ from the framework's own `src/`."""
    source_root = framework_root / "src"
    target_root = workspace / "src"
    changed: list[str] = []
    for name in packages:
        source = source_root / name
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(source_root)
            mirror = target_root / relative
            if not mirror.is_file() or mirror.read_bytes() != path.read_bytes():
                changed.append(relative.as_posix())
    for launcher in LAUNCHERS:
        source, mirror = framework_root / launcher, workspace / launcher
        if not source.is_file():
            continue
        if not mirror.is_file() or mirror.read_bytes() != source.read_bytes():
            changed.append(launcher)
    return tuple(changed)


def plan_upgrade(
    workspace: Path,
    *,
    framework_root: Path,
    packages: Sequence[str] = VENDORED_PACKAGES,
) -> UpgradeDecision:
    """Decide between installing, upgrading, leaving alone, and refusing."""
    workspace_src = workspace / "src"
    if not workspace_src.is_dir() or not any(
        (workspace_src / name).is_dir() for name in packages
    ):
        return UpgradeDecision("install", "workspace carries no vendored runtime")

    stamp = read_stamp(workspace)
    changed = _changed_against_framework(workspace, framework_root, packages=packages)
    if stamp is None:
        return UpgradeDecision(
            "refuse",
            "src/ is present but unstamped, so its origin is unknown",
            changed,
        )

    actual = tree_hash(workspace_src, packages=packages)
    if actual != stamp.get("tree_hash"):
        return UpgradeDecision(
            "refuse",
            "the vendored runtime was edited in place since it was stamped",
            changed,
        )
    stamped = str(stamp.get("agentzero_version"))
    current = framework_version(framework_root)
    if not changed:
        if stamped != current:
            # Same bytes, newer release. Without a restamp, materialize would call
            # this current while preflight reported it stale — forever, since
            # nothing would ever change the stamp.
            return UpgradeDecision("upgrade", f"restamp {stamped} → {current}; runtime unchanged")
        return UpgradeDecision("current", f"already at {current}")
    if stamped == current:
        # The version was not bumped, so it cannot be what changed; say what did.
        noun = "file" if len(changed) == 1 else "files"
        detail = f"{len(changed)} {noun} changed within {current} (version not bumped)"
    else:
        detail = f"{stamped} → {current}, {len(changed)} files changed"
    return UpgradeDecision("upgrade", detail, changed)


def apply_upgrade(
    workspace: Path,
    *,
    framework_root: Path,
    packages: Sequence[str] = VENDORED_PACKAGES,
) -> list[str]:
    """Copy the framework's packages into the workspace and restamp it."""
    source_root = framework_root / "src"
    target_root = workspace / "src"
    target_root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name in packages:
        source = source_root / name
        if not source.is_dir():
            raise FileNotFoundError(f"framework package not found: {source}")
        target = target_root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=_IGNORE)
        written.append(name)
    # The launcher belongs to the runtime it launches: a workspace upgraded from before
    # `./a0` existed would otherwise print hints naming a command it does not have.
    for launcher in LAUNCHERS:
        source = framework_root / launcher
        if source.is_file():
            shutil.copy2(source, workspace / launcher)
            written.append(launcher)
    write_stamp(workspace, framework_root=framework_root, packages=packages)
    return written


@dataclass(frozen=True)
class ConventionPlan:
    """What bringing a workspace's convention files forward would write."""

    stale: tuple[str, ...] = ()
    """As the framework last wrote them, and the framework has moved: replaced."""
    missing: tuple[str, ...] = ()
    """Framework-owned or seeded, and absent: created."""
    edited: tuple[str, ...] = ()
    """Differ from both the framework and what was stamped: the operator's, refused."""

    @property
    def writes(self) -> tuple[str, ...]:
        return self.stale + self.missing


def plan_conventions(workspace: Path, *, framework_root: Path) -> ConventionPlan:
    """Sort each framework-owned file into current, stale, missing or edited.

    A file with no stamped hash (a workspace stamped before hashes were recorded)
    cannot be told apart from an edit, so it is treated as one.
    """
    template = framework_root / "template"
    stamp = read_stamp(workspace) or {}
    recorded = stamp.get("conventions")
    hashes = recorded if isinstance(recorded, dict) else {}
    stale: list[str] = []
    missing: list[str] = []
    edited: list[str] = []
    for name in convention_paths(template):
        target = workspace / name
        if not target.is_file():
            missing.append(name)
        elif target.read_bytes() != (template / name).read_bytes():
            (stale if hashes.get(name) == file_hash(target) else edited).append(name)
    missing.extend(name for name in seeded_paths(template) if not (workspace / name).exists())
    return ConventionPlan(tuple(stale), tuple(missing), tuple(edited))


def apply_conventions(
    workspace: Path, *, framework_root: Path, plan: ConventionPlan, force: bool = False
) -> list[str]:
    """Write the framework's copy of each file the plan names; edited ones only with force.

    Restamps whenever it wrote something or the stamp lacks a file's hash, so the next
    upgrade can tell the framework's moves from the operator's edits.
    """
    template = framework_root / "template"
    names = [*plan.writes, *(plan.edited if force else ())]
    for name in names:
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template / name, target)
    stamp = read_stamp(workspace) or {}
    recorded = stamp.get("conventions")
    hashes = recorded if isinstance(recorded, dict) else {}
    unrecorded = any(
        name not in hashes for name in convention_paths(template) if (workspace / name).is_file()
    )
    if names or unrecorded:
        write_stamp(workspace, framework_root=framework_root)
    return names
