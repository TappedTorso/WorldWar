/*
  WorldWar Dashboard — Phase 3 (Defensibility)

  Adds:
  - Lens presets (Editorial / Armed Conflict / War-Connectedness / Coercion)
  - Evidence block in info panel (last verified, confidence, sources) — collapsed by default
  - About/Methodology modal — intentionally opened by the user (caveats hidden behind a disclosure)

  Keeps:
  - Phase 1 hardening: no inline onclick, no unsafe innerHTML for user content, tooltip escaping
  - Phase 2 separation: data loaded from /data/*.json; engine isolated in /assets/app.js
  - Modeling fix: org nodes don't fill country polygons (prevents "EU colors Belgium")
*/

const COLORS = {
  WAR: '#ef4444',
  ALLY: '#0ea5e9',
  POLICY: '#10b981',
  SPILLOVER: '#f97316',
  TENSION: '#eab308',
  INTERNAL: '#a855f7',
  MAP_BG: '#121826',
  MAP_BORDER: '#2a344d'
};

const DEFAULT_FILTERS = ['WAR', 'ALLY', 'POLICY', 'SPILLOVER', 'TENSION', 'INTERNAL'];

const LENS_PRESETS = {
  EDITORIAL: {
    label: 'Editorial',
    filters: [...DEFAULT_FILTERS],
    hint: 'All interaction types'
  },
  IHL: {
    label: 'Armed Conflict',
    filters: ['WAR', 'INTERNAL'],
    hint: 'Wars + civil conflicts'
  },
  CONNECTEDNESS: {
    label: 'War-Connectedness',
    filters: ['ALLY', 'SPILLOVER'],
    hint: 'Support + spillover'
  },
  COERCION: {
    label: 'Coercion',
    filters: ['POLICY', 'TENSION'],
    hint: 'Sanctions + escalation'
  }
};

function escapeHTML(s) {
  return String(s ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));
}

function slugId(name) {
  return String(name)
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40);
}

function arrKey(arr) {
  return [...(arr || [])].slice().sort().join(',');
}

function inferLensFromFilters(filters) {
  const key = arrKey(filters);
  for (const [k, v] of Object.entries(LENS_PRESETS)) {
    if (arrKey(v.filters) === key) return k;
  }
  return 'CUSTOM';
}

async function loadJSON(url, { noStore = false } = {}) {
  const res = await fetch(url, { cache: noStore ? 'no-store' : 'default' });
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

async function loadAll() {
  const meta = await loadJSON('./data/meta.json', { noStore: true });
  const ver = encodeURIComponent(meta.last_updated || Date.now());
  const [rawData, rawEvents] = await Promise.all([
    loadJSON(`./data/map_data.json?v=${ver}`),
    loadJSON(`./data/events.json?v=${ver}`).catch(() => ({ events: [], metadata: {} }))
  ]);
  return { meta, rawData, rawEvents };
}

function el(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Missing #${id}`);
  return node;
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

function formatDate(iso, { includeTime = false } = {}) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return includeTime
      ? d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return String(iso);
  }
}

function parseHashState() {
  const state = { theater: 'ALL', lens: 'EDITORIAL', filters: [...DEFAULT_FILTERS], selected: null };
  if (!window.location.hash) return state;

  try {
    const params = new URLSearchParams(window.location.hash.slice(1));

    if (params.has('theater')) state.theater = params.get('theater') || 'ALL';

    // Lens preset (if present) overrides filters
    if (params.has('lens')) {
      const lens = String(params.get('lens') || '').toUpperCase();
      if (LENS_PRESETS[lens]) {
        state.lens = lens;
        state.filters = [...LENS_PRESETS[lens].filters];
      }
    }

    // Filters (if present) override defaults; if lens was set, filters are optional
    if (params.has('filters')) {
      const f = params.get('filters');
      state.filters = f ? f.split(',').filter(Boolean) : [];
      state.lens = inferLensFromFilters(state.filters);
      if (state.lens !== 'CUSTOM' && state.lens !== 'EDITORIAL') {
        // If filters correspond to a preset, keep that preset name
        // (unless a different lens was explicitly provided in the URL)
      }
    } else {
      // No filters param; infer lens from filters
      state.lens = inferLensFromFilters(state.filters);
    }

    if (params.has('selected')) state.selected = params.get('selected');
  } catch {
    // ignore
  }

  // Normalize: if lens preset exists, make sure filters match
  if (state.lens !== 'CUSTOM' && LENS_PRESETS[state.lens]) {
    state.filters = [...LENS_PRESETS[state.lens].filters];
  }

  return state;
}

function writeHashState(state) {
  try {
    const params = new URLSearchParams();

    if (state.theater !== 'ALL') params.set('theater', state.theater);

    // If a non-default preset is selected, store lens.
    // Otherwise store filters when custom (including empty).
    if (state.lens && state.lens !== 'EDITORIAL' && state.lens !== 'CUSTOM' && LENS_PRESETS[state.lens]) {
      params.set('lens', state.lens);
    } else {
      // Persist custom filters (including none selected)
      const isDefault = arrKey(state.filters) === arrKey(DEFAULT_FILTERS);
      if (!isDefault || state.lens === 'CUSTOM') {
        params.set('filters', (state.filters || []).join(','));
      }
    }

    if (state.selected) params.set('selected', state.selected);

    const hash = params.toString();
    const newUrl = hash ? `#${hash}` : window.location.pathname;
    window.history.replaceState(null, '', newUrl);
  } catch {
    // ignore
  }
}

