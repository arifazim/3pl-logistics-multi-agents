// State
const S = { samples:[], selected:null, lastResult:null };

// Agent types for UI
const STEPS = [
  {tool:'sanitize_vendor_text', n:1, actor:'VTS · Text Sanitizer',    title:'Sanitize vendor input',           copy:'Checks carrier text for prompt injection before entering agent context.'},
  {tool:'rank_vendors_for_lane',n:2, actor:'VS · Vendor Scorer',       title:'Rank carriers (70% reliability)',  copy:'MCP vendor.rank_for_lane — reliability × 0.7 + cost × 0.3. Selects best fit.'},
  {tool:'compute_margin_quote', n:3, actor:'QE · Quotation Engine',    title:'Build protected customer quote',   copy:'vendor_cost ÷ (1−0.12) = 12% floor. ME Margin Evaluator validates.'},
  {tool:'check_compliance',     n:4, actor:'Policy MCP · HITL Gate',   title:'Check compliance + escalate',     copy:'policy.check_compliance × 3. HITL triggers if margin/SLA/weight fails.'},
  {tool:'trajectory_eval',      n:5, actor:'Trajectory Evaluator',     title:'Assert 8-step workflow',          copy:'Deterministic 8-assertion check: vendor quoted → priced → margin OK → compliant → HITL evaluated.'},
];

// Selectors
const $  = id => document.getElementById(id);
const m$ = v => v == null ? '—' : `$${Number(v).toFixed(2)}`;
const p$ = v => v == null ? '—' : `${Number(v).toFixed(1)}%`;

// Page navigation
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  $(`page-${name}`).classList.add('active');
  document.querySelector(`.nav-tab[onclick*="'${name}'"]`)?.classList.add('active');
  if (name === 'audit') loadTelemetry();
}

// Health check
async function checkHealth() {
  try {
    const d = await fetch('/health').then(r => r.json());
    $('health-txt').textContent = `${(d.status||'ok').toUpperCase()} · ${d.agent?.agy||'agent'}`;
    $('queue-mode').textContent = d.agent?.instruction_loaded ? 'ADK Ready' : 'Offline';
  } catch { $('health-txt').textContent = 'API unavailable'; }
}

// Load samples
async function loadSamples() {
  const d = await fetch('/api/eval-samples').then(r => r.json());
  S.samples = d.samples || [];
  $('sample-count').textContent = d.count || S.samples.length;
  if (!S.selected && S.samples.length) { S.selected = S.samples[0]; applySample(S.selected); }
  renderQueue();
}

function filteredSamples() {
  const lane = $('lane-filter')?.value || 'all', sla = $('sla-filter')?.value || 'all';
  return S.samples.filter(s => (lane==='all'||s.lane===lane) && (sla==='all'||s.sla_tier===sla));
}

function renderQueue() {
  $('shipment-queue').innerHTML = filteredSamples().slice(0,100).map(s => {
    const a = S.selected?.shipment_id===s.shipment_id?' active':'';
    return `<button class="shipment-card${a}" data-id="${s.shipment_id}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-sm);">
        <strong>${s.shipment_id}</strong>
        <span class="chip ${s.sla_tier==='express'?'yellow':'blue'}">${s.sla_tier}</span>
      </div>
      <div style="font-size:var(--font-size-caption);color:var(--muted);margin-bottom:var(--space-sm);">${s.lane}</div>
      <div style="display:flex;justify-content:space-between;font-size:var(--font-size-caption);">
        <span>${s.weight.toLocaleString()} lbs</span><span>${s.delivery_time}h</span>
      </div>
    </button>`;
  }).join('');
  $('shipment-queue').querySelectorAll('.shipment-card').forEach(row =>
    row.addEventListener('click', () => {
      S.selected = S.samples.find(s => s.shipment_id===row.dataset.id);
      applySample(S.selected); renderQueue(); runWorkflow();
    })
  );
}

function applySample(s) {
  if (!s) return;
  $('lane').value=s.lane; $('weight').value=s.weight; $('sla').value=s.sla_tier; $('delivery-time').value=s.delivery_time;
  $('active-shipment').textContent = `${s.shipment_id} · ${s.customer||'Sample customer'} · ${s.lane}`;
}

