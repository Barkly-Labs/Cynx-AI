const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const chat = fs.readFileSync(path.join(root, 'interfaces/web/static/chat.js'), 'utf8');
const shell = fs.readFileSync(path.join(root, 'interfaces/web/static/chat-shell.js'), 'utf8');
const dx = fs.readFileSync(path.join(root, 'interfaces/web/static/dx.js'), 'utf8');
const template = fs.readFileSync(path.join(root, 'interfaces/web/templates/dx.html'), 'utf8');

test('chat feedback offers accessible up/down ratings and optional explanation', () => {
  assert.match(chat, /Rate this response helpful/);
  assert.match(chat, /Rate this response not helpful/);
  assert.match(chat, /Optional explanation/);
  assert.match(chat, /Choose a reason/);
  assert.match(chat, /\/api\/feedback\//);
  assert.match(chat, /updateMessageFeedback/);
});

test('conversation restore retains feedback metadata and selected rating', () => {
  assert.match(shell, /typeof message === "object" \? message : \{\}/);
  assert.match(shell, /updateMessageFeedback/);
  assert.match(chat, /Your rating:/);
});

test('DX review view exposes scoped, shared, correction, and discard actions', () => {
  assert.match(template, /data-view="learning"/);
  assert.match(dx, /Accept for this user/);
  assert.match(dx, /Accept shared behavior/);
  assert.match(dx, /Correct &amp; accept/);
  assert.match(dx, /data-review="discard"/);
  assert.match(dx, /Generalized shared lesson/);
});
