---
name: task-pypi-pip-pick
max_turns: 6
---

requirements.txt asks for `widget>=1.0`, and widget-versions.txt lists what the index has: 1.0, 1.1, 2.0b1. Which version does pip install, and would a plain specifier membership test (packaging's `SpecifierSet.contains()`, no prereleases argument) pick a different one? Name both versions. Save the full machine-readable result as result.json in this folder. Everything you need is in this message and the two files; there is no network access, so do not install packages or query an index.
