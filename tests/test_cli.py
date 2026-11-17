"""AC-4: CLI contract - exit codes, error lines, JSON keys, --from, skipped candidates."""
from __future__ import annotations

import json
import re

import pytest

from conftest import run_subprocess

CHECK_KEYS = {"ecosystem", "range", "policy", "normalized", "human", "notes", "version", "normalized_version",
              "in_interval", "prerelease_gate", "matches", "reason", "explanation"}
BEST_KEYS = {"ecosystem", "range", "policy", "normalized", "candidates", "selected", "matching", "skipped",
             "explanation"}
INTERSECT_KEYS = {"ecosystem", "range", "policy", "normalized", "ranges", "intersection", "overlaps",
                  "explanation"}
EXPLAIN_KEYS = {"ecosystem", "range", "policy", "normalized", "human", "notes", "rule_summary", "explanation"}


def test_a_false_verdict_still_exits_zero(cli):
    code, out, err = cli("check", "npm", "^0.2.3", "0.3.0")
    assert (code, err) == (0, "") and "does NOT match" in out


def test_exit_status_flag_turns_verdicts_into_exit_one(cli):
    assert cli("check", "npm", "^0.2.3", "0.3.0", "--exit-status")[0] == 1
    assert cli("check", "npm", "^0.2.3", "0.2.9", "--exit-status")[0] == 0
    assert cli("best", "npm", "^3", "1.0.0", "--exit-status")[0] == 1
    assert cli("best", "npm", "^1", "1.0.0", "--exit-status")[0] == 0
    assert cli("intersect", "npm", "^0.2.3", "^0.3.0", "--exit-status")[0] == 1
    assert cli("intersect", "npm", "^1", "^1.2", "--exit-status")[0] == 0
    assert cli("explain", "npm", "^1", "--exit-status")[0] == 0


@pytest.mark.parametrize("args,pattern", [
    (("check", "npm", "^1.2.x.y", "1.0.0"), r"^rangewise: error: invalid npm range '\^1\.2\.x\.y': .+"),
    (("check", "npm", ">=1.0", "1.0"), r"^rangewise: error: invalid npm version '1\.0': .+"),
    (("check", "cargo", "", "1.0.0"), r"^rangewise: error: invalid cargo range '': .+"),
    (("check", "pypi", "1.0", "1.0"), r"^rangewise: error: invalid pypi range '1\.0': .+"),
    (("check", "pypi", "~=1", "1.0"), r"invalid pypi range '~=1': ~= needs at least two"),
    (("check", "pypi", ">=1.*", "1.0"), r"invalid pypi range '>=1\.\*': a '\.\*' wildcard"),
    (("check", "pypi", ">=1.0", "not-a-version"), r"invalid pypi version 'not-a-version'"),
    (("check", "maven", "[1.0,2.0", "1.5"), r"invalid maven range '\[1\.0,2\.0': malformed interval"),
    (("check", "maven", "[2.0,1.0]", "1.5"), r"invalid maven range '\[2\.0,1\.0\]': the lower bound is above"),
    (("check", "composer", "^1.0@bogus", "1.0.0"), r"invalid composer range"),
    (("best", "npm", "^1", "--from", "/nonexistent/versions.txt"), r"cannot read candidate file"),
    (("best", "npm", "^1"), r"no candidate versions given"),
    (("best", "npm", "^1", "foo", "bar"), r"none of the candidate versions could be parsed"),
    (("check", "npm", "^1", "1.0.0", "--pre-policy", "install"), r"option --pre-policy applies to pypi only, not to npm"),
    (("check", "pypi", "^1", "1.0.0", "--include-prerelease"), r"--include-prerelease applies to npm/cargo only"),
    (("check", "npm", "^1", "1.0.0", "--minimum-stability", "beta"), r"--minimum-stability applies to composer"),
])
def test_invalid_input_exits_two_with_a_fixing_message(cli, args, pattern):
    code, out, err = cli(*args)
    assert code == 2 and out == ""
    assert re.search(pattern, err, re.M), err


def test_argparse_errors_also_exit_two(cli):
    assert cli("check", "rubygems", "^1", "1.0.0")[0] == 2
    assert cli("check", "npm")[0] == 2
    assert cli("frobnicate")[0] == 2


@pytest.mark.parametrize("eco,rng,feature", [
    ("npm", "workspace:^1.0.0", "workspace:"), ("npm", "file:../local", "file:"), ("npm", "latest", "dist-tag"),
    ("npm", "github:user/repo", "github:"), ("npm", "user/repo", "git or path source"),
    ("pypi", "requests>=2; python_version<'3.11'", "environment marker"),
    ("pypi", "pkg @ https://example.com/pkg.whl", "direct URL reference"),
    ("composer", "dev-main", "branch or alias constraint"), ("composer", "^1.0 as 2.0", "branch or alias constraint"),
    ("composer", "1.0.x-dev", "branch or alias constraint"),
    ("maven", "${project.version}", "property reference ${...}"), ("maven", "LATEST", "meta version LATEST"),
    ("maven", "RELEASE", "meta version RELEASE"),
])
def test_unsupported_forms_exit_three(cli, eco, rng, feature):
    code, out, err = cli("check", eco, rng, "1.0.0")
    first = err.splitlines()[0]
    assert code == 3 and out == ""
    assert first == f"rangewise: unsupported: {feature} in {eco} range '{rng}' — not evaluated"


