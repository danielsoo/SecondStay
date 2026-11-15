import test from "node:test";
import assert from "node:assert/strict";
import { floorAccounting, gridSegments, drawnSqft, polygonArea } from "../secondstay/static/floor_accounting.mjs";

const square = (s) => [[0, 0], [s, 0], [s, s], [0, s]];

test("polygon and drawn room areas", () => {
  assert.equal(polygonArea(square(10)), 100);
  assert.equal(drawnSqft([{ units: "metres", rooms: [{ polygon: square(10), holes: [square(2)] }] }]), Math.round(96 * 10.7639));
  assert.equal(drawnSqft([{ units: "plan_relative", rooms: [{ polygon: square(10) }] }]), null);
});

test("every part of the floor carries its reason", () => {
  const building = {
    floors: [{ floor: 15, sqft: 27000, occupied_sqft: 12000, tenancies: 3 }],
    spaces: [
      { id: 1, suite: "1500", floor: 15, sqft: 3589, plan_url: "p1", scans: ["s1"] },
      { id: 2, suite: "1550", floor: 15, sqft: 1861, plan_url: "p2", scans: [] },
      { id: 3, suite: "1520", floor: 15, sqft: 2241, plan_url: "", scans: [] },
      { id: 4, suite: "1578", floor: 15, sqft: 1500, plan_url: "", scans: ["s4"] },
      { id: 5, suite: "900", floor: 9, sqft: 9000, plan_url: "", scans: [] },
    ],
  };
  const catalog = { floors: [{ floor: 15, assets: [
    { key: "space:1:s1", space_id: "1", geometry_available: true },
    { key: "space:4:s4", space_id: "4", geometry_available: false },
  ] }] };
  const shown = [{ space_id: "1", suite: "1500", units: "metres", rooms: [{ polygon: square(10) }] }];
  const a = floorAccounting({ building, catalog, floor: 15, shownModels: shown });
  const kinds = Object.fromEntries(a.parts.map(p => [p.label, p.kind]));
  assert.deepEqual(kinds, {
    "Suite 1500": "drawn", "Suite 1550": "listed_plan", "Suite 1520": "listed_none", "Suite 1578": "listed_tour",
  }); // leased space and the rest of the floor are not listed: they are not on the market
  assert.equal(a.onMarket, 4);
  assert.equal(a.marketSqft, 1861 + 2241 + 1500);
  assert.equal(a.basis, "CoStar floor size");
});

test("a floor with nothing on the market lists nothing", () => {
  const a = floorAccounting({ building: { floors: [{ floor: 3, sqft: 9000, tenancies: 2, occupied_sqft: 9000 }], spaces: [] }, catalog: {}, floor: 3 });
  assert.equal(a.parts.length, 0);
  assert.equal(a.onMarket, 0);
  assert.equal(a.floorSqft, 9000);
});

test("grid lines stay inside the outline", () => {
  const segs = gridSegments([square(10)], 3);
  assert.equal(segs.length, 6); // three horizontal and three vertical lines, at 3, 6 and 9
  for (const [x1, y1, x2, y2] of segs) for (const v of [x1, y1, x2, y2]) assert.ok(v >= 0 && v <= 10);
  const ell = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]];
  const across = gridSegments([ell], 6).find(([, y1, , y2]) => y1 === 6 && y2 === 6);
  assert.deepEqual(across, [0, 6, 4, 6]); // stops at the inside corner of the L
});
