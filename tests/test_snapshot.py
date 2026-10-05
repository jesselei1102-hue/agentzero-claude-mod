import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SRC = ROOT / "plugins/agentzero/kernel/src"
SCRIPT = ROOT / "plugins/agentzero/tools/snapshot.py"
UPGRADE = "this workspace's AgentZero is too old for the HUD; run /agentzero upgrade"


def _env(pythonpath):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pythonpath)
    return env


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "ws"
    subprocess.run(
        [sys.executable, "-m", "adapter", "init", str(workspace), "--harness", "claude"],
        check=True, capture_output=True, env=_env(KERNEL_SRC),
    )
    return workspace


def mem(ws, *args):
    subprocess.run(
        [sys.executable, "-m", "memory", *args],
        check=True, capture_output=True, cwd=ws, env=_env(ws / "src"),
    )


def run_snapshot(ws, pythonpath=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(ws)],
        capture_output=True, env=_env(pythonpath or ws / "src"),
    )


def snapshot(ws, pythonpath=None):
    done = run_snapshot(ws, pythonpath)
    return done.returncode, json.loads(done.stdout.decode("utf-8"))


def test_counts_active_and_lists_pending(ws):
    mem(ws, "remember", "Use pnpm, never npm.", "--said", "Use pnpm, never npm.")
    mem(ws, "propose", "fact", "Never deploy on Fridays.")
    code, snap = snapshot(ws)
    assert code == 0 and snap["schema"] == 1 and "error" not in snap
    assert snap["active"] == 1
    [item] = snap["pending"]
    assert item["id"].startswith("fact:") and item["kind"] == "fact"
    assert item["sentence"] == "Never deploy on Fridays."
    assert item["provenance"] and item["createdAt"][:4].isdigit()


def test_hot_set_time_after_a_load(ws):
    assert snapshot(ws)[1]["hotSet"] is None
    mem(ws, "hot-set", "--scope", "project", "--hints", "deploy")
    hot = snapshot(ws)[1]["hotSet"]
    assert isinstance(hot["at"], str) and hot["at"] and isinstance(hot["factIds"], list)


def test_output_keeps_chinese_as_is(ws):
    mem(ws, "propose", "fact", "周五不部署")
    assert "周五不部署" in run_snapshot(ws).stdout.decode("utf-8")


def test_old_workspace_reports_upgrade(ws, tmp_path):
    (tmp_path / "empty").mkdir()
    code, snap = snapshot(ws, pythonpath=tmp_path / "empty")
    assert code == 0
    assert snap == {"schema": 1, "error": UPGRADE}


def test_missing_workspace_is_an_error_not_a_crash(ws, tmp_path):
    code, snap = snapshot(tmp_path / "nowhere", pythonpath=ws / "src")
    assert code == 0 and isinstance(snap["error"], str)


def test_python_without_pyyaml_says_so(ws, tmp_path):
    fake = tmp_path / "noyaml" / "yaml"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text('raise ImportError("No module named yaml", name="yaml")\n')
    code, snap = snapshot(ws, pythonpath=f"{tmp_path / 'noyaml'}{os.pathsep}{ws / 'src'}")
    assert code == 0
    assert snap == {"schema": 1, "error": "no usable Python 3.11 with PyYAML"}