def test_json_has_the_documented_keys_per_command(cli_json):
    assert CHECK_KEYS <= set(cli_json("check", "npm", "^1", "1.2.3"))
    assert {"applies", "passed", "rule"} == set(cli_json("check", "npm", "^1", "1.2.3")["prerelease_gate"])
    assert "by_policy" in cli_json("check", "pypi", ">=1", "1.0")
    assert BEST_KEYS <= set(cli_json("best", "npm", "^1", "1.2.3"))
    assert INTERSECT_KEYS <= set(cli_json("intersect", "npm", "^1", "^1.2"))
    assert EXPLAIN_KEYS <= set(cli_json("explain", "npm", "^1"))
    interval = cli_json("explain", "npm", "^1")["normalized"][0]
    assert set(interval) == {"lower", "lower_inclusive", "upper", "upper_inclusive"}
    assert cli_json("explain", "npm", "*")["normalized"][0]["upper"] is None  # open end is null


def test_reasons_use_the_fixed_vocabulary(cli_json):
    reasons = {
        cli_json("check", "npm", "^1", "1.2.3")["reason"], cli_json("check", "npm", "^1", "2.0.0")["reason"],
        cli_json("check", "npm", "^1", "1.2.3-beta.1")["reason"],
        cli_json("check", "composer", "^1", "1.2.3-beta1")["reason"], cli_json("check", "maven", "1.0", "1.0")["reason"],
    }
    assert reasons == {"matched", "outside_interval", "excluded_prerelease_gate", "excluded_stability",
                       "soft_requirement"}


def test_from_file_and_stdin(cli_json, cli, tmp_path):
    path = tmp_path / "versions.txt"
    path.write_text("# registry dump\n0.8.4\n\n0.9.0   # stable\n0.9.1-build.4\n", encoding="utf-8")
    out = cli_json("best", "npm", ">=0.9.0", "--from", str(path))
    assert out["candidates"] == ["0.8.4", "0.9.0", "0.9.1-build.4"] and out["selected"] == "0.9.0"
    code, text, _ = cli("best", "npm", "^1", "--from", "-", "--json", stdin="1.0.0\n1.4.0\n2.0.0\n")
    assert code == 0 and json.loads(text)["selected"] == "1.4.0"
    # positional candidates and --from can be combined
    out = cli_json("best", "npm", "^1", "1.9.0", "--from", str(path))
    assert out["candidates"][0] == "1.9.0" and out["selected"] == "1.9.0"


def test_unparseable_candidates_are_skipped_not_fatal(cli_json):
    out = cli_json("best", "npm", "^1", "1.0.0", "banana", "1.5.0")
    assert out["selected"] == "1.5.0"
    assert [s["version"] for s in out["skipped"]] == ["banana"] and out["skipped"][0]["error"]


def test_real_process_exit_codes_and_streams():
    code, out, err = run_subprocess("check", "npm", "^0.2.3", "0.3.0", "--json")
    assert code == 0 and '"matches": false' in out and err == ""
    code, out, err = run_subprocess("check", "npm", "workspace:^1.0.0", "1.0.0")
    assert code == 3 and out == "" and "unsupported" in err
    code, _, err = run_subprocess("check", "npm", "^x.y", "1.0.0")
    assert code == 2 and err.startswith("rangewise: error: invalid npm range")
    code, out, _ = run_subprocess("best", "npm", "^1", "--from", "-", "--exit-status", stdin="2.0.0\n")
    assert code == 1 and "Nothing is picked" in out


def test_version_flag(cli, capsys):
    assert cli("--version")[0] == 0


# --- round 2 regressions: undecodable candidates, huge numbers --------------------------------
def test_non_utf8_candidate_file_exits_two_with_a_hint(cli, tmp_path):
    path = tmp_path / "broken.txt"
    path.write_bytes(b"1.0.0\n\xff\xfe\x80bad\n1.2.0\n")
    code, out, err = cli("best", "npm", "^1", "--from", str(path))
    assert code == 2 and out == ""
    assert err.startswith("rangewise: error:") and "not UTF-8" in err and "Traceback" not in err
    code, _, err = cli("best", "npm", "^1", "--from", str(path), env={"RANGEWISE_LANG": "ko"})
    assert code == 2 and "UTF-8" in err and "저장" in err


def test_non_utf8_stdin_exits_two(rw, capsys):
    def bad_stdin():
        yield "1.0.0\n"
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    code = rw.main(["best", "npm", "^1", "--from", "-"], environ={"RANGEWISE_LANG": "en"}, stdin=bad_stdin())
    assert code == 2 and "not UTF-8" in capsys.readouterr().err


@pytest.mark.parametrize("eco,rng,ver", [
    ("npm", "^1." + "1" * 5000, "1.0.0"),
    ("npm", "^1", "1." + "9" * 5000 + ".0"),
    ("cargo", "^1", "1." + "9" * 5000 + ".0"),
    ("pypi", ">=1", "1." + "9" * 5000),
    ("composer", "^1", "1." + "9" * 5000 + ".0"),
    ("maven", "[1,2)", "1." + "9" * 5000),
])
def test_huge_numbers_are_an_invalid_input_not_a_crash(cli, eco, rng, ver):
    code, out, err = cli("check", eco, rng, ver)
    assert code == 2 and out == ""
    assert err.startswith("rangewise: error: invalid") and "too long" in err


def test_huge_candidate_is_skipped_by_best(cli_json):
    out = cli_json("best", "npm", "^1", "1.2.0", "1." + "9" * 5000 + ".0")
    assert out["selected"] == "1.2.0" and len(out["skipped"]) == 1
