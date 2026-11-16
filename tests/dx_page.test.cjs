const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'interfaces/web/templates/dx.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'interfaces/web/static/dx.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'interfaces/web/static/dx.css'), 'utf8');

const navViews = ['overview', 'model', 'benchmark', 'personality-studio', 'learning', 'tools', 'requests', 'diagnostics', 'configuration', 'history'];
const benchmarkSections = ['overview', 'questions', 'watchdog', 'personality', 'trace', 'performance', 'errors'];

test('all DX destinations remain in the labeled workspace navigation', () => {
  for (const view of navViews) {
    assert.match(html, new RegExp(`data-view="${view}"`));
    assert.match(js, new RegExp(`['"]${view}['"]`));
  }
  assert.match(html, /aria-label="Workspace sections"/);
  assert.match(html, /aria-current="page"/);
  assert.match(js, /setAttribute\('aria-current','page'\)/);
});

test('benchmark sections stay visible and section navigation scrolls instead of hiding them', () => {
  for (const section of benchmarkSections) {
    assert.match(js, new RegExp(`data-bench-target="${section}"`));
    assert.match(js, new RegExp(`data-bench-panel="${section}"`));
    assert.match(js, new RegExp(`aria-controls="benchmark-panel-${section}"`));
  }
  assert.match(js, /panel\.hidden=false/);
  assert.match(js, /scrollIntoView/);
  assert.doesNotMatch(css, /\[data-bench-panel\]\[hidden\]/);
});

test('context snapshot remains in the reading flow at narrower widths', () => {
  assert.match(css, /@media\(max-width:1120px\)[\s\S]*?\.context\s*\{[\s\S]*?position:\s*static/);
  assert.match(css, /@media\(max-width:700px\)[\s\S]*?\.context,[\s\S]*?display:\s*block/);
  assert.match(html, /id="context-panel" aria-label="System snapshot"/);
});

test('section hierarchy and keyboard focus remain understandable', () => {
  assert.match(html, /<h1 id="page-title">/);
  assert.match(html, /role="region" aria-labelledby="page-title"/);
  assert.match(css, /\.view h2::before[\s\S]*counter\(dx-section, decimal-leading-zero\)/);
  assert.match(css, /details\s*>\s*summary:focus-visible/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
});

test('technical analysis labels remain present in the full benchmark report', () => {
  for (const phrase of [
    'Classification service: <strong>not instrumented</strong>',
    'Runtime telemetry and tool trace',
    'Missing telemetry is not estimated.',
    'Evaluator results remain experimental',
    'Captured routing, tool, and request events',
  ]) assert.ok(js.includes(phrase), `expected retained technical detail: ${phrase}`);
});
