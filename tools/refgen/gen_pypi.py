"""Generates one half of tests/data/pypi_cases.json from the packaging library that runs this script.

usage: python gen_pypi.py <inputs.json> <out.json>
Run it once under packaging 26.x and once under packaging 24.2, then merge with build_pypi.py.
"""
import json
import sys

import packaging
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

inp = json.load(open(sys.argv[1]))["pypi"]
contains, ranges = {}, []
for r in inp["ranges"]:
    try:
        s = SpecifierSet(r)
    except InvalidSpecifier:
        continue
    ranges.append(r)
    row = []
    for v in inp["versions"]:
        try:
            if s.contains(Version(v)):
                row.append(v)
        except Exception:
            pass
    contains[r] = row
flt = []
for r in inp["filter_ranges"]:
    s = SpecifierSet(r)
    for lst in inp["filter_lists"]:
        flt.append({"range": r, "versions": lst, "filter": list(s.filter(lst))})
json.dump({"source": f"packaging {packaging.__version__}", "contains": contains, "filter": flt},
          open(sys.argv[2], "w"))
