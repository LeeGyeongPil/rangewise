# Ecosystem rules at a glance

Checked 2026-11-17 against the sources listed at the end. Bounds are the exact ones the script prints under "Exact interval bounds": a trailing `-0` (npm) or `-dev` (Composer) is the smallest prerelease of that version, so `<0.3.0-0` reads as "below 0.3.0, including its prereleases".

## Same symbol, different meaning

| Range | npm | Cargo | Composer | PyPI (PEP 440) | Maven |
|---|---|---|---|---|---|
| `1.2.3` | exactly 1.2.3 | caret, `>=1.2.3 <2.0.0` | exactly 1.2.3 | invalid (needs `==`) | soft preference, not a limit |
| `^0.2.3` | `>=0.2.3 <0.3.0-0` | `>=0.2.3 <0.3.0` | `>=0.2.3 <0.3.0-dev` | n/a | n/a |
| `^0.0` | `<0.1.0-0` | `<0.1.0` | `<0.1.0-dev` | n/a | n/a |
| `~1.2` | `<1.3.0-0` | `<1.3.0` | `<2.0.0-dev` | n/a | n/a |
| `~1.2.3` | `<1.3.0-0` | `<1.3.0` | `<1.3.0-dev` | n/a | n/a |
| `~=1.4` | n/a | n/a | n/a | `>=1.4, ==1.*` so `<2` | n/a |
| `~=1.4.2` | n/a | n/a | n/a | `>=1.4.2, ==1.4.*` so `<1.5` | n/a |
| `<=1.2` | `<1.3.0-0` | `<1.3.0` | `<=1.2.0` | `<=1.2` | n/a |

The caret keeps the left-most non-zero part of the given digits; with all-zero digits it bumps the last given one.

## Prerelease handling

| Ecosystem | Rule | Option |
|---|---|---|
| npm | a prerelease matches only if a comparator in the same AND-set has a prerelease on the same major.minor.patch | `--include-prerelease` |
| Cargo | same rule as npm | `--include-prerelease` |
| PyPI | `install` (default): skipped unless the specifier names a prerelease, pip falls back to them when nothing else matches. `membership`: no gate (packaging 26 `contains()`) | `--pre-policy install` or `membership` |
| Composer | versions below `minimum-stability` (default stable) are skipped unless the range carries an `@flag` or a stability suffix | `--minimum-stability` |
| Maven | no gate; qualifiers only change order: alpha, beta, milestone, rc (= cr), snapshot, release (= ga = final), sp | none |

So `>=0.9.0` does not match `0.9.1-build.4` in npm (inside the interval, blocked by the gate), and Maven `[1.0,2.0)` does include `2.0-rc1` and `2.0-SNAPSHOT` because both sort below `2.0`.

## PEP 440 details

- `2.0.0-beta.1` normalizes to `2.0b1`; trailing zeros are ignored (`1.0 == 1.0.0`); `1.0+local.7` matches `==1.0` but `==1.0+local.7` does not match `1.0`.
- `>1.5` excludes `1.5.post1`; `<1.5` excludes `1.5.0a1` (unless the bound is itself a prerelease).
- `==1.4.*` is a prefix match and also matches `1.4.0rc1` under the `membership` policy.

## Not evaluated (exit code 3)

npm `workspace:` `file:` `link:` `npm:` git or URL specs and dist-tags such as `latest`; PEP 508 environment markers and direct URL references; Composer `dev-*` branches, `as` aliases and `1.x-dev`; Maven `${...}` properties, `LATEST` and `RELEASE`. Registry lookups and lockfiles are out of scope.

## Sources

- node-semver 7.8.6: https://github.com/npm/node-semver
- Cargo: https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html
- PEP 440 / version specifiers: https://packaging.python.org/en/latest/specifications/version-specifiers/
- Composer: https://getcomposer.org/doc/articles/versions.md
- Maven: https://maven.apache.org/pom.html#dependency-version-requirement-specification
