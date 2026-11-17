"""Writes tests/data/{cargo,composer,maven}_cases.json.

These three ecosystems have no reference implementation installed here, so every expectation is
derived by hand from an official document (the URL of each case is stored next to it, checked
2026-11-17). Edit the tables below and re-run:

    python tools/refgen/doc_cases.py tests/data
"""
import json
import sys
from pathlib import Path

CARGO = "https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html"
SEMVER_CRATE = "https://docs.rs/semver/latest/semver/struct.VersionReq.html"
COMPOSER = "https://getcomposer.org/doc/articles/versions.md"
MAVEN_POM = "https://maven.apache.org/pom.html#dependency-version-requirement-specification"
MAVEN_ORDER = "https://maven.apache.org/pom.html#version-order-specification"

# (range, version, matches, source)   Cargo: bare version = caret, comma = AND, pre-releases gated.
CARGO_CASES = [
    # caret requirements and the bare form
    ("1.2.3", "1.2.3", True, CARGO), ("1.2.3", "1.9.0", True, CARGO), ("1.2.3", "2.0.0", False, CARGO),
    ("1.2.3", "1.2.2", False, CARGO), ("^1.2.3", "1.2.3", True, CARGO), ("^1.2", "1.99.0", True, CARGO),
    ("^1.2", "2.0.0", False, CARGO), ("^1.2", "1.1.9", False, CARGO), ("^1", "1.0.0", True, CARGO),
    ("^1", "2.0.0", False, CARGO), ("^1", "0.9.9", False, CARGO), ("^0.2.3", "0.2.9", True, CARGO),
    ("^0.2.3", "0.3.0", False, CARGO), ("0.2.3", "0.3.0", False, CARGO), ("^0.2", "0.2.99", True, CARGO),
    ("^0.2", "0.3.0", False, CARGO), ("^0.0.3", "0.0.3", True, CARGO), ("^0.0.3", "0.0.4", False, CARGO),
    ("^0.0.3", "0.0.2", False, CARGO), ("^0.0", "0.0.9", True, CARGO), ("^0.0", "0.1.0", False, CARGO),
    ("^0", "0.9.9", True, CARGO), ("^0", "1.0.0", False, CARGO),
    # tilde requirements
    ("~1.2.3", "1.2.9", True, CARGO), ("~1.2.3", "1.3.0", False, CARGO), ("~1.2.3", "1.2.2", False, CARGO),
    ("~1.2", "1.2.0", True, CARGO), ("~1.2", "1.3.0", False, CARGO), ("~1", "1.9.9", True, CARGO),
    ("~1", "2.0.0", False, CARGO),
    # wildcard requirements
    ("*", "0.0.0", True, CARGO), ("*", "99.0.0", True, CARGO), ("1.*", "1.9.9", True, CARGO),
    ("1.*", "2.0.0", False, CARGO), ("1.*", "0.9.9", False, CARGO), ("1.2.*", "1.2.9", True, CARGO),
    ("1.2.*", "1.3.0", False, CARGO),
    # comparison requirements (partial versions follow the semver crate)
    (">= 1.2.0", "1.2.0", True, CARGO), (">= 1.2.0", "1.1.9", False, CARGO), ("> 1", "1.9.9", False, SEMVER_CRATE),
    ("> 1", "2.0.0", True, SEMVER_CRATE), ("< 2", "1.9.9", True, CARGO), ("< 2", "2.0.0", False, CARGO),
    ("= 1.2.3", "1.2.3", True, CARGO), ("= 1.2.3", "1.2.4", False, CARGO), (">=1.2, <1.5", "1.4.9", True, CARGO),
    (">=1.2, <1.5", "1.5.0", False, CARGO), (">=1.2, <1.5", "1.1.9", False, CARGO),
    ("<=1.2", "1.2.9", True, SEMVER_CRATE), ("<=1.2", "1.3.0", False, SEMVER_CRATE),
    # pre-release section
    ("1.0", "1.0.0-alpha", False, CARGO), ("1.0.0-alpha", "1.0.0-alpha", True, CARGO),
    ("1.0.0-alpha", "1.0.0-beta", True, CARGO), ("1.0.0-alpha", "1.0.0", True, CARGO),
    ("1.0.0-alpha", "1.2.0", True, CARGO), ("1.0.0-alpha", "1.0.1-alpha", False, CARGO),
    ("1.0.0-alpha", "1.0.1-beta", False, CARGO), ("^1.2.3-beta.2", "1.2.3-beta.4", True, CARGO),
    ("^1.2.3-beta.2", "1.2.4-beta.2", False, CARGO), ("^1.2.3-beta.2", "1.2.4", True, CARGO),
]

