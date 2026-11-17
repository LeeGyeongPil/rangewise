---
name: rangewise
description: Decides package version ranges exactly the way each ecosystem does (npm, Cargo, PyPI/PEP 440, Composer, Maven) with a bundled offline script, so the answer comes from computed intervals and prerelease rules instead of memory. Use when someone asks whether a version satisfies a dependency range from package.json, Cargo.toml, pyproject.toml, requirements.txt, composer.json or pom.xml, which version an install would pick from a list of candidates, whether two requirements conflict or overlap, or what a range such as ^0.2.3, ~1.2, ~=1.4 or [1.0,2.0) really allows. Not for bumping versions, looking up the latest release, auditing vulnerabilities or editing lockfiles.
license: MIT
compatibility: Python 3.10+ (standard library only). No network access.
---

# Version range decisions

The same symbol means different things per ecosystem (`~1.2` is `<1.3.0` in npm but `<2.0.0` in Composer), `^0.x` stops at the next minor, prereleases are gated differently, and Maven ranges include `2.0-rc1`. Do not solve these by hand - run the script.

1. Run `python3 scripts/rangewise.py check <eco> "<range>" <version>` where `<eco>` is `npm`, `cargo`, `pypi`, `composer` or `maven`. Always quote the range. Other commands, same shape:
   - `best <eco> "<range>" <v1> <v2> ...` (or `--from FILE`, one version per line) - which candidate gets picked
   - `intersect <eco> "<range1>" "<range2>"` - do two requirements overlap
   - `explain <eco> "<range>"` - what the range means as exact intervals
2. Add `--json` when the user wants a saved or machine-readable result (redirect it into the file they name, for example `> result.json`). Add `--lang ko` for Korean explanations. For PyPI the output shows both prerelease policies; for Composer use `--minimum-stability`, for npm and Cargo `--include-prerelease`.
3. Report the ecosystem and policy, then the two steps separately: inside the interval or not, and whether the prerelease gate lets it through. For `best`, name the selected version; for PyPI mention when `install` (what pip picks) and `membership` (`contains()` in packaging 26) differ.
4. Exit code 3 means the form cannot be evaluated from the range string alone (for example `workspace:`, `${project.version}`, environment markers): say so and do not guess a result. Exit code 2 means the input was malformed - show the error line as is, it says how to fix it.

Rule tables per ecosystem are in `references/ecosystems.md`; read it only when the user asks why a rule works that way.