// Pipeline rendering
function renderInitialPipeline() {
  $('pipeline').innerHTML = STEPS.map((step, i) => `
    <div class="pipeline-step">
      <div class="pipeline-icon"><span>${step.n}</span></div>
      <div class="pipeline-content">
        <div class="pipeline-title">${step.actor}</div>
        <div class="pipeline-desc">${step.title}</div>
      </div>
      <span class="chip grey">Pending</span>
    </div>`).join('');
}

// Run workflow with animation
async function runWorkflow() {
  $('run-workflow').disabled = true;
  animatePipelineSteps();
  try {
    const r = await fetch('/api/dual-quote', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        lane: $('lane').value, weight: +$('weight').value,
        sla_tier: $('sla').value, delivery_time: +$('delivery-time').value,
        shipment_id: S.selected?.shipment_id||'MANUAL-001',
      })
    }).then(r => r.json());
    S.lastResult = r;
    renderResult(r);
    updateAuditTab(r);
  } catch(e) {
    $('decision-title').textContent = 'Workflow error: ' + e.message;
  } finally { $('run-workflow').disabled = false; }
}

async function animatePipelineSteps() {
  for (let i = 0; i < STEPS.length; i++) {
    renderRunningPipeline(i);
    await new Promise(r => setTimeout(r, 300));
  }
}

function renderRunningPipeline(activeIdx) {
  $('pipeline').innerHTML = STEPS.map((step, i) => {
    const cls = i < activeIdx ? 'done' : i === activeIdx ? 'running' : '';
    const icon = i < activeIdx 
      ? `<span>${step.n}</span>`
      : `<span>${step.n}</span>`;
    const badge = i < activeIdx ? `<span class="chip green">Done</span>`
      : i === activeIdx ? `<span class="chip blue">Running…</span>`
      : `<span class="chip grey">Pending</span>`;
    return `<div class="pipeline-step ${cls}">
      <div class="pipeline-icon">${icon}</div>
      <div class="pipeline-content">
        <div class="pipeline-title">${step.actor}</div>
        <div class="pipeline-desc">${step.title}</div>
      </div>
      ${badge}
    </div>`;
  }).join('');
}

// Result rendering
function renderResult(r) {
  const q=r.customer_quote||{}, v=r.recommended_vendor||{}, hitl=r.hitl||{}, traj=r.trajectory_eval||{};
  const trace=new Set(r.tool_trace||[]);

  $('kpi-vendor').textContent  = q.selected_vendor_name||v.vendor_id||'—';
  $('kpi-rate').textContent    = m$(q.total_rate);
  $('kpi-margin').textContent  = p$(q.margin_percentage);
  $('kpi-hitl').textContent    = hitl.requires_approval?'⚠ Yes':'✓ No';
  $('kpi-hitl').style.color    = hitl.requires_approval?'var(--danger)':'var(--success)';

  $('pipeline').innerHTML = STEPS.map((step, i) => {
    const skipped = step.tool==='sanitize_vendor_text' && !trace.has(step.tool);
    const done = step.tool==='trajectory_eval' ? !!r.trajectory_eval : trace.has(step.tool);
    const cls = done?'done':skipped?'':'';
    const icon = done ? `<span>${step.n}</span>` : skipped ? `<span>—</span>` : `<span>${step.n}</span>`;
    const badge = done ? `<span class="chip green">Done</span>` : skipped ? `<span class="chip grey">Skip</span>` : `<span class="chip yellow">Pending</span>`;
    return `<div class="pipeline-step ${cls}">
      <div class="pipeline-icon">${icon}</div>
      <div class="pipeline-content">
        <div class="pipeline-title">${step.actor}</div>
        <div class="pipeline-desc">${step.title}</div>
      </div>
      ${badge}
    </div>`;
  }).join('');

  $('h-promise').textContent = `${r.lane||q.lane||'—'} / ${q.sla_tier||'—'} / ${m$(q.total_rate)}`;
  $('h-cover').textContent   = `${q.selected_vendor_name||v.vendor_id||'—'} @ ${m$(q.vendor_cost)}`;
  $('h-outcome').textContent = hitl.requires_approval?'⚠ Hold for manager approval':'✓ Ready to dispatch';
  $('decision-title').textContent = traj.passed ? '✓ All 8 trajectory checks passed — auto-dispatch eligible' : '⚠ Needs review — see compliance gates';
  $('decision-copy').textContent = buildExpl(r);
  $('decision-price').textContent = m$(q.total_rate);
  $('raw-json').textContent = JSON.stringify(r, null, 2);

  renderVendors(r.ranked_vendors||[]);
  renderCompliance(r.compliance||{}, hitl);
}