# (range, version, matches, minimum_stability or None, source)
COMPOSER_CASES = [
    ("1.0.2", "1.0.2", True, None, COMPOSER), ("1.0.2", "1.0.3", False, None, COMPOSER),
    (">=1.0", "1.0.0", True, None, COMPOSER), (">=1.0", "0.9.9", False, None, COMPOSER),
    (">=1.0 <2.0", "1.5.0", True, None, COMPOSER), (">=1.0 <2.0", "2.0.0", False, None, COMPOSER),
    (">=1.0,<2.0", "1.5.0", True, None, COMPOSER),
    (">=1.0 <1.1 || >=1.2", "1.0.5", True, None, COMPOSER), (">=1.0 <1.1 || >=1.2", "1.1.5", False, None, COMPOSER),
    (">=1.0 <1.1 || >=1.2", "1.2.0", True, None, COMPOSER), (">=1.0 <1.1 | >=1.2", "1.2.0", True, None, COMPOSER),
    ("1.0 - 2.0", "1.0.0", True, None, COMPOSER), ("1.0 - 2.0", "2.0.9", True, None, COMPOSER),
    ("1.0 - 2.0", "2.1.0", False, None, COMPOSER), ("1.0 - 2.0", "0.9.9", False, None, COMPOSER),
    ("1.0.0 - 2.1.0", "2.1.0", True, None, COMPOSER), ("1.0.0 - 2.1.0", "2.1.1", False, None, COMPOSER),
    ("1.0.*", "1.0.0", True, None, COMPOSER), ("1.0.*", "1.0.9", True, None, COMPOSER),
    ("1.0.*", "1.1.0", False, None, COMPOSER), ("1.*", "1.9.9", True, None, COMPOSER),
    ("1.*", "2.0.0", False, None, COMPOSER),
    ("~1.2", "1.2.0", True, None, COMPOSER), ("~1.2", "1.9.9", True, None, COMPOSER),
    ("~1.2", "2.0.0", False, None, COMPOSER), ("~1.2", "1.1.9", False, None, COMPOSER),
    ("~1.2.3", "1.2.3", True, None, COMPOSER), ("~1.2.3", "1.2.9", True, None, COMPOSER),
    ("~1.2.3", "1.3.0", False, None, COMPOSER), ("~1.2.3", "1.2.2", False, None, COMPOSER),
    ("~1", "1.9.0", True, None, COMPOSER), ("~1", "2.0.0", False, None, COMPOSER),
    ("^1.2.3", "1.2.3", True, None, COMPOSER), ("^1.2.3", "1.9.0", True, None, COMPOSER),
    ("^1.2.3", "2.0.0", False, None, COMPOSER), ("^1.2.3", "1.2.2", False, None, COMPOSER),
    ("^0.3", "0.3.0", True, None, COMPOSER), ("^0.3", "0.3.9", True, None, COMPOSER),
    ("^0.3", "0.4.0", False, None, COMPOSER), ("^0.0.3", "0.0.3", True, None, COMPOSER),
    ("^0.0.3", "0.0.4", False, None, COMPOSER), ("^1.2 || ^2.0", "2.5.0", True, None, COMPOSER),
    ("^1.2 || ^2.0", "1.9.0", True, None, COMPOSER), ("^1.2 || ^2.0", "3.0.0", False, None, COMPOSER),
    ("v1.2.3", "1.2.3", True, None, COMPOSER), ("*", "7.7.7", True, None, COMPOSER),
    # stability: minimum-stability defaults to stable, @flags lower it for one constraint
    ("^1.0", "1.5.0-beta1", False, None, COMPOSER), ("^1.0", "1.5.0-RC1", False, None, COMPOSER),
    ("^1.0", "1.5.0-dev", False, None, COMPOSER), ("^1.0@beta", "1.5.0-beta1", True, None, COMPOSER),
    ("^1.0@beta", "1.5.0-RC1", True, None, COMPOSER), ("^1.0@beta", "1.5.0-alpha1", False, None, COMPOSER),
    ("^1.0@dev", "1.5.0-dev", True, None, COMPOSER), ("^1.0", "1.5.0-RC1", True, "RC", COMPOSER),
    ("^1.0", "1.5.0-beta1", False, "RC", COMPOSER), ("^1.0", "1.5.0-beta1", True, "beta", COMPOSER),
    ("^1.0", "1.5.0-alpha1", True, "alpha", COMPOSER), ("^1.0", "1.5.0-dev", True, "dev", COMPOSER),
    ("^1.0", "2.0.0-beta1", False, "beta", COMPOSER),
]

