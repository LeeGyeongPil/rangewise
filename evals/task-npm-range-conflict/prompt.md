---
name: task-npm-range-conflict
max_turns: 6
---

packages/a depends on shared at `^0.2.3` and packages/b depends on shared at `^0.3.0`. Can one version of shared satisfy both manifests? Save the full machine-readable result as result.json in this folder and summarize the answer. Everything you need is in this message and the two package.json files; there is no network access, so do not install packages or query a registry.
