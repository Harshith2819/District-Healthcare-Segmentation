const palette = { violet: '#a78bfa', lime: '#c9f66c', coral: '#ff9d83', muted: '#a3aec4', grid: 'rgba(222,228,255,.12)' };
const number = (value, digits = 1) => Number(value).toFixed(digits);
const byId = id => document.getElementById(id);
let dashboard, selected, comparison, simulated, charts = {}, activeState = 'all';

Chart.defaults.color = palette.muted;
Chart.defaults.font.family = 'Manrope, Arial, sans-serif';
Chart.defaults.borderColor = palette.grid;

async function init() {
  dashboard = await fetch('static/data/dashboard.json').then(response => {
    if (!response.ok) throw new Error('Dashboard data is unavailable. Run website/scripts/build_dashboard_data.py once.');
    return response.json();
  });
  selected = dashboard.districts[0];
  comparison = dashboard.districts[1];
  simulated = [...selected.values];
  ensureAnimatedPickerMarkup();
  renderRibbon(); renderGaps(); renderInsights(); renderMethods(); createCharts(); renderSelectors(); refresh();
  enableAnimatedContent();
}

function ensureAnimatedPickerMarkup() {
  const pickers = [
    ['district', 'Focus district', 'Choose a district', 'Search district or state'],
    ['state', 'Filter by state', 'All states', 'Search state'],
    ['compare', 'Compare against', 'Choose a district', 'Search comparison district'],
  ];
  pickers.forEach(([prefix, label, placeholder, searchPlaceholder]) => {
    if (byId(`${prefix}-trigger`)) return;
    const legacySelect = byId(`${prefix}-select`);
    if (!legacySelect || !legacySelect.parentElement) return;
    const holder = legacySelect.parentElement;
    holder.className = 'district-picker';
    holder.innerHTML = `<label for="${prefix}-trigger">${label}</label><button id="${prefix}-trigger" type="button" aria-expanded="false"><span id="${prefix}-trigger-text">${placeholder}</span><b>⌄</b></button><div id="${prefix}-popover" class="district-popover" hidden><input id="${prefix}-search" type="search" placeholder="${searchPlaceholder}"><div id="${prefix}-list" class="animated-list" role="listbox"></div></div>`;
  });
}

function enableAnimatedContent() {
  const sections = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const children = [...entry.target.children];
      children.forEach((child, index) => child.style.setProperty('--content-delay', `${index * 0.08}s`));
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.1 });
  sections.forEach(section => observer.observe(section));
}

function renderRibbon() {
  const higher = dashboard.districts.filter(d => d.cluster === 0).length;
  const items = [[dashboard.meta.district_count, 'districts analyzed'], [dashboard.meta.feature_count, 'care-access indicators'], [higher, 'higher-coverage baseline'], [dashboard.meta.district_count - higher, 'lower-coverage baseline']];
  byId('stat-ribbon').innerHTML = items.map(([value, label]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join('');
}

function renderSelectors() {
  configurePicker('district', renderDistrictItems, id => { selectDistrict(id); });
  configurePicker('state', renderStateItems, id => {
    activeState = id;
    byId('state-trigger-text').textContent = id === 'all' ? 'All states' : id;
    const candidates = dashboard.districts.filter(d => id === 'all' || d.state === id);
    populateDistricts(candidates, candidates[0]?.id);
  });
  configurePicker('compare', renderComparisonItems, id => {
    comparison = dashboard.districts.find(d => d.id === id);
    byId('compare-trigger-text').textContent = `${comparison.district}, ${comparison.state}`;
    refresh();
  });
  populateDistricts(dashboard.districts, selected.id);
  byId('compare-trigger-text').textContent = `${comparison.district}, ${comparison.state}`;
  byId('reset-button').addEventListener('click', () => { simulated = [...selected.values]; refresh(); });
}

function configurePicker(prefix, renderer, onSelect) {
  const trigger = byId(`${prefix}-trigger`);
  const search = byId(`${prefix}-search`);
  trigger.addEventListener('click', () => togglePicker(prefix, renderer));
  search.addEventListener('input', renderer);
  byId(`${prefix}-list`).addEventListener('click', event => {
    const item = event.target.closest('[data-id]');
    if (!item) return;
    onSelect(item.dataset.id);
    togglePicker(prefix, renderer, false);
  });
}

function togglePicker(prefix, renderer, force) {
  const popover = byId(`${prefix}-popover`);
  const shouldOpen = force ?? popover.hidden;
  ['district', 'state', 'compare'].forEach(name => {
    const current = byId(`${name}-popover`);
    const open = name === prefix && shouldOpen;
    current.hidden = !open;
    byId(`${name}-trigger`).setAttribute('aria-expanded', String(open));
  });
  if (shouldOpen) { renderer(); byId(`${prefix}-search`).focus(); }
}

function populateDistricts(items, preferredId) {
  byId('district-list').dataset.items = JSON.stringify(items.map(item => item.id));
  byId('district-search').value = '';
  renderDistrictItems();
  selectDistrict(preferredId || items[0]?.id);
}

function renderDistrictItems() {
  const ids = JSON.parse(byId('district-list').dataset.items || '[]');
  const query = byId('district-search').value.trim().toLowerCase();
  const items = ids.map(id => dashboard.districts.find(d => d.id === id)).filter(district => district && `${district.district} ${district.state}`.toLowerCase().includes(query));
  byId('district-list').innerHTML = items.map((district, index) => `<button type="button" role="option" aria-selected="${district.id === selected.id}" class="animated-list-item${district.id === selected.id ? ' selected' : ''}" data-id="${district.id}" style="--item-delay:${Math.min(index, 12) * .035}s"><span><strong>${district.district}</strong><small>${district.state}</small></span><em>${number(district.coverage_score)}</em></button>`).join('') || '<p class="no-results">No district found.</p>';
}

function renderStateItems() {
  const query = byId('state-search').value.trim().toLowerCase();
  const states = [...new Set(dashboard.districts.map(d => d.state))].sort().filter(state => state.toLowerCase().includes(query));
  const all = query === '' ? [{ id: 'all', title: 'All states', description: `${dashboard.districts.length} districts` }] : [];
  const items = [...all, ...states.map(state => ({ id: state, title: state, description: `${dashboard.districts.filter(d => d.state === state).length} districts` }))];
  byId('state-list').innerHTML = items.map((item, index) => listItem(item, activeState === item.id, index, '')).join('') || '<p class="no-results">No state found.</p>';
}

function renderComparisonItems() {
  const query = byId('compare-search').value.trim().toLowerCase();
  const items = dashboard.districts.filter(d => `${d.district} ${d.state}`.toLowerCase().includes(query));
  byId('compare-list').innerHTML = items.map((district, index) => listItem({ id: district.id, title: district.district, description: district.state, meta: number(district.coverage_score) }, comparison.id === district.id, index, '')).join('') || '<p class="no-results">No district found.</p>';
}

function listItem(item, selectedItem, index) {
  return `<button type="button" role="option" aria-selected="${selectedItem}" class="animated-list-item${selectedItem ? ' selected' : ''}" data-id="${item.id}" style="--item-delay:${Math.min(index, 12) * .035}s"><span><strong>${item.title}</strong><small>${item.description}</small></span>${item.meta ? `<em>${item.meta}</em>` : ''}</button>`;
}

function selectDistrict(id) {
  selected = dashboard.districts.find(d => d.id === id);
  if (!selected) return;
  simulated = [...selected.values];
  byId('district-trigger-text').textContent = `${selected.district}, ${selected.state}`;
  byId('selected-segment').textContent = selected.cluster_label.toUpperCase();
  if (activeState !== 'all' && activeState !== selected.state) {
    activeState = selected.state;
    byId('state-trigger-text').textContent = selected.state;
  }
  renderDistrictItems();
  refresh();
}

function score(values) {
  return values.reduce((sum, value, index) => {
    const feature = dashboard.features[index];
    return sum + 100 * (value - feature.min) / ((feature.max - feature.min) || 1);
  }, 0) / values.length;
}

function renderSliders() {
  byId('sliders').innerHTML = dashboard.features.map((feature, index) => `<div class="slider"><label title="${feature.label}"><span>${feature.short_label}</span><output id="value-${index}">${number(simulated[index])}</output></label><input data-index="${index}" type="range" min="${feature.min}" max="${feature.max}" step="0.1" value="${simulated[index]}"></div>`).join('');
  document.querySelectorAll('#sliders input').forEach(input => input.addEventListener('input', event => {
    const index = Number(event.target.dataset.index);
    simulated[index] = Number(event.target.value);
    byId(`value-${index}`).textContent = number(simulated[index]);
    refresh({ keepSliders: true });
  }));
}

function refresh(options = {}) {
  const original = selected.coverage_score;
  const simulatedScore = score(simulated);
  const rawDelta = simulatedScore - original;
  const delta = Math.abs(rawDelta) < 0.00001 ? 0 : rawDelta;
  byId('score-number').textContent = number(simulatedScore);
  byId('score-caption').textContent = `${selected.district}, ${selected.state} · ${delta === 0 ? 'original values' : `scenario ${delta > 0 ? '+' : ''}${number(delta)} points`}`;
  byId('score-progress').style.width = `${Math.max(0, Math.min(100, simulatedScore))}%`;
  byId('score-delta').textContent = `${delta >= 0 ? '+' : ''}${number(delta)} pts`;
  byId('delta-copy').textContent = `Original score ${number(original)} → scenario score ${number(simulatedScore)}. The data table itself remains unchanged.`;
  if (!options.keepSliders) renderSliders();
  updateCharts(original, simulatedScore);
}

function chartOptions(extra = {}) { return { responsive: true, maintainAspectRatio: false, animation: { duration: 260 }, plugins: { legend: { labels: { color: palette.muted, boxWidth: 10, usePointStyle: true } }, tooltip: { backgroundColor: '#111827', titleColor: '#fff', bodyColor: '#d9e1f4', borderColor: 'rgba(255,255,255,.15)', borderWidth: 1 } }, ...extra }; }

function createCharts() {
  const labels = dashboard.features.map(f => f.short_label);
  charts.indicators = new Chart(byId('indicator-chart'), { type: 'bar', data: { labels, datasets: [{ label: 'Scenario values (%)', data: simulated, backgroundColor: palette.violet, borderRadius: 5, maxBarThickness: 18 }, { label: 'Comparison district (%)', data: comparison.values, backgroundColor: 'rgba(201,246,108,.55)', borderRadius: 5, maxBarThickness: 18 }] }, options: chartOptions({ scales: { x: { display: false }, y: { beginAtZero: true, max: 100, ticks: { callback: value => `${value}%` }, grid: { color: palette.grid } } } }) });
  charts.pie = new Chart(byId('cluster-chart'), { type: 'doughnut', data: { labels: ['Scenario score', 'Remaining range'], datasets: [{ data: [score(simulated), 100 - score(simulated)], backgroundColor: [palette.lime, '#2b3750'], borderWidth: 0, hoverOffset: 6 }] }, options: chartOptions({ cutout: '70%' }) });
  charts.radar = new Chart(byId('radar-chart'), { type: 'radar', data: { labels, datasets: [] }, options: chartOptions({ scales: { r: { min: 0, max: 100, angleLines: { color: palette.grid }, grid: { color: palette.grid }, pointLabels: { display: false }, ticks: { display: false } } } }) });
  charts.scenario = new Chart(byId('scenario-chart'), { type: 'bar', data: { labels: ['Original', 'Scenario'], datasets: [{ label: 'Analytical score', data: [selected.coverage_score, score(simulated)], backgroundColor: [palette.violet, palette.lime], borderRadius: 10, barThickness: 38 }] }, options: chartOptions({ plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, max: 100, ticks: { callback: value => `${value}` } } } }) });
  const states = dashboard.states.slice().sort((a,b) => a.mean_score - b.mean_score);
  charts.states = new Chart(byId('state-chart'), { type: 'line', data: { labels: states.map(s => s.state), datasets: [{ label: 'Mean analytical score', data: states.map(s => s.mean_score), borderColor: palette.violet, backgroundColor: 'rgba(167,139,250,.20)', pointBackgroundColor: palette.lime, pointRadius: 3, fill: true, tension: .35 }] }, options: chartOptions({ scales: { x: { display: false }, y: { min: 0, max: 100, grid: { color: palette.grid } } } }) });
}

