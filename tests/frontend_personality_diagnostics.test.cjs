const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

const source = fs.readFileSync("interfaces/web/static/dx.js", "utf8");
const functionBody = (name, nextName) => {
    const start = source.indexOf(`async function ${name}`);
    const end = source.indexOf(`async function ${nextName}`, start + 1);
    assert.notEqual(start, -1, `${name} exists`);
    assert.notEqual(end, -1, `${nextName} follows it`);
    return source.slice(start, end);
};

test("diagnostic polling is keyed and throttled instead of reloading on each benchmark tick", () => {
    const load = functionBody("loadPersonalityHistory", "evaluatePersonalityRun");
    assert.match(load, /personalityNextFetchAt/);
    assert.match(load, /personalityHistoryKey===key\|\|state\.personalityRequestKey===key/);
    assert.match(load, /state\.personalityBusy\)return/);
    assert.match(load, /Date\.now\(\)\+3000/);
});

test("refresh preserves saved diagnostics and ignores stale or unchanged responses", () => {
    const load = functionBody("loadPersonalityHistory", "evaluatePersonalityRun");
    assert.match(load, /state\.personalityHistoryKey!==key&&!state\.personalityHistory/);
    assert.match(load, /token!==state\.personalityRequestToken/);
    assert.match(load, /signature!==state\.personalityHistorySignature/);
    assert.match(load, /saved results are still shown/);
    assert.match(load, /if\(state\.personalityHistoryKey!==key&&!state\.personalityHistory&&state\.personalityErrorKey!==key\)panel\.innerHTML/);
    assert.match(load, /state\.personalityErrorKey!==key/);
});

test("evaluations cannot be double-submitted and expanded findings are retained", () => {
    const start = source.indexOf("async function evaluatePersonalityRun");
    const end = source.indexOf("function selectPersonalityRun", start);
    const evaluate = source.slice(start, end);
    assert.match(evaluate, /state\.personalityEvaluationBusy\)return/);
    assert.match(source, /data-diagnostic-id=\"\$\{esc\(item\.diagnostic_id\)\}\"/);
    assert.match(source, /openDiagnostics\.has\(detail\.dataset\.diagnosticId\)/);
});
