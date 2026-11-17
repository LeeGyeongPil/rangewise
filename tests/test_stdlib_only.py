"""AC-6: the skill script uses only the standard library, parses as Python 3.10, and starts fast."""
from __future__ import annotations

import ast
import sys
import time

from conftest import SCRIPT, run_subprocess


def test_only_standard_library_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            imported.add((node.module or "").split(".")[0])
    stdlib = set(sys.stdlib_module_names)
    assert imported <= stdlib, imported - stdlib


def test_source_parses_as_python_3_10():
    ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 10))


def test_no_network_or_process_modules():
    imported = {n.names[0].name for n in ast.walk(ast.parse(SCRIPT.read_text())) if isinstance(n, ast.Import)}
    assert not imported & {"socket", "subprocess", "urllib", "http", "ssl"}


def test_start_command_is_fast_and_correct():
    started = time.perf_counter()
    code, out, err = run_subprocess("check", "npm", "^0.2.3", "0.3.0", "--json")
    elapsed = time.perf_counter() - started
    assert code == 0 and '"matches": false' in out and err == ""
    assert elapsed < 1.0, elapsed


def test_help_works_for_every_command():
    for args in (("--help",), ("check", "--help"), ("best", "--help"), ("intersect", "--help"), ("explain", "--help")):
        code, out, _ = run_subprocess(*args)
        assert code == 0 and "usage:" in out