function updateCharts(original, simulatedScore) {
  const profile = dashboard.cluster_profiles.find(profile => profile.cluster === selected.cluster);
  charts.indicators.data.datasets[0].data = simulated;
  charts.indicators.data.datasets[1].data = comparison.values;
  charts.indicators.data.datasets[1].label = `${comparison.district} (%)`;
  charts.indicators.update();
  charts.pie.data.datasets[0].data = [simulatedScore, 100 - simulatedScore];
  charts.pie.update();
  charts.radar.data.datasets = [{ label: 'Scenario values', data: simulated, borderColor: palette.lime, backgroundColor: 'rgba(201,246,108,.18)', pointBackgroundColor: palette.lime, borderWidth: 2 }, { label: `${profile.label} profile`, data: profile.values, borderColor: palette.violet, backgroundColor: 'rgba(167,139,250,.10)', pointBackgroundColor: palette.violet, borderWidth: 1.4 }];
  charts.radar.update();
  charts.scenario.data.datasets[0].data = [original, simulatedScore];
  charts.scenario.update();
  const state = dashboard.states.find(item => item.state === selected.state);
  const adjustedStateScore = state.mean_score + (simulatedScore - original) / state.districts;
  const ordered = dashboard.states.slice().sort((a,b) => a.mean_score - b.mean_score);
  charts.states.data.datasets[0].data = ordered.map(item => item.state === selected.state ? adjustedStateScore : item.mean_score);
  charts.states.update();
}