# (range, version, matches, source)
MAVEN_CASES = [
    ("[1.0]", "1.0", True, MAVEN_POM), ("[1.0]", "1.0.0", True, MAVEN_POM), ("[1.0]", "1.1", False, MAVEN_POM),
    ("(,1.0]", "0.5", True, MAVEN_POM), ("(,1.0]", "1.0", True, MAVEN_POM), ("(,1.0]", "1.0.1", False, MAVEN_POM),
    ("[1.2,1.3]", "1.2.5", True, MAVEN_POM), ("[1.2,1.3]", "1.3", True, MAVEN_POM),
    ("[1.2,1.3]", "1.3.1", False, MAVEN_POM), ("[1.2,1.3]", "1.1.9", False, MAVEN_POM),
    ("[1.0,2.0)", "1.0", True, MAVEN_POM), ("[1.0,2.0)", "1.9.9", True, MAVEN_POM),
    ("[1.0,2.0)", "2.0", False, MAVEN_POM), ("[1.0,2.0)", "0.9", False, MAVEN_POM),
    ("[1.0,2.0)", "2.0-rc1", True, MAVEN_POM), ("[1.0,2.0)", "2.0-alpha-1", True, MAVEN_POM),
    ("[1.0,2.0)", "2.0-SNAPSHOT", True, MAVEN_ORDER),
    ("[1.5,)", "1.5", True, MAVEN_POM), ("[1.5,)", "1.4.9", False, MAVEN_POM), ("[1.5,)", "99", True, MAVEN_POM),
    ("(,1.0],[1.2,)", "1.0", True, MAVEN_POM), ("(,1.0],[1.2,)", "1.1", False, MAVEN_POM),
    ("(,1.0],[1.2,)", "1.2", True, MAVEN_POM), ("(,1.0],[1.2,)", "0.1", True, MAVEN_POM),
    ("(,1.1),(1.1,)", "1.1", False, MAVEN_POM), ("(,1.1),(1.1,)", "1.0", True, MAVEN_POM),
    ("(,1.1),(1.1,)", "1.2", True, MAVEN_POM), ("(,1.1),(1.1,)", "1.1.0", False, MAVEN_POM),
    ("[1,1.999999]", "1.5", True, MAVEN_POM), ("[1,1.999999]", "2.0-rc1", False, MAVEN_POM),
    ("[1,2-alpha)", "1.9", True, MAVEN_POM), ("[1,2-alpha)", "2-alpha", False, MAVEN_POM),
    ("[1,2-alpha)", "2-beta", False, MAVEN_POM),
    ("(1.0,2.0)", "1.0", False, MAVEN_POM), ("(1.0,2.0)", "1.0.1", True, MAVEN_POM),
    ("(1.0,2.0)", "2.0", False, MAVEN_POM), ("[1.0,2.0]", "2.0", True, MAVEN_POM),
    ("[1.0,)", "1.0-SNAPSHOT", False, MAVEN_ORDER), ("[1.0,)", "1.0-sp", True, MAVEN_ORDER),
    ("1.0", "3.7", True, MAVEN_POM), ("1.0", "1.0", True, MAVEN_POM),
]

# Version order specification: each group is a chain a < b < c ...; "=" groups are equal.
MAVEN_ORDER_CHAINS = [
    ["1", "1.1"], ["1-snapshot", "1", "1-sp"], ["1-foo2", "1-foo10"], ["1-foo", "1-1", "1.1"],
    ["1-alpha", "1-beta", "1-milestone", "1-rc", "1-snapshot", "1", "1-sp"],
    ["1-a1", "1-b1", "1-m1", "1-rc1"], ["1.7", "1.k"][::-1], ["5.aardvark", "5.zebra"],
    ["1-ga", "1-sp"], ["1-ga.1", "1-sp.1"], ["1-sp-1", "1-ga-1"], ["1.0-rc1", "1.0-snapshot", "1.0"],
    ["1.b", "1.α"],
]
MAVEN_EQUAL_GROUPS = [
    ["1.ga", "1-ga", "1-0", "1_0", "1.0", "1"], ["1-a1", "1-alpha-1"], ["1.0-alpha1", "1.0-ALPHA1"],
    ["1.foo", "1-foo"], ["1.0.0", "1"], ["1-rc1", "1-cr1"], ["1-final", "1-release", "1"],
]


def main(out_dir: str) -> None:
    out = Path(out_dir)
    cargo = [{"range": r, "version": v, "expected": e, "source": s} for r, v, e, s in CARGO_CASES]
    composer = [{"range": r, "version": v, "expected": e, "minimum_stability": m, "source": s}
                for r, v, e, m, s in COMPOSER_CASES]
    maven = {"cases": [{"range": r, "version": v, "expected": e, "source": s} for r, v, e, s in MAVEN_CASES],
             "order_chains": MAVEN_ORDER_CHAINS, "equal_groups": MAVEN_EQUAL_GROUPS, "order_source": MAVEN_ORDER}
    (out / "cargo_cases.json").write_text(json.dumps({"checked": "2026-11-17", "cases": cargo}, indent=1))
    (out / "composer_cases.json").write_text(json.dumps({"checked": "2026-11-17", "cases": composer}, indent=1))
    (out / "maven_cases.json").write_text(json.dumps({"checked": "2026-11-17", **maven}, indent=1))
    print(len(cargo), len(composer), len(maven["cases"]))


if __name__ == "__main__":
    main(sys.argv[1])
