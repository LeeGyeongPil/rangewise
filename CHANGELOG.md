# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-17

### Added
- Agent skill `rangewise` with the offline, standard-library-only script `scripts/rangewise.py`.
- Commands `check`, `best`, `intersect` and `explain` for npm, Cargo, PyPI (PEP 440), Composer and Maven ranges.
- Two-step decisions: interval membership plus the ecosystem's prerelease gate, with explicit options
  (`--include-prerelease`, `--pre-policy install|membership`, `--minimum-stability`).
- JSON output (`--json`), exit codes 0/1/2/3 and `--exit-status`.
- English and Korean explanations (`--lang`, `RANGEWISE_LANG`, `LC_ALL`/`LC_MESSAGES`/`LANG`).
- Expected-value tables generated from node-semver 7.8.6 and packaging 26.3 / 24.2, plus doc-derived tables for
  Cargo, Composer and Maven; evaluation set under `evals/`.
