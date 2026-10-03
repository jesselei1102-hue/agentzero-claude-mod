"""Draft an unsigned Answer key from MCP-shaped YAML (or a fixture of the same shape)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from score.yamlio import load_mapping


def draft_answer_key(source: Path, destination: Path) -> None:
    """Write unsigned Answer key rows. The draft is not valid for scored runs."""
    payload = load_mapping(source)
    observations = payload.get("observations") or []
    items = [_draft_item(row) for row in observations]
    drafted = {"model": payload.get("model"), "items": items}
    destination.write_text(yaml.safe_dump(drafted, sort_keys=False), encoding="utf-8")


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: python -m score.draft SOURCE DEST")
    draft_answer_key(Path(args[0]), Path(args[1]))


def _draft_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "category": row["category"],
        "hold_out": bool(row.get("hold_out", False)),
        "observed": row["observed"],
        "result": row["result"],
        "signed_off": False,
    }


if __name__ == "__main__":
    main()
