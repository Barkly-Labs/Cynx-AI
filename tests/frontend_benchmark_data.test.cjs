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
  assert.match(source, /metricCell\('Tool calls',toolsObserved\?\(selected\.tools\|\|\[\]\)\.length:null\)/);
  assert.match(source, /selected\?\.tool_telemetry_available===true/);
});

test("question results show every actual multi-turn user prompt and response", () => {
  assert.match(source, /function renderQuestionConversation\(question\)/);
  assert.match(source, /question\?\.conversation_turns\)\?question\.conversation_turns:\[\]/);
  assert.match(source, /turn\.user_message\|\|'No user message saved\.'/);
  assert.match(source, /turn\.response\|\|'No response saved\.'/);
});

test("question results distinguish recorded zero tool calls from unavailable telemetry", () => {
  assert.match(source, /function renderQuestionTools\(question\)/);
  assert.match(source, /tool_telemetry_available===true/);
  assert.match(source, /list\|\|'None recorded'/);
  assert.match(source, /Tool calls: unavailable \(not captured\)/);
});

test("watchdog trait values come only from saved personality evaluations", () => {
  assert.match(source, /Scores are aggregated from saved, versioned Personality Diagnostics/);
  assert.match(source, /\$\{esc\(value\.value\)\} \/ 4 · \$\{esc\(value\.sample_count\)\} sample/);
  assert.match(source, /Traits are not inferred from response text/);
});

test("Benchmark Watch renders run-specific metadata, full turns, metric comparisons, and captured tool traces", () => {
  assert.match(source, /Run identity and captured configuration/);
  assert.match(source, /Current-run performance · saved measurements/);
  assert.match(source, /renderWatchdogTurns\(selected\.conversation_turns\)/);
  assert.match(source, /selected\.personality_trace\|\|telemetry\.events/);
  assert.match(source, /comparisonTable/);
  assert.match(source, /Input tokens: \$\{esc\(telemetry\.prompt_tokens/);
  assert.match(source, /Output tokens: \$\{esc\(telemetry\.completion_tokens/);
  assert.match(source, /Generation duration: \$\{esc\(telemetry\.generation_duration_seconds/);
});

test("Personality Diagnostics exposes the exact historical conversation and versioned score criteria", () => {
  assert.match(source, /personalitySourceRun\?\.run_id===currentId/);
  assert.match(source, /Complete scenario prompt and actual conversation/);
  assert.match(source, /Versioned scoring criteria and methodology/);
  assert.match(source, /scored samples · \$\{items\.filter\(x=>x\.status==='pass'\)\.length\} pass/);
  assert.match(source, /configuration_availability/);
});

test("benchmark question and turn views render input, output, total, and timing metrics", () => {
  assert.match(source, /metricCell\('Input tokens',metrics\.prompt_tokens\)/);
  assert.match(source, /metricCell\('Output tokens',metrics\.completion_tokens\?\?metrics\.tokens_generated\)/);
  assert.match(source, /metricCell\('Total tokens',metrics\.total_tokens\)/);
  assert.match(source, /metricCell\('Generation duration',metrics\.generation_duration_seconds,'s'\)/);
  assert.match(source, /metricCell\('Request duration',metrics\.response_time_seconds,'s'\)/);
  assert.match(source, /Turn performance/);
});

test("benchmark overview shows real aggregate metrics with measurement coverage", () => {
  assert.match(source, /run\.metrics_summary\|\|\{\}/);
  assert.match(source, /aggregateMetricCell\('Input tokens',summary\.prompt_tokens\)/);
  assert.match(source, /aggregateMetricCell\('Output tokens',summary\.completion_tokens\)/);
  assert.match(source, /aggregateMetricCell\('Total tokens',summary\.total_tokens\)/);
  assert.match(source, /Aggregate tokens\/sec/);
  assert.match(source, /measured_questions\?\?0/);
});

test("valid zero-valued telemetry is rendered as zero instead of unavailable", () => {
  assert.match(source, /value===null\|\|value===undefined\?'Unavailable'/);
  assert.match(source, /metrics\.prompt_tokens/);
});
