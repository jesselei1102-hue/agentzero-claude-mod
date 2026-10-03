"""Hook-written Trace: synthetic MCP/stop payloads → Trace artifact. Never agent self-review."""

from traces.writer import run_is_valid, write_trace

__all__ = [
    "run_is_valid",
    "write_trace",
]