function inferType(nodeName) {
  const n = String(nodeName).toLowerCase();
  if (n.includes('union') || n === 'nato' || n.includes('united nations')) return 'org';
  if (n === 'palestine' || n === 'taiwan') return 'territory';
  return 'state';
}

function normalizeData(raw) {
  const nodes = raw.nodes || raw.countries || [];
  const edges = raw.edges || [];

  const normNodes = nodes.map((n) => {
    const id = n.id || slugId(n.name);
    return {
      id,
      name: n.name,
      type: n.type || inferType(n.name),
      geoName: n.geoName ?? null,
      theaters: n.theaters || [],
      coords: n.coords,
      category: n.category,
      ihl: n.ihl || null,
      exposure: n.exposure || null,
      intensity: typeof n.intensity === 'number' ? n.intensity : 2,
      color: n.color || COLORS[n.category] || '#94a3b8',
      summary: n.summary || n.details || '',
      updated_at: n.updated_at || null,
      confidence: n.confidence || null,
      sources: n.sources || [],
      aliases: n.aliases || [],
      tags: n.tags || []
    };
  });

  const nodesById = new Map(normNodes.map((n) => [n.id, n]));
  const nodesByName = new Map(normNodes.map((n) => [n.name, n]));

  const normEdges = edges.map((e, i) => {
    const fromNode = nodesById.get(e.from) || nodesByName.get(e.from);
    const toNode = nodesById.get(e.to) || nodesByName.get(e.to);
    const from = fromNode?.id || slugId(e.from);
    const to = toNode?.id || slugId(e.to);

    return {
      id: e.id || `${from}__${to}__${String(e.type || e.category || 'EDGE').toUpperCase()}__${i}`,
      from,
      to,
      theater: e.theater,
      category: e.category,
      type: e.type || '',
      effect: e.effect || 'solid',
      color: e.color || COLORS[e.category] || '#94a3b8',
      summary: e.summary || e.details || '',
      updated_at: e.updated_at || null,
      confidence: e.confidence || null,
      sources: e.sources || [],
      layer: e.layer || null
    };
  });

  const adj = new Map();
  for (const e of normEdges) {
    if (!adj.has(e.from)) adj.set(e.from, []);
    if (!adj.has(e.to)) adj.set(e.to, []);
    adj.get(e.from).push(e);
    adj.get(e.to).push(e);
  }

  return { nodes: normNodes, edges: normEdges, nodesById, nodesByName, adj, metadata: raw.metadata || {} };
}

function buildDot(color) {
  const dot = document.createElement('span');
  dot.className = 'w-1.5 h-1.5 rounded-full';
  dot.style.background = color;
  return dot;
}

function updateStatsBar(statsBarEl, visibleNodes) {
  const counts = { WAR: 0, TENSION: 0, INTERNAL: 0, ALLY: 0, POLICY: 0, SPILLOVER: 0 };
  for (const n of visibleNodes) counts[n.category] = (counts[n.category] || 0) + 1;

  statsBarEl.replaceChildren();

  const items = [
    ['WAR', 'Wars'],
    ['INTERNAL', 'Civil'],
    ['TENSION', 'Tensions'],
    ['ALLY', 'Support'],
    ['POLICY', 'Policy'],
    ['SPILLOVER', 'Spillover']
  ];

  let any = false;
  for (const [k, label] of items) {
    if (!counts[k]) continue;
    any = true;
    const span = document.createElement('span');
    span.className = 'flex items-center gap-1';
    span.append(buildDot(COLORS[k]));
    span.append(document.createTextNode(` ${counts[k]} ${label}`));
    statsBarEl.append(span);
  }

  if (!any) {
    const span = document.createElement('span');
    span.textContent = 'No matches found';
    statsBarEl.append(span);
  }
}

function ensureEvidenceContainer() {
  let c = document.getElementById('evidence-container');
  if (c) return c;

  c = document.createElement('div');
  c.id = 'evidence-container';
  c.className = 'mb-4';

  // Insert right after badges
  const badges = el('dual-classification-badges');
  badges.insertAdjacentElement('afterend', c);
  return c;
}

