// Generates tests/data/npm_cases.json from node-semver (the reference implementation).
// usage: node gen_npm.js <dir containing node_modules/semver> <inputs.json> <out.json>
const fs = require('fs');
const path = require('path');
const semver = require(path.join(process.argv[2], 'node_modules', 'semver'));
const pkg = JSON.parse(fs.readFileSync(path.join(process.argv[2], 'node_modules', 'semver', 'package.json')));
const inp = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')).npm;
const valid = inp.ranges.filter(r => semver.validRange(r) !== null);
const table = {};
for (const r of valid) table[r] = inp.versions.filter(v => semver.satisfies(v, r));
const inc = {};
for (const r of inp.include_prerelease_ranges) inc[r] = inp.versions.filter(v => semver.satisfies(v, r, { includePrerelease: true }));
const max = [];
for (const r of inp.max_ranges) for (const l of inp.max_lists) max.push({ range: r, versions: l, selected: semver.maxSatisfying(l, r) });
// node-semver quirks around star comparators (empty sets reported as intersecting): skipped on purpose
const skip = ['', '>*', '<*', '>=*', '<=*'];
const inter = [];
for (let i = 0; i < valid.length; i++) for (let j = i + 1; j < valid.length; j++) {
  if (skip.includes(valid[i]) || skip.includes(valid[j])) continue;
  inter.push([valid[i], valid[j], semver.intersects(valid[i], valid[j])]);
}
fs.writeFileSync(process.argv[4], JSON.stringify({
  source: `node-semver ${pkg.version}`, versions: inp.versions, satisfies: table,
  include_prerelease: inc, max_satisfying: max, intersects: inter,
}, null, 0));
