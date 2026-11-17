"""AC-2: prerelease and stability rules per ecosystem."""
from __future__ import annotations

import pytest


def test_npm_gate_headline_case(cli_json):
    out = cli_json("check", "npm", ">=0.9.0", "0.9.1-build.4")
    assert out["in_interval"] is True
    assert out["prerelease_gate"]["passed"] is False
    assert out["matches"] is False
    assert out["reason"] == "excluded_prerelease_gate"


def test_npm_gate_opens_with_same_tuple_prerelease_comparator(cli_json):
    assert cli_json("check", "npm", ">=0.9.1-build.1", "0.9.1-build.4")["matches"] is True
    assert cli_json("check", "npm", ">=0.9.0-0", "0.9.1-build.4")["matches"] is False


def test_npm_include_prerelease_skips_the_gate(cli_json):
    out = cli_json("check", "npm", ">=0.9.0", "0.9.1-build.4", "--include-prerelease")
    assert out["matches"] is True
    assert out["prerelease_gate"]["applies"] is False
    assert out["policy"] == "npm-include-prerelease"


def test_npm_gate_is_per_and_set(cli_json):
    # the prerelease comparator sits in the other OR branch, so it must not open the gate
    assert cli_json("check", "npm", ">=1.2.3-beta.1 <1.2.3 || >=1.0.0 <1.2.0", "1.2.3-beta.2")["matches"] is True
    assert cli_json("check", "npm", ">=1.0.0 <1.3.0 || 1.2.3-alpha.1", "1.2.3-beta.2")["matches"] is False


def test_cargo_gate(cli_json):
    out = cli_json("check", "cargo", "1.0", "1.2.0-alpha")
    assert out["in_interval"] is True and out["matches"] is False
    assert cli_json("check", "cargo", "1.0", "1.0.0-alpha")["in_interval"] is False  # sorts below 1.0.0
    assert cli_json("check", "cargo", "1.0.0-alpha", "1.0.0-beta")["matches"] is True
    assert cli_json("check", "cargo", "1.0", "1.2.0-alpha", "--include-prerelease")["matches"] is True


def test_pypi_policies_differ_on_exactly_the_documented_case(cli_json):
    out = cli_json("check", "pypi", ">=1.0", "2.0b1")
    assert out["policy"] == "pypi-install"
    assert out["by_policy"] == {"install": False, "membership": True}
    assert out["matches"] is False
    assert out["prerelease_gate"] == {"applies": True, "passed": False, "rule": "pypi_install"}
    out = cli_json("check", "pypi", ">=1.0", "2.0b1", "--pre-policy", "membership")
    assert out["matches"] is True and out["policy"] == "pypi-membership"
    assert out["prerelease_gate"]["applies"] is False


def test_pypi_install_opens_when_the_specifier_names_a_prerelease(cli_json):
    assert cli_json("check", "pypi", ">=1.0b1", "2.0b1")["matches"] is True
    assert cli_json("check", "pypi", "==1.4.*", "1.4.0rc1")["matches"] is False
    assert cli_json("check", "pypi", "==1.4.*", "1.4.0rc1", "--pre-policy", "membership")["matches"] is True


def test_pypi_exclusive_comparison_rules(cli_json):
    assert cli_json("check", "pypi", ">1.5", "1.5.post1")["matches"] is False
    assert cli_json("check", "pypi", "<1.5", "1.5.0a1", "--pre-policy", "membership")["matches"] is False
    assert cli_json("check", "pypi", "==1.0", "1.0+local.7")["matches"] is True
    assert cli_json("check", "pypi", "==1.0+local.7", "1.0")["matches"] is False


def test_pypi_alternate_prerelease_spellings_normalize(cli_json):
    out = cli_json("check", "pypi", "==2.0.0-beta.1", "2.0b1", "--pre-policy", "membership")
    assert out["matches"] is True and out["normalized_version"] == "2.0b1"


@pytest.mark.parametrize("floor,version,expected", [
    ("stable", "1.5.0-beta1", False), ("RC", "1.5.0-RC1", True), ("RC", "1.5.0-beta1", False),
    ("beta", "1.5.0-beta1", True), ("alpha", "1.5.0-alpha1", True), ("dev", "1.5.0-dev", True),
])
def test_composer_minimum_stability(cli_json, floor, version, expected):
    out = cli_json("check", "composer", "^1.0", version, "--minimum-stability", floor)
    assert out["matches"] is expected
    if not expected:
        assert out["in_interval"] is True and out["reason"] == "excluded_stability"


def test_composer_flag_lowers_the_floor_for_that_constraint(cli_json):
    out = cli_json("check", "composer", "^1.0@beta", "1.5.0-beta1")
    assert out["matches"] is True
    assert out["notes"], "the lowered stability floor should be explained"
    assert cli_json("check", "composer", "^1.0@beta", "1.5.0-alpha1")["matches"] is False


def test_composer_suffix_in_the_constraint_names_the_stability(cli_json):
    assert cli_json("check", "composer", ">=1.0.0-beta1", "1.0.0-beta2")["matches"] is True


def test_maven_has_no_gate_and_snapshot_sorts_before_release(cli_json):
    out = cli_json("check", "maven", "[1.0,2.0)", "2.0-rc1")
    assert out["matches"] is True
    assert out["prerelease_gate"] == {"applies": False, "passed": True, "rule": "maven_none"}
    assert cli_json("check", "maven", "[1.0,)", "1.0-SNAPSHOT")["matches"] is False
    assert cli_json("check", "maven", "(,1.0]", "1.0-SNAPSHOT")["matches"] is True
