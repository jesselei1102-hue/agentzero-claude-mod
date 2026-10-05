"""Print AgentZero's memory state as one line of JSON, for the plugin's HUD.

usage: python snapshot.py WORKSPACE   (with PYTHONPATH=WORKSPACE/src)

It reads through the workspace's own AgentZero modules and writes nothing. It always
exits 0: a failure is reported in the JSON as {"schema": 1, "error": "..."}.
"""
import datetime
import json
import re
import sys
from pathlib import Path

UPGRADE = "this workspace's AgentZero is too old for the HUD; run /agentzero upgrade"
NO_PYTHON = "no usable Python 3.11 with PyYAML"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _hot_set(memory_dir: Path):
    import yaml

    try:
        state = yaml.safe_load((memory_dir / "traces" / "hot-set.last").read_text("utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(state, dict):
        return None
    at = state.get("at")
    if isinstance(at, (datetime.date, datetime.datetime)):
        at = at.isoformat()
    ids = state.get("fact_ids")
    return {
        "at": str(at) if at else None,
        "factIds": [str(i) for i in ids] if isinstance(ids, list) else [],
    }


def snapshot(workspace: Path) -> dict:
    # The plugin may have found a Python that is too old or lacks PyYAML; say that, not "upgrade".
    try:
        import yaml  # noqa: F401
    except ImportError:
        return {"schema": 1, "error": NO_PYTHON}
    if sys.version_info < (3, 11):
        return {"schema": 1, "error": NO_PYTHON}
    try:
        from memory.lifecycle import live_fact_ids
        from memory.review import collect_pending
    except ImportError as exc:
        if (exc.name or "").startswith("memory"):
            return {"schema": 1, "error": UPGRADE}
        raise

    if not (workspace / "memory").is_dir():
        return {"schema": 1, "error": f"no memory/ directory under {workspace}"}
    memory_dir = workspace / "memory"
    pending = collect_pending(workspace)
    pending_facts = {item.id for item in pending if item.kind == "fact"}
    return {
        "schema": 1,
        "active": len(live_fact_ids(memory_dir) - pending_facts),
        "pending": [
            {
                "id": item.qualified_id,
                "kind": item.kind,
                "sentence": item.sentence,
                "provenance": item.provenance,
                "createdAt": str(item.sort_key) if _DATE.match(str(item.sort_key)) else None,
            }
            for item in pending
        ],
        "hotSet": _hot_set(memory_dir),
    }


def main(argv: list[str]) -> int:
    try:
        if len(argv) != 1:
            raise ValueError("usage: snapshot.py WORKSPACE")
        result = snapshot(Path(argv[0]))
    except Exception as exc:  # the HUD shows the reason; it must never crash
        message = f"{type(exc).__name__}: {exc}".splitlines()[0]
        result = {"schema": 1, "error": message}
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
