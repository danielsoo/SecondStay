// Permits per year on a building's parcel, read from the Tiger Data continuous aggregate.
// permitYearsSvg is pure, so it can be tested without a browser.

const money = (v) => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}k` : `$${Math.round(v)}`);

export function permitYearsSvg(years, now = new Date().getFullYear()) {
  const rows = (years || []).filter((r) => Number.isFinite(r.year) && r.permits > 0);
  if (!rows.length) return "";
  const start = Math.min(...rows.map((r) => r.year)), end = Math.max(now, ...rows.map((r) => r.year));
  const W = 520, H = 120, base = 86, top = 14, span = Math.max(1, end - start + 1);
  const slot = (W - 32) / span, peak = Math.max(...rows.map((r) => r.permits));
  const bars = rows.map((r) => {
    const h = Math.max(1.5, (r.permits / peak) * (base - top)), x = 16 + (r.year - start) * slot;
    const value = r.declared_valuation ? ` · ${money(r.declared_valuation)} declared on ${r.valued}` : "";
    return `<rect x="${(x + slot * 0.12).toFixed(1)}" y="${(base - h).toFixed(1)}" width="${Math.max(1, slot * 0.76).toFixed(1)}" height="${h.toFixed(1)}" rx="1" class="tl-dot"><title>${r.year}: ${r.permits} permit${r.permits === 1 ? "" : "s"}${value}</title></rect>`;
  }).join("");
  const busiest = rows.reduce((a, b) => (b.permits > a.permits ? b : a));
  const ticks = [...new Set([start, Math.round((start + end) / 2), end])].map((y) => {
    const x = 16 + (y - start + 0.5) * slot;
    return `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${base}" y2="${base + 5}" class="tl-axis"/><text x="${x.toFixed(1)}" y="${base + 18}" text-anchor="middle" class="tl-text">${y}</text>`;
  }).join("");
  const total = rows.reduce((t, r) => t + r.permits, 0);
  const declared = rows.reduce((t, r) => t + (r.declared_valuation || 0), 0), valued = rows.reduce((t, r) => t + (r.valued || 0), 0);
  return `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Permits on this parcel by year">
      <line x1="16" x2="${W - 16}" y1="${base}" y2="${base}" class="tl-axis"/>${ticks}${bars}
      <text x="16" y="10" class="tl-text strong">${total.toLocaleString("en-US")} permits since ${start} · busiest ${busiest.year} (${busiest.permits})</text></svg>
    <p class="legend">Every LADBS permit on the parcel, counted per year by a Tiger Data continuous aggregate.${valued ? ` ${money(declared)} declared on ${valued} of them; declared valuation is what the applicant wrote, not what the work cost.` : ""} Permits record work that was filed, not what is installed today.</p>`;
}

export async function mountPermitYears(host, propertyId) {
  if (!host || !propertyId) return;
  try {
    const response = await fetch(`/api/spaces/${encodeURIComponent(propertyId)}/permit-years.json`);
    if (!response.ok) return; // no database configured: the per-topic timeline above still stands
    const data = await response.json();
    if (!host.isConnected) return;
    const svg = permitYearsSvg(data.years);
    if (svg) host.innerHTML = `<h3 style="margin-top:18px">All permits on this parcel, by year</h3>${svg}`;
  } catch {
    // network or database unavailable: show nothing rather than a guess
  }
}