function normalizeSourceItem(src) {
  if (!src) return null;

  if (typeof src === 'string') {
    const s = src.trim();
    if (!s) return null;
    const isUrl = /^https?:\/\//i.test(s);
    return {
      title: isUrl ? s.replace(/^https?:\/\//i, '') : s,
      url: isUrl ? s : null,
      publisher: null,
      published_at: null,
      accessed_at: null,
      note: null,
      citation: !isUrl ? s : null
    };
  }

  if (typeof src === 'object') {
    const url = typeof src.url === 'string' ? src.url : null;
    const title = typeof src.title === 'string' ? src.title : (url ? url.replace(/^https?:\/\//i, '') : 'Source');
    const citation = typeof src.citation === 'string' ? src.citation : null;
    return {
      title,
      url,
      publisher: typeof src.publisher === 'string' ? src.publisher : null,
      published_at: typeof src.published_at === 'string' ? src.published_at : null,
      accessed_at: typeof src.accessed_at === 'string' ? src.accessed_at : null,
      note: typeof src.note === 'string' ? src.note : null,
      citation
    };
  }

  return null;
}

function renderEvidence(container, { updated_at, confidence, sources } = {}) {
  container.replaceChildren();

  const last = formatDate(updated_at);
  const conf = confidence ?? '—';

  const details = document.createElement('details');
  details.className = 'bg-slate-800/30 p-3 rounded-lg border border-slate-700/50';

  const summary = document.createElement('summary');
  summary.className = 'cursor-pointer list-none select-none flex items-center justify-between text-xs font-semibold text-slate-200';

  const left = document.createElement('span');
  left.textContent = 'Evidence';

  const right = document.createElement('span');
  right.className = 'text-[10px] font-medium text-slate-400';
  right.textContent = `Last verified: ${last} • Confidence: ${String(conf)}`;

  summary.append(left, right);
  details.append(summary);

  const body = document.createElement('div');
  body.className = 'mt-2 space-y-2 text-xs text-slate-200';

  const metaRow = document.createElement('div');
  metaRow.className = 'grid grid-cols-1 sm:grid-cols-2 gap-2';

  const lastBox = document.createElement('div');
  lastBox.className = 'bg-slate-900/40 p-2 rounded border border-slate-700/40';
  const lastLabel = document.createElement('div');
  lastLabel.className = 'text-[10px] uppercase tracking-wider text-slate-400 font-bold';
  lastLabel.textContent = 'Last verified';
  const lastVal = document.createElement('div');
  lastVal.className = 'mt-0.5';
  lastVal.textContent = last;
  lastBox.append(lastLabel, lastVal);

  const confBox = document.createElement('div');
  confBox.className = 'bg-slate-900/40 p-2 rounded border border-slate-700/40';
  const confLabel = document.createElement('div');
  confLabel.className = 'text-[10px] uppercase tracking-wider text-slate-400 font-bold';
  confLabel.textContent = 'Confidence';
  const confVal = document.createElement('div');
  confVal.className = 'mt-0.5';
  confVal.textContent = String(conf);
  confBox.append(confLabel, confVal);

  metaRow.append(lastBox, confBox);
  body.append(metaRow);

  const srcHeader = document.createElement('div');
  srcHeader.className = 'text-[10px] uppercase tracking-wider text-slate-400 font-bold';
  srcHeader.textContent = 'Sources';
  body.append(srcHeader);

  const srcList = document.createElement('ul');
  srcList.className = 'space-y-2';

  const srcNorm = (sources || []).map(normalizeSourceItem).filter(Boolean);

  if (!srcNorm.length) {
    const li = document.createElement('li');
    li.className = 'text-slate-400';
    li.textContent = 'No sources attached yet.';
    srcList.append(li);
  } else {
    for (const s of srcNorm.slice(0, 10)) {
      const li = document.createElement('li');
      li.className = 'bg-slate-900/30 p-2 rounded border border-slate-700/40';

      const top = document.createElement('div');
      top.className = 'flex items-start justify-between gap-2';

      const title = document.createElement(s.url ? 'a' : 'div');
      title.className = s.url
        ? 'font-semibold text-slate-200 hover:underline break-words'
        : 'font-semibold text-slate-200 break-words';
      title.textContent = s.title || 'Source';
      if (s.url) {
        title.href = s.url;
        title.target = '_blank';
        title.rel = 'noreferrer';
      }

      const pub = document.createElement('div');
      pub.className = 'text-[10px] text-slate-400 whitespace-nowrap';
      const pubBits = [];
      if (s.publisher) pubBits.push(s.publisher);
      if (s.published_at) pubBits.push(formatDate(s.published_at));
      pub.textContent = pubBits.join(' • ');

      top.append(title, pub);

      li.append(top);

      if (s.note || s.citation) {
        const note = document.createElement('div');
        note.className = 'mt-1 text-[11px] text-slate-300';
        note.textContent = s.note || s.citation;
        li.append(note);
      }

      srcList.append(li);
    }
  }

  body.append(srcList);
  details.append(body);

  container.append(details);
}

function defaultAbout(meta, datasetMeta) {
  const title = (datasetMeta?.title || meta?.title || 'WorldWar Dashboard').trim();
  const last = meta?.ui_date_label || meta?.last_updated || datasetMeta?.generated_at_utc || '—';
  return {
    title,
    subtitle: 'An editorial map of active conflicts and conflict-connected power moves.',
    last_reviewed_at: last,
    sections: [
      {
        heading: 'How to read the map',
        bullets: [
          'Click a country/node to spotlight its network (connections brighten; others fade).',
          'Use “Zoom To Theater” to focus on a region.',
          'Use filters to hide interaction types when the map gets noisy.'
        ]
      },
      {
        heading: 'Lens presets',
        bullets: [
          'Editorial: all categories (default).',
          'Armed Conflict: focuses on wars & civil conflicts.',
          'War-Connectedness: focuses on support, basing, spillover.',
          'Coercion: focuses on sanctions/policy + escalation risk.'
        ]
      }
    ],
    caveats: {
      heading: 'Caveats & Definitions',
      bullets: [
        'This is an editorial project. Categories and summaries reflect the author’s assessment at the time of writing.',
        'IHL labels are included as a reference framework, not as legal determinations or official rulings.',
        'Terms like “war”, “self-defense”, or “genocide” can be contested and may change as evidence develops and formal processes conclude.',
        'Use sources and timestamps: every node/edge can carry confidence + citations (expand “Evidence” in the panel).'
      ]
    }
  };
}

function setupAboutModal({ meta, datasetMeta }) {
  const about = (datasetMeta && datasetMeta.about) ? datasetMeta.about : defaultAbout(meta, datasetMeta);

  // Create a button in the header (near the date).
  const dateBadge = document.getElementById('ui-date');
  if (dateBadge && !document.getElementById('about-btn')) {
    const btn = document.createElement('button');
    btn.id = 'about-btn';
    btn.className = 'text-[10px] sm:text-xs font-semibold bg-slate-800 text-slate-300 hover:text-white px-2 py-1 rounded-md border border-slate-700 whitespace-nowrap';
    btn.textContent = 'About';

    // Insert right after the date badge
    dateBadge.insertAdjacentElement('afterend', btn);
  }

  // Modal overlay
  if (document.getElementById('about-modal')) {
    // already exists
    return;
  }

  const overlay = document.createElement('div');
  overlay.id = 'about-modal';
  overlay.className = 'fixed inset-0 z-50 hidden items-center justify-center p-4';
  overlay.style.background = 'rgba(0,0,0,0.55)';

  const card = document.createElement('div');
  card.className = 'glass-panel w-full max-w-2xl rounded-xl p-5 md:p-6 text-slate-200 max-h-[85vh] overflow-y-auto';

  const topRow = document.createElement('div');
  topRow.className = 'flex items-start justify-between gap-3';

  const titleWrap = document.createElement('div');

  const h2 = document.createElement('h2');
  h2.className = 'text-xl md:text-2xl font-bold text-white';
  h2.textContent = about.title || 'About';

  const sub = document.createElement('div');
  sub.className = 'text-sm text-slate-300 mt-1';
  sub.textContent = about.subtitle || '';

  const last = document.createElement('div');
  last.className = 'text-[11px] text-slate-400 mt-2';
  const lastText = about.last_reviewed_at || meta?.ui_date_label || meta?.last_updated;
  last.textContent = lastText ? `Last reviewed: ${String(lastText)}` : '';

  titleWrap.append(h2, sub, last);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'text-slate-300 hover:text-white bg-slate-800 rounded-full p-2 border border-slate-600 transition-colors shrink-0';
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

  topRow.append(titleWrap, closeBtn);
  card.append(topRow);

  const body = document.createElement('div');
  body.className = 'mt-5 space-y-5';

  // Sections
  const sections = Array.isArray(about.sections) ? about.sections : [];
  for (const sec of sections) {
    const block = document.createElement('div');

    const h = document.createElement('h3');
    h.className = 'text-[11px] uppercase tracking-wider text-slate-400 font-bold mb-2';
    h.textContent = sec.heading || 'Section';

    block.append(h);

    const bullets = Array.isArray(sec.bullets) ? sec.bullets : [];
    if (bullets.length) {
      const ul = document.createElement('ul');
      ul.className = 'list-disc pl-5 space-y-1 text-sm text-slate-200';
      for (const b of bullets) {
        const li = document.createElement('li');
        li.textContent = String(b);
        ul.append(li);
      }
      block.append(ul);
    } else if (sec.body) {
      const p = document.createElement('p');
      p.className = 'text-sm text-slate-200';
      p.textContent = String(sec.body);
      block.append(p);
    }

    body.append(block);
  }

  // Caveats — intentionally hidden behind a disclosure
  const caveats = about.caveats;
  if (caveats) {
    const det = document.createElement('details');
    det.className = 'bg-slate-800/30 p-4 rounded-lg border border-slate-700/50';

    const sum = document.createElement('summary');
    sum.className = 'cursor-pointer list-none select-none text-sm font-semibold text-slate-200';
    sum.textContent = caveats.heading || 'Caveats & Definitions (click to expand)';

    det.append(sum);

    const inner = document.createElement('div');
    inner.className = 'mt-3';

    const bullets = Array.isArray(caveats.bullets) ? caveats.bullets : [];
    if (bullets.length) {
      const ul = document.createElement('ul');
      ul.className = 'list-disc pl-5 space-y-1 text-sm text-slate-200';
      for (const b of bullets) {
        const li = document.createElement('li');
        li.textContent = String(b);
        ul.append(li);
      }
      inner.append(ul);
    } else if (caveats.body) {
      const p = document.createElement('p');
      p.className = 'text-sm text-slate-200';
      p.textContent = String(caveats.body);
      inner.append(p);
    }

    det.append(inner);
    body.append(det);
  }

  card.append(body);
  overlay.append(card);
  document.body.append(overlay);

  const open = () => {
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
  };

  const close = () => {
    overlay.classList.add('hidden');
    overlay.classList.remove('flex');
  };

  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !overlay.classList.contains('hidden')) close();
  });

  const btn = document.getElementById('about-btn');
  if (btn) btn.addEventListener('click', open);
}

