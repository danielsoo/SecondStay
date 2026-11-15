import test from "node:test";
import assert from "node:assert/strict";
import { permitYearsSvg } from "../secondstay/static/permit_years.mjs";

test("one bar per year with permits, labelled with the busiest year", () => {
  const svg = permitYearsSvg([
    { year: 2019, permits: 16, valued: 2, declared_valuation: 484100 },
    { year: 2022, permits: 1, valued: 0, declared_valuation: null },
    { year: 2024, permits: 22, valued: 6, declared_valuation: 581501 },
  ], 2026);
  assert.equal((svg.match(/<rect /g) || []).length, 3);
  assert.match(svg, /39 permits since 2019 · busiest 2024 \(22\)/);
  assert.match(svg, /declared on 8 of them/);
  assert.match(svg, /not what the work cost/);
});

test("no permits draws nothing", () => {
  assert.equal(permitYearsSvg([]), "");
  assert.equal(permitYearsSvg([{ year: 2020, permits: 0 }]), "");
});
