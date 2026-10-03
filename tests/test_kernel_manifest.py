import hashlib
import json
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[1] / "plugins/agentzero/kernel"


def test_kernel_matches_its_manifest():
    files = json.loads((KERNEL / "SOURCE.json").read_text())["files"]
    on_disk = {
        p.relative_to(KERNEL).as_posix()
        for p in KERNEL.rglob("*")
        if p.is_file() and p.name != "SOURCE.json"
    }
    assert on_disk - set(files) == set(), "files the manifest does not name"
    assert set(files) - on_disk == set(), "manifest names missing files"
    for rel, digest in files.items():
        assert hashlib.sha256((KERNEL / rel).read_bytes()).hexdigest() == digest, rel
