// What each part of one floor is, and why it is or is not drawn.
// Pure functions, so they can be tested without a browser.

const SQFT_PER_SQM = 10.7639;
export const GRID_FT = 10;

export function polygonArea(points) {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i], [x2, y2] = points[(i + 1) % points.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

/** Square feet of room boundaries drawn by the shown models; drafts without scale count as unknown. */
export function drawnSqft(models) {
  let total = 0, measured = false;
  for (const m of models || []) {
    if (!m || m.units === "plan_relative") continue;
    for (const room of m.rooms || []) {
      let area = polygonArea(room.polygon || []);
      for (const hole of room.holes || []) area -= polygonArea(hole);
      total += Math.max(0, area); measured = true;
    }
  }
  return measured ? Math.round(total * SQFT_PER_SQM) : null;
}

function suiteName(s) { return s.suite ? `Suite ${s.suite}` : "Listed space"; }

/**
 * Area of the drawn part. Models in metres are summed from their rooms. A plan_relative draft has no scale,
 * so its area is the listed size CoStar records for that suite, never a figure read off the drawing.
 * If any shown model has neither, the drawn area is unknown rather than a partial sum.
 */
function drawnArea(shownModels, spaces) {
  const relative = shownModels.filter(m => m?.units === "plan_relative");
  const measured = shownModels.filter(m => m && m.units !== "plan_relative");
  const fromRooms = measured.length ? drawnSqft(measured) : 0;
  const listed = relative.map(m => spaces.find(s => String(s.id) === String(m.space_id || ""))?.sqft || null);
  const sqft = fromRooms == null || listed.some(v => v == null) ? null : fromRooms + listed.reduce((t, v) => t + v, 0);
  const basis = !relative.length ? "rooms" : !measured.length ? "listing" : "mixed";
  const reason = sqft == null && relative.length
    ? "Rooms traced from a plan with no printed lengths, and CoStar records no size for this listing."
    : { rooms: "Rooms drawn from scan walls or a traced plan.",
        listing: "Rooms traced from a plan with no printed lengths; the area is CoStar's listed size for the space, not measured from the drawing.",
        mixed: "Scan rooms are summed from their walls; traced plans without printed lengths count CoStar's listed size." }[basis];
  return { sqft, basis, reason };
}

/**
 * Parts of the floor, each with its area and the reason it is or is not drawn.
 * kinds: drawn · listed_unplaced · listed_plan · listed_tour · listed_none. Only spaces on the market are listed.
 */
export function floorAccounting({ building, catalog, floor, shownModels = [], footprintSqft = null }) {
  const record = (building.floors || []).find(f => f.floor === floor) || null;
  const floorSqft = record?.sqft || footprintSqft || null;
  const basis = record?.sqft ? "CoStar floor size" : footprintSqft ? "Vexcel footprint" : "";
  const assets = (catalog?.floors || []).find(f => f.floor === floor)?.assets || [];
  const shownIds = new Set(shownModels.map(m => String(m.space_id || "")).filter(Boolean));
  const parts = [];
  if (shownModels.length) {
    const drawn = drawnArea(shownModels, building.spaces || []);
    parts.push({ kind: "drawn", label: shownModels.map(m => m.space_id ? (m.suite ? `Suite ${m.suite}` : "Listed space") : (m.suite || m.label || "Linked geometry")).join(" + "),
      sqft: drawn.sqft, area_basis: drawn.basis, reason: drawn.reason });
  }
  for (const s of (building.spaces || []).filter(x => x.floor === floor)) {
    if (shownIds.has(String(s.id))) continue;
    const mine = assets.filter(a => String(a.space_id) === String(s.id));
    const base = { label: suiteName(s), sqft: s.sqft || null, space_id: String(s.id) };
    const placed = mine.find(a => a.geometry_available && a.registered);
    if (placed) {
      parts.push({ ...base, kind: "listed_unplaced", placed: true, reason: "A 3D model placed on this floor exists; choose it under Interior source to draw it here.",
        asset: placed.key });
    } else if (mine.some(a => a.geometry_available)) {
      parts.push({ ...base, kind: "listed_unplaced", reason: "A 3D model exists, but its position on this floor is not linked yet.",
        asset: mine.find(a => a.geometry_available).key });
    } else if (s.plan_url) {
      parts.push({ ...base, kind: "listed_plan", reason: "CoStar holds a floor plan image; its rooms are not traced into 3D yet.", url: s.plan_url });
    } else if ((s.scans || []).length) {
      parts.push({ ...base, kind: "listed_tour", reason: "A 3D tour exists, but it carries no wall data to draw from.", scan: s.scans[0] });
    } else {
      parts.push({ ...base, kind: "listed_none", reason: "On the market, but no floor plan or scan is on record." });
    }
  }
  const marketSqft = parts.filter(p => p.space_id).reduce((t, p) => t + (p.sqft || 0), 0);
  const onMarket = parts.filter(p => p.space_id).length + shownModels.filter(m => m.space_id).length;
  return { floor, floorSqft, basis, parts, onMarket, marketSqft,
    note: "Only spaces on the market are shown. Leased space and the rest of the floor are not part of this review." };
}

/** Grid lines clipped to one or more closed outlines (coordinates in metres). */
export function gridSegments(outlines, spacing) {
  const rings = outlines.filter(r => r && r.length >= 3);
  if (!rings.length || !(spacing > 0)) return [];
  const pts = rings.flat(), xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const edges = rings.flatMap(r => r.map((p, i) => [p, r[(i + 1) % r.length]]));
  const crossings = (value, axis) => {
    const out = [];
    for (const [a, b] of edges) {
      const [a0, a1, b0, b1] = axis === "y" ? [a[1], a[0], b[1], b[0]] : [a[0], a[1], b[0], b[1]];
      if ((a0 > value) !== (b0 > value)) out.push(a1 + (value - a0) / (b0 - a0) * (b1 - a1));
    }
    return out.sort((p, q) => p - q);
  };
  const segments = [];
  for (let y = Math.floor(minY / spacing) * spacing + spacing; y < maxY; y += spacing) { // edges are drawn by the outline
    const c = crossings(y + 1e-9, "y");
    for (let i = 0; i + 1 < c.length; i += 2) segments.push([c[i], y, c[i + 1], y]);
  }
  for (let x = Math.floor(minX / spacing) * spacing + spacing; x < maxX; x += spacing) {
    const c = crossings(x + 1e-9, "x");
    for (let i = 0; i + 1 < c.length; i += 2) segments.push([x, c[i], x, c[i + 1]]);
  }
  return segments;
}