function initUI({ meta, data, events }) {
  el('ui-date').textContent = meta.ui_date_label || meta.last_updated || '—';

  // About modal (intentionally opened)
  setupAboutModal({ meta, datasetMeta: data.metadata });

  // Collapsible filters
  const toggleBtn = el('toggle-filters-btn');
  const filterControls = el('filter-controls-container');
  const iconUp = el('icon-chevron-up');
  const iconDown = el('icon-chevron-down');

  let filtersVisible = window.innerWidth > 768;
  if (!filtersVisible) {
    filterControls.classList.add('collapsed');
    iconUp.classList.add('hidden');
    iconDown.classList.remove('hidden');
  }

  toggleBtn.addEventListener('click', () => {
    filtersVisible = !filtersVisible;
    if (filtersVisible) {
      filterControls.classList.remove('collapsed');
      iconUp.classList.remove('hidden');
      iconDown.classList.add('hidden');
    } else {
      filterControls.classList.add('collapsed');
      iconUp.classList.add('hidden');
      iconDown.classList.remove('hidden');
    }
  });

  // Lens controls (preset groupings)
  const lensWrap = document.createElement('div');
  lensWrap.className = 'mb-4';
  lensWrap.id = 'lens-controls';

  const lensHeader = document.createElement('div');
  lensHeader.className = 'flex justify-between items-center mb-2';
  const lensTitle = document.createElement('h4');
  lensTitle.className = 'text-[10px] uppercase tracking-wider text-slate-500 font-bold';
  lensTitle.textContent = 'Lens';

  const lensHint = document.createElement('div');
  lensHint.id = 'lens-hint';
  lensHint.className = 'text-[10px] text-slate-400';
  lensHint.textContent = '';

  lensHeader.append(lensTitle, lensHint);

  const lensBtnsRow = document.createElement('div');
  lensBtnsRow.className = 'flex flex-wrap gap-1.5';

  const lensButtons = new Map();

  for (const [lensKey, preset] of Object.entries(LENS_PRESETS)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.lens = lensKey;
    b.className = 'px-2.5 py-1 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs rounded border border-slate-700 transition-colors';
    b.textContent = preset.label;
    lensButtons.set(lensKey, b);
    lensBtnsRow.append(b);
  }

  const customBadge = document.createElement('span');
  customBadge.id = 'lens-custom-badge';
  customBadge.className = 'px-2 py-1 text-[10px] font-bold uppercase tracking-wide bg-slate-900/50 text-slate-300 rounded border border-slate-700/50 hidden';
  customBadge.textContent = 'Custom';
  lensBtnsRow.append(customBadge);

  lensWrap.append(lensHeader, lensBtnsRow);

  // Insert lens controls right above the interaction filters (preferred).
  // If the expected DOM structure changes, fall back to prepending.
  const toggleAll = document.getElementById('toggle-all-filters');
  const filtersSection = toggleAll ? toggleAll.closest('div')?.parentElement : null;
  if (filtersSection && filtersSection.parentElement === filterControls) {
    filterControls.insertBefore(lensWrap, filtersSection);
  } else {
    filterControls.prepend(lensWrap);
  }

  // Datalist
  const datalist = el('country-datalist');
  datalist.replaceChildren();
  for (const n of data.nodes) {
    const opt = document.createElement('option');
    opt.value = n.name;
    datalist.append(opt);
  }

  const state = parseHashState();
  // If URL didn't explicitly include lens, infer from filters
  state.lens = state.lens || inferLensFromFilters(state.filters);

  const chart = echarts.init(el('map-container'));

  const evidenceContainer = ensureEvidenceContainer();

  const syncLensUI = () => {
    const lens = state.lens;

    // Highlight preset buttons
    for (const [k, btn] of lensButtons.entries()) {
      const active = lens === k;
      btn.classList.toggle('bg-blue-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-slate-800', !active);
      btn.classList.toggle('text-slate-300', !active);
    }

    const isCustom = lens === 'CUSTOM';
    customBadge.classList.toggle('hidden', !isCustom);

    // Hint text
    const hintEl = document.getElementById('lens-hint');
    if (hintEl) {
      if (isCustom) {
        hintEl.textContent = 'Custom filters';
      } else {
        hintEl.textContent = LENS_PRESETS[lens]?.hint || '';
      }
    }
  };

  const syncFilterUI = () => {
    document.querySelectorAll('.filter-cb').forEach((cb) => {
      cb.checked = state.filters.includes(cb.value);
    });
    el('toggle-all-filters').textContent = state.filters.length === DEFAULT_FILTERS.length ? 'Deselect All' : 'Select All';

    document.querySelectorAll('.theater-btn').forEach((btn) => {
      const active = btn.dataset.theater === state.theater;
      btn.classList.toggle('bg-blue-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-slate-800', !active);
      btn.classList.toggle('text-slate-300', !active);
    });

    syncLensUI();
  };

  const renderLinePanel = (lineDatum) => {
    el('info-title').textContent = `${lineDatum.fromName} → ${lineDatum.toName}`;

    const badges = el('dual-classification-badges');
    badges.replaceChildren();
    const badge = document.createElement('span');
    badge.className = 'px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wide';
    badge.style.background = `${lineDatum.color}30`;
    badge.style.color = lineDatum.color;
    badge.style.border = `1px solid ${lineDatum.color}`;
    badge.textContent = lineDatum.type;
    badges.append(badge);

    el('info-context').textContent = lineDatum.summary || '';

    // Evidence (collapsed by default)
    renderEvidence(evidenceContainer, {
      updated_at: lineDatum.updated_at,
      confidence: lineDatum.confidence,
      sources: lineDatum.sources
    });

    el('connections-container').classList.add('hidden');
    el('events-container').classList.add('hidden');
    setPanelOpen(true);
  };

  const renderNodePanel = (nodeId) => {
    const node = data.nodesById.get(nodeId);
    if (!node) return;

    el('info-title').textContent = node.name;
    el('info-context').textContent = node.summary || '';

    // Badges
    const badges = el('dual-classification-badges');
    badges.replaceChildren();

    const ihl = document.createElement('span');
    ihl.className = 'px-2.5 py-1 rounded-md text-[10px] sm:text-xs font-bold uppercase tracking-wide bg-slate-800 border border-slate-600 text-slate-300';
    ihl.textContent = `IHL: ${node.ihl ?? '—'}`;
    badges.append(ihl);

    const policy = document.createElement('span');
    policy.className = 'px-2.5 py-1 rounded-md text-[10px] sm:text-xs font-bold uppercase tracking-wide';
    policy.style.background = `${node.color}30`;
    policy.style.color = node.color;
    policy.style.border = `1px solid ${node.color}`;
    policy.textContent = `Policy: ${node.exposure ?? '—'}`;
    badges.append(policy);

    // Evidence (collapsed by default)
    renderEvidence(evidenceContainer, {
      updated_at: node.updated_at,
      confidence: node.confidence,
      sources: node.sources
    });

    // Connections
    const edges = data.adj.get(nodeId) || [];
    const connectionsContainer = el('connections-container');
    const list = el('info-connections');
    list.replaceChildren();

    if (edges.length) {
      connectionsContainer.classList.remove('hidden');
      for (const e of edges) {
        const otherId = e.from === nodeId ? e.to : e.from;
        const other = data.nodesById.get(otherId);
        if (!other) continue;

        const li = document.createElement('li');
        li.className = 'flex items-start gap-2 bg-slate-800/40 p-2.5 rounded border border-slate-700/50 hover:bg-slate-700/50 transition-colors cursor-pointer';
        li.addEventListener('click', () => selectNode(otherId));

        const dot = document.createElement('span');
        dot.className = 'w-2.5 h-2.5 rounded-full mt-1 shrink-0';
        dot.style.background = e.color;
        dot.style.boxShadow = `0 0 5px ${e.color}`;

        const wrap = document.createElement('div');

        const title = document.createElement('div');
        title.className = 'font-semibold text-slate-200';
        title.textContent = other.name;

        const metaRow = document.createElement('div');
        metaRow.className = 'flex items-center gap-2 mt-0.5';

        const dir = document.createElement('span');
        dir.className = 'text-[10px] uppercase font-bold text-slate-400 bg-slate-700/50 px-1 rounded';
        dir.textContent = (e.from === nodeId) ? '→ To' : '← From';

        const kind = document.createElement('span');
        kind.className = 'text-xs font-medium';
        kind.style.color = e.color;
        kind.textContent = e.type;

        metaRow.append(dir, kind);
        wrap.append(title, metaRow);
        li.append(dot, wrap);
        list.append(li);
      }
    } else {
      connectionsContainer.classList.add('hidden');
    }

    // Events (optional feed)
    const evContainer = el('events-container');
    const evList = el('info-events');
    evList.replaceChildren();

    const related = (events.events || []).filter((evt) => {
      const tags = evt.tags || [];
      return tags.includes(nodeId) || tags.includes(node.name);
    }).slice(0, 5);

    if (related.length) {
      evContainer.classList.remove('hidden');
      for (const evt of related) {
        const li = document.createElement('li');
        li.className = 'bg-slate-800/40 p-2.5 rounded border border-slate-700/50';

        const a = document.createElement('a');
        a.href = evt.url || '#';
        a.target = '_blank';
        a.rel = 'noreferrer';
        a.className = 'font-semibold text-slate-200 hover:underline';
        a.textContent = evt.headline || 'Untitled event';

        const metaRow = document.createElement('div');
        metaRow.className = 'text-xs text-slate-400 mt-1';
        metaRow.textContent = evt.published_at ? formatDate(evt.published_at, { includeTime: true }) : '';

        li.append(a, metaRow);
        evList.append(li);
      }
    } else {
      evContainer.classList.add('hidden');
    }

    setPanelOpen(true);
  };

  const updateMap = () => {
    // First compute which nodes are visible under current filters
    const visibleNodes = data.nodes.filter((n) => {
      const matchesCat = state.filters.includes(n.category);
      const matchesTheater = state.theater === 'ALL' || n.theaters.includes(state.theater);
      return matchesCat && matchesTheater;
    });

    updateStatsBar(el('stats-bar'), visibleNodes);

    const visibleIds = new Set(visibleNodes.map((n) => n.id));

    // If selection is no longer visible (e.g., lens changed), drop selection
    if (state.selected && !visibleIds.has(state.selected)) {
      state.selected = null;
      setPanelOpen(false);
    }

    const connectedNodes = new Set();
    const connectedEdgeIds = new Set();

    if (state.selected) {
      connectedNodes.add(state.selected);
      for (const e of (data.adj.get(state.selected) || [])) {
        connectedNodes.add(e.from);
        connectedNodes.add(e.to);
        connectedEdgeIds.add(e.id);
      }
    }

    const mapNodes = visibleNodes.map((n) => {
      const isSelected = state.selected === n.id;
      const isConnected = connectedNodes.has(n.id);
      const opacity = state.selected ? (isConnected ? 1 : 0.2) : 1;
      const size = (n.intensity * 2) + 3;

      return {
        name: n.name,
        value: n.coords.concat([size]),
        itemStyle: {
          color: n.color,
          opacity,
          borderColor: isSelected ? '#ffffff' : n.color,
          borderWidth: isSelected ? 2 : 1,
          shadowBlur: isConnected ? 10 : 0,
          shadowColor: n.color
        },
        nodeId: n.id,
        ihl: n.ihl,
        status: n.exposure,
        details: n.summary
      };
    });

    const focusNodes = mapNodes.filter((n) => n.nodeId === state.selected);
    const ambientNodes = mapNodes.filter((n) => n.nodeId !== state.selected);

    const filteredEdges = data.edges.filter((e) => {
      const matchesCat = state.filters.includes(e.category);
      const matchesTheater = state.theater === 'ALL' || e.theater === state.theater;
      const fromValid = visibleIds.has(e.from);
      const toValid = visibleIds.has(e.to);
      return matchesCat && matchesTheater && fromValid && toValid;
    });

    const mapLines = filteredEdges.map((e, idx) => {
      const fromNode = data.nodesById.get(e.from);
      const toNode = data.nodesById.get(e.to);
      if (!fromNode || !toNode) return null;

      const isConnected = state.selected ? connectedEdgeIds.has(e.id) : false;
      const opacity = state.selected ? (isConnected ? 0.85 : 0.02) : 0.15;
      const lineWidth = isConnected ? 2.5 : 1;

      const baseCurve = 0.2 + (idx % 3) * 0.1;
      const curveness = e.from < e.to ? baseCurve : -baseCurve;

      return {
        coords: [fromNode.coords, toNode.coords],
        fromName: fromNode.name,
        toName: toNode.name,
        type: e.type,
        summary: e.summary,
        color: e.color,
        edgeId: e.id,
        updated_at: e.updated_at,
        confidence: e.confidence,
        sources: e.sources,
        lineStyle: {
          color: e.color,
          width: lineWidth,
          type: e.effect,
          curveness,
          opacity
        }
      };
    }).filter(Boolean);

    // Fill polygons only for state/territory nodes
    const mapFills = visibleNodes
      .filter((n) => (n.type === 'state' || n.type === 'territory') && n.geoName)
      .map((n) => ({
        name: n.geoName,
        itemStyle: {
          areaColor: n.color + (state.selected && !connectedNodes.has(n.id) ? '05' : '30'),
          borderColor: n.color + (state.selected && !connectedNodes.has(n.id) ? '10' : 'ff')
        }
      }));

    chart.setOption({
      geo: { id: 'baseGeo', regions: mapFills },
      series: [
        {
          id: 'focusNode',
          name: 'focusNode',
          type: 'effectScatter',
          coordinateSystem: 'geo',
          geoIndex: 0,
          zlevel: 3,
          rippleEffect: { brushType: 'stroke', scale: 3 },
          symbolSize: (val) => val[2] * 1.2,
          data: focusNodes
        },
        {
          id: 'ambientNodes',
          name: 'ambientNodes',
          type: 'scatter',
          coordinateSystem: 'geo',
          geoIndex: 0,
          zlevel: 2,
          symbolSize: (val) => val[2],
          data: ambientNodes
        },
        {
          id: 'linesSeries',
          name: 'linesSeries',
          type: 'lines',
          coordinateSystem: 'geo',
          geoIndex: 0,
          zlevel: 1,
          symbol: ['none', 'arrow'],
          symbolSize: 6,
          effect: { show: true, period: 4, trailLength: 0.1, symbol: 'circle', symbolSize: 3 },
          data: mapLines
        }
      ]
    });

    // Keep lens in sync if user created a custom filter selection
    const lensNow = inferLensFromFilters(state.filters);
    if (lensNow !== state.lens) {
      state.lens = lensNow;
      syncLensUI();
    }
  };

  const selectNode = (nodeId) => {
    const node = data.nodesById.get(nodeId);
    if (!node) return;

    if (state.theater !== 'ALL' && !node.theaters.includes(state.theater)) state.theater = 'ALL';

    state.selected = nodeId;
    chart.setOption({ geo: { center: node.coords, zoom: 4 } });

    syncFilterUI();
    updateMap();
    renderNodePanel(nodeId);
    writeHashState(state);
  };

  const clearSelection = () => {
    state.selected = null;
    updateMap();
    setPanelOpen(false);
    writeHashState(state);
  };

  // Lens button actions
  for (const [lensKey, btn] of lensButtons.entries()) {
    btn.addEventListener('click', () => {
      state.lens = lensKey;
      state.filters = [...LENS_PRESETS[lensKey].filters];
      state.selected = null;
      setPanelOpen(false);
      syncFilterUI();
      updateMap();
      writeHashState(state);
    });
  }

  // Initial map center/zoom
  let initialCenter = [10, 30];
  let initialZoom = 1.2;
  if (state.theater !== 'ALL') {
    const btn = document.querySelector(`.theater-btn[data-theater="${state.theater}"]`);
    if (btn) {
      initialCenter = JSON.parse(btn.dataset.center);
      initialZoom = parseFloat(btn.dataset.zoom);
    }
  }
  if (state.selected && data.nodesById.get(state.selected)) {
    initialCenter = data.nodesById.get(state.selected).coords;
    initialZoom = 4;
  }

  chart.setOption({
    backgroundColor: 'transparent',
    geo: {
      id: 'baseGeo',
      map: 'world',
      roam: true,
      zoom: initialZoom,
      center: initialCenter,
      label: { emphasis: { show: false } },
      itemStyle: { areaColor: COLORS.MAP_BG, borderColor: COLORS.MAP_BORDER, borderWidth: 1 },
      emphasis: { itemStyle: { areaColor: '#1e2538' } }
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#fff' },
      formatter: (params) => {
        if (!params) return '';
        if (params.seriesType === 'effectScatter' || params.seriesType === 'scatter') {
          const d = params.data || {};
          const name = escapeHTML(d.name);
          const ihl = escapeHTML(d.ihl);
          const status = escapeHTML(d.status);
          const details = escapeHTML(d.details);
          const color = d?.itemStyle?.color || '#94a3b8';
          return `
            <div class="font-bold text-base mb-1">${name}</div>
            <div class="text-xs mb-1 text-slate-300"><span class="font-bold text-slate-400">IHL:</span> ${ihl}</div>
            <div class="text-xs px-2 py-0.5 rounded-full inline-block mb-2 mt-1" style="background:${color}40; color:${color}; border: 1px solid ${color}">${status}</div>
            <div class="text-sm max-w-[250px] whitespace-normal text-slate-200">${details}</div>
          `;
        }
        if (params.seriesType === 'lines') {
          const d = params.data || {};
          const fromName = escapeHTML(d.fromName);
          const toName = escapeHTML(d.toName);
          const type = escapeHTML(d.type);
          const details = escapeHTML(d.summary);
          const color = d.color || '#94a3b8';
          return `
            <div class="font-bold mb-1">${fromName} &rarr; ${toName}</div>
            <div class="text-xs mb-1 font-semibold" style="color:${color}">${type}</div>
            <div class="text-sm max-w-[250px] whitespace-normal text-slate-200">${details}</div>
          `;
        }
        return '';
      }
    }
  });

  // ECharts interactions
  chart.on('click', (params) => {
    if (params.seriesType === 'effectScatter' || params.seriesType === 'scatter') {
      const nodeId = params?.data?.nodeId;
      if (nodeId) {
        state.selected = nodeId;
        updateMap();
        renderNodePanel(nodeId);
        writeHashState(state);
      }
      return;
    }

    if (params.seriesType === 'lines') {
      state.selected = null;
      updateMap();
      renderLinePanel(params.data);
      writeHashState(state);
    }
  });

  chart.getZr().on('click', (e) => {
    if (!e.target) clearSelection();
  });

  window.addEventListener('resize', () => chart.resize());

  // Filters
  document.querySelectorAll('.filter-cb').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const v = e.target.value;
      if (e.target.checked) {
        if (!state.filters.includes(v)) state.filters.push(v);
      } else {
        state.filters = state.filters.filter((x) => x !== v);
      }

      state.lens = inferLensFromFilters(state.filters);

      updateMap();
      writeHashState(state);
      syncFilterUI();
    });
  });

  el('toggle-all-filters').addEventListener('click', () => {
    state.filters = state.filters.length === DEFAULT_FILTERS.length ? [] : [...DEFAULT_FILTERS];
    state.lens = inferLensFromFilters(state.filters);
    syncFilterUI();
    updateMap();
    writeHashState(state);
  });

  // Theater buttons
  document.querySelectorAll('.theater-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      state.theater = e.target.dataset.theater;
      const center = JSON.parse(e.target.dataset.center);
      const zoom = parseFloat(e.target.dataset.zoom);
      chart.setOption({ geo: { center, zoom } });
      state.selected = null;
      setPanelOpen(false);
      syncFilterUI();
      updateMap();
      writeHashState(state);
    });
  });

  // Search
  const searchInput = el('country-search');
  searchInput.addEventListener('input', (e) => {
    const val = e.target.value;
    if (!val) return;
    const n = data.nodes.find((x) => x.name.toLowerCase() === val.toLowerCase());
    if (n) {
      selectNode(n.id);
      searchInput.value = '';
      searchInput.blur();
    }
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = e.target.value;
      const match = data.nodes.find((x) => x.name.toLowerCase() === val.toLowerCase());
      if (!match) {
        searchInput.classList.add('animate-shake', 'border-red-500');
        setTimeout(() => searchInput.classList.remove('animate-shake', 'border-red-500'), 700);
      }
    }
  });

  // Close panel
  el('close-panel').addEventListener('click', clearSelection);

  syncFilterUI();
  updateMap();

  if (state.selected) renderNodePanel(state.selected);
}

(async function main() {
  try {
    const { meta, rawData, rawEvents } = await loadAll();
    const data = normalizeData(rawData);
    initUI({ meta, data, events: rawEvents });
  } catch (err) {
    console.error(err);
    alert('Failed to load data. Check console for details.');
  }
})();
