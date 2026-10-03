"""Knowledge: the reference material a workspace declares in `knowledge.yaml` (SETTLED #19)."""

# Before anything imports yaml: a Python without PyYAML gets a fix, not a traceback.
from memory.host import require_yaml

require_yaml()

from knowledge.sources import (
    TYPES,
    Added,
    Reach,
    Source,
    add_source,
    forget_source,
    load_sources,
    reach,
)

__all__ = [
    "TYPES", "Added", "Reach", "Source", "add_source", "forget_source", "load_sources", "reach",
]
