# Regenerating the expected-value tables

Only needed when you add cases or want to re-check against newer reference implementations.
Tests and the skill itself never need these tools.

```
# npm: node-semver (7.8.6 was used)
npm install semver --prefix /tmp/refgen-node
node tools/refgen/gen_npm.js /tmp/refgen-node tools/refgen/inputs.json tests/data/npm_cases.json

# PyPI: packaging 26.x (membership) and 24.2 (install), one virtualenv each
python -m venv /tmp/p26 && /tmp/p26/bin/pip install packaging
python -m venv /tmp/p24 && /tmp/p24/bin/pip install packaging==24.2
/tmp/p26/bin/python tools/refgen/gen_pypi.py tools/refgen/inputs.json /tmp/p26.json
/tmp/p24/bin/python tools/refgen/gen_pypi.py tools/refgen/inputs.json /tmp/p24.json
python tools/refgen/build_pypi.py tools/refgen/inputs.json /tmp/p26.json /tmp/p24.json tests/data/pypi_cases.json

# Cargo, Composer, Maven: hand-written from official docs (edit the tables, then run)
python tools/refgen/doc_cases.py tests/data
```

`inputs.json` lists the ranges and versions that form the grids. Only the reference implementations' verdicts
(true/false, selected version) are stored; no code from them is copied.
