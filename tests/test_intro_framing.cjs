// Run with: node --test tests/test_intro_framing.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');

const html = readFileSync(resolve(__dirname, '../secondstay/static/index.html'), 'utf8');
const source = html.slice(html.indexOf('function introPhotoHeight('), html.indexOf('\nfunction buildingScene('));
const height = runInNewContext(`${source}\nintroPhotoHeight`);

test('photo covers wide, square, and tall viewports with an offset building', () => {
  for (const aspect of [0.6, 1, 1.94, 3.2]) {
    for (const [cx, cy] of [[0, 0], [24, -16], [-24, 16]]) {
      const h = height(240, 220, cx, cy, aspect, 42, 240);
      const halfDepth = h * Math.tan(42 * Math.PI / 360);
      const halfWidth = halfDepth * aspect;
      assert.ok(h > 0 && h <= 240);
      assert.ok(Math.abs(cx) + halfWidth < 120);
      assert.ok(Math.abs(cy) + halfDepth < 110);
    }
  }
});

test('widening the viewport brings the camera closer to retain photo coverage', () => {
  assert.ok(height(240, 220, 0, 0, 2, 42, 240) < height(240, 220, 0, 0, 1, 42, 240));
  assert.equal(height(240, 220, 0, 0, 1, 42, 80), 80);
});
