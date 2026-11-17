---
name: task-error-maven-property
max_turns: 6
---

pom.xml declares lib-core with the version expression `${project.version}`. Does version 1.4.2 satisfy it? If you have a version-range checker available, run it and quote exactly what it reports; if the expression cannot be evaluated, say why. Everything you need is in this message and pom.xml; there is no network access, so do not install tools or query a repository.
