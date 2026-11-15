const levels = ['low', 'typical', 'high'];
const scenarios = {base: 'Called-for work', with_possible: 'Plus possible work', everything: 'All listed work', custom: 'My selection'};
const labels = {soft_cost_share: 'Soft costs / hard costs', contingency: 'Contingency share', months_to_convert: 'Conversion months', occupancy: 'Housing occupancy share', operating_cost_share: 'Operating cost share'};
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (v) => v == null ? 'Unavailable' : new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(v);
const range = (v, format = money) => v ? levels.map(k => format(v[k])).join(' / ') : 'Unavailable';
const numeric = (el) => el.value === '' ? null : Number(el.value);
function input(name, value, label, step = 'any') {
  return `<label>${esc(label)}<input type="number" min="0" step="${step}" name="${esc(name)}" value="${esc(value)}"></label>`;
}
function rangeInputs(name, values, label = '') {
  return `<div class="cost-range">${levels.map(k => input(`${name}.${k}`, values?.[k], `${label} ${k}`.trim())).join('')}</div>`;
}
function source(entry) {
  const url = /^https?:\/\//.test(entry?.source || '') ? `<a href="${esc(entry.source)}" target="_blank" rel="noopener">Source</a>` : esc(entry?.source || 'No source; not priced');
  return `<p class="sub">${url} · ${esc(entry?.confidence)}${entry?.published ? ' · published ' + esc(entry.published) : ''}${entry?.accessed ? ' · accessed ' + esc(entry.accessed) : ''}<br>${esc(entry?.notes)} ${esc(entry?.excludes)}</p>`;
}
async function request(url, options, limitMs = 0) {
  const init = options === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(options)};
  if (limitMs) init.signal = AbortSignal.timeout(limitMs);
  let response;
  try { response = await fetch(url, init); }
  catch (error) {
    if (error.name === 'TimeoutError') throw new Error(`no answer after ${Math.round(limitMs / 1000)} seconds. The check keeps running on the server; try again in a minute and a finished result opens at once`);
    throw error;
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Cost calculation unavailable');
  return data;
}
const plain = (v) => String(v ?? '').replace(/_/g, ' ');
const qty = (q, unit) => q == null ? 'quantity not known' : `${Math.round(q).toLocaleString('en-US')} ${unit === 'sqft' ? 'sq ft' : unit === 'each' ? '' : unit}`.trim();
function photosView(data) {
  const m = data.minimum || {}, p = data.photos || {};
  const figures = m.low == null ? '<p class="sub">No called-for work has a price yet.</p>' : `
    <div class="cost-figure"><b>${money(m.low)}</b><span>typical ${money(m.typical)}</span></div>`;
  const la = data.la_prices || {}, laPrices = la.prices || {};
  const perUnit = unit => unit === 'each' ? 'each' : unit === 'sqft' ? 'per sq ft' : `per ${unit}`;
  const evidence = e => `<details class="la-permits"><summary>Based on ${e.permits} LA permits, ${esc(e.period[0])} to ${esc(e.period[1])}: ${money(e.rate.low)} / ${money(e.rate.typical)} / ${money(e.rate.high)} ${perUnit(e.unit)}</summary>
      <p class="sub">${esc(e.notes)} ${esc(e.excludes)}</p>
      <table><thead><tr><th>Permit</th><th>Issued</th><th>Declared value</th><th>Per unit</th><th>Scope (model summary)</th></tr></thead><tbody>
      ${e.examples.map(x => `<tr><td>${esc(x.permit)}</td><td>${esc(x.issued)}</td><td>${money(x.value)}</td><td>${money(x.per_unit)}</td><td>${esc(x.scope)}</td></tr>`).join('')}</tbody></table>
      <p class="sub"><a href="${esc(e.source)}" target="_blank" rel="noopener">Open the LADBS permit dataset</a></p></details>`;
  const included = (m.included || []).map(i => `<li><b>${esc(i.title)}</b> · ${esc(qty(i.quantity, i.unit))} · from ${money(i.low)}<br><span class="sub">${esc(i.basis)}</span>
    ${laPrices[i.key] ? evidence(laPrices[i.key]) : `<br><span class="sub">Price source: ${/^https?:/.test(i.source || '') ? `<a href="${esc(i.source)}" target="_blank" rel="noopener">published source</a>` : esc(i.source)}</span>`}</li>`).join('');
  const bench = Object.entries(la.benchmarks || {}).map(([k, e]) => `<li>${esc(e.measures || k)}: ${money(e.rate.low)} / ${money(e.rate.typical)} / ${money(e.rate.high)} ${perUnit(e.unit)} across ${e.permits} permits</li>`).join('')
    + (la.published || []).map(f => `<li>${esc(f.measures)}: <b>${money(f.value)}</b> per ${esc(f.unit)} (${esc(f.year)}) · <a href="${esc(f.source)}" target="_blank" rel="noopener">source</a><br><span>${esc(f.note)}</span></li>`).join('');
  const quote = (m.to_quote || []).map(i => `<li><b>${esc(i.title)}</b> · ${esc(qty(i.quantity, i.unit))}<br><span class="sub">${esc(i.reason)}</span></li>`).join('');
  let photos;
  if (!p.available) photos = `<p class="sub">${esc(p.reason)}</p>`;
  else if (!p.read && p.can_read === false) photos = `<p class="sub">${esc(p.reason)}</p>`;
  else if (!p.read) photos = `<p class="sub">AI checks the tour photos for sprinkler heads, alarm devices, exit signs, water lines and windows, and updates the work list. It never sets a price.</p>
    <button type="button" class="btn" data-read-photos>Check the photos with AI</button><p class="sub">Usually under a minute; the first check of a tour also gathers its photos.</p>${p.reason && p.reason !== 'Not read yet.' ? `<p class="sub">${esc(p.reason)}</p>` : ''}`;
  else photos = `<ul class="cost-factors">${(p.considered || []).map(f => `<li><b>${esc(f.label)}</b>: ${esc(plain(f.seen))}<br>
      <span class="sub">${esc(f.effect)}${f.evidence ? ' Seen: ' + esc(f.evidence) + '.' : ''}</span></li>`).join('')}</ul>
    <p class="sub">Photos ${esc(p.method)} by ${esc(p.model)}. ${esc(p.notes)}</p>`;
  const nIncluded = (m.included || []).length, nQuote = (m.to_quote || []).length;
  return `<section class="cost-photos"><h3>Cost details</h3>${figures}
    <p class="cost-sum">${nIncluded} priced item${nIncluded === 1 ? '' : 's'}${nQuote ? ` · <span class="to-quote-count">${nQuote} still to quote</span>` : ''} · not a quote</p>
    <details class="fold" data-panel="what"><summary>What is in this figure</summary>
      <p class="sub">Called-for work at the low end of LA prices, plus soft costs and contingency. A site visit and contractor pricing set the real figure.</p>
      ${included ? `<ul class="cost-factors">${included}</ul>` : ''}
      ${quote ? `<h4>Still to quote, not in the figure</h4><ul class="cost-factors to-quote">${quote}</ul>` : ''}
      <p class="sub">Not counted: ${m.possible || 0} possible and ${m.unknown || 0} unknown items that need confirmation.</p>
      ${m.one_home ? `<p class="sub">One home alone still brings the whole building under the rules: ${money(m.one_home.building.low)} of priced building-wide work${m.one_home.building_to_quote.length ? ` (${esc(m.one_home.building_to_quote.join(', '))} still to quote)` : ''} plus ${money(m.one_home.per_home.low)} for one home's average ${esc(m.one_home.per_home_items.join(', ').toLowerCase())}: at least ${money(m.one_home.total.low)}.${m.one_home.building_if_needed ? ` Items still to confirm would add ${money(m.one_home.building_if_needed.low)} if they are needed: ${esc(m.one_home.building_if_needed_items.map(i => `${i.title} ${money(i.low)}${i.per_home ? " (one home's share)" : ''}`).join('; '))}.` : ''}${(m.one_home.building_possible_unpriced || []).length ? ` No price yet: ${esc(m.one_home.building_possible_unpriced.join(', '))}.` : ''}</p>` : ''}
      ${la.built ? `<p class="sub">LA prices: ${la.permits_kept.toLocaleString('en-US')} building permits read by a language model, built ${esc(la.built)}. Declared values run below final cost.</p>` : ''}
      ${bench ? `<details><summary>Other LA figures, for comparison</summary><ul class="sub">${bench}</ul></details>` : ''}
    </details>
    <details class="fold" data-panel="photos"><summary>Tour photo check${p.read ? '' : p.available ? ' · not run yet' : ''}</summary>${photos}</details></section>`;
}
// What the homes could earn: the AI-chosen comparables, the neighbourhood, and the rent range computed from them.
const PLACE_LABELS = {rail_station:'Rail station', fire_station:'Fire station', police:'Police station', hospital:'Hospital',
  supermarket:'Supermarkets', park:'Parks', school:'Schools'};
function incomeView(data) {
  const r = data.income_research || {}, rent = data.rent || {}, per = rent.monthly_rent_per_unit;
  const pay = data.scenarios?.[data.scenario]?.payback, units = data.income?.units;
  const netYear = pay?.monthly_net_income?.typical != null ? pay.monthly_net_income.typical * 12 : null;
  // The big figure lives in the "Could rent for" card at the top of the page; this fold holds the method behind it.
  const figure = per ? `<p class="sub">${money(per.low)} to ${money(per.high)} a month per home${units ? ` · ${units.toLocaleString('en-US')} homes` : ''}${netYear != null ? ` · ${money(netYear)} a year after vacancy and operating costs` : ''} · asking rents, not achieved.</p>`
    : `<p class="sub">${esc(rent.reason || 'No rent figure yet.')}</p>`;
  if (!r.read) {
    return `<details class="fold income-fold" data-panel="income"><summary>What the homes could earn${per ? ` · ${money(per.typical)} a month per home` : ''}</summary>${figure}
      <p class="sub">${per ? 'Now: every studio floor plan within 3 miles. ' : ''}AI can pick the nearby communities that resemble this tower, using their neighbourhoods (stations, fire and police, shops, parks, schools); the rent is then computed from their floor plans.</p>
      <button type="button" class="btn" data-read-income>Research the income with AI</button>
      <div class="ai-progress" data-income-progress hidden></div>
      ${r.reason && r.reason !== 'Not researched yet.' ? `<p class="sub">${esc(r.reason)}</p>` : ''}</details>`;
  }
  const t = r.target?.profile || {};
  const place = k => { const p = t[k] || {}; return ['supermarket', 'park', 'school'].includes(k)
    ? `<li><b>${PLACE_LABELS[k]}</b> · ${p.within_walk ?? 0} within 0.5 mi${p.miles != null ? `<br><span class="sub">nearest ${p.miles.toFixed(1)} mi${p.name ? ', ' + esc(p.name) : ''}</span>` : ''}</li>`
    : `<li><b>${PLACE_LABELS[k]}</b> · ${p.miles != null ? p.miles.toFixed(1) + ' mi' : 'none within 4 mi'}${p.name ? `<br><span class="sub">${esc(p.name)}</span>` : ''}</li>`; };
  // Dot strip: every similar-size floor plan in range, scaled to one home, by how the AI rated its community.
  const pts = r.points || [], lanes = [['close', 'Close'], ['partial', 'Partial'], ['not used', 'Not used']];
  const vals = pts.map(p => p.rent), lo = Math.min(...vals, per?.low ?? Infinity), hi = Math.max(...vals, per?.high ?? 0);
  const W = 520, x = v => 80 + ((v - lo) / Math.max(1, hi - lo)) * (W - 100);
  const dots = pts.map(p => { const lane = lanes.findIndex(l => l[0] === p.match); return `<circle cx="${x(p.rent).toFixed(1)}" cy="${22 + lane * 24 + ((p.rent * 7) % 9) - 4}" r="${p.match === 'not used' ? 2.2 : 3.4}" style="fill:${p.match === 'close' ? 'var(--accent)' : p.match === 'partial' ? 'var(--amber)' : 'var(--muted)'};opacity:${p.match === 'not used' ? 0.45 : 0.9}"/>`; }).join('');
  const band = per ? `<rect x="${x(per.low)}" y="8" width="${Math.max(1, x(per.high) - x(per.low))}" height="72" style="fill:var(--accent);opacity:.08"/>
    <line x1="${x(per.typical)}" x2="${x(per.typical)}" y1="6" y2="82" style="stroke:var(--ink);stroke-width:1.5"/>
    <text x="${x(per.typical)}" y="96" text-anchor="middle" style="fill:var(--ink);font:600 11px var(--mono)">${money(per.typical)}</text>` : '';
  const chart = pts.length ? `<svg viewBox="0 0 ${W} 112" style="width:100%;height:auto;display:block;margin-top:8px" role="img" aria-label="Rent per home of nearby floor plans">
    ${band}${lanes.map(([, label], i) => `<text x="0" y="${26 + i * 24}" style="fill:var(--muted);font:11px var(--mono)">${label}</text>`).join('')}${dots}
    <text x="80" y="110" style="fill:var(--muted);font:10px var(--mono)">${money(lo)}</text><text x="${W - 20}" y="110" text-anchor="end" style="fill:var(--muted);font:10px var(--mono)">${money(hi)}</text></svg>
    <p class="sub">Each dot is one floor plan of 350 to 800 sq ft within 3 miles, its asking rent scaled to a ${esc(r.target?.unit_sqft || 500)} sq ft home. The shaded band is the range used; the line is the typical rent.</p>` : '';
  const comps = (r.comparables || []).map(c => `<li><b>${c.match === 'close' ? 'Close' : 'Partial'}</b> · ${c.miles.toFixed(1)} mi · ${esc(c.style || 'style unknown')}${c.stories ? `, ${c.stories} stories` : ''}${c.year ? `, built ${c.year}` : ''}${c.per_home ? ` · ${money(c.per_home)} per home` : ' · no plan of a similar size'}<br><span class="sub">${esc(c.reason)}</span></li>`).join('');
  const evidence = [
    r.vacancy_percent != null ? `Vacancy reported at the chosen communities: ${r.vacancy_percent}% (the income uses the project's occupancy assumption).` : '',
    r.station ? `Floor plans within 0.5 mi of a rail station ask ${money(r.station.near_median)} per home against ${money(r.station.far_median)} farther away (${r.station.near_plans} and ${r.station.far_plans} plans).` : 'Too few plans sit near a rail station to compare.',
    r.furnished ? `Furnished corporate housing nearby: ${money(r.furnished.median)} per home across ${r.furnished.plans} plans.` : '',
    r.rentals?.count ? `Homes for rent nearby (Homes.com): ${r.rentals.count}, ${r.rentals.leased} with an agreed rent; median ${money(r.rentals.median_rent)} a month.` : '',
  ].filter(Boolean).map(e => `<li>${esc(e)}</li>`).join('');
  return `<details class="fold income-fold" data-panel="income"><summary>What the homes could earn${per ? ` · ${money(per.typical)} a month per home · researched` : ''}</summary>${figure}${chart}
    <button type="button" class="btn" data-read-income>Research again with AI</button>
    <div class="ai-progress" data-income-progress hidden></div>
    <details class="fold"><summary>The neighbourhood</summary><ul class="cost-factors">${Object.keys(PLACE_LABELS).map(place).join('')}</ul>
      <p class="sub">${r.places_note ? esc(r.places_note) : `From OpenStreetMap, ${r.places_found} public places within 4 miles. The same profile was read for every community compared.`}</p></details>
    <details class="fold"><summary>Comparables chosen by AI · ${(r.comparables || []).length} of ${r.considered}</summary><ul class="cost-factors">${comps}</ul>
      <p class="sub">${esc(r.notes)}</p></details>
    <details class="fold"><summary>Other evidence, not added to the figure</summary><ul class="cost-factors">${evidence}</ul></details>
    <p class="sub">Comparables chosen by ${esc(r.model)} from CoStar apartment listings and property records; every figure is computed from the chosen floor plans, as asking rents, not achieved rents.</p></details>`;
}
function resultsView(data) {
  const result = data.scenarios[data.scenario], pay = result.payback;
  const years = v => v == null ? 'No payback' : `${v.toFixed(1)} years`;
  const reason = (key) => esc(typeof pay?.reasons[key] === 'object' ? Object.entries(pay.reasons[key]).map(([k,v]) => `${k}: ${v}`).join('; ') : pay?.reasons[key]);
  return `<h3>${esc(scenarios[data.scenario])}</h3>
    <p class="cost-warning">${result.partial ? `Partial estimate: ${result.left_out.length} selected items are unpriced or have unknown quantities. Totals and payback use only the priced subset; they are not a full project budget.` : 'Totals cover only listed work with the inputs below; additional project costs may exist.'}</p>
    <p class="sub">Ranges below: low / typical / high. Low payback is favorable; low income and gain are adverse.</p>
    <dl class="cost-totals">
      <dt>Hard costs</dt><dd>${range(result.subtotal)}</dd>
      <dt>Soft costs</dt><dd>${range(result.soft_costs)}</dd>
      <dt>Contingency</dt><dd>${range(result.contingency)}</dd>
      <dt>${result.partial ? 'Priced subset total' : 'Listed work total'}</dt><dd><strong>${range(result.total)}</strong> ${esc(result.total_reason)}</dd>
      <dt>Monthly net housing income</dt><dd>${range(pay?.monthly_net_income)} ${reason('monthly_net_income')}</dd>
      <dt>Monthly gain over today</dt><dd>${range(pay?.monthly_gain)} ${reason('monthly_gain')}</dd>
      <dt>Simple payback, including conversion time</dt><dd>${range(pay?.payback_years, years)} ${reason('payback_years')}</dd>
      <dt>Gain over ${esc(pay?.horizon_years)} years</dt><dd>${range(pay?.gain_over_horizon)} ${reason('gain_over_horizon')}</dd>
    </dl>
    ${result.left_out.length ? `<h4>Selected work left out of the total</h4><ul>${result.left_out.map(x => `<li><b>${esc(x.title)}</b>: ${esc(x.reason)}</li>`).join('')}</ul>` : ''}
    ${result.not_in_scenario.length ? `<details><summary>${result.not_in_scenario.length} items excluded by this scenario</summary><ul>${result.not_in_scenario.map(x => `<li>${esc(x.title)} (${esc(x.certainty)})</li>`).join('')}</ul></details>` : ''}
    <h4>Compare scenarios</h4><div class="cost-scroll"><table><thead><tr><th>Scenario</th><th>Total low / typical / high</th><th>Unpriced selected items</th><th>Difference from called-for work</th></tr></thead><tbody>
    ${Object.entries(data.scenarios).map(([k,v]) => `<tr><th>${esc(scenarios[k])}${v.partial ? ' · partial' : ''}</th><td>${range(v.total)}</td><td>${v.left_out.length}</td><td>${range(v.difference_from_base)}</td></tr>`).join('')}</tbody></table></div>
    <h4>Three inputs that move payback most</h4><p class="sub">One input varies across its range at a time; all other inputs stay fixed. This uses the priced subset when the estimate is partial.</p>
    ${data.sensitivity.ranking.length ? `<ul>${data.sensitivity.ranking.map(x => `<li><b>${esc(labels[x.name] || x.name)}</b>: ${years(x.payback_at_low)} → ${years(x.payback_at_high)}${source(x.input)}</li>`).join('')}</ul>` : `<p>${esc(data.sensitivity.reason || 'No sensitivity result available.')}</p>`}
    <details><summary>Applied line costs and sources</summary>${result.lines.filter(x => x.in_scenario).map(x => `<h4>${esc(x.title)} · ${esc(x.scope)}</h4><p>${esc(x.quantity ?? 'Unknown quantity')} ${esc(x.unit)} · ${esc(x.quantity_basis)}<br>${range(x.cost)} · ${esc(x.reason)}</p>${source(x)}`).join('')}
    <h4>Applied income and project assumptions</h4>${Object.entries({...result.inputs, ...pay?.inputs}).map(([k,v]) => `<p><b>${esc(labels[k] || k)}</b>: ${esc(JSON.stringify(v.value))}</p>${source(v)}`).join('')}</details>`;
}

