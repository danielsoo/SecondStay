// Floor fan / isolation interaction informed by FireSight's explode.ts and Rooms.tsx.
// Independent implementation; no generated interior layouts are used.
export function floorPose(number, count, storyHeight, span, mode, selected) {
  if (!Number.isInteger(number) || number < 1 || number > count) throw new Error("Floor outside the recorded range");
  if (mode === "isolated") return { x: 0, y: (number - selected) * storyHeight * 3, z: 0, opacity: number === selected ? 1 : 0 };
  // Keep the building aligned; open space immediately around the selected story.
  const gap = Math.min(storyHeight * 1.6, span * 0.15);
  return { x: number === selected ? span * 0.32 : 0,
    y: (number - 1) * storyHeight + (number >= selected ? gap : 0) + (number > selected ? gap : 0), z: 0,
    opacity: number === selected ? 1 : 0.72 };
}

export function validFloor(value, count) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 1 && number <= count ? number : null;
}

export function sameScope(a, b) {
  return a.floor === b.floor && String(a.space_id || "") === String(b.space_id || "")
    && String(a.scan_id || "") === String(b.scan_id || "") && String(a.asset_key || "") === String(b.asset_key || "");
}

export function floorAssets(catalog, floor) {
  return catalog?.floors?.find(f=>f.floor===floor)?.assets || [];
}

export function chooseFloorAsset(catalog, floor, key, preferredSpace) {
  const assets = floorAssets(catalog, floor);
  const preferred = assets.filter(a=>preferredSpace && a.space_id===String(preferredSpace));
  const ranked = preferred.length ? preferred : assets;
  return assets.find(a=>a.key===key) || ranked.find(a=>a.geometry_available) || ranked.find(a=>a.plan_url) || ranked[0] || null;
}
