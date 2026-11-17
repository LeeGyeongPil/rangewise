"""AC-8: the evaluation set has the required shape, and every task grader matches the *real* script output.

The graders look at result.json (written by redirecting `--json`) or at the script's own error line, so a
stand-in script that prints nothing cannot pass them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import ROOT, run_subprocess

EVALS = ROOT / "evals"


def _front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head = text.split("---\n")[1]
    out = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---\n", 2)[2].strip()


def _cases(prefix: str):
    return sorted(p for p in EVALS.iterdir() if p.is_dir() and p.name.startswith(prefix))


def test_composition():
    trig, near, far = _cases("trigger-"), _cases("notrigger-near-"), [
        p for p in _cases("notrigger-") if not p.name.startswith("notrigger-near-")]
    tasks, errors = _cases("task-"), _cases("task-error-")
    assert len(trig) >= 10 and len(near) >= 5 and len(near) + len(far) >= 10
    assert len(tasks) >= 5 and len(errors) >= 1
    korean = [p for p in trig if re.search(r"[가-힣]", _body(p / "prompt.md"))]
    assert len(korean) >= 2


def test_trigger_prompts_do_not_name_the_skill():
    for case in _cases("trigger-"):
        body = _body(case / "prompt.md")
        assert not re.search(r"rangewise|\bskill\b", body, re.I), case.name
        grader = _front(case / "graders" / "skill-fired.md")
        assert grader["tool"] == "Skill" and grader["arm"] == "both" and "rangewise" in grader["input_match"]


def test_notrigger_graders_forbid_any_skill_call():
    for case in _cases("notrigger-"):
        grader = _front(case / "graders" / "skill-not-fired.md")
        assert grader["tool"] == "Skill" and grader["max"] == "0" and grader["arm"] == "both"


def test_prompts_respect_the_turn_budget():
    for case in EVALS.iterdir():
        if case.name != "fixtures" and case.is_dir():
            assert _front(case / "prompt.md")["max_turns"] == "6", case.name


def test_every_task_has_fixture_script_grader_and_exact_value_regex():
    for case in _cases("task-"):
        assert (EVALS / "fixtures" / case.name).is_dir(), case.name
        ran = _front(case / "graders" / "script-ran.md")
        assert ran["tool"] == "Bash" and ran["arm"] == "with-only" and "rangewise" in ran["input_match"]
        regexes = [g for g in (case / "graders").glob("*.md") if g.name != "script-ran.md"]
        assert regexes, case.name
        for g in regexes:
            fm = _front(g)
            assert fm["type"] == "regex" and len(fm["pattern"]) >= 12, g
            re.compile(fm["pattern"])


# case -> (command arguments built from the fixture, where the graders look)
def _arg_sets():
    fx = EVALS / "fixtures"
    read = lambda case, name: (fx / case / name).read_text(encoding="utf-8")  # noqa: E731
    versions = lambda case, name: [v for v in read(case, name).split() if v]  # noqa: E731
    pkg = json.loads(read("task-npm-prerelease-pick", "package.json"))["dependencies"]["@acme/core"]
    serde = re.search(r'serde = "([^"]+)"', read("task-cargo-bare-version", "Cargo.toml")).group(1)
    widget = re.search(r"widget(\S+)", read("task-pypi-pip-pick", "requirements.txt")).group(1)
    tilde = json.loads(read("task-composer-tilde-upper", "composer.json"))["require"]["vendor/lib"]
    pom = re.search(r"<version>([^<]+)</version>", read("task-maven-range-pick", "pom.xml")).group(1)
    a = json.loads(read("task-npm-range-conflict", "packages/a/package.json"))["dependencies"]["shared"]
    b = json.loads(read("task-npm-range-conflict", "packages/b/package.json"))["dependencies"]["shared"]
    return {
        "task-npm-prerelease-pick": ("npm", pkg, *versions("task-npm-prerelease-pick", "registry-versions.txt")),
        "task-cargo-bare-version": ("cargo", serde, *versions("task-cargo-bare-version", "crate-versions.txt")),
        "task-pypi-pip-pick": ("pypi", widget, *versions("task-pypi-pip-pick", "widget-versions.txt")),
        "task-maven-range-pick": ("maven", pom, *versions("task-maven-range-pick", "maven-versions.txt")),
        "task-composer-tilde-upper": ("composer", tilde),
        "task-npm-range-conflict": ("npm", a, b),
    }


@pytest.mark.parametrize("case", sorted(_arg_sets()))
def test_task_prompts_inline_their_fixture_data(case):
    """The no-skill baseline must be able to answer inside max_turns (6).

    So every range and candidate version the script would read from the fixture is also written in the
    prompt (no file-reading round trips needed), and the prompt says there is no network, so the baseline
    does not spend its turns trying to install or query packaging tools.
    """
    _eco, *values = _arg_sets()[case]
    body = _body(EVALS / case / "prompt.md")
    for value in values:
        assert value in body, (case, value)
    assert "no network access" in body, case


def test_error_task_prompt_inlines_the_expression_and_bounds_the_search():
    case = "task-error-maven-property"
    pom = (EVALS / "fixtures" / case / "pom.xml").read_text(encoding="utf-8")
    expr = re.search(r"<version>([^<]+)</version>", pom).group(1)
    body = _body(EVALS / case / "prompt.md")
    assert expr in body and "1.4.2" in body and "no network access" in body


@pytest.mark.parametrize("case", sorted(_arg_sets()))
def test_task_graders_match_the_real_script_output(case):
    eco, *rest = _arg_sets()[case]
    command = {"task-composer-tilde-upper": "explain", "task-npm-range-conflict": "intersect"}.get(case, "best")
    code, out, err = run_subprocess(command, eco, *rest, "--json")
    assert code == 0, err
    for grader in (EVALS / case / "graders").glob("*.md"):
        if grader.name != "script-ran.md":
            pattern = _front(grader)["pattern"]
            assert re.search(pattern, out), (case, grader.name, pattern)


@pytest.mark.parametrize("case", sorted(_arg_sets()))
def test_task_graders_reject_a_stand_in_output(case):
    """A script that prints nothing, or plausible hand-written JSON, must not satisfy the graders."""
    guess = json.dumps({"selected": "1.1", "overlaps": False, "upper": "2.0.0"})
    patterns = [_front(g)["pattern"] for g in (EVALS / case / "graders").glob("*.md") if g.name != "script-ran.md"]
    assert not any(re.search(p, "") for p in patterns)
    # at least one grader needs the script's own value shape (key order, internal bounds, policy names)
    assert not all(re.search(p, guess) for p in patterns), case


def test_error_task_reports_the_unsupported_line():
    case = "task-error-maven-property"
    pom = (EVALS / "fixtures" / case / "pom.xml").read_text(encoding="utf-8")
    expr = re.search(r"<version>([^<]+)</version>", pom).group(1)
    code, out, err = run_subprocess("check", "maven", expr, "1.4.2")
    grader = _front(EVALS / case / "graders" / "unsupported-line.md")
    assert grader["target"] == "trace" and code == 3 and out == ""
    assert re.search(grader["pattern"], err)
