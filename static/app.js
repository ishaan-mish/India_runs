let payload = null;
let candidates = [];
let selected = null;

const $ = (id) => document.getElementById(id);
const pct = (v) => `${Math.max(0, Math.min(100, v || 0))}%`;
const esc = (s) => String(s ?? "").replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function shortLane(lane){ return lane.replace(' Builder','').replace(' Engineer','').replace(' Lead',''); }
function initials(name){ return (name || '?').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase(); }

async function init(){
  payload = await fetch('/api/payload').then(r => r.json());
  candidates = payload.candidates || [];
  $('topOvr').textContent = candidates.length ? Math.round(candidates[0].score) : '--';
  $('avgTop10').textContent = payload.summary?.average_top10 ? Math.round(payload.summary.average_top10) : '--';
  $('candidateCount').textContent = candidates.length;
  bindTabs(); bindSearch(); bindTeam();
  renderRoster(candidates);
  selectCandidate(candidates[0]);
  renderTeam();
}

function bindTabs(){
  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tab)));
  $('goDossier').addEventListener('click', () => showTab('dossier'));
}
function showTab(name){
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('is-active', b.dataset.tab === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('is-active', p.id === `tab-${name}`));
}
function bindSearch(){
  $('search').addEventListener('input', e => {
    const q = e.target.value.toLowerCase().trim();
    const list = candidates.filter(c => [c.name,c.headline,c.role_lane,c.current_company,...(c.skills||[])].join(' ').toLowerCase().includes(q));
    renderRoster(list);
  });
}
function bindTeam(){
  $('budget').addEventListener('input', () => { $('budgetVal').textContent = $('budget').value; renderTeam(); });
}

function renderRoster(list){
  $('roster').innerHTML = list.map(c => `
    <div class="roster-item ${selected && selected.candidate_id===c.candidate_id?'is-active':''}" data-id="${esc(c.candidate_id)}">
      <div class="rank-mini">${c.rank}</div>
      <div><div class="roster-name">${esc(c.name)}</div><div class="roster-lane">${esc(shortLane(c.role_lane))} · ${esc(c.location)}</div></div>
      <div class="roster-score">${Math.round(c.score)}</div>
    </div>`).join('');
  document.querySelectorAll('.roster-item').forEach(el => el.addEventListener('click', () => selectCandidate(candidates.find(c => c.candidate_id === el.dataset.id))));
}

function selectCandidate(c){
  if(!c) return; selected = c;
  renderRoster(Array.from(document.querySelectorAll('.roster-item')).length ? candidates.filter(x => [x.name,x.headline,x.role_lane,x.current_company,...(x.skills||[])].join(' ').toLowerCase().includes(($('search').value || '').toLowerCase())) : candidates);
  $('ovr').textContent = Math.round(c.score); $('roleLane').textContent = c.role_lane; $('portrait').textContent = initials(c.name);
  $('candName').textContent = c.name; $('headline').textContent = c.headline || c.current_title;
  $('factExp').textContent = `${c.years_experience.toFixed(1)} yrs`; $('factLoc').textContent = c.location || c.country; $('factSalary').textContent = c.salary_mid_lpa ? `${c.salary_mid_lpa} LPA` : 'salary n/a';
  const stats = [ ['RET', c.group_scores.retrieval], ['VEC', c.group_scores.vector], ['RANK', c.group_scores.ranking], ['PROD', c.group_scores.production], ['PY', c.group_scores.python], ['LLM', c.group_scores.llm], ['SHIP', c.group_scores.shipping], ['CHEM', c.chemistry] ];
  $('cardStats').innerHTML = stats.map(([k,v]) => `<div class="hex-stat"><span>${k}</span><b>${Math.round(v || 0)}</b></div>`).join('');
  $('reportName').textContent = c.name; $('rankPill').textContent = `Rank ${c.rank}`; $('reason').textContent = c.reasoning;
  $('c2rText').textContent = c.candidate_to_company; $('r2cText').textContent = c.company_to_candidate; $('c2rBar').style.width = pct(c.candidate_to_company); $('r2cBar').style.width = pct(c.company_to_candidate);
  const chips = [...(c.strengths||[]).slice(0,3), ...(c.risk_flags||[]).slice(0,2).map(x=>'Probe: '+x)];
  $('signalChips').innerHTML = chips.map(x=>`<span>${esc(x)}</span>`).join('');
  renderAttributes(c); renderDossier(c);
}

