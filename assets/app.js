/*
  WorldWar Dashboard — Phase 3 (Defensibility)

  Zoom/pan strategy (final, verified against ECharts source):
  - roam: 'move' — ECharts handles drag natively (geo + series move together via updateTransform)
  - Wheel zoom uses dispatchAction({ type:'geoRoam', componentType:'geo', geoIndex:0 })
    → componentType:'geo' is CRITICAL: updates the shared Geo coordinate object
    → all dependent series re-project against it in the same updateTransform pass
    → no split-frame artifact (the previous mistake was omitting componentType:'geo',
      which defaults to 'series' and only updates series models, leaving the base tile alone)
  - setOption is NOT used for zoom (triggers full heavy lifecycle, causes jank)
  - Wheel: capture-phase intercept + RAF throttle (accumulate ticks, apply once/frame)
  - Pinch: capture-phase intercept + PINCH_DAMPING factor
  - georoam event: pan clamping via setOption (acceptable for rare drag-limit corrections)
  - trailLength: 0 on lines effect — eliminates particle streak artifacts during roam
*/

const COLORS = {
  WAR: '#ef4444', ALLY: '#0ea5e9', POLICY: '#10b981',
  SPILLOVER: '#f97316', TENSION: '#eab308', INTERNAL: '#a855f7',
  MAP_BG: '#121826', MAP_BORDER: '#2a344d'
};

const DEFAULT_FILTERS = ['WAR', 'ALLY', 'POLICY', 'SPILLOVER', 'TENSION', 'INTERNAL'];

const LENS_PRESETS = {
  EDITORIAL:     { label: 'Editorial',         filters: [...DEFAULT_FILTERS],          hint: 'All interaction types' },
  IHL:           { label: 'Armed Conflict',     filters: ['WAR', 'INTERNAL'],           hint: 'Wars + civil conflicts' },
  CONNECTEDNESS: { label: 'War-Connectedness',  filters: ['ALLY', 'SPILLOVER'],         hint: 'Support + spillover' },
  COERCION:      { label: 'Coercion',           filters: ['POLICY', 'TENSION'],         hint: 'Sanctions + escalation' }
};

// ── Zoom / pan constants ──────────────────────────────────────────────────────
const GEO_MIN_ZOOM   = 1.2;   // floor — cannot zoom out past full-world view
const GEO_MAX_ZOOM   = 20;
const WHEEL_STEP     = 1.08;  // 8% per scroll tick — slow & precise
const PINCH_DAMPING  = 0.35;  // apply 35% of raw pinch ratio
const DEFAULT_CENTER = [10, 30];

// ─────────────────────────────────────────────────────────────────────────────