function buildExpl(r) {
  const q=r.customer_quote||{}, c=r.compliance||{}, hitl=r.hitl||{};
  const ok = c.passed?'passed all 3 policy gates':'did not pass all policy gates';
  const h  = hitl.requires_approval?`HITL triggered: ${(hitl.reasons||[]).join('; ')}`:'No human approval required.';
  return `${q.selected_vendor_name||'Vendor'} selected · ${m$(q.total_rate)} · ${p$(q.margin_percentage)} margin · Load ${ok}. ${h}`;
}

function renderVendors(vs) {
  if (!vs.length) { $('vendor-list').innerHTML='<div class="empty">No vendors for this lane.</div>'; return; }
  $('vendor-list').innerHTML = vs.map((v,i) => `
    <div class="shipment-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-sm);">
        <strong><span style="display:inline-flex;align-items:center;justify-content:center;background:${i===0?'var(--success)':'var(--primary)}';color:#fff;border-radius:50%;width:24px;height:24px;font-size:12px;">${i+1}</span> ${v.name||v.vendor_id}${i===0?'<span style="color:var(--success);margin-left:var(--space-xs);">SELECTED</span>':''}</strong>
        <span class="chip ${i===0?'green':'blue'}">Score ${v.final_score}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:var(--font-size-caption);color:var(--muted);">
        <span>Cost ${m$(v.effective_rate)}</span><span>Reliability ${p$(v.reliability_score)}</span>
      </div>
    </div>`).join('');
}

function renderCompliance(c, hitl) {
  const gates=[
    ['① Margin ≥ 12%', c.margin_compliance],
    ['② SLA ≤ 24h', c.sla_compliance],
    ['③ Weight ≤ 45k lbs', c.weight_compliance],
    ['④ HITL Gate', {compliant:!hitl.requires_approval, rule:hitl.requires_approval?(hitl.reasons||[]).join(', ')||'Escalation required':'No escalation'}],
  ];
  $('compliance-list').innerHTML = gates.map(([name,g]) => {
    const ok=g&&g.compliant;
    return `<div class="gate">
      <div><strong>${name}</strong><div style="font-size:var(--font-size-caption);color:var(--muted);">${g?g.rule||'—':'Not checked'}</div></div>
      <span class="chip ${ok?'green':'yellow'}">${ok?'Pass':'Review'}</span>
    </div>`;
  }).join('');
}

// Audit tab
function updateAuditTab(r) {
  const traj = r.trajectory_eval||{};
  const steps = traj.steps||[];
  if (steps.length) {
    $('trajectory-steps').innerHTML = steps.map(s => `
      <div class="pipeline-step ${s.passed?'done':'fail'}">
        <div class="pipeline-icon"><span>${s.passed?'✓':'✗'}</span></div>
        <div class="pipeline-content">
          <div class="pipeline-title">${s.name.replace(/_/g,' ')}</div>
          <div class="pipeline-desc">${s.detail||''}</div>
        </div>
        <span class="chip ${s.passed?'green':'red'}">${s.passed?'Pass':'Fail'}</span>
      </div>`).join('');
  }
  const trace = r.tool_trace||[];
  if (trace.length) {
    $('tool-trace-list').innerHTML = `<div style="font-size:var(--font-size-caption);margin-bottom:var(--space-sm);color:var(--muted);">Agent called ${trace.length} tool(s) in order:</div>` +
      trace.map((t,i) => `<div style="display:flex;gap:var(--space-sm);align-items:center;padding:var(--space-sm) var(--space-md);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:var(--space-xs);font-size:var(--font-size-caption);">
        <span style="background:var(--primary);color:#fff;border-radius:50%;width:24px;height:24px;display:grid;place-items:center;font-size:12px;font-weight:var(--font-weight-bold);">${i+1}</span>
        <code style="font-size:var(--font-size-caption);">${t}</code>
      </div>`).join('');
  }
}

