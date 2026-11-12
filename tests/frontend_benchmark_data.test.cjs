const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

const source = fs.readFileSync("interfaces/web/static/dx.js", "utf8");

test("benchmark overview and history preserve unavailable metrics", () => {
  assert.match(source, /const metricText = \(value, digits=2\) => hasMetric\(value\)/);
  assert.match(source, /metricText\(latest\.average_score\)/);
  assert.match(source, /average response .*not available/);
  assert.doesNotMatch(source, /Number\(latest\.average_score\|\|0\)/);
});

test("legacy runs use read-only detail rendering and skip live polling", () => {
  assert.match(source, /if\(state\.activeRun\?\.legacy_record&&!force\)return/);
  assert.match(source, /state\.activeRun=await api\(`\/api\/dx\/benchmark\/runs\/\$\{encodeURIComponent\(button\.dataset\.loadRun\)\}`\)/);
});

test("terminal benchmark questions are labeled as historical rather than current", () => {
  assert.match(source, /\['completed','completed_with_failures','stopped','interrupted','failed','incomplete'\]\.includes\(run\.status\)\?'LAST QUESTION':'CURRENT QUESTION'/);
});

test("Run Again repeats the selected run's suite and mode", () => {
  assert.match(source, /if\(action==='again'\)\{await startBenchmark\(run\.suite,run\.mode\);return\}/);
});