function escapeHTML(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
function sanitizeHttpUrl(raw) {
  if (!raw || typeof raw !== 'string') return null;
  try {
    const u = new URL(raw, window.location.origin);
    if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
  } catch {}
  return null;
}
function sanitizeColor(raw, fallback = '#94a3b8') {
  if (typeof raw !== 'string') return fallback;
  const c = raw.trim();
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(c) ? c : fallback;
}
function slugId(name) {
  return String(name).toUpperCase().replace(/[^A-Z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,40);
}
function arrKey(arr) { return [...(arr||[])].sort().join(','); }
function inferLensFromFilters(filters) {
  const key = arrKey(filters);
  for (const [k,v] of Object.entries(LENS_PRESETS)) if (arrKey(v.filters)===key) return k;
  return 'CUSTOM';
}

async function loadJSON(url, { noStore=false }={}) {
  const res = await fetch(url, { cache: noStore ? 'no-store' : 'default' });
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return res.json();
}
async function loadAll() {
  const meta = await loadJSON('./data/meta.json', { noStore: true });
  const ver = encodeURIComponent(meta.last_updated || Date.now());
  const [rawData, rawEvents] = await Promise.all([
    loadJSON(`./data/map_data.json?v=${ver}`),
    loadJSON(`./data/events.json?v=${ver}`).catch(() => ({ events:[], metadata:{} }))
  ]);
  return { meta, rawData, rawEvents };
}

function el(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`Missing #${id}`);
  return n;
}
function setPanelOpen(isOpen) {
  const panel = el('info-panel');
  if (isOpen) {
    panel.classList.add('open');
    el('default-info').classList.add('hidden');
    el('dynamic-info').classList.remove('hidden');
  } else {
    panel.classList.remove('open');
  }
}
function formatDate(iso, { includeTime=false }={}) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return includeTime
      ? d.toLocaleString(undefined, { year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
      : d.toLocaleDateString(undefined, { year:'numeric', month:'short', day:'numeric' });
  } catch { return String(iso); }
}

function parseHashState() {
  const state = { theater:'ALL', lens:'EDITORIAL', filters:[...DEFAULT_FILTERS], selected:null };
  if (!window.location.hash) return state;
  try {
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (params.has('theater')) state.theater = params.get('theater') || 'ALL';
    if (params.has('lens')) {
      const lens = String(params.get('lens')||'').toUpperCase();
      if (LENS_PRESETS[lens]) { state.lens=lens; state.filters=[...LENS_PRESETS[lens].filters]; }
    }
    if (params.has('filters')) {
      const f = params.get('filters');
      state.filters = f ? f.split(',').filter(Boolean) : [];
      state.lens = inferLensFromFilters(state.filters);
    } else {
      state.lens = inferLensFromFilters(state.filters);
    }
    if (params.has('selected')) state.selected = params.get('selected');
  } catch {}
  if (state.lens !== 'CUSTOM' && LENS_PRESETS[state.lens])
    state.filters = [...LENS_PRESETS[state.lens].filters];
  return state;
}
function writeHashState(state) {
  try {
    const params = new URLSearchParams();
    if (state.theater !== 'ALL') params.set('theater', state.theater);
    if (state.lens && state.lens!=='EDITORIAL' && state.lens!=='CUSTOM' && LENS_PRESETS[state.lens]) {
      params.set('lens', state.lens);
    } else {
      const isDefault = arrKey(state.filters) === arrKey(DEFAULT_FILTERS);
      if (!isDefault || state.lens==='CUSTOM') params.set('filters', (state.filters||[]).join(','));
    }
    if (state.selected) params.set('selected', state.selected);
    const hash = params.toString();
    window.history.replaceState(null,'', hash ? `#${hash}` : window.location.pathname);
  } catch {}
}

function inferType(nodeName) {
  const n = String(nodeName).toLowerCase();
  if (n.includes('union') || n==='nato' || n.includes('united nations')) return 'org';
  if (n==='palestine' || n==='taiwan') return 'territory';
  return 'state';
}

function normalizeData(raw) {
  const nodes = raw.nodes || raw.countries || [];
  const edges = raw.edges || [];
  const normNodes = nodes.map(n => {
    const id = n.id || slugId(n.name);
    return { id, name:n.name, type:n.type||inferType(n.name), geoName:n.geoName??null,
      theaters:n.theaters||[], coords:n.coords, category:n.category,
      ihl:n.ihl||null, exposure:n.exposure||null,
      intensity:typeof n.intensity==='number'?n.intensity:2,
      color:n.color||COLORS[n.category]||'#94a3b8',
      summary:n.summary||n.details||'', updated_at:n.updated_at||null,
      confidence:n.confidence||null, sources:n.sources||[],
      aliases:n.aliases||[], tags:n.tags||[] };
  });
  const nodesById   = new Map(normNodes.map(n=>[n.id,n]));
  const nodesByName = new Map(normNodes.map(n=>[n.name,n]));
  const normEdges = edges.map((e,i)=>{
    const fromNode = nodesById.get(e.from)||nodesByName.get(e.from);
    const toNode   = nodesById.get(e.to)||nodesByName.get(e.to);
    const from = fromNode?.id||slugId(e.from);
    const to   = toNode?.id||slugId(e.to);
    return { id:e.id||`${from}__${to}__${String(e.type||e.category||'EDGE').toUpperCase()}__${i}`,
      from, to, theater:e.theater, category:e.category, type:e.type||'',
      effect:e.effect||'solid', color:e.color||COLORS[e.category]||'#94a3b8',
      summary:e.summary||e.details||'', updated_at:e.updated_at||null,
      confidence:e.confidence||null, sources:e.sources||[], layer:e.layer||null };
  });
  const adj = new Map();
  for (const e of normEdges) {
    if (!adj.has(e.from)) adj.set(e.from,[]);
    if (!adj.has(e.to))   adj.set(e.to,[]);
    adj.get(e.from).push(e);
    adj.get(e.to).push(e);
  }
  return { nodes:normNodes, edges:normEdges, nodesById, nodesByName, adj, metadata:raw.metadata||{} };
}

function buildDot(color) {
  const d = document.createElement('span');
  d.className='w-1.5 h-1.5 rounded-full'; d.style.background=color; return d;
}
function updateStatsBar(statsBarEl, visibleNodes) {
  const counts = { WAR:0,TENSION:0,INTERNAL:0,ALLY:0,POLICY:0,SPILLOVER:0 };
  for (const n of visibleNodes) counts[n.category]=(counts[n.category]||0)+1;
  statsBarEl.replaceChildren();
  const items = [['WAR','Wars'],['INTERNAL','Civil'],['TENSION','Tensions'],['ALLY','Support'],['POLICY','Policy'],['SPILLOVER','Spillover']];
  let any=false;
  for (const [k,label] of items) {
    if (!counts[k]) continue; any=true;
    const span=document.createElement('span'); span.className='flex items-center gap-1';
    span.append(buildDot(COLORS[k])); span.append(document.createTextNode(` ${counts[k]} ${label}`));
    statsBarEl.append(span);
  }
  if (!any) { const s=document.createElement('span'); s.textContent='No matches found'; statsBarEl.append(s); }
}

function ensureEvidenceContainer() {
  let c = document.getElementById('evidence-container');
  if (c) return c;
  c=document.createElement('div'); c.id='evidence-container'; c.className='mb-4';
  el('dual-classification-badges').insertAdjacentElement('afterend',c); return c;
}
function normalizeSourceItem(src) {
  if (!src) return null;
  if (typeof src==='string') {
    const s=src.trim(); if (!s) return null;
    const isUrl=/^https?:\/\//i.test(s);
    return { title:isUrl?s.replace(/^https?:\/\//i,''):s, url:isUrl?s:null,
      publisher:null,published_at:null,accessed_at:null,note:null,citation:!isUrl?s:null };
  }
  if (typeof src==='object') {
    const url=sanitizeHttpUrl(typeof src.url==='string'?src.url:null);
    const title=typeof src.title==='string'?src.title:(url?url.replace(/^https?:\/\//i,''):'Source');
    return { title, url, publisher:typeof src.publisher==='string'?src.publisher:null,
      published_at:typeof src.published_at==='string'?src.published_at:null,
      accessed_at:typeof src.accessed_at==='string'?src.accessed_at:null,
      note:typeof src.note==='string'?src.note:null,
      citation:typeof src.citation==='string'?src.citation:null };
  }
  return null;
}
function renderEvidence(container, { updated_at, confidence, sources }={}) {
  container.replaceChildren();
  const last=formatDate(updated_at), conf=confidence??'—';
  const details=document.createElement('details');
  details.className='bg-slate-800/30 p-3 rounded-lg border border-slate-700/50';
  const summary=document.createElement('summary');
  summary.className='cursor-pointer list-none select-none flex items-center justify-between text-xs font-semibold text-slate-200';
  const left=document.createElement('span'); left.textContent='Evidence';
  const right=document.createElement('span');
  right.className='text-[10px] font-medium text-slate-400';
  right.textContent=`Last verified: ${last} • Confidence: ${String(conf)}`;
  summary.append(left,right); details.append(summary);
  const body=document.createElement('div'); body.className='mt-2 space-y-2 text-xs text-slate-200';
  const metaRow=document.createElement('div'); metaRow.className='grid grid-cols-1 sm:grid-cols-2 gap-2';
  function makeBox(labelText,valueText) {
    const box=document.createElement('div'); box.className='bg-slate-900/40 p-2 rounded border border-slate-700/40';
    const lbl=document.createElement('div'); lbl.className='text-[10px] uppercase tracking-wider text-slate-400 font-bold'; lbl.textContent=labelText;
    const val=document.createElement('div'); val.className='mt-0.5'; val.textContent=valueText;
    box.append(lbl,val); return box;
  }
  metaRow.append(makeBox('Last verified',last),makeBox('Confidence',String(conf)));
  body.append(metaRow);
  const srcHeader=document.createElement('div');
  srcHeader.className='text-[10px] uppercase tracking-wider text-slate-400 font-bold';
  srcHeader.textContent='Sources'; body.append(srcHeader);
  const srcList=document.createElement('ul'); srcList.className='space-y-2';
  const srcNorm=(sources||[]).map(normalizeSourceItem).filter(Boolean);
  if (!srcNorm.length) {
    const li=document.createElement('li'); li.className='text-slate-400'; li.textContent='No sources attached yet.'; srcList.append(li);
  } else {
    for (const s of srcNorm.slice(0,10)) {
      const li=document.createElement('li'); li.className='bg-slate-900/30 p-2 rounded border border-slate-700/40';
      const top=document.createElement('div'); top.className='flex items-start justify-between gap-2';
      const title=document.createElement(s.url?'a':'div');
      title.className=s.url?'font-semibold text-slate-200 hover:underline break-words':'font-semibold text-slate-200 break-words';
      title.textContent=s.title||'Source';
      const safeUrl=sanitizeHttpUrl(s.url);
      if (safeUrl) { title.href=safeUrl; title.target='_blank'; title.rel='noreferrer'; }
      const pub=document.createElement('div'); pub.className='text-[10px] text-slate-400 whitespace-nowrap';
      const bits=[]; if(s.publisher)bits.push(s.publisher); if(s.published_at)bits.push(formatDate(s.published_at));
      pub.textContent=bits.join(' • '); top.append(title,pub); li.append(top);
      if (s.note||s.citation) {
        const note=document.createElement('div'); note.className='mt-1 text-[11px] text-slate-300';
        note.textContent=s.note||s.citation; li.append(note);
      }
      srcList.append(li);
    }
  }
  body.append(srcList); details.append(body); container.append(details);
}

function defaultAbout(meta, datasetMeta) {
  const title=(datasetMeta?.title||meta?.title||'WorldWar Dashboard').trim();
  const last=meta?.ui_date_label||meta?.last_updated||datasetMeta?.generated_at_utc||'—';
  return { title, subtitle:'An editorial map of active conflicts and conflict-connected power moves.',
    last_reviewed_at:last,
    sections:[
      { heading:'How to read the map', bullets:['Click a country/node to spotlight its network (connections brighten; others fade).','Use "Zoom To Theater" to focus on a region.','Use filters to hide interaction types when the map gets noisy.'] },
      { heading:'Lens presets', bullets:['Editorial: all categories (default).','Armed Conflict: focuses on wars & civil conflicts.','War-Connectedness: focuses on support, basing, spillover.','Coercion: focuses on sanctions/policy + escalation risk.'] }
    ],
    caveats:{ heading:'Caveats & Definitions', bullets:["This is an editorial project. Categories and summaries reflect the author's assessment at the time of writing.",'IHL labels are included as a reference framework, not as legal determinations or official rulings.','Terms like "war", "self-defense", or "genocide" can be contested and may change as evidence develops and formal processes conclude.','Use sources and timestamps: every node/edge can carry confidence + citations (expand "Evidence" in the panel).'] }
  };
}
function setupAboutModal({ meta, datasetMeta }) {
  const about=(datasetMeta&&datasetMeta.about)?datasetMeta.about:defaultAbout(meta,datasetMeta);
  const dateBadge=document.getElementById('ui-date');
  if (dateBadge&&!document.getElementById('about-btn')) {
    const btn=document.createElement('button'); btn.id='about-btn';
    btn.className='text-[10px] sm:text-xs font-semibold bg-slate-800 text-slate-300 hover:text-white px-2 py-1 rounded-md border border-slate-700 whitespace-nowrap';
    btn.textContent='About'; dateBadge.insertAdjacentElement('afterend',btn);
  }
  if (document.getElementById('about-modal')) return;
  const overlay=document.createElement('div'); overlay.id='about-modal';
  overlay.className='fixed inset-0 z-50 hidden items-center justify-center p-4';
  overlay.style.background='rgba(0,0,0,0.55)';
  const card=document.createElement('div');
  card.className='glass-panel w-full max-w-2xl rounded-xl p-5 md:p-6 text-slate-200 max-h-[85vh] overflow-y-auto';
  const topRow=document.createElement('div'); topRow.className='flex items-start justify-between gap-3';
  const titleWrap=document.createElement('div');
  const h2=document.createElement('h2'); h2.className='text-xl md:text-2xl font-bold text-white'; h2.textContent=about.title||'About';
  const sub=document.createElement('div'); sub.className='text-sm text-slate-300 mt-1'; sub.textContent=about.subtitle||'';
  const lastEl=document.createElement('div'); lastEl.className='text-[11px] text-slate-400 mt-2';
  const lastText=about.last_reviewed_at||meta?.ui_date_label||meta?.last_updated;
  lastEl.textContent=lastText?`Last reviewed: ${String(lastText)}`:'';
  titleWrap.append(h2,sub,lastEl);
  const closeBtn=document.createElement('button');
  closeBtn.className='text-slate-300 hover:text-white bg-slate-800 rounded-full p-2 border border-slate-600 transition-colors shrink-0';
  closeBtn.setAttribute('aria-label','Close');
  closeBtn.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
  topRow.append(titleWrap,closeBtn); card.append(topRow);
  const body=document.createElement('div'); body.className='mt-5 space-y-5';
  for (const sec of (Array.isArray(about.sections)?about.sections:[])) {
    const block=document.createElement('div');
    const h=document.createElement('h3'); h.className='text-[11px] uppercase tracking-wider text-slate-400 font-bold mb-2'; h.textContent=sec.heading||'Section'; block.append(h);
    const bullets=Array.isArray(sec.bullets)?sec.bullets:[];
    if (bullets.length) {
      const ul=document.createElement('ul'); ul.className='list-disc pl-5 space-y-1 text-sm text-slate-200';
      for (const b of bullets) { const li=document.createElement('li'); li.textContent=String(b); ul.append(li); }
      block.append(ul);
    } else if (sec.body) { const p=document.createElement('p'); p.className='text-sm text-slate-200'; p.textContent=String(sec.body); block.append(p); }
    body.append(block);
  }
  const caveats=about.caveats;
  if (caveats) {
    const det=document.createElement('details'); det.className='bg-slate-800/30 p-4 rounded-lg border border-slate-700/50';
    const sum=document.createElement('summary'); sum.className='cursor-pointer list-none select-none text-sm font-semibold text-slate-200';
    sum.textContent=caveats.heading||'Caveats & Definitions (click to expand)'; det.append(sum);
    const inner=document.createElement('div'); inner.className='mt-3';
    const bullets=Array.isArray(caveats.bullets)?caveats.bullets:[];
    if (bullets.length) {
      const ul=document.createElement('ul'); ul.className='list-disc pl-5 space-y-1 text-sm text-slate-200';
      for (const b of bullets) { const li=document.createElement('li'); li.textContent=String(b); ul.append(li); }
      inner.append(ul);
    } else if (caveats.body) { const p=document.createElement('p'); p.className='text-sm text-slate-200'; p.textContent=String(caveats.body); inner.append(p); }
    det.append(inner); body.append(det);
  }
  card.append(body); overlay.append(card); document.body.append(overlay);
  const open=()=>{ overlay.classList.remove('hidden'); overlay.classList.add('flex'); };
  const close=()=>{ overlay.classList.add('hidden'); overlay.classList.remove('flex'); };
  closeBtn.addEventListener('click',close);
  overlay.addEventListener('click',e=>{ if(e.target===overlay)close(); });
  window.addEventListener('keydown',e=>{ if(e.key==='Escape'&&!overlay.classList.contains('hidden'))close(); });
  const btn=document.getElementById('about-btn'); if(btn)btn.addEventListener('click',open);
}

function initUI({ meta, data, events }) {
  el('ui-date').textContent = meta.ui_date_label||meta.last_updated||'—';
  const ef = events?.metadata?.generated_at_utc||meta.events_last_updated||null;
  el('ui-events-date').textContent = ef ? `Events: ${formatDate(ef)}` : 'Events: not refreshed yet';
  setupAboutModal({ meta, datasetMeta: data.metadata });

  // Filter panel toggle
  const filterControls=el('filter-controls-container');
  const iconUp=el('icon-chevron-up'), iconDown=el('icon-chevron-down');
  let filtersVisible=window.innerWidth>768;
  if (!filtersVisible) { filterControls.classList.add('collapsed'); iconUp.classList.add('hidden'); iconDown.classList.remove('hidden'); }
  el('toggle-filters-btn').addEventListener('click',()=>{
    filtersVisible=!filtersVisible;
    if (filtersVisible) { filterControls.classList.remove('collapsed'); iconUp.classList.remove('hidden'); iconDown.classList.add('hidden'); }
    else { filterControls.classList.add('collapsed'); iconUp.classList.add('hidden'); iconDown.classList.remove('hidden'); }
  });

  // Lens buttons
  const lensWrap=document.createElement('div'); lensWrap.className='mb-4'; lensWrap.id='lens-controls';
  const lensHeader=document.createElement('div'); lensHeader.className='flex justify-between items-center mb-2';
  const lensTitle=document.createElement('h4'); lensTitle.className='text-[10px] uppercase tracking-wider text-slate-500 font-bold'; lensTitle.textContent='Lens';
  const lensHint=document.createElement('div'); lensHint.id='lens-hint'; lensHint.className='text-[10px] text-slate-400';
  lensHeader.append(lensTitle,lensHint);
  const lensBtnsRow=document.createElement('div'); lensBtnsRow.className='flex flex-wrap gap-1.5';
  const lensButtons=new Map();
  for (const [lensKey,preset] of Object.entries(LENS_PRESETS)) {
    const b=document.createElement('button'); b.type='button'; b.dataset.lens=lensKey;
    b.className='px-2.5 py-1 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs rounded border border-slate-700 transition-colors';
    b.textContent=preset.label; lensButtons.set(lensKey,b); lensBtnsRow.append(b);
  }
  const customBadge=document.createElement('span');
  customBadge.id='lens-custom-badge';
  customBadge.className='px-2 py-1 text-[10px] font-bold uppercase tracking-wide bg-slate-900/50 text-slate-300 rounded border border-slate-700/50 hidden';
  customBadge.textContent='Custom'; lensBtnsRow.append(customBadge);
  lensWrap.append(lensHeader,lensBtnsRow);
  const toggleAll=document.getElementById('toggle-all-filters');
  const filtersSection=toggleAll?toggleAll.closest('div')?.parentElement:null;
  if (filtersSection&&filtersSection.parentElement===filterControls) filterControls.insertBefore(lensWrap,filtersSection);
  else filterControls.prepend(lensWrap);

  const datalist=el('country-datalist'); datalist.replaceChildren();
  for (const n of data.nodes) { const opt=document.createElement('option'); opt.value=n.name; datalist.append(opt); }

  const state=parseHashState();
  state.lens=state.lens||inferLensFromFilters(state.filters);

  const chart=echarts.init(el('map-container'));
  const evidenceContainer=ensureEvidenceContainer();

  const syncLensUI=()=>{
    const lens=state.lens;
    for (const [k,btn] of lensButtons.entries()) {
      const active=lens===k;
      btn.classList.toggle('bg-blue-600',active); btn.classList.toggle('text-white',active);
      btn.classList.toggle('bg-slate-800',!active); btn.classList.toggle('text-slate-300',!active);
    }
    customBadge.classList.toggle('hidden',lens!=='CUSTOM');
    const hintEl=document.getElementById('lens-hint');
    if (hintEl) hintEl.textContent=lens==='CUSTOM'?'Custom filters':(LENS_PRESETS[lens]?.hint||'');
  };
  const syncFilterUI=()=>{
    document.querySelectorAll('.filter-cb').forEach(cb=>{ cb.checked=state.filters.includes(cb.value); });
    el('toggle-all-filters').textContent=state.filters.length===DEFAULT_FILTERS.length?'Deselect All':'Select All';
    document.querySelectorAll('.theater-btn').forEach(btn=>{
      const active=btn.dataset.theater===state.theater;
      btn.classList.toggle('bg-blue-600',active); btn.classList.toggle('text-white',active);
      btn.classList.toggle('bg-slate-800',!active); btn.classList.toggle('text-slate-300',!active);
    });
    syncLensUI();
  };

  const renderLinePanel=(lineDatum)=>{
    el('info-title').textContent=`${lineDatum.fromName} → ${lineDatum.toName}`;
    const badges=el('dual-classification-badges'); badges.replaceChildren();
    const badge=document.createElement('span');
    badge.className='px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wide';
    badge.style.background=`${lineDatum.color}30`; badge.style.color=lineDatum.color;
    badge.style.border=`1px solid ${lineDatum.color}`; badge.textContent=lineDatum.type; badges.append(badge);
    el('info-context').textContent=lineDatum.summary||'';
    renderEvidence(evidenceContainer,{ updated_at:lineDatum.updated_at, confidence:lineDatum.confidence, sources:lineDatum.sources });
    el('connections-container').classList.add('hidden'); el('events-container').classList.add('hidden');
    setPanelOpen(true);
  };

  const renderNodePanel=(nodeId)=>{
    const node=data.nodesById.get(nodeId); if(!node) return;
    el('info-title').textContent=node.name; el('info-context').textContent=node.summary||'';
    const badges=el('dual-classification-badges'); badges.replaceChildren();
    const ihl=document.createElement('span');
    ihl.className='px-2.5 py-1 rounded-md text-[10px] sm:text-xs font-bold uppercase tracking-wide bg-slate-800 border border-slate-600 text-slate-300';
    ihl.textContent=`IHL: ${node.ihl??'—'}`; badges.append(ihl);
    const policy=document.createElement('span');
    policy.className='px-2.5 py-1 rounded-md text-[10px] sm:text-xs font-bold uppercase tracking-wide';
    policy.style.background=`${node.color}30`; policy.style.color=node.color;
    policy.style.border=`1px solid ${node.color}`; policy.textContent=`Policy: ${node.exposure??'—'}`; badges.append(policy);
    renderEvidence(evidenceContainer,{ updated_at:node.updated_at, confidence:node.confidence, sources:node.sources });
    const edges=data.adj.get(nodeId)||[];
    const connContainer=el('connections-container'); const list=el('info-connections'); list.replaceChildren();
    if (edges.length) {
      connContainer.classList.remove('hidden');
      for (const e of edges) {
        const otherId=e.from===nodeId?e.to:e.from;
        const other=data.nodesById.get(otherId); if(!other) continue;
        const li=document.createElement('li');
        li.className='flex items-start gap-2 bg-slate-800/40 p-2.5 rounded border border-slate-700/50 hover:bg-slate-700/50 transition-colors cursor-pointer';
        li.addEventListener('click',()=>selectNode(otherId));
        const dot=document.createElement('span'); dot.className='w-2.5 h-2.5 rounded-full mt-1 shrink-0';
        dot.style.background=e.color; dot.style.boxShadow=`0 0 5px ${e.color}`;
        const wrap=document.createElement('div');
        const title=document.createElement('div'); title.className='font-semibold text-slate-200'; title.textContent=other.name;
        const metaRow=document.createElement('div'); metaRow.className='flex items-center gap-2 mt-0.5';
        const dir=document.createElement('span'); dir.className='text-[10px] uppercase font-bold text-slate-400 bg-slate-700/50 px-1 rounded';
        dir.textContent=(e.from===nodeId)?'→ To':'← From';
        const kind=document.createElement('span'); kind.className='text-xs font-medium'; kind.style.color=e.color; kind.textContent=e.type;
        metaRow.append(dir,kind); wrap.append(title,metaRow); li.append(dot,wrap); list.append(li);
      }
    } else { connContainer.classList.add('hidden'); }
    const evContainer=el('events-container'); const evList=el('info-events'); evList.replaceChildren();
    const related=(events.events||[]).filter(evt=>{ const tags=evt.tags||[]; return tags.includes(nodeId)||tags.includes(node.name); }).slice(0,5);
    if (related.length) {
      evContainer.classList.remove('hidden');
      for (const evt of related) {
        const li=document.createElement('li'); li.className='bg-slate-800/40 p-2.5 rounded border border-slate-700/50';
        const safeUrl=sanitizeHttpUrl(evt.url);
        const a=document.createElement(safeUrl?'a':'span');
        if(safeUrl){a.href=safeUrl;a.target='_blank';a.rel='noreferrer';}
        a.className='font-semibold text-slate-200 hover:underline'; a.textContent=evt.headline||'Untitled event';
        const mr=document.createElement('div'); mr.className='text-xs text-slate-400 mt-1';
        mr.textContent=evt.published_at?formatDate(evt.published_at,{includeTime:true}):'';
        li.append(a,mr); evList.append(li);
      }
    } else { evContainer.classList.add('hidden'); }
    setPanelOpen(true);
  };

  const updateMap=()=>{
    const theaterNodes=data.nodes.filter(n=>state.theater==='ALL'||n.theaters.includes(state.theater));
    const theaterIds=new Set(theaterNodes.map(n=>n.id));
    const candidateEdges=data.edges.filter(e=>{
      const matchesCat=state.filters.includes(e.category);
      const matchesTheater=state.theater==='ALL'||e.theater===state.theater;
      return matchesCat&&matchesTheater&&theaterIds.has(e.from)&&theaterIds.has(e.to);
    });
    const connectedByFilteredEdge=new Set();
    for (const e of candidateEdges) { connectedByFilteredEdge.add(e.from); connectedByFilteredEdge.add(e.to); }
    const visibleNodes=theaterNodes.filter(n=>state.filters.includes(n.category)||connectedByFilteredEdge.has(n.id));
    updateStatsBar(el('stats-bar'),visibleNodes);
    const visibleIds=new Set(visibleNodes.map(n=>n.id));
    if (state.selected&&!visibleIds.has(state.selected)) { state.selected=null; setPanelOpen(false); }
    const connectedNodes=new Set(); const connectedEdgeIds=new Set();
    if (state.selected) {
      connectedNodes.add(state.selected);
      for (const e of (data.adj.get(state.selected)||[])) { connectedNodes.add(e.from); connectedNodes.add(e.to); connectedEdgeIds.add(e.id); }
    }
    const mapNodes=visibleNodes.map(n=>{
      const isSelected=state.selected===n.id, isConnected=connectedNodes.has(n.id);
      const opacity=state.selected?(isConnected?1:0.2):1, size=(n.intensity*2)+3;
      return { name:n.name, value:n.coords.concat([size]),
        itemStyle:{ color:n.color, opacity, borderColor:isSelected?'#ffffff':n.color,
          borderWidth:isSelected?2:1, shadowBlur:isConnected?10:0, shadowColor:n.color },
        nodeId:n.id, ihl:n.ihl, status:n.exposure, details:n.summary };
    });
    const focusNodes=mapNodes.filter(n=>n.nodeId===state.selected);
    const ambientNodes=mapNodes.filter(n=>n.nodeId!==state.selected);
    const filteredEdges=candidateEdges.filter(e=>visibleIds.has(e.from)&&visibleIds.has(e.to));
    const mapLines=filteredEdges.map((e,idx)=>{
      const fromNode=data.nodesById.get(e.from), toNode=data.nodesById.get(e.to);
      if(!fromNode||!toNode) return null;
      const isConnected=state.selected?connectedEdgeIds.has(e.id):false;
      const opacity=state.selected?(isConnected?0.85:0.02):0.15;
      const lineWidth=isConnected?2.5:1;
      const baseCurve=0.2+(idx%3)*0.1;
      const curveness=e.from<e.to?baseCurve:-baseCurve;
      return { coords:[fromNode.coords,toNode.coords], fromName:fromNode.name, toName:toNode.name,
        type:e.type, summary:e.summary, color:e.color, edgeId:e.id,
        updated_at:e.updated_at, confidence:e.confidence, sources:e.sources,
        lineStyle:{ color:e.color, width:lineWidth, type:e.effect, curveness, opacity } };
    }).filter(Boolean);
    const mapFills=visibleNodes.filter(n=>(n.type==='state'||n.type==='territory')&&n.geoName).map(n=>({
      name:n.geoName, itemStyle:{ areaColor:n.color+(state.selected&&!connectedNodes.has(n.id)?'05':'30'), borderColor:n.color+(state.selected&&!connectedNodes.has(n.id)?'10':'ff') }
    }));
    chart.setOption({
      geo:{ id:'baseGeo', regions:mapFills },
      series:[
        { id:'focusNode', name:'focusNode', type:'effectScatter', coordinateSystem:'geo', geoIndex:0, zlevel:3, rippleEffect:{ brushType:'stroke', scale:3 }, symbolSize:val=>val[2]*1.2, data:focusNodes },
        { id:'ambientNodes', name:'ambientNodes', type:'scatter', coordinateSystem:'geo', geoIndex:0, zlevel:2, symbolSize:val=>val[2], data:ambientNodes },
        { id:'linesSeries', name:'linesSeries', type:'lines', coordinateSystem:'geo', geoIndex:0, zlevel:1,
          symbol:['none','arrow'], symbolSize:6,
          // trailLength:0 eliminates particle streak artifacts during roam
          effect:{ show:true, period:4, trailLength:0, symbol:'circle', symbolSize:3 },
          data:mapLines }
      ]
    });
    const lensNow=inferLensFromFilters(state.filters);
    if (lensNow!==state.lens) { state.lens=lensNow; syncLensUI(); }
  };

  const selectNode=(nodeId)=>{
    const node=data.nodesById.get(nodeId); if(!node) return;
    if (state.theater!=='ALL'&&!node.theaters.includes(state.theater)) state.theater='ALL';
    state.selected=nodeId;
    // Use setOption for programmatic jumps (theater/node select) — these aren't
    // frame-sensitive interactive operations, so the full lifecycle is fine here.
    chart.setOption({ geo:{ center:node.coords, zoom:4 } });
    syncFilterUI(); updateMap(); renderNodePanel(nodeId); writeHashState(state);
  };
  const clearSelection=()=>{ state.selected=null; updateMap(); setPanelOpen(false); writeHashState(state); };

  for (const [lensKey,btn] of lensButtons.entries()) {
    btn.addEventListener('click',()=>{
      state.lens=lensKey; state.filters=[...LENS_PRESETS[lensKey].filters]; state.selected=null;
      setPanelOpen(false); syncFilterUI(); updateMap(); writeHashState(state);
    });
  }

  let initialCenter=[...DEFAULT_CENTER], initialZoom=GEO_MIN_ZOOM;
  if (state.theater!=='ALL') {
    const btn=document.querySelector(`.theater-btn[data-theater="${state.theater}"]`);
    if (btn) { initialCenter=JSON.parse(btn.dataset.center); initialZoom=parseFloat(btn.dataset.zoom); }
  }
  if (state.selected&&data.nodesById.get(state.selected)) {
    initialCenter=data.nodesById.get(state.selected).coords; initialZoom=4;
  }

  chart.setOption({
    backgroundColor:'transparent',
    geo:{
      id:'baseGeo', map:'world',
      // roam:'move' — ECharts handles drag natively (moves geo+series together).
      // Wheel zoom is fully disabled in ECharts; we intercept and handle it below.
      roam:'move',
      zoom:initialZoom, center:initialCenter,
      scaleLimit:{ min:GEO_MIN_ZOOM, max:GEO_MAX_ZOOM },
      label:{ emphasis:{ show:false } },
      itemStyle:{ areaColor:COLORS.MAP_BG, borderColor:COLORS.MAP_BORDER, borderWidth:1 },
      emphasis:{ itemStyle:{ areaColor:'#1e2538' } }
    },
    tooltip:{
      trigger:'item', backgroundColor:'rgba(15,23,42,0.95)', borderColor:'rgba(255,255,255,0.1)', textStyle:{ color:'#fff' },
      formatter:(params)=>{
        if (!params) return '';
        if (params.seriesType==='effectScatter'||params.seriesType==='scatter') {
          const d=params.data||{}, color=sanitizeColor(d?.itemStyle?.color);
          return `<div class="font-bold text-base mb-1">${escapeHTML(d.name)}</div><div class="text-xs mb-1 text-slate-300"><span class="font-bold text-slate-400">IHL:</span> ${escapeHTML(d.ihl)}</div><div class="text-xs px-2 py-0.5 rounded-full inline-block mb-2 mt-1" style="background:${color}40;color:${color};border:1px solid ${color}">${escapeHTML(d.status)}</div><div class="text-sm max-w-[250px] whitespace-normal text-slate-200">${escapeHTML(d.details)}</div>`;
        }
        if (params.seriesType==='lines') {
          const d=params.data||{}, color=sanitizeColor(d.color);
          return `<div class="font-bold mb-1">${escapeHTML(d.fromName)} &rarr; ${escapeHTML(d.toName)}</div><div class="text-xs mb-1 font-semibold" style="color:${color}">${escapeHTML(d.type)}</div><div class="text-sm max-w-[250px] whitespace-normal text-slate-200">${escapeHTML(d.summary)}</div>`;
        }
        return '';
      }
    }
  });

  chart.on('click',(params)=>{
    if (params.seriesType==='effectScatter'||params.seriesType==='scatter') {
      const nodeId=params?.data?.nodeId;
      if (nodeId) { state.selected=nodeId; updateMap(); renderNodePanel(nodeId); writeHashState(state); }
      return;
    }
    if (params.seriesType==='lines') { state.selected=null; updateMap(); renderLinePanel(params.data); writeHashState(state); }
  });
  chart.getZr().on('click',e=>{ if(!e.target) clearSelection(); });
  window.addEventListener('resize',()=>chart.resize());

  // ══════════════════════════════════════════════════════════════════════════
  // ZOOM CONTROL — wheel + pinch
  //
  // Key insight from ECharts source (src/action/geoRoam.js):
  //   dispatchAction({ type:'geoRoam', componentType:'geo' }) updates the geo
  //   component model's center+zoom via updateCenterAndZoom(), which writes back
  //   to the shared Geo coordinate system object. All series that declare
  //   coordinateSystem:'geo' + geoIndex:0 share this same object, so when the
  //   updateTransform pipeline runs, all layers re-project in a single pass.
  //   No split-frame artifact.
  //
  //   Without componentType:'geo' (the default is 'series'), the action only
  //   updates series-type models, leaving the base geo tile untouched — which
  //   is exactly the desync we saw in the previous attempt.
  //
  //   setOption({ geo: { zoom } }) triggers the full heavy lifecycle and can
  //   cause jank on rapid wheel events — not suitable for per-frame zoom.
  //   We still use setOption for large programmatic jumps (theater select,
  //   node select, pan clamp corrections) where the cost is acceptable.
  // ══════════════════════════════════════════════════════════════════════════

  const mapEl=el('map-container');

  const getGeoState=()=>{
    const opt=chart.getOption();
    return { zoom:opt?.geo?.[0]?.zoom??GEO_MIN_ZOOM, center:opt?.geo?.[0]?.center??[...DEFAULT_CENTER] };
  };

  // ── applyZoom: the correct approach ──────────────────────────────────────
  // dispatchAction with componentType:'geo' updates the shared Geo object →
  // all series re-project in the same updateTransform pass → no split frame.
  // ECharts handles the anchor math internally via originX/originY.
  // We pre-clamp the factor so we never exceed scaleLimit.
  const applyZoom=(factor, pixelX, pixelY)=>{
    const { zoom:curZoom }=getGeoState();
    const targetZoom=Math.max(GEO_MIN_ZOOM, Math.min(GEO_MAX_ZOOM, curZoom*factor));
    const clampedFactor=targetZoom/curZoom;
    if (Math.abs(clampedFactor-1)<0.0001) return; // already at limit, nothing to do

    chart.dispatchAction({
      type:        'geoRoam',
      componentType: 'geo',   // CRITICAL — without this it defaults to 'series'
      geoIndex:    0,
      zoom:        clampedFactor,
      originX:     pixelX,
      originY:     pixelY
    });
  };

  // RAF throttle: accumulate wheel ticks within one animation frame, apply once.
  // Mac trackpad fires 8-12 wheel events per physical gesture tick; without
  // throttling, each would dispatch a separate geoRoam, causing microstutter.
  let rafId=null, pendingFactor=1, pendingPx=0, pendingPy=0;

  mapEl.addEventListener('wheel',(e)=>{
    e.preventDefault();
    e.stopImmediatePropagation(); // block any ECharts bubble-phase wheel handlers

    const rect=mapEl.getBoundingClientRect();
    pendingFactor *= (e.deltaY<0 ? WHEEL_STEP : 1/WHEEL_STEP);
    pendingPx=e.clientX-rect.left;
    pendingPy=e.clientY-rect.top;

    if (!rafId) {
      rafId=requestAnimationFrame(()=>{
        applyZoom(pendingFactor, pendingPx, pendingPy);
        pendingFactor=1; rafId=null;
      });
    }
  },{ passive:false, capture:true });

  // ── Pinch (two-finger / iPhone) ───────────────────────────────────────────
  let lastPinchDist=null;

  mapEl.addEventListener('touchstart',(e)=>{
    if (e.touches.length===2) {
      lastPinchDist=Math.hypot(
        e.touches[0].clientX-e.touches[1].clientX,
        e.touches[0].clientY-e.touches[1].clientY);
      e.preventDefault(); e.stopImmediatePropagation();
    }
  },{ passive:false, capture:true });

  mapEl.addEventListener('touchmove',(e)=>{
    if (e.touches.length!==2||lastPinchDist===null) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const newDist=Math.hypot(
      e.touches[0].clientX-e.touches[1].clientX,
      e.touches[0].clientY-e.touches[1].clientY);
    const rawRatio=newDist/lastPinchDist;
    const factor=1+(rawRatio-1)*PINCH_DAMPING;
    const rect=mapEl.getBoundingClientRect();
    const midX=(e.touches[0].clientX+e.touches[1].clientX)/2-rect.left;
    const midY=(e.touches[0].clientY+e.touches[1].clientY)/2-rect.top;
    applyZoom(factor,midX,midY);
    lastPinchDist=newDist;
  },{ passive:false, capture:true });

  mapEl.addEventListener('touchend',()=>{ lastPinchDist=null; },{ capture:true });

  // ══════════════════════════════════════════════════════════════════════════
  // PAN CLAMPING via georoam event
  //
  // The georoam event fires after any roam — both native drag (roam:'move')
  // and our dispatchAction calls. We use it to enforce bounds:
  //   • At/near global zoom: snap to DEFAULT_CENTER (no drift allowed)
  //   • At all zooms: hard geographic bounds so map can't escape viewport
  //
  // setOption is acceptable here — pan corrections are rare (user must drag
  // to an extreme), not per-frame, so the full lifecycle cost is fine.
  // ══════════════════════════════════════════════════════════════════════════

  let clampingPan=false;

  chart.on('georoam',()=>{
    if (clampingPan) return;
    const { zoom, center }=getGeoState();
    let [lng,lat]=center;

    // At global zoom — lock center, no panning
    if (zoom<=GEO_MIN_ZOOM*1.1) {
      const dLat=Math.abs(lat-DEFAULT_CENTER[1]);
      const dLng=Math.abs(lng-DEFAULT_CENTER[0]);
      if (dLat>2||dLng>6) {
        clampingPan=true;
        chart.setOption({ geo:{ center:[...DEFAULT_CENTER] } });
        clampingPan=false;
      }
      return;
    }

    // At higher zooms — geographic hard bounds
    const clampedLat=Math.max(-75,Math.min(80,lat));
    const clampedLng=Math.max(-220,Math.min(260,lng));
    if (Math.abs(clampedLat-lat)>0.5||Math.abs(clampedLng-lng)>0.5) {
      clampingPan=true;
      chart.setOption({ geo:{ center:[clampedLng,clampedLat] } });
      clampingPan=false;
    }
  });

  // ── End zoom/pan control ──────────────────────────────────────────────────

  document.querySelectorAll('.filter-cb').forEach(cb=>{
    cb.addEventListener('change',e=>{
      const v=e.target.value;
      if (e.target.checked) { if(!state.filters.includes(v))state.filters.push(v); }
      else { state.filters=state.filters.filter(x=>x!==v); }
      state.lens=inferLensFromFilters(state.filters);
      updateMap(); writeHashState(state); syncFilterUI();
    });
  });
  el('toggle-all-filters').addEventListener('click',()=>{
    state.filters=state.filters.length===DEFAULT_FILTERS.length?[]:[...DEFAULT_FILTERS];
    state.lens=inferLensFromFilters(state.filters);
    syncFilterUI(); updateMap(); writeHashState(state);
  });
  document.querySelectorAll('.theater-btn').forEach(btn=>{
    btn.addEventListener('click',e=>{
      state.theater=e.target.dataset.theater;
      const center=JSON.parse(e.target.dataset.center);
      const zoom=parseFloat(e.target.dataset.zoom);
      chart.setOption({ geo:{ center, zoom } });
      state.selected=null; setPanelOpen(false); syncFilterUI(); updateMap(); writeHashState(state);
    });
  });

  const searchInput=el('country-search');
  searchInput.addEventListener('input',e=>{
    const val=e.target.value; if(!val)return;
    const n=data.nodes.find(x=>x.name.toLowerCase()===val.toLowerCase());
    if(n){ selectNode(n.id); searchInput.value=''; searchInput.blur(); }
  });
  searchInput.addEventListener('keydown',e=>{
    if (e.key==='Enter') {
      const match=data.nodes.find(x=>x.name.toLowerCase()===e.target.value.toLowerCase());
      if (!match) { searchInput.classList.add('animate-shake','border-red-500'); setTimeout(()=>searchInput.classList.remove('animate-shake','border-red-500'),700); }
    }
  });

  el('close-panel').addEventListener('click',clearSelection);
  syncFilterUI(); updateMap();
  if (state.selected) renderNodePanel(state.selected);
}

(async function main() {
  try {
    const { meta, rawData, rawEvents }=await loadAll();
    const data=normalizeData(rawData);
    initUI({ meta, data, events:rawEvents });
  } catch(err) {
    console.error(err);
    alert('Failed to load data. Check console for details.');
  }
})();