function renderAttributes(c){
  const labels = payload.groups || {};
  const entries = Object.entries(c.group_scores).map(([k,v]) => [labels[k]?.label || k, v]);
  entries.push(['JD lexical match', c.lexical_jd_score], ['Experience fit', c.experience_score], ['Behavioral signal', c.behavior_score]);
  $('attributes').innerHTML = entries.map(([name,v]) => `
    <div class="attribute-row"><div class="attr-name">${esc(name)}</div><div class="attr-bar"><i style="width:${pct(v)}"></i></div><div class="attr-score">${Math.round(v)}</div></div>`).join('');
}

function renderDossier(c){
  $('dossierTitle').textContent = `${c.name} · ${c.role_lane}`;
  $('dossierFacts').innerHTML = [
    ['Candidate ID', c.candidate_id], ['Current Role', c.current_title], ['Company', c.current_company], ['Location', `${c.location}, ${c.country}`], ['Experience', `${c.years_experience.toFixed(1)} years`], ['Notice', `${c.notice_days} days`], ['Work Mode', c.preferred_work_mode || 'n/a'], ['Expected Salary', c.salary_mid_lpa ? `${c.salary_mid_lpa} LPA` : 'n/a']
  ].map(([a,b]) => `<div class="fact-box"><span>${esc(a)}</span><b>${esc(b)}</b></div>`).join('');
  $('strengths').innerHTML = (c.strengths || []).map(x => `<span>${esc(x)}</span>`).join('') || '<span>Needs manual review</span>';
  $('concerns').innerHTML = (c.concerns || ['No major concern surfaced by the local model']).map(x => `<span>${esc(x)}</span>`).join('');
  $('skills').innerHTML = (c.skills || []).slice(0,18).map(x => `<span class="skill">${esc(x)}</span>`).join('');
  $('interview').innerHTML = Object.entries(c.interview_proxy || {}).map(([k,v]) => `<div class="score-card"><div class="fit-row"><span>${esc(k)}</span><b>${v}</b></div><div class="meter"><i style="width:${pct(v)}"></i></div></div>`).join('');
  const p = c.verified || {};
  $('proof').innerHTML = [
    ['Email', p.email ? 'Verified' : 'Not verified'], ['Phone', p.phone ? 'Verified' : 'Not verified'], ['LinkedIn', p.linkedin ? 'Connected' : 'Not connected'], ['GitHub activity', p.github_activity === -1 ? 'Not linked' : p.github_activity], ['Open to work', p.open_to_work ? 'Yes' : 'No'], ['Response rate', `${Math.round((p.response_rate || 0)*100)}%`]
  ].map(([a,b]) => `<div class="proof-item"><span>${esc(a)}</span><b>${esc(b)}</b></div>`).join('');
}

function renderTeam(){
  const budget = Number($('budget').value || 180);
  const lanes = payload.team_lanes || [];
  let used = new Set(), total = 0, chosen = [];
  for(const lane of lanes){
    const pool = candidates.filter(c => !used.has(c.candidate_id)).sort((a,b) => (b.team_lane_scores?.[lane] || 0) - (a.team_lane_scores?.[lane] || 0));
    let pick = pool.find(c => total + (c.salary_mid_lpa || 35) <= budget) || pool[0];
    if(pick){ used.add(pick.candidate_id); total += (pick.salary_mid_lpa || 35); chosen.push([lane,pick]); }
  }
  const coverage = chosen.reduce((s,[lane,c]) => s + (c.team_lane_scores?.[lane] || 0), 0) / Math.max(1, chosen.length);
  const affordability = Math.max(0, Math.min(100, 100 - Math.max(0,total-budget)*2));
  const signal = chosen.reduce((s,[,c]) => s + (c.behavior_score || 0), 0) / Math.max(1, chosen.length);
  const chem = Math.round(.52*coverage + .28*affordability + .20*signal);
  $('chemScore').textContent = chem;
  const spots = [[50,18],[27,38],[73,38],[34,67],[66,67]];
  $('teamArena').innerHTML = chosen.map(([lane,c],i) => {
    const [x,y] = spots[i] || [50,50];
    return `<div class="slot" style="left:${x}%;top:${y}%"><div class="slot-score">${Math.round(c.team_lane_scores?.[lane] || c.score)}</div><h4>${esc(lane)}</h4><div class="slot-name">${esc(c.name)}</div><div class="slot-meta">${esc(shortLane(c.role_lane))} · ${c.salary_mid_lpa || 'n/a'} LPA</div></div>`;
  }).join('') + `<div class="slot" style="left:50%;top:88%"><h4>Budget Used</h4><div class="slot-name">${total.toFixed(1)} / ${budget} LPA</div><div class="slot-meta">${chosen.length} complementary candidates</div></div>`;
}

init().catch(err => { console.error(err); document.body.insertAdjacentHTML('afterbegin', `<pre style="color:white">${esc(err.stack || err)}</pre>`); });
