#!/usr/bin/env python3
"""Copy a release of AgentZero into the plugin's kernel/ folder (stdlib only).

usage: sync_kernel.py SOURCE_CHECKOUT [--ref REF] --denylist FILE [--dest DIR]
"""
import argparse
import datetime
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

ITEMS = ["src", "template", "pyproject.toml", "LICENSE"]
SKIP_NAMES = {"__pycache__", ".DS_Store"}
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "plugins/agentzero/kernel"


class SyncError(Exception):
    pass


def git(source, *args, text=True):
    try:
        return subprocess.run(
            ["git", "-C", str(source), *args], check=True, capture_output=True, text=text
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr if text else exc.stderr.decode("utf-8", "replace")
        raise SyncError(f"git {args[0]} failed: {detail.strip()}") from exc


def skipped(rel):
    parts = rel.split("/")
    if SKIP_NAMES & set(parts):
        return True
    for i in range(len(parts) - 2):
        if parts[i] == "memory" and parts[i + 1] == "traces":
            return parts[-1] != ".gitkeep"
    return False


def load_denylist(path):
    terms = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line.lower())
    return terms


def sync(source, ref, denylist, dest):
    source, dest = Path(source), Path(dest)
    commit = git(source, "rev-parse", f"{ref}^{{commit}}").strip()
    archive = git(source, "archive", "--format=tar", commit, *ITEMS, text=False)
    terms = load_denylist(denylist)

    files = {}
    tmp = dest.parent / (dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar:
                if not member.isfile() or skipped(member.name):
                    continue
                data = tar.extractfile(member).read()
                try:
                    lowered = data.decode("utf-8").lower()
                except UnicodeDecodeError:
                    lowered = None
                if lowered is not None:
                    for term in terms:
                        if term in lowered:
                            raise SyncError(
                                f"denylisted term {term!r} found in {member.name}"
                            )
                target = tmp / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(member.mode & 0o777)
                files[member.name] = hashlib.sha256(data).hexdigest()

        try:
            version = tomllib.loads((tmp / "pyproject.toml").read_text("utf-8"))[
                "project"
            ]["version"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
            raise SyncError(f"cannot read the version from pyproject.toml: {exc}") from exc

        manifest = {
            "commit": commit,
            "ref": ref,
            "version": version,
            "synced_at": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "files": dict(sorted(files.items())),
        }
        (tmp / "SOURCE.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")

        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--denylist", required=True)
    parser.add_argument("--dest", default=str(DEFAULT_DEST))
    args = parser.parse_args(argv)
    try:
        sync(args.source, args.ref, args.denylist, args.dest)
    except (SyncError, OSError) as exc:
        print(f"sync_kernel: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
