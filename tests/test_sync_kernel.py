import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_kernel.py"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def make_source(tmp_path):
    src = tmp_path / "az"
    (src / "src/adapter").mkdir(parents=True)
    (src / "template/memory/traces").mkdir(parents=True)
    (src / "src/adapter/x.py").write_text("print('x')\n")
    (src / "template/System.md").write_text("# System\nhello secretword here\n")
    (src / "template/memory/traces/.gitkeep").write_text("")
    (src / "template/memory/traces/run.yaml").write_text("a: 1\n")
    (src / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    (src / "LICENSE").write_text("MIT\n")
    git(src, "init", "-q")
    git(src, "config", "user.email", "t@example.com")
    git(src, "config", "user.name", "t")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "init")
    (src / "src/dirty.py").write_text("dirty\n")
    return src


def run(src, dest, denylist, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(src), "--denylist", str(denylist),
         "--dest", str(dest), *extra],
        capture_output=True, text=True,
    )


def setup(tmp_path, deny="# comment\nnothingmatches\n"):
    src = make_source(tmp_path)
    denylist = tmp_path / "deny.txt"
    denylist.write_text(deny)
    return src, tmp_path / "kernel", denylist


def test_copies_the_four_items_from_the_ref(tmp_path):
    src, dest, deny = setup(tmp_path)
    r = run(src, dest, deny)
    assert r.returncode == 0, r.stderr
    for rel in ["src/adapter/x.py", "template/System.md", "pyproject.toml", "LICENSE"]:
        assert (dest / rel).is_file(), rel


def test_uncommitted_work_is_not_copied(tmp_path):
    src, dest, deny = setup(tmp_path)
    assert run(src, dest, deny).returncode == 0
    assert not (dest / "src/dirty.py").exists()


def test_trace_content_is_skipped_but_gitkeep_kept(tmp_path):
    src, dest, deny = setup(tmp_path)
    assert run(src, dest, deny).returncode == 0
    assert (dest / "template/memory/traces/.gitkeep").exists()
    assert not (dest / "template/memory/traces/run.yaml").exists()


def test_manifest_names_every_file_with_its_hash(tmp_path):
    src, dest, deny = setup(tmp_path)
    assert run(src, dest, deny).returncode == 0
    m = json.loads((dest / "SOURCE.json").read_text())
    assert m["version"] == "9.9.9"
    assert m["commit"] == git(src, "rev-parse", "HEAD")
    assert m["ref"] == "HEAD"
    assert m["synced_at"]
    on_disk = {
        p.relative_to(dest).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and p.name != "SOURCE.json"
    }
    assert set(m["files"]) == on_disk
    for rel, digest in m["files"].items():
        assert hashlib.sha256((dest / rel).read_bytes()).hexdigest() == digest


def test_a_denylisted_term_fails_and_keeps_the_old_copy(tmp_path):
    src, dest, deny = setup(tmp_path, deny="SecretWord\n")
    dest.mkdir()
    (dest / "old.txt").write_text("old")
    r = run(src, dest, deny)
    assert r.returncode == 1
    assert r.stderr.strip()
    assert (dest / "old.txt").read_text() == "old"
    assert not (dest / "src").exists()


def test_a_second_sync_replaces_the_old_copy(tmp_path):
    src, dest, deny = setup(tmp_path)
    (src / "src/adapter/y.py").write_text("print('y')\n")
    git(src, "add", "src/adapter/y.py")
    git(src, "commit", "-q", "-m", "add y")
    assert run(src, dest, deny).returncode == 0
    assert (dest / "src/adapter/x.py").exists()
    git(src, "rm", "-q", "src/adapter/x.py")
    git(src, "commit", "-q", "-m", "drop x")
    assert run(src, dest, deny).returncode == 0
    assert not (dest / "src/adapter/x.py").exists()