export async function mountCosts(root, url, onData = () => {}) {
  root.innerHTML = '<p role="status">Loading cost inputs…</p>';
  try {
    const data = await request(url);
    if (!root.isConnected) return;
    const defaults = data.defaults, lines = data.scenarios.base.lines;
    onData(data);
    root.innerHTML = `<div data-photos>${photosView(data)}</div><div data-income>${incomeView(data)}</div>
      <details class="fold cost-more" data-panel="more"><summary>Scenarios, income and assumptions</summary>
      <p class="cost-warning">Residential scope: ${esc(data.scope)}. Building-wide work is counted at building quantities.</p>
      <form><div class="cost-controls"><label>Scenario<select name="scenario">${Object.entries(scenarios).map(([k,v]) => `<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
      ${input('units', defaults.income.units, 'Housing units (income only)', '1')}${input('horizon_years', 5, 'Comparison horizon (years)')}</div>
      <p class="sub">Unit count is a planning assumption, not a layout determination. Changing income units does not change work quantities; edit those below.</p>
      <fieldset><legend>Monthly asking rent per home ($)</legend>${rangeInputs('rent', defaults.income.monthly_rent_per_unit)}
      <p class="sub">${data.rent.method === 'ai_selected_comparables' ? `Researched: ${esc(data.rent.notes)}` : `CoStar studio floor plans within 3 miles; 25th / 50th / 75th percentiles, minimum 3 comparables. ${data.rent.count} matching plans. ${esc(data.rent.reason)} ${esc(data.rent.notes)}`}</p></fieldset>
      <fieldset><legend>Current monthly income for this same residential scope ($)</legend>${rangeInputs('current', defaults.income.current_monthly_income)}
      <p class="sub">Set to $0: the owner's office is taken as unused today. If it is leased, enter today's net income on the same basis as housing income.</p><button type="button" class="btn" data-vacant>Assume vacant: $0 today</button></fieldset>
      <details><summary>Work quantities, prices and custom selection</summary><p class="sub">Prices are fixed dollars plus dollars per unit. Enter all six values to price an item. Edits are labelled Team assumptions. Unknown prices remain blank. Checkboxes affect “My selection” only.</p>
      ${lines.map(c => `<fieldset data-line="${esc(c.key)}"><legend>${esc(c.title)} · ${esc(c.certainty)} · ${esc(c.scope)}</legend>
        <label class="cost-check"><input type="checkbox" name="pick.${esc(c.key)}" ${c.in_scenario ? 'checked' : ''}> Include in my selection</label>
        ${input(`quantity.${c.key}`, c.quantity, `Quantity (${c.unit})`)}<p class="sub">${esc(c.quantity_basis)}</p>
        <div>Fixed charge ($)</div>${rangeInputs(`price.${c.key}.fixed`, defaults.prices[c.key]?.fixed, 'Fixed')}
        <div>Rate ($ / ${esc(c.unit)})</div>${rangeInputs(`price.${c.key}.rate`, defaults.prices[c.key]?.rate, 'Rate')}
        <details><summary>Original price-book source (before edits)</summary>${source(defaults.prices[c.key])}</details></fieldset>`).join('')}</details>
      <details><summary>Project assumptions</summary><p class="sub">Shares are fractions from 0 to 1; 0.25 means 25%. Soft costs apply to hard costs; contingency applies to hard plus soft costs.</p>
      ${Object.entries(defaults.globals).map(([k,v]) => `<fieldset><legend>${esc(labels[k] || k)}</legend>${rangeInputs(`global.${k}`, v)}<details><summary>Original assumption source (before edits)</summary>${source(v)}</details></fieldset>`).join('')}</details>
      <p class="sub">Edits last on this screen only and reset when you switch spaces or scans.</p>
      <button class="btn" type="submit">Recalculate</button><p data-status role="status" aria-live="polite"></p></form>
      <div data-results>${resultsView(data)}</div></details>`;
    // Sub-tabs: the figure stays on top and one part of the detail shows at a time.
    const SUBTABS = [['what', 'What is in the figure'], ['photos', 'Photo check'], ['income', 'What it could earn'], ['more', 'Scenarios and assumptions']];
    root.classList.add('tabbed');
    root.dataset.sub = root.dataset.sub || 'what';
    root.insertAdjacentHTML('afterbegin', `<nav class="cost-subtabs" role="tablist" aria-label="Cost details">${SUBTABS.map(([k, v]) =>
      `<button type="button" role="tab" data-sub="${k}">${v}</button>`).join('')}</nav>`);
    const openPanels = () => root.querySelectorAll('[data-panel]').forEach(d => { d.open = true; });
    const showSub = (k) => { root.dataset.sub = k; root.querySelectorAll('.cost-subtabs [data-sub]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.sub === k))); };
    root.querySelectorAll('.cost-subtabs [data-sub]').forEach(b => { b.onclick = () => showSub(b.dataset.sub); });
    openPanels(); showSub(root.dataset.sub);
    const form = root.querySelector('form'), status = root.querySelector('[data-status]');
    let readPhotos = false, clock = 0;
    const bindPhotos = () => {
      const button = root.querySelector('[data-read-photos]');
      if (button) button.onclick = () => {
        readPhotos = true; button.disabled = true;
        const started = Date.now(), tick = () => { button.textContent = `Checking the photos… ${Math.round((Date.now() - started) / 1000)} s`; };
        tick(); clock = setInterval(tick, 1000); form.requestSubmit();
      };
    };
    bindPhotos();
    let readIncome = false;
    // Live progress while the research runs: the server reports its stage; the bar eases toward the next one.
    const progressUrl = url.replace(/\/cost(\?.*)?$/, '/income-progress');
    let watch = 0;
    const watchIncome = () => {
      const box = root.querySelector('[data-income-progress]');
      if (!box) return;
      box.hidden = false; box.classList.remove('done');
      box.innerHTML = '<span class="ring" aria-hidden="true"></span><span class="msg">Starting the research…</span><span class="pct">1%</span><div class="bar"><span></span></div>';
      let shown = 1, target = 3, ceiling = 30;
      const paint = (msg) => {
        shown = Math.min(ceiling - 1, Math.max(shown, target) + Math.max(0.15, (ceiling - shown) * 0.02));
        box.querySelector('.pct').textContent = `${Math.round(shown)}%`;
        box.querySelector('.bar span').style.width = `${shown}%`;
        if (msg) box.querySelector('.msg').textContent = msg;
      };
      const next = { 3: 35, 35: 55, 55: 88, 88: 99 };
      watch = setInterval(async () => {
        let msg = '';
        try {
          const p = await (await fetch(progressUrl)).json();
          if (p.running) { target = p.percent; ceiling = next[p.percent] ?? 99; msg = p.message; }
        } catch {}
        paint(msg);
      }, 1000);
    };
    const stopIncome = (ok) => {
      clearInterval(watch);
      const box = root.querySelector('[data-income-progress]');
      if (!box || box.hidden) return;
      box.classList.add('done');
      box.querySelector('.pct').textContent = ok ? '100%' : '–';
      box.querySelector('.bar span').style.width = ok ? '100%' : '0';
      box.querySelector('.msg').textContent = ok ? 'Research finished' : 'The research stopped';
    };
    let aiAllowed = true;
    fetch('/api/agent').then(r => r.json()).then(c => { aiAllowed = c.ai_allowed !== false; bindIncome(); }).catch(() => {});
    const bindIncome = () => {
      const button = root.querySelector('[data-read-income]');
      if (!button) return;
      if (!aiAllowed) {
        button.disabled = true;
        if (!button.nextElementSibling?.classList.contains('ai-locked')) button.insertAdjacentHTML('afterend', '<p class="ai-locked">AI runs open with the judges\' link.</p>');
        return;
      }
      button.onclick = () => { readIncome = true; button.disabled = true; button.textContent = 'Researching…'; showSub('income'); watchIncome(); form.requestSubmit(); };
    };
    bindIncome();
    const field = name => form.elements.namedItem(name);
    const readRange = name => Object.fromEntries(levels.map(k => [k, numeric(field(`${name}.${k}`))]));
    const nullableRange = name => { const v = readRange(name); return Object.values(v).every(x => x == null) ? null : v; };
    form.addEventListener('input', () => { status.textContent = 'Inputs changed. Recalculate to update the results below.'; });
    root.querySelector('[data-vacant]').onclick = () => { levels.forEach(k => { field(`current.${k}`).value = 0; }); status.textContent = 'Vacancy assumed. Recalculate to update results.'; };
    form.onsubmit = async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]'); button.disabled = true;
      status.textContent = 'Calculating…';
      const options = {read_photos:readPhotos, scenario:field('scenario').value, selected_keys:lines.filter(c => field(`pick.${c.key}`).checked).map(c => c.key),
        income:{units:numeric(field('units')), horizon_years:numeric(field('horizon_years')), monthly_rent_per_unit:nullableRange('rent'), current_monthly_income:nullableRange('current')},
        quantities:Object.fromEntries(lines.map(c => [c.key,numeric(field(`quantity.${c.key}`))])),
        prices:Object.fromEntries(lines.map(c => [c.key,{fixed:readRange(`price.${c.key}.fixed`), rate:readRange(`price.${c.key}.rate`)}])),
        globals:Object.fromEntries(Object.keys(defaults.globals).map(k => [k, readRange(`global.${k}`)]))};
      if (readIncome) { options.read_income = true; delete options.income.monthly_rent_per_unit; } // the research sets the rent
      const controls = [...form.querySelectorAll('input, select, button')];
      controls.forEach(el => { el.disabled = true; });
      try {
        // The AI reads can take a while; give up waiting after a set time rather than spin without end.
        const result = await request(url, options, readIncome ? 240000 : readPhotos ? 150000 : 60000);
        if (!root.isConnected) return;
        root.querySelector('[data-results]').innerHTML = resultsView(result);
        root.querySelector('[data-photos]').innerHTML = photosView(result); bindPhotos(); onData(result);
        if (readIncome) stopIncome(Boolean(result.income_research?.read));
        root.querySelector('[data-income]').innerHTML = incomeView(result); bindIncome();
        openPanels();
        if (readIncome) showSub('income'); else if (readPhotos) showSub('photos'); // show what was just read
        if (readIncome && result.income_research?.read) levels.forEach(k => { field(`rent.${k}`).value = result.income.monthly_rent_per_unit?.[k] ?? ''; });
        status.textContent = readIncome ? (result.income_research?.read ? 'Income researched. The rent and payback now use the chosen comparables.' : 'The income research did not finish; the earlier rent is kept.')
          : readPhotos ? 'Photos checked. The work list and minimum now reflect them.' : 'Results updated. Edited values are Team assumptions.';
      } catch (error) {
        status.textContent = `Could not recalculate: ${error.message}. Previous results remain below.`;
        const photoButton = root.querySelector('[data-read-photos]');
        if (readPhotos && photoButton) { photoButton.disabled = false; photoButton.textContent = 'Check the photos with AI'; photoButton.insertAdjacentHTML('afterend', `<p class="sub">${esc(error.message)}.</p>`); }
      }
      finally { clearInterval(clock); if (readIncome) stopIncome(false); readPhotos = false; readIncome = false; controls.forEach(el => { el.disabled = false; }); }
    };
  } catch (error) { root.textContent = `Cost inputs unavailable: ${error.message}`; }
}
