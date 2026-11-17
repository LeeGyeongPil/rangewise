"""Shared helpers: load the skill script as a module and run it like a user would."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "rangewise" / "scripts" / "rangewise.py"
DATA = Path(__file__).resolve().parent / "data"


def _load():
    spec = importlib.util.spec_from_file_location("rangewise", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rangewise"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def rw():
    return _load()


def load_data(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture()
def cli(rw, capsys):
    """Run main() in-process: returns (exit_code, stdout, stderr). Language comes from env only."""

    def run(*args: str, env: dict | None = None, stdin: str | None = None):
        environ = {"RANGEWISE_LANG": "en"} if env is None else env
        code = rw.main(list(args), environ=environ, stdin=io.StringIO(stdin or ""))
        out = capsys.readouterr()
        return code, out.out, out.err

    return run


@pytest.fixture()
def cli_json(cli):
    def run(*args: str, env: dict | None = None):
        code, out, err = cli(*args, "--json", env=env)
        assert code == 0, err
        return json.loads(out)

    return run


def run_subprocess(*args: str, env: dict | None = None, stdin: str | None = None):
    """The real thing: a fresh interpreter, a clean environment (only what the test passes)."""
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          input=stdin, env=env if env is not None else {"RANGEWISE_LANG": "en"}, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr
