const fmt = (value, digits = 1) => Number(value).toFixed(digits);
const optionText = d => `${d.district}, ${d.state}`;
let data, selectedDistrict, simulatedValues;

async function load() {
  data = await fetch('static/data/healthcare_dashboard_data.json').then(r => r.json());
  selectedDistrict = data.districts[0];
  document.querySelector('#subtitle').textContent = `${data.metadata.district_count} districts • ${data.metadata.feature_count} indicators • ${data.metadata.baseline}`;
  renderOverview(); renderExplorer(); renderDistrictOptions(); renderComparisonOptions(); renderGaps(); renderQuality(); renderMethods();
  selectDistrict(selectedDistrict.id);
}

function renderOverview() {
  const high = data.districts.filter(d => d.cluster === 0).length;
  document.querySelector('#summary-cards').innerHTML = [
    [data.metadata.district_count, 'Districts analyzed'], [data.metadata.feature_count, 'Healthcare indicators'],
    [high, 'Higher-coverage baseline segment'], [data.districts.length - high, 'Lower-coverage baseline segment']
  ].map(([n, label]) => `<div class="card"><strong>${n}</strong><span>${label}</span></div>`).join('');
  document.querySelector('#insight-list').innerHTML = data.insights.map(text => `<li>${text}</li>`).join('');
}

function renderExplorer() {
  const states = [...new Set(data.districts.map(d => d.state))].sort();
  document.querySelector('#state-select').innerHTML = states.map(s => `<option>${s}</option>`).join('');
  document.querySelector('#state-select').onchange = renderState;
  renderMap();
  renderState();
}

function normalise(value) { return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
function coordinatePairs(value, points = []) { if (Array.isArray(value) && typeof value[0] === 'number') points.push(value); else if (Array.isArray(value)) value.forEach(v => coordinatePairs(v, points)); return points; }
function rings(value, found = []) { if (Array.isArray(value) && Array.isArray(value[0]) && typeof value[0][0] === 'number') found.push(value); else if (Array.isArray(value)) value.forEach(v => rings(v, found)); return found; }
function property(properties, names) { const key = Object.keys(properties || {}).find(k => names.includes(normalise(k))); return key ? properties[key] : ''; }
async function renderMap() {
  const holder = document.querySelector('#map-status');
  try {
    const response = await fetch(data.map.boundary_file);
    if (!response.ok) throw new Error('not supplied');
    const geo = await response.json(), features = geo.features || [];
    const points = features.flatMap(f => coordinatePairs(f.geometry?.coordinates));
    if (!points.length) throw new Error('invalid GeoJSON');
    const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]), minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    const project = ([x,y]) => [10 + 480*(x-minX)/(maxX-minX), 10 + 560*(maxY-y)/(maxY-minY)];
    const pathFor = geometry => rings(geometry.coordinates).map(ring => ring.map((p,i) => `${i?'L':'M'}${project(p).map(n=>n.toFixed(1)).join(' ')}`).join(' ') + 'Z').join(' ');
    const paths = features.map(feature => {
      const state = property(feature.properties, ['state','stnm','stateut','statename']);
      const district = property(feature.properties, ['district','districtname','districtna','dtname']);
      const match = data.districts.find(d => normalise(d.state) === normalise(state) && normalise(d.district) === normalise(district));
      const colour = match ? (match.cluster === 0 ? '#54a782' : '#d98a38') : '#dfe8e3';
      return `<path d="${pathFor(feature.geometry)}" fill="${colour}" data-id="${match?.id || ''}"><title>${match ? `${match.district}: ${match.cluster_label}` : `${district || 'Unmatched boundary'}`}</title></path>`;
    }).join('');
    holder.innerHTML = `<strong>District boundary explorer</strong><p class="small">Green = higher-coverage baseline segment; orange = lower-coverage. Gray boundaries did not match project district names.</p><svg viewBox="0 0 500 580" role="img" aria-label="India district healthcare segmentation map">${paths}</svg>`;
    holder.querySelectorAll('path[data-id]').forEach(path => path.onclick = () => { if (path.dataset.id) { document.querySelector('#district-select').value = path.dataset.id; selectDistrict(path.dataset.id); } });
  } catch (_) {
    holder.innerHTML = `<strong>Geographic boundary layer</strong><p>${data.map.message}</p><p class="small">Until a compatible GeoJSON is added, use this live state/district explorer to inspect the real segmentation results.</p>`;
  }
}

function renderState() {
  const state = document.querySelector('#state-select').value;
  const summary = data.states.find(s => s.state === state);
  const districts = data.districts.filter(d => d.state === state).sort((a,b) => a.district.localeCompare(b.district));
  document.querySelector('#state-card').innerHTML = `<strong>${state}</strong><span>${summary.districts} districts • ${fmt(summary.lower_coverage_share)}% lower-coverage • mean analytical score ${fmt(summary.mean_score)}</span>`;
  document.querySelector('#state-districts').innerHTML = districts.map(d => `<tr><td><button class="district-link" data-id="${d.id}">${d.district}</button></td><td>${d.cluster_label}</td><td>${fmt(d.coverage_score)}</td></tr>`).join('');
  document.querySelectorAll('.district-link').forEach(button => button.onclick = () => { document.querySelector('#district-select').value = button.dataset.id; selectDistrict(button.dataset.id); document.querySelector('#district').scrollIntoView({behavior:'smooth'}); });
}

function renderDistrictOptions() {
  const options = data.districts.slice().sort((a,b)=>optionText(a).localeCompare(optionText(b))).map(d => `<option value="${d.id}">${optionText(d)}</option>`).join('');
  const select = document.querySelector('#district-select'); select.innerHTML = options; select.onchange = e => selectDistrict(e.target.value);
}

function selectDistrict(id) {
  selectedDistrict = data.districts.find(d => d.id === id);
  document.querySelector('#district-select').value = id;
  simulatedValues = [...selectedDistrict.values];
  const profile = data.cluster_profiles.find(p => p.cluster === selectedDistrict.cluster);
  const differences = selectedDistrict.values.map((v,i) => ({feature:data.features[i], value:v, mean:profile.values[i], diff:v-profile.values[i]}));
  const prominent = differences.slice().sort((a,b)=>Math.abs(b.diff)-Math.abs(a.diff)).slice(0,3);
  document.querySelector('#district-explanation').innerHTML = `<div class="callout"><strong>${selectedDistrict.district}, ${selectedDistrict.state}</strong><span>${selectedDistrict.cluster_label} baseline segment • analytical score ${fmt(selectedDistrict.coverage_score)}</span></div><div class="callout"><strong>Why this assignment?</strong><span>Its 15 actual values are compared with the ${profile.label.toLowerCase()} segment profile. Largest departures: ${prominent.map(x => `${x.feature.short_label} (${x.diff >= 0 ? '+' : ''}${fmt(x.diff)} pp)`).join('; ')}.</span></div>`;
  document.querySelector('#profile-table').innerHTML = differences.map(x => `<tr><td>${x.feature.short_label}</td><td>${fmt(x.value)}</td><td>${fmt(x.mean)}</td><td>${x.diff >= 0 ? '+' : ''}${fmt(x.diff)}</td></tr>`).join('');
  renderSimulator();
}

function renderComparisonOptions() {
  const options = data.districts.slice().sort((a,b)=>optionText(a).localeCompare(optionText(b))).map(d => `<option value="${d.id}">${optionText(d)}</option>`).join('');
  ['#compare-a','#compare-b'].forEach((id, index) => { const el=document.querySelector(id); el.innerHTML=options; el.value=data.districts[index + 1].id; el.onchange=renderComparison; });
  renderComparison();
}

