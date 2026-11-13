const byId = id => document.getElementById(id);
let dashboard;
let selectedDistrict;
let charts = {};
const palette = { teal: '#087f82', paleTeal: '#9dd9d7', grid: '#d6e2e5', ink: '#173042', muted: '#536878' };
Chart.defaults.font.family = "'DM Sans', Arial, sans-serif"; Chart.defaults.color = palette.muted; Chart.defaults.borderColor = palette.grid;

async function requestPlan() {
  const values = dashboard.features.map((_, index) => Number(byId(`input-${index}`).value));
  byId('form-message').textContent = 'Calculating your service scenario…';
  const response = await fetch('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ district_id: selectedDistrict.id, values }) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'The scenario could not be calculated.');
  renderPlan(payload); byId('form-message').textContent = payload.notice;
}

async function init() {
  try {
    const response = await fetch('/api/dashboard'); if (!response.ok) throw new Error('Website data is unavailable. Run website/scripts/build_dashboard_data.py once.');
    dashboard = await response.json(); populateStates(); selectedDistrict = dashboard.districts[0]; populateDistricts(); createCharts(); renderDistrict(); await requestPlan();
    byId('state-select').addEventListener('change', async () => { populateDistricts(); await requestPlan(); });
    byId('district-select').addEventListener('change', async event => { selectedDistrict = dashboard.districts.find(row => row.id === event.target.value); renderDistrict(); await requestPlan(); });
    byId('reset-button').addEventListener('click', async () => { renderInputs(selectedDistrict.values); await requestPlan(); });
    byId('calculate-button').addEventListener('click', async () => { try { await requestPlan(); } catch (error) { byId('form-message').textContent = error.message; } });
  } catch (error) { byId('form-message').textContent = error.message; }
}

function populateStates() { byId('state-select').innerHTML = '<option value="all">All states</option>' + [...new Set(dashboard.districts.map(row => row.state))].sort().map(state => `<option value="${escapeHtml(state)}">${escapeHtml(state)}</option>`).join(''); }
function populateDistricts() { const state = byId('state-select').value; const candidates = dashboard.districts.filter(row => state === 'all' || row.state === state); byId('district-select').innerHTML = candidates.map(row => `<option value="${escapeHtml(row.id)}">${escapeHtml(row.district)}, ${escapeHtml(row.state)}</option>`).join(''); selectedDistrict = candidates[0]; renderDistrict(); }
function renderDistrict() { byId('district-select').value = selectedDistrict.id; byId('baseline-segment').textContent = selectedDistrict.cluster_label; byId('selected-place').textContent = `${selectedDistrict.district}, ${selectedDistrict.state}`; renderInputs(selectedDistrict.values); }
function groupFor(label) { const text = label.toLowerCase(); if (text.includes('water') || text.includes('sanitation') || text.includes('insurance')) return 'Household access and protection'; if (text.includes('child') || text.includes('vaccine') || text.includes('vitamin')) return 'Child health and immunisation'; return 'Maternal and birth care'; }
function renderInputs(values) { const groups = new Map(); dashboard.features.forEach((feature, index) => { const name = groupFor(feature.label); if (!groups.has(name)) groups.set(name, []); groups.get(name).push({ feature, index, value: values[index] }); }); byId('input-groups').innerHTML = [...groups].map(([name, items]) => `<section class="input-group"><h4>${name}</h4>${items.map(({ feature, index, value }) => `<div class="input-row"><label for="input-${index}">${escapeHtml(feature.short_label)}<small>Dataset range: ${feature.min}%–${feature.max}%</small></label><input id="input-${index}" type="number" min="${feature.min}" max="${feature.max}" step="0.1" value="${Number(value).toFixed(1)}" aria-label="${escapeHtml(feature.label)} percentage"></div>`).join('')}</section>`).join(''); }
function createCharts() { charts.score = new Chart(byId('score-chart'), { type: 'bar', data: { labels: ['Baseline', 'Scenario'], datasets: [{ data: [0, 0], backgroundColor: [palette.paleTeal, palette.teal], borderRadius: 7, maxBarThickness: 55 }] }, options: chartOptions({ plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { min: 0, max: 100, ticks: { callback: value => `${value}` } } } }) }); charts.indicators = new Chart(byId('indicator-chart'), { type: 'bar', data: { labels: [], datasets: [{ label: 'Baseline', data: [], backgroundColor: palette.paleTeal, borderRadius: 4 }, { label: 'Scenario', data: [], backgroundColor: palette.teal, borderRadius: 4 }] }, options: chartOptions({ indexAxis: 'y', scales: { x: { max: 100, ticks: { callback: value => `${value}%` } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } }) }); }
function chartOptions(extra = {}) { return { responsive: true, maintainAspectRatio: false, animation: { duration: 260 }, plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { backgroundColor: palette.ink, titleColor: '#fff', bodyColor: '#fff' } }, ...extra }; }
function renderPlan(plan) { byId('baseline-score').textContent = plan.original_score.toFixed(1); byId('scenario-score').textContent = plan.scenario_score.toFixed(1); byId('score-change').textContent = `${plan.score_change >= 0 ? '+' : ''}${plan.score_change.toFixed(1)} points compared with the district baseline`; charts.score.data.datasets[0].data = [plan.original_score, plan.scenario_score]; charts.score.update(); const changed = plan.changed_indicators; charts.indicators.data.labels = changed.map(item => item.label); charts.indicators.data.datasets[0].data = changed.map(item => item.original); charts.indicators.data.datasets[1].data = changed.map(item => item.scenario); charts.indicators.update(); byId('action-list').innerHTML = plan.service_actions.map(item => `<article class="action-item"><strong>${escapeHtml(item.indicator)}</strong><div class="action-meta"><span class="tag">Current: ${item.current}%</span><span class="tag coral">Gap to higher-coverage reference: ${item.gap}%</span></div><p>${escapeHtml(item.action)}</p></article>`).join(''); byId('change-list').innerHTML = changed.length ? changed.map(item => `<article class="change-item"><strong>${escapeHtml(item.label)}</strong><p>${item.original}% → ${item.scenario}% (${item.change >= 0 ? '+' : ''}${item.change} points)</p></article>`).join('') : '<p class="empty-state">No edited values yet. The scenario matches the district baseline.</p>'; }
function escapeHtml(value) { const element = document.createElement('div'); element.textContent = String(value); return element.innerHTML; }
init();
