"""AC-3: best (maxSatisfying / pip pick), intersect (node-semver intersects) and explain."""
from __future__ import annotations

from conftest import load_data

NPM = load_data("npm_cases.json")
PYPI = load_data("pypi_cases.json")


def test_best_matches_node_semver_max_satisfying(rw):
    assert len(NPM["max_satisfying"]) >= 30
    wrong = [c for c in NPM["max_satisfying"]
             if rw.cmd_best("npm", c["range"], c["versions"], rw.Options())[0]["selected"] != c["selected"]]
    assert not wrong, wrong[:3]


def test_best_install_policy_matches_packaging_filter(rw):
    """packaging 26 filter(): final releases first, prereleases only as a fallback = pip's pick."""
    assert len(PYPI["filter_pip"]) >= 30
    wrong = []
    for c in PYPI["filter_pip"]:
        out = rw.cmd_best("pypi", c["range"], c["versions"], rw.Options(pre_policy="install"))[0]
        key = rw.Pep440.parse
        want = max(c["filter"], key=key) if c["filter"] else None
        if out["selected"] != want or sorted(out["matching"], key=key) != sorted(c["filter"], key=key):
            wrong.append(c)
    assert not wrong, wrong[:3]


def test_best_pypi_documented_examples(cli_json):
    out = cli_json("best", "pypi", ">=1.0", "1.0", "1.1", "2.0b1")
    assert out["selected"] == "1.1" and out["matching"] == ["1.0", "1.1"]
    assert out["by_policy"] == {"install": "1.1", "membership": "2.0b1"}
    out = cli_json("best", "pypi", ">=1.5", "1.0", "2.0b1")
    assert out["selected"] == "2.0b1"  # only a prerelease satisfies, pip falls back to it
    assert out["by_policy"]["membership"] == "2.0b1"


def test_best_membership_policy_picks_the_highest_member(cli_json):
    out = cli_json("best", "pypi", ">=1.0", "1.0", "1.1", "2.0b1", "--pre-policy", "membership")
    assert out["selected"] == "2.0b1" and out["policy"] == "pypi-membership"


def test_best_maven_picks_the_rc(cli_json):
    out = cli_json("best", "maven", "[1.0,2.0)", "1.5", "2.0-rc1", "2.0")
    assert out["selected"] == "2.0-rc1" and out["matching"] == ["1.5", "2.0-rc1"]


def test_best_maven_soft_requirement_prefers_the_named_version(cli_json):
    out = cli_json("best", "maven", "1.0", "0.9", "1.0.0", "2.0")
    assert out["selected"] == "1.0.0"
    assert any("soft" in n.lower() for n in out["notes"])


def test_best_npm_prerelease_pick_headline(cli_json):
    out = cli_json("best", "npm", ">=0.9.0", "0.8.4", "0.9.0", "0.9.1-build.4")
    assert out["selected"] == "0.9.0" and out["candidates"] == ["0.8.4", "0.9.0", "0.9.1-build.4"]


def test_best_cargo_and_composer(cli_json):
    assert cli_json("best", "cargo", "0.2.3", "0.2.9", "0.3.0", "1.0.0")["selected"] == "0.2.9"
    out = cli_json("best", "composer", "~1.2", "1.2.0", "1.9.9", "2.0.0", "2.0.0-RC1")
    assert out["selected"] == "1.9.9"


def test_best_without_a_match_selects_none(cli_json):
    out = cli_json("best", "npm", "^3", "1.0.0", "2.0.0")
    assert out["selected"] is None and out["matching"] == []


def test_intersect_matches_node_semver_intersects(rw):
    assert len(NPM["intersects"]) >= 30
    wrong = [(a, b, want) for a, b, want in NPM["intersects"]
             if rw.cmd_intersect("npm", a, b, rw.Options())[0]["overlaps"] != want]
    assert not wrong, wrong[:5]


def test_intersect_headline_conflict(cli_json):
    out = cli_json("intersect", "npm", "^0.2.3", "^0.3.0")
    assert out["overlaps"] is False and out["intersection"] == []
    assert [r["range"] for r in out["ranges"]] == ["^0.2.3", "^0.3.0"]
    first, second = (r["normalized"][0] for r in out["ranges"])
    assert (first["lower"], first["upper"]) == ("0.2.3", "0.3.0-0")
    assert (second["lower"], second["upper"]) == ("0.3.0", "0.4.0-0")


def test_intersect_shows_the_shared_interval(cli_json):
    out = cli_json("intersect", "composer", "~1.2", "^1.3")
    assert out["overlaps"] is True
    assert out["intersection"][0]["lower"] == "1.3.0" and out["intersection"][0]["upper"] == "2.0.0-dev"


def test_intersect_pypi_maven_cargo(cli_json):
    assert cli_json("intersect", "pypi", "~=1.4", ">=2")["overlaps"] is False
    assert cli_json("intersect", "pypi", "~=1.4", ">=1.6,!=1.7.*")["overlaps"] is True
    assert cli_json("intersect", "maven", "[1.0,2.0)", "[2.0,3.0)")["overlaps"] is False
    assert cli_json("intersect", "maven", "[1.0,2.0]", "[2.0,3.0)")["overlaps"] is True
    assert cli_json("intersect", "cargo", "^1.2", "~1.4")["overlaps"] is True


def test_explain_npm_zero_zero_caret(cli_json):
    out = cli_json("explain", "npm", "^0.0")
    assert out["normalized"] == [{"lower": "0.0.0", "lower_inclusive": True,
                                  "upper": "0.1.0-0", "upper_inclusive": False}]
    assert out["human"] == [">=0.0.0 <0.1.0"]
    assert "0.1.0-0" in out["explanation"]


def test_explain_composer_tilde(cli_json):
    out = cli_json("explain", "composer", "~1.2")
    assert out["normalized"][0]["upper"] == "2.0.0-dev"
    assert out["human"] == [">=1.2.0 <2.0.0"]
    assert out["rule_summary"].startswith("composer:")


def test_explain_pypi_compatible_release_and_union(cli_json):
    assert cli_json("explain", "pypi", "~=1.4")["human"] == [">=1.4 <2"]
    assert cli_json("explain", "pypi", "~=1.4.2")["human"] == [">=1.4.2 <1.5"]
    assert cli_json("explain", "pypi", "!=1.4.*")["human"] == ["<1.4", ">=1.5"]
    assert cli_json("explain", "maven", "(,1.0],[1.2,)")["human"] == ["<=1.0", ">=1.2"]
    assert cli_json("explain", "npm", "1.2.3 - 2.3 || >=3.1.0-beta.1")["human"] == [
        ">=1.2.3 <2.4.0", ">=3.1.0-beta.1"]


def test_explain_text_mentions_rule_and_exact_bounds(cli):
    code, out, _ = cli("explain", "npm", "^0.2.3")
    assert code == 0
    assert "[0.2.3, 0.3.0-0)" in out and "Rule:" in out
