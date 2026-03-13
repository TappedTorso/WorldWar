/*
  WorldWar Dashboard — refactor starter

  Goals implemented:
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

function parseHashState() {
  const state = { theater: 'ALL', filters: [...DEFAULT_FILTERS], selected: null };
  if (!window.location.hash) return state;
  try {
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (params.has('theater')) state.theater = params.get('theater') || 'ALL';
    if (params.has('filters')) {
      const f = params.get('filters');
      if (f) state.filters = f.split(',').filter(Boolean);
    }
    if (params.has('selected')) state.selected = params.get('selected');
  } catch {
    // ignore
  }
  return state;
}

function writeHashState(state) {
  try {
    const params = new URLSearchParams();
    if (state.theater !== 'ALL') params.set('theater', state.theater);
    if (state.filters.length > 0 && state.filters.length < DEFAULT_FILTERS.length) {
      params.set('filters', state.filters.join(','));
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
      sources: n.sources || []
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
      sources: e.sources || []
    };
  });

  const adj = new Map();
  for (const e of normEdges) {
    if (!adj.has(e.from)) adj.set(e.from, []);
    if (!adj.has(e.to)) adj.set(e.to, []);
    adj.get(e.from).push(e);
    adj.get(e.to).push(e);
  }

  return { nodes: normNodes, edges: normEdges, nodesById, nodesByName, adj };
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

function initUI({ meta, data, events }) {
  el('ui-date').textContent = meta.ui_date_label || meta.last_updated || '—';

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

  // Datalist
  const datalist = el('country-datalist');
  datalist.replaceChildren();
  for (const n of data.nodes) {
    const opt = document.createElement('option');
    opt.value = n.name;
    datalist.append(opt);
  }

  const state = parseHashState();
  const chart = echarts.init(el('map-container'));

  const syncFilterUI = () => {
    document.querySelectorAll('.filter-cb').forEach((cb) => {
      cb.checked = state.filters.includes(cb.value);
    });
    el('toggle-all-filters').textContent = state.filters.length === 0 ? 'Select All' : 'Deselect All';

    document.querySelectorAll('.theater-btn').forEach((btn) => {
      const active = btn.dataset.theater === state.theater;
      btn.classList.toggle('bg-blue-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-slate-800', !active);
      btn.classList.toggle('text-slate-300', !active);
    });
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

        const meta = document.createElement('div');
        meta.className = 'text-xs text-slate-400 mt-1';
        meta.textContent = evt.published_at ? new Date(evt.published_at).toLocaleString() : '';

        li.append(a, meta);
        evList.append(li);
      }
    } else {
      evContainer.classList.add('hidden');
    }

    setPanelOpen(true);
  };

  const updateMap = () => {
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

    const visibleNodes = data.nodes.filter((n) => {
      const matchesCat = state.filters.includes(n.category);
      const matchesTheater = state.theater === 'ALL' || n.theaters.includes(state.theater);
      return matchesCat && matchesTheater;
    });

    updateStatsBar(el('stats-bar'), visibleNodes);
    const visibleIds = new Set(visibleNodes.map((n) => n.id));

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
    }, { notMerge: true });
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
      updateMap();
      writeHashState(state);
      syncFilterUI();
    });
  });

  el('toggle-all-filters').addEventListener('click', () => {
    state.filters = state.filters.length ? [] : [...DEFAULT_FILTERS];
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