function renderGaps() {
  const largest = dashboard.gaps[0].absolute_gap;
  byId('gap-bars').innerHTML = dashboard.gaps.slice(0, 10).map(gap => `<div class="bar-row"><div><span>${gap.short_label}</span><strong>${number(gap.absolute_gap)} pp</strong></div><div class="bar-track"><i style="width:${100 * gap.absolute_gap / largest}%"></i></div></div>`).join('');
}

function renderInsights() {
  byId('insight-list').innerHTML = dashboard.insights.map(insight => `<li>${insight}</li>`).join('');
  byId('quality-value').textContent = dashboard.quality.cleaned_missing_values;
  byId('quality-copy').textContent = `${dashboard.quality.cleaned_missing_values} missing values remain in the cleaned table. ${dashboard.quality.imputation_note}`;
}

function renderMethods() {
  byId('algorithm-list').innerHTML = dashboard.algorithms.map(result => `<div class="algorithm-row"><div><span>${result.algorithm}</span><small>${result.config_id}</small></div><strong>Sil. ${number(result.silhouette, 3)}</strong></div>`).join('');
  const seed = dashboard.seed_stability[0];
  byId('stability-note').textContent = `K-Means seed stability: ${seed.seeds_tested} seeds, ${seed.pairwise_comparisons} comparisons, median ARI ${number(seed.ari_median, 3)}.`;
}

init().catch(error => { document.body.innerHTML = `<main class="fatal"><h1>Dashboard data needs a refresh.</h1><p>${error.message}</p></main>`; });
