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
async function request(url, options) {
  const response = await fetch(url, options === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(options)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Cost calculation unavailable');
  return data;
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

export async function mountCosts(root, url) {
  root.innerHTML = '<p role="status">Loading cost inputs…</p>';
  try {
    const data = await request(url);
    if (!root.isConnected) return;
    const defaults = data.defaults, lines = data.scenarios.base.lines;
    root.innerHTML = `<h2>Conversion costs and income</h2><p class="cost-warning">Residential scope: ${esc(data.scope)}. Building-wide work is included at building quantities; costs are not allocated to a suite. Confirm that each quantity belongs in your project.</p>
      <form><div class="cost-controls"><label>Scenario<select name="scenario">${Object.entries(scenarios).map(([k,v]) => `<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
      ${input('units', defaults.income.units, 'Housing units (income only)', '1')}${input('horizon_years', 5, 'Comparison horizon (years)')}</div>
      <p class="sub">Unit count is a planning assumption, not a layout determination. Changing income units does not change work quantities; edit those below.</p>
      <fieldset><legend>Monthly asking rent per home ($)</legend>${rangeInputs('rent', defaults.income.monthly_rent_per_unit)}
      <p class="sub">CoStar studio floor plans within 3 miles; 25th / 50th / 75th percentiles, minimum 3 comparables. ${data.rent.count} matching plans. ${esc(data.rent.reason)} ${esc(data.rent.notes)}</p></fieldset>
      <fieldset><legend>Current monthly income for this same residential scope ($)</legend>${rangeInputs('current', null)}
      <p class="sub">Unknown until you enter it. A space on the market is not necessarily vacant. Use net income on the same basis as housing income.</p><button type="button" class="btn" data-vacant>Assume vacant: $0 today</button></fieldset>
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
      <div data-results>${resultsView(data)}</div>`;
    const form = root.querySelector('form'), status = root.querySelector('[data-status]');
    const field = name => form.elements.namedItem(name);
    const readRange = name => Object.fromEntries(levels.map(k => [k, numeric(field(`${name}.${k}`))]));
    const nullableRange = name => { const v = readRange(name); return Object.values(v).every(x => x == null) ? null : v; };
    form.addEventListener('input', () => { status.textContent = 'Inputs changed. Recalculate to update the results below.'; });
    root.querySelector('[data-vacant]').onclick = () => { levels.forEach(k => { field(`current.${k}`).value = 0; }); status.textContent = 'Vacancy assumed. Recalculate to update results.'; };
    form.onsubmit = async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]'); button.disabled = true;
      status.textContent = 'Calculating…';
      const options = {scenario:field('scenario').value, selected_keys:lines.filter(c => field(`pick.${c.key}`).checked).map(c => c.key),
        income:{units:numeric(field('units')), horizon_years:numeric(field('horizon_years')), monthly_rent_per_unit:nullableRange('rent'), current_monthly_income:nullableRange('current')},
        quantities:Object.fromEntries(lines.map(c => [c.key,numeric(field(`quantity.${c.key}`))])),
        prices:Object.fromEntries(lines.map(c => [c.key,{fixed:readRange(`price.${c.key}.fixed`), rate:readRange(`price.${c.key}.rate`)}])),
        globals:Object.fromEntries(Object.keys(defaults.globals).map(k => [k, readRange(`global.${k}`)]))};
      const controls = [...form.querySelectorAll('input, select, button')];
      controls.forEach(el => { el.disabled = true; });
      try {
        const result = await request(url, options);
        if (!root.isConnected) return;
        root.querySelector('[data-results]').innerHTML = resultsView(result);
        status.textContent = 'Results updated. Edited values are Team assumptions.';
      } catch (error) { status.textContent = `Could not recalculate: ${error.message}. Previous results remain below.`; }
      finally { controls.forEach(el => { el.disabled = false; }); }
    };
  } catch (error) { root.textContent = `Cost inputs unavailable: ${error.message}`; }
}