// Loops
async function runLoop(n) {
  const statusEl = $(`l${n}-status`), resultEl = $(`l${n}-result`);
  statusEl.className='chip yellow'; statusEl.textContent='Running…';
  resultEl.classList.remove('visible'); resultEl.innerHTML='';

  const sample = S.samples[n-1] || {lane:'Tracy->Fremont',weight:1000,sla_tier:'standard',delivery_time:20,shipment_id:'LOOP-TEST'};
  try {
    const response = await fetch(`/api/loop/${n}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({lane:sample.lane, weight:sample.weight, sla_tier:sample.sla_tier, delivery_time:sample.delivery_time, shipment_id:sample.shipment_id, margin:14.0})
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const d = await response.json();
    statusEl.className='chip green'; statusEl.textContent='✓ Complete';
    let html='<div class="loop-result-box">';
    
    console.log(`Loop ${n} response:`, d);
    
    if (n===1) {
      const status = d.status || d.result?.status || 'unknown';
      const iterations = d.iteration_count || d.iterations || 1;
      html+=`<strong>Vendor Evaluator Loop</strong> · Status: ${status} · ${iterations} iteration(s)<br>`;
      if(d.selected_vendor) html+=`Selected: <strong>${d.selected_vendor.vendor_id||d.selected_vendor.name||'N/A'}</strong> (score ${d.selected_vendor.final_score||d.selected_vendor.score||'N/A'})<br>`;
      if(d.quote) html+=`Quote: ${m$(d.quote.customer_price||d.quote.total_rate)} · Margin: ${p$(d.quote.margin_percentage||d.quote.margin)}<br>`;
      if(d.tried_vendors?.length) html+=`Tried: [${d.tried_vendors.join(', ')}]`;
      if(d.escalation_reason) html+=`<br><span style="color:var(--danger);font-size:var(--font-size-caption);">⚠ ${d.escalation_reason}</span>`;
    } else if (n===2) {
      const status = d.status || d.result?.status || 'unknown';
      const iterations = d.iteration_count || d.iterations || 1;
      html+=`<strong>Compliance-Critic Loop</strong> · Status: ${status} · ${iterations} iteration(s)<br>`;
      if(d.violations?.length) html+=`Violations resolved: ${d.violations.map(v=>v.type||v).join(', ')}<br>`;
      if(d.final_plan) html+=`Final vendor: ${d.final_plan.vendor_id||d.final_plan.vendor||'N/A'}`;
      if(d.escalation_reason) html+=`<br><span style="color:var(--danger);font-size:var(--font-size-caption);">⚠ ${d.escalation_reason}</span>`;
    } else {
      const status = d.status || d.result?.status || 'unknown';
      const iterations = d.iterations || d.iteration_count || 1;
      html+=`<strong>Kaizen Meta-Loop</strong> · Status: ${status} · ${iterations} cycle(s)<br>`;
      html+=`Auto-refined: ${d.auto_refined?'✓ Yes':'✗ No (all tests passing)'}<br>`;
      if(d.refinements_applied?.length) d.refinements_applied.forEach(r=>{ html+=`→ ${r.type||'refinement'}: <code>${r.config_key||'config'}</code> ${r.old_value||'old'} → ${r.new_value||'new'}<br>`; });
      html+=`Final eval: ${d.final_eval?.passed?'✓ All pass':`${d.final_eval?.failed_count||d.failures?.length||0} failure(s) remain`}`;
    }
    html+=`<details style="margin-top:var(--space-md);"><summary style="font-size:var(--font-size-caption);color:var(--muted);cursor:pointer;">Raw response</summary><pre style="font-size:var(--font-size-caption);background:var(--soft);padding:var(--space-sm);border-radius:var(--radius-sm);margin-top:var(--space-xs);overflow:auto;">${JSON.stringify(d, null, 2)}</pre></details>`;
    html+='</div>';
    resultEl.innerHTML=html; resultEl.classList.add('visible');
  } catch(e) {
    statusEl.className='chip red'; statusEl.textContent='Error';
    resultEl.innerHTML=`<div class="loop-result-box" style="background:rgba(255,92,92,.08);border-color:rgba(255,92,92,.4);">Error: ${e.message}<br><small style="color:var(--muted);">Check browser console for details</small></div>`;
    resultEl.classList.add('visible');
    console.error(`Loop ${n} error:`, e);
  }
}

// A2A
async function runA2A() {
  const btn = document.querySelector('[onclick="runA2A()"]');
  if (btn) { btn.disabled=true; btn.textContent='Negotiating…'; }
  $('a2a-result').innerHTML='<div class="empty">Sending QuoteRequest to vendor-side agents…</div>';
  try {
    const d = await fetch('/api/a2a-negotiate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({lane:$('a2a-lane').value, weight:+$('a2a-weight').value, sla_tier:$('a2a-sla').value, shipment_id:S.selected?.shipment_id||'A2A-001'})
    }).then(r => r.json());

    let html=`<div style="margin-bottom:var(--space-md);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:var(--space-sm);">
      <div><strong style="font-size:var(--font-size-section);">${d.summary}</strong><div style="font-size:var(--font-size-caption);color:var(--muted);">MCP reference cost: ${m$(d.mcp_reference_cost)} · Lane: ${d.lane}</div></div>
      <span class="chip ${d.agreed?'green':'red'}">${d.agreed?'✓ Agreement reached':'✗ No agreement'}</span></div>`;
    (d.rounds||[]).forEach(round => {
      html+=`<div style="border:1px solid var(--border);border-radius:var(--radius-lg);padding:var(--space-md);margin-bottom:var(--space-md);">
        <div style="display:flex;justify-content:space-between;margin-bottom:var(--space-sm);">
          <strong>Round ${round.round} — Broker target: ${m$(round.broker_target)}</strong>
          <span class="chip blue">${round.acceptances} accepted · ${round.counters} counter(s)</span>
        </div><div style="display:grid;gap:var(--space-sm);">`;
      (round.offers||[]).forEach(o => {
        html+=`<div style="display:flex;justify-content:space-between;align-items:center;padding:var(--space-sm) var(--space-md);border-radius:var(--radius-sm);font-size:var(--font-size-caption);
          background:${o.accepted?'rgba(35,193,107,.08)':'rgba(255,176,32,.08)}";border:1px solid ${o.accepted?'rgba(35,193,107,.4)':'rgba(255,176,32,.4)}">
          <span><strong>${o.vendor_name}</strong> (${o.vendor_id}) — offered ${m$(o.offered_rate)}</span>
          <span>${o.accepted?'<span class="chip green">✓ Accepted</span>':`<span class="chip yellow">Counter: ${m$(o.counter_offer)}</span>`}</span>
        </div><div style="font-size:var(--font-size-caption);color:var(--muted);padding:0 4px;">${o.reason}</div>`;
      });
      html+=`</div></div>`;
    });
    $('a2a-result').innerHTML = html;
  } catch(e) {
    $('a2a-result').innerHTML=`<div class="empty" style="color:var(--danger);">Error: ${e.message}</div>`;
  } finally { if(btn){btn.disabled=false;btn.textContent='▶ Run A2A';} }
}

// Telemetry
async function loadTelemetry() {
  try {
    const d = await fetch('/api/telemetry').then(r => r.json());
    if($('tele-ships'))   $('tele-ships').textContent = d.shipments_today??'—';
    if($('tele-ontime'))  $('tele-ontime').textContent = d.on_time_rate!=null?`${d.on_time_rate}%`:'—';
    if($('tele-margin'))  $('tele-margin').textContent = d.margin_avg_pct!=null?`${d.margin_avg_pct}%`:'—';
    if($('tele-raw'))     $('tele-raw').textContent = JSON.stringify(d,null,2);
  } catch(e) { if($('tele-raw')) $('tele-raw').textContent=e.message; }
}

// Eval batch
async function runEval() {
  $('btn-eval').disabled=true; $('btn-eval').textContent='Running…';
  $('eval-summary').textContent='Running 20 shipments through the full agent pipeline…';
  try {
    const d = await fetch('/api/eval-run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:20})}).then(r=>r.json());
    $('eval-summary').textContent=`${d.passed}/${d.count} passed · ${d.pass_rate}% pass rate`;
    $('eval-body').innerHTML=(d.results||[]).map((item,i)=>`<tr>
      <td>${i+1}</td><td>${item.shipment_id}</td><td>${item.lane}</td>
      <td>${item.selected_vendor||'—'}</td><td>${m$(item.total_rate)}</td>
      <td>${p$(item.margin_percentage)}</td>
      <td><span class="chip ${item.compliance_passed?'green':'yellow'}">${item.compliance_passed?'Pass':'Fail'}</span></td>
      <td><span class="chip ${item.hitl_required?'red':'green'}">${item.hitl_required?'Yes':'No'}</span></td>
      <td><span class="chip ${item.trajectory_passed?'green':'yellow'}">${item.trajectory_passed?'Pass':'Review'}</span></td>
    </tr>`).join('');
  } catch(e){ $('eval-summary').textContent=e.message; }
  finally { $('btn-eval').disabled=false; $('btn-eval').textContent='▶ Run 20-case eval'; }
}

// Deploy modal
function showDeployModal() {
  const ex=document.getElementById('deploy-modal'); if(ex){ex.remove();return;}
  const m=document.createElement('div'); m.id='deploy-modal';
  m.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:1000;display:flex;align-items:center;justify-content:center;padding:var(--space-lg);';
  m.innerHTML=`<div style="background:var(--surface);border-radius:var(--radius-xl);padding:var(--space-xl);max-width:560px;width:100%;box-shadow:var(--shadow-lg);">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-lg);">
      <h2 style="font-size:var(--font-size-section);font-weight:var(--font-weight-bold);">☁ Deploy to Google Cloud Run</h2>
      <button onclick="document.getElementById('deploy-modal').remove()" style="background:none;border:0;font-size:22px;cursor:pointer;color:var(--muted);">✕</button>
    </div>
    <p style="font-size:var(--font-size-normal);margin-bottom:var(--space-md);">Run the one-click script from your project root:</p>
    <pre style="background:#0F172A;color:#BFDBFE;border-radius:var(--radius-md);padding:var(--space-lg);font-size:var(--font-size-caption);overflow:auto;margin-bottom:var(--space-md);"># 1. Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. Set API key
export GEMINI_API_KEY="your-key-here"

# 3. One-click deploy (8 steps, ~5 min)
./deployment/cloudrun/deploy.sh YOUR_PROJECT_ID us-central1</pre>
    <div style="background:rgba(35,193,107,.12);border:1px solid rgba(35,193,107,.4);border-radius:var(--radius-md);padding:var(--space-md);font-size:var(--font-size-caption);line-height:1.8;">
      <strong>8-step deploy script:</strong><br>
      ① Enable APIs · ② Artifact Registry · ③ Service account + IAM<br>
      ④ Secret Manager (GEMINI_API_KEY) · ⑤ Cloud Build image<br>
      ⑥ Render service.yaml · ⑦ Deploy Cloud Run · ⑧ Print URL
    </div>
    <div style="margin-top:var(--space-sm);font-size:var(--font-size-caption);color:var(--muted);">Prerequisites: <code>gcloud</code> CLI installed · GCP billing enabled</div>
  </div>`;
  document.body.appendChild(m);
  m.addEventListener('click', e => { if(e.target===m) m.remove(); });
}

// Events
$('run-workflow')?.addEventListener('click', runWorkflow);
$('btn-eval')?.addEventListener('click', runEval);
$('lane-filter')?.addEventListener('change', renderQueue);
$('sla-filter')?.addEventListener('change', renderQueue);

// Boot
checkHealth();
renderInitialPipeline();
loadSamples().then(() => runWorkflow());