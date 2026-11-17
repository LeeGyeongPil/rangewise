---
name: task-npm-prerelease-pick
max_turns: 6
---

package.json asks for @acme/core at `>=0.9.0`, and registry-versions.txt lists what the registry has: 0.8.4, 0.9.0, 0.9.1-build.4. Which version would npm install? Save the full machine-readable result as result.json in this folder, then tell me the version and why. Everything you need is in this message and the two files; there is no network access, so do not install packages or query a registry.
