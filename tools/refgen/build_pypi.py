"""Merge the two gen_pypi.py outputs into tests/data/pypi_cases.json.

usage: python build_pypi.py <inputs.json> <packaging-26.json> <packaging-24.json> <out.json>
"""
import json
import sys

inp = json.load(open(sys.argv[1]))["pypi"]
new, old = json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))
ranges = [r for r in new["contains"] if r in old["contains"]]
out = {
    "sources": {"membership": new["source"], "install": old["source"]},
    "versions": inp["versions"],
    "membership": {r: new["contains"][r] for r in ranges},
    "install": {r: old["contains"][r] for r in ranges},
    # packaging 26 filter() is what pip installs: final releases first, prereleases only as a fallback
    "filter_pip": new["filter"],
}
json.dump(out, open(sys.argv[4], "w"))
