// Run with: node --test tests/test_scan_viewer.cjs
// Synthetic scan only; no network or third-party credentials are used.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const html = readFileSync(resolve(__dirname, '../secondstay/static/index.html'), 'utf8');
const source = html.slice(html.indexOf('function mountScanViewer('), html.indexOf('\nfunction outline('));

function setup(modelId = 'SYNTHETIC') {
  const nodes = new Map();
  let creations = 0;
  const frames = [];
  const host = {
    innerHTML: '', hidden: false,
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {
        hidden: false, appendChild(frame) { frames.push(frame); },
      });
      return nodes.get(selector);
    },
  };
  const document = { createElement(tag) {
    assert.equal(tag, 'iframe');
    creations++;
    return { loads: 0, set src(value) { this.url = value; this.loads++; } };
  } };
  const mount = runInNewContext(`${source}\nmountScanViewer`, { document, esc: String });
  const show = mount(host, { scan: { model_id: modelId } });
  return { host, show, frames, creations: () => creations };
}

test('scan starts only on request and survives checklist navigation', () => {
  const s = setup();
  s.show(true);
  assert.equal(s.host.hidden, false);
  assert.equal(s.creations(), 0);
  const open = s.host.querySelector('[data-open-scan]');
  open.onclick();
  assert.equal(s.frames.length, 1);
  const frame = s.frames[0];
  assert.equal(frame.loads, 1);
  s.show(false);
  assert.equal(s.host.hidden, true);
  s.show(true);
  open.onclick();
  assert.equal(s.creations(), 1);
  assert.equal(s.frames[0], frame);
  assert.equal(frame.loads, 1);
  s.host.querySelector('[data-reload-scan]').onclick();
  assert.equal(frame.loads, 2);
});

test('a building without a scan never opens a viewer', () => {
  const s = setup('');
  s.show(true);
  assert.equal(s.host.hidden, true);
  assert.equal(s.host.innerHTML, '');
  assert.equal(s.creations(), 0);
});
