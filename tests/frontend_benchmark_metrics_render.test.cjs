const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("interfaces/web/static/dx.js", "utf8");
const start = source.indexOf("  const esc = value =>");
const end = source.indexOf("  const runResponseCount =", start);
const conversationStart = source.indexOf("  function renderQuestionConversation(", end);
const conversationEnd = source.indexOf("  function renderQuestionTools(", conversationStart);
assert.notEqual(start, -1, "DX metric rendering helpers exist");
assert.notEqual(end, -1, "DX metric rendering helper boundary exists");
assert.notEqual(conversationStart, -1, "DX Results turn renderer exists");
assert.notEqual(conversationEnd, -1, "DX Results turn renderer boundary exists");
const helperSource = source.slice(start, end) + source.slice(conversationStart, conversationEnd);
const sandbox = {};
vm.runInNewContext(`${helperSource}\nglobalThis.renderRuntimeMetrics=renderRuntimeMetrics;globalThis.renderQuestionConversation=renderQuestionConversation;globalThis.aggregateMetricCell=aggregateMetricCell;`, sandbox);

test("actual DX metric renderer displays measured input/output/total and timing values", () => {
  const html = sandbox.renderRuntimeMetrics({
    prompt_tokens: 41, completion_tokens: 13, total_tokens: 54,
    ttft_seconds: 0.25, generation_duration_seconds: 2,
    response_time_seconds: 8, tokens_per_second: 6.5,
  });
  for (const text of [
    "Input tokens</strong><span>41", "Output tokens</strong><span>13",
    "Total tokens</strong><span>54", "TTFT</strong><span>0.25s",
    "Generation duration</strong><span>2s", "Request duration</strong><span>8s",
    "Tokens per second</strong><span>6.5",
  ]) assert.ok(html.includes(text), `rendered metrics include ${text}`);
});

test("actual DX metric renderer keeps zero distinct from missing telemetry", () => {
  const html = sandbox.renderRuntimeMetrics({prompt_tokens: 0, completion_tokens: 0, total_tokens: 0});
  assert.match(html, /Input tokens<\/strong><span>0<\/span>/);
  assert.match(html, /Output tokens<\/strong><span>0<\/span>/);
  assert.match(html, /Total tokens<\/strong><span>0<\/span>/);
  assert.match(html, /TTFT<\/strong><span>Unavailable<\/span>/);
  assert.match(html, /Tokens per second<\/strong><span>Unavailable<\/span>/);
});

test("actual aggregate renderer includes values and telemetry coverage", () => {
  const html = sandbox.aggregateMetricCell("Input tokens", {
    total: 41, measured_questions: 1, eligible_questions: 2,
  });
  assert.match(html, /Input tokens<\/strong><span>41<\/span>/);
  assert.match(html, /1\/2 measured questions/);
  const missing = sandbox.aggregateMetricCell("Output tokens", {
    total: null, measured_questions: 0, eligible_questions: 2,
  });
  assert.match(missing, /Unavailable/);
  const zero = sandbox.aggregateMetricCell("Output tokens", {
    total: 0, measured_questions: 1, eligible_questions: 1,
  });
  assert.match(zero, /Output tokens<\/strong><span>0<\/span>/);
});

test("actual Results renderer shows token metrics beside each multi-turn answer", () => {
  const html = sandbox.renderQuestionConversation({conversation_turns:[{
    turn_index:1, request_id:'req-turn-1', user_message:'First prompt',
    response:'First actual response',
    metrics:{prompt_tokens:17,completion_tokens:4,total_tokens:21,
      response_time_seconds:1.2,ttft_seconds:0.1,generation_duration_seconds:0.4,tokens_per_second:10},
  },{
    turn_index:2, request_id:'req-turn-2', user_message:'Second prompt',
    response:'Second actual response',
    metrics:{prompt_tokens:25,completion_tokens:8,total_tokens:33,
      response_time_seconds:2.1,ttft_seconds:null,generation_duration_seconds:0.8,tokens_per_second:10},
  }]});
  assert.match(html, /First actual response/);
  assert.match(html, /Second actual response/);
  assert.match(html, /Input tokens<\/strong><span>17<\/span>/);
  assert.match(html, /Output tokens<\/strong><span>8<\/span>/);
  assert.match(html, /Total tokens<\/strong><span>33<\/span>/);
  assert.match(html, /TTFT<\/strong><span>Unavailable<\/span>/);
});