function renderComparison() {
  const a = data.districts.find(d=>d.id===document.querySelector('#compare-a').value), b = data.districts.find(d=>d.id===document.querySelector('#compare-b').value);
  document.querySelector('#compare-a-head').textContent = a.district; document.querySelector('#compare-b-head').textContent = b.district;
  document.querySelector('#comparison-summary').innerHTML = `<strong>${a.district}</strong><span>${a.cluster_label}, score ${fmt(a.coverage_score)}</span><strong>${b.district}</strong><span>${b.cluster_label}, score ${fmt(b.coverage_score)}</span>`;
  document.querySelector('#comparison-table').innerHTML = data.features.map((f,i) => `<tr><td>${f.short_label}</td><td>${fmt(a.values[i])}</td><td>${fmt(b.values[i])}</td><td>${a.values[i]-b.values[i] >= 0 ? '+' : ''}${fmt(a.values[i]-b.values[i])}</td></tr>`).join('');
}

function score(values) { return values.reduce((sum,value,i) => sum + 100*(value-data.features[i].min)/(data.features[i].max-data.features[i].min || 1), 0) / values.length; }
function renderSimulator() {
  const controls = document.querySelector('#sim-controls');
  controls.innerHTML = data.features.map((f,i) => `<label title="${f.label}">${f.short_label}<output id="out-${i}">${fmt(simulatedValues[i])}</output><input type="range" min="${f.min}" max="${f.max}" step="0.1" value="${simulatedValues[i]}" data-index="${i}"></label>`).join('');
  document.querySelector('#sim-district').textContent = `${selectedDistrict.district}, ${selectedDistrict.state}`;
  document.querySelectorAll('#sim-controls input').forEach(input => input.oninput = e => { const i=Number(e.target.dataset.index); simulatedValues[i]=Number(e.target.value); document.querySelector(`#out-${i}`).textContent=fmt(simulatedValues[i]); updateScore(); });
  document.querySelector('#reset-simulation').onclick = () => { simulatedValues=[...selectedDistrict.values]; renderSimulator(); };
  updateScore();
}
function updateScore() { const original=selectedDistrict.coverage_score, changed=score(simulatedValues); document.querySelector('#score-result').textContent = `Original score ${fmt(original)} → simulated score ${fmt(changed)} (${changed-original >= 0 ? '+' : ''}${fmt(changed-original)})`; }

function renderGaps() {
  const max = data.gaps[0].absolute_gap;
  document.querySelector('#gap-bars').innerHTML = data.gaps.slice(0,10).map(g => `<div class="bar-row"><span>${g.short_label}</span><div class="bar"><i style="width:${100*g.absolute_gap/max}%"></i></div><strong>${fmt(g.absolute_gap)} pp</strong></div>`).join('');
}
function renderQuality() {
  document.querySelector('#quality-summary').innerHTML = `<div class="callout"><strong>${data.quality.cleaned_missing_values}</strong><span>missing values in the cleaned feature table</span></div><div class="callout"><strong>Imputation trace</strong><span>${data.quality.imputation_note}</span></div>`;
  document.querySelector('#quality-table').innerHTML = data.features.map(f => `<tr><td>${f.short_label}</td><td>${fmt(f.min)}–${fmt(f.max)}</td><td>${f.missing}</td><td>${fmt(f.scaled_mean,3)}</td><td>${fmt(f.scaled_std,3)}</td></tr>`).join('');
}
function renderMethods() {
  document.querySelector('#algorithm-table').innerHTML=data.algorithms.map(a=>`<tr><td>${a.algorithm}</td><td>${a.config_id}</td><td>${a.n_clusters}</td><td>${fmt(a.silhouette,3)}</td><td>${fmt(a.davies_bouldin,3)}</td><td>${fmt(100*a.clustered_fraction)}%</td></tr>`).join('');
  const seed=data.seed_stability[0], subsample=data.subsample_stability.map(s=>`${s.algorithm}: median ARI ${fmt(s.ari_median,3)} (${s.valid_replicates}/${s.replicates} valid subsamples)`).join(' • ');
  document.querySelector('#stability-summary').innerHTML=`<strong>K-Means seed stability:</strong><span>${seed.seeds_tested} seeds and ${seed.pairwise_comparisons} pairwise comparisons; median ARI ${fmt(seed.ari_median,3)}, minimum ${fmt(seed.ari_min,3)}.</span><span class="small">Subsample stability: ${subsample}</span>`;
}
load().catch(error => { document.querySelector('#subtitle').textContent = `Unable to load project data: ${error.message}`; });
