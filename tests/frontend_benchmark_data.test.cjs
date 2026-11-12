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

test("personality coverage distinguishes untargeted runs and offers the real versioned suite", () => {
  assert.match(source, /runContext\?\.targeted_scenarios/);
  assert.match(source, /dimensionTargets\[dim\.id\]/);
  assert.match(source, /This run has no personality-targeted scenarios/);
  assert.match(source, /data-personality-start-suite/);
  assert.match(source, /startBenchmark\(suite,'automatic'\)/);
  assert.match(source, /personality-diagnostics-v1\.json/);
});

test("personality trend does not draw empty axes when stored scores are all null", () => {
  assert.match(source, /if\(!values\.some\(run=>dimensions\.some\(dimension=>Number\.isFinite\(run\.dimensions\?\.\[dimension\.id\]\)\)\)\)return ''/);
  assert.match(source, /No stored scores match these filters yet/);
});

test("personality severity rows use a shared scale and report finding totals", () => {
  assert.match(source, /maxTotal=Math\.max\(1,\.\.\.rows\.map/);
  assert.match(source, /Inspect \$\{sum\} diagnostics/);
  assert.match(source, /<strong>\$\{sum\}<\/strong>/);
});

test("performance fields use persisted whole-question generation aggregates", () => {
  assert.match(source, /generationDetails=events\.filter\(e=>e\.stage==='generation_response_received'\)/);
  assert.match(source, /sumTraceMetric\('tokens_generated'\)/);
  assert.match(source, /sumTraceMetric\('generation_duration_nanoseconds'\)/);
  assert.match(source, /selected\?\.metrics\?\.tokens_generated\?\?traceTokens/);
  assert.match(source, /selected\?\.metrics\?\.tokens_per_second\?\?/);
  assert.doesNotMatch(source, /const generated=traceDetails\.find/);
});

test("request diagnostics prefer the failing turn ID and preserve event turn mapping", () => {
  assert.match(source, /q\.terminal_request_id\|\|q\.request_id/);
  assert.match(source, /selected\.request_ids\|\|\[selected\.request_id\]/);
  assert.match(source, /aria-valuetext',`\$\{attempted\} of \$\{total\} questions processed`/);
});

test("legacy unavailable tool telemetry is not rendered as zero calls", () => {
  assert.match(source, /toolsObserved\?selected\.tools\.length:'Unavailable'/);
  assert.match(source, /selected\?\.tool_telemetry_available===true/);
});
