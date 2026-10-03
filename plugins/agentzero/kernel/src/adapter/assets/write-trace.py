#!/usr/bin/env python3
"""Harness adapter entry: forward hook stdin to traces.hook.

Fails open to the harness — a broken hook must never break the operator's
session — but leaves a breadcrumb, because silence is what let a workspace with
no runtime packages look installed while recording nothing (SETTLED #18.1/#25).
"""
from __future__ import annotations

import runpy
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
BREADCRUMB = ROOT / "memory" / "traces" / ".hook-error.log"
MAX_LOG_BYTES = 64_000

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _breadcrumb(exc: BaseException) -> None:
    """Record why the hook failed. Must never raise out of the hook itself."""
    try:
        BREADCRUMB.parent.mkdir(parents=True, exist_ok=True)
        # A broken hook fires on every event, so keep the log bounded.
        if BREADCRUMB.exists() and BREADCRUMB.stat().st_size > MAX_LOG_BYTES:
            BREADCRUMB.write_text("(truncated)\n", encoding="utf-8")
        stamp = datetime.now(UTC).isoformat()
        entry = (
            f"{stamp}\tinterpreter={sys.executable}\tsrc={SRC}\n"
            f"\t{type(exc).__name__}: {exc}\n"
            + "".join("\t" + line for line in traceback.format_exc().splitlines(keepends=True))
            + "\n"
        )
        with BREADCRUMB.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except Exception:  # the hook must stay silent toward the harness
        pass


try:
    runpy.run_module("traces.hook", run_name="__main__")
except Exception as exc:  # fail open to the harness, but never silently
    _breadcrumb(exc)
    print("{}", flush=True)
