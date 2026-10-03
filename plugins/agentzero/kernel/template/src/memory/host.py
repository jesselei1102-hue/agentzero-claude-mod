"""The interpreter this host actually has, and commands spelled with it.

System.md spells every command `python -m …` so the convention stays portable,
but a host may have only `python3` — macOS ships no `python` at all. The Trace
hooks already resolve this at materialize time (SETTLED #38). Instruction files
and printed hints must do the same, or an agent following the rules fails on its
very first command and quietly falls back to reading `memory/` by hand, which is
exactly the degraded mode System rule 3 exists to avoid.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

# `python` as a command word, not inside another name or a path: `PYTHONPATH`,
# `cpython` and `/usr/bin/python` are left alone.
_BARE = re.compile(r"(?<![\w/.-])python(?= -m )")


def interpreter() -> str:
    """`python3` when on PATH, else `python` — the same rule the hooks use."""
    return "python3" if shutil.which("python3") else "python"


def render(text: str, exe: str | None = None) -> str:
    """Spell every `python -m …` command with the interpreter this host has."""
    return _BARE.sub(exe or interpreter(), text)


_LAUNCHED = ("memory", "knowledge", "skills")
"""What `./a0` runs: the packages a workspace uses. `adapter` lives in a framework checkout."""


def command(args: str) -> str:
    """A runnable command line, in the form the System rules use.

    A workspace command goes through `./a0` (SETTLED #71), which picks the workspace's own
    `src/` and a Python with PyYAML; spelled out, 13 of System.md's 15 commands had lost
    their `PYTHONPATH=src`. Framework commands keep the spelled-out form.
    """
    if args.split(" ", 1)[0] in _LAUNCHED:
        return f"./a0 {args}"
    return f"PYTHONPATH=src {interpreter()} -m {args}"


def relay(text: str) -> str:
    """The last line of a write: what the agent says to the operator about it.

    The rules ask the agent to say in one line what a write printed; three of seven
    agents in the test kit did not, while all of them followed what a command told them.
    """
    return f"→ tell the operator, in their language: {text}\n"


def ask(sentence: str, qualified_id: str) -> str:
    """The question an agent puts to the operator about something it proposed."""
    return (
        f'→ ask the operator before this run ends, in their language: "{sentence}" — keep it? '
        f"yes: {command(f'memory review --confirm {qualified_id}')}  "
        f"no: {command(f'memory review --reject {qualified_id}')}\n"
    )


def reminder(line: str | None) -> str:
    return f"→ {line}\n" if line else ""


_PYTHON_CANDIDATES = (
    "python3",
    "python",
    "/usr/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
)


def require_yaml() -> None:
    """Stop with a fix, not a traceback, when this Python has no PyYAML.

    Agent apps ship their own Python (WorkBuddy, Doubao Work), and theirs had no
    PyYAML: every command died in a traceback, and one agent spent a dozen calls
    finding an interpreter that worked. Say which one does, if this machine has one.
    """
    import subprocess
    import sys

    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        return
    lines = [f"AgentZero needs PyYAML, and this Python has none: {sys.executable}"]
    # Compare paths as given, not resolved: a venv's python links to a system binary that
    # does have PyYAML in its own site-packages. The probe below decides, not the path.
    current = Path(sys.executable).absolute()
    for candidate in _PYTHON_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if not found or Path(found).absolute() == current:
            continue
        try:
            probe = subprocess.run(
                [found, "-c", "import yaml"], capture_output=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            lines.append(
                f"  this one has it: run the command through ./a0, which finds it, or as "
                f"PYTHONPATH=src {found} -m ..."
            )
            break
    lines.append(f'  or install it: {sys.executable} -m pip install "pyyaml>=6,<7"')
    message = "\n".join(lines)
    if sys.argv and sys.argv[0] == "-m":  # `python -m memory|knowledge|skills`: a command
        sys.stderr.write(message + "\n")
        raise SystemExit(1)
    raise ModuleNotFoundError(message, name="yaml")


def warn_if_foreign_runtime(workspace: Path, package: str) -> None:
    """Warn when this command runs a copy of AgentZero other than the workspace's own.

    A workspace carries its runtime in `src/`. Run without `PYTHONPATH=src`, `python3 -m`
    finds whatever copy is installed instead — in a real run, a newer one wrote a
    Knowledge id the workspace's own version would not have, and nothing said so.
    """
    import sys

    own = workspace / "src" / package / "__init__.py"
    module = sys.modules.get(package)
    if not own.is_file() or module is None or not module.__file__:
        return
    running = Path(module.__file__).resolve()
    if running == own.resolve():
        return
    sys.stderr.write(
        f"warning: this is AgentZero from {running.parent.parent}, not this workspace's own "
        f"{workspace / 'src'}; run it as ./a0 {package} ... so the workspace's version runs\n"
    )
