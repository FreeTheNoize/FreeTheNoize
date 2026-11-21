/* FreeTheNoize UI.
 *
 * Same page for the desktop window and for browsers: everything goes through
 * the HTTP API (/api/*) and live updates arrive over Server-Sent Events. In
 * the desktop window, window.pywebview.api adds native dialogs, "show in
 * folder" and the SoundCloud sign-in window.
 */
(function () {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const { SpectrogramView, CMAP_NAMES, fmtHz, fmtTime } = window.Spectro;

  const state = {
    mode: 'desktop',
    settings: {},
    jobs: new Map(),
    resolving: new Map(),
    subs: new Map(),
    soundcloud: { logged_in: false },
    ytdlp: '',
    version: '',
    library: [],
  };
  const isServer = () => state.mode === 'server';

  // ── HTTP ───────────────────────────────────────────────────────────────

  class HttpError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function http(method, url, body, { quiet = false } = {}) {
    const opts = { method, headers: {}, credentials: 'same-origin' };
    if (body instanceof FormData) opts.body = body;
    else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
    let res;
    try { res = await fetch(url, opts); }
    catch (e) { if (!quiet) toast('Sin conexión con FreeTheNoize.', 'error'); throw e; }
    const data = res.headers.get('content-type')?.includes('json') ? await res.json() : null;
    if (!res.ok) {
      const msg = (data && (data.error || data.detail)) || res.statusText;
      if (res.status === 401) showGate();
      else if (!quiet) toast(msg, 'error');
      throw new HttpError(res.status, msg);
    }
    return data;
  }
  const GET = (u, o) => http('GET', u, undefined, o);
  const POST = (u, b, o) => http('POST', u, b ?? {}, o);
  const PATCH = (u, b) => http('PATCH', u, b);
  const DEL = (u) => http('DELETE', u);
  const q = (path) => encodeURIComponent(path);

  // ── Native bridge (desktop window only) ────────────────────────────────

  let nativeReady = null;
  function native() {
    if (state.mode !== 'desktop') return Promise.resolve(null);
    if (!nativeReady) {
      nativeReady = new Promise((resolve) => {
        if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
        window.addEventListener('pywebviewready', () => resolve(window.pywebview.api), { once: true });
        setTimeout(() => resolve(window.pywebview && window.pywebview.api || null), 4000);
      });
    }
    return nativeReady;
  }

  // Pick audio files: native dialog (paths) or browser picker + upload.
  async function pickAudio(multiple = false) {
    const n = await native();
    if (n) return await n.choose_audio_files(multiple);
    const input = $('#file-input');
    input.multiple = multiple;
    input.value = '';
    const files = await new Promise((resolve) => {
      input.onchange = () => resolve([...input.files]);
      input.click();
    });
    return uploadFiles(files);
  }

  async function uploadFiles(files) {
    const paths = [];
    for (const f of files) {
      const t = toast(`Subiendo ${f.name}…`, '', 0);
      try {
        const fd = new FormData();
        fd.append('file', f, f.name);
        const r = await http('POST', '/api/upload', fd);
        paths.push(r.path);
      } finally { t.remove(); }
    }
    return paths;
  }

  async function reveal(path) {
    const n = await native();
    if (n) return n.reveal(path);
    const a = h('a', { href: '/api/files/download?path=' + q(path), download: '' });
    document.body.append(a); a.click(); a.remove();
  }
  async function openUrl(url) {
    const n = await native();
    if (n) return n.open_url(url);
    window.open(url, '_blank', 'noopener');
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  function toast(text, kind = '', ms) {
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.textContent = text;
    $('#toasts').append(el);
    const life = ms ?? (kind === 'error' ? 7000 : 3500);
    if (life) setTimeout(() => el.remove(), life);
    return el;
  }

  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (k === 'style') el.setAttribute('style', v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  const ICONS = {
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    retry: '<path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4"/>',
    folder: '<path d="M3 7h6l2 2h10v9H3z"/>',
    save: '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/>',
    wave: '<path d="M4 18V9m4 9V5m4 13v-7m4 7V7m4 11v-4"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    play: '<path d="M7 5v14l12-7z" fill="currentColor" stroke="none"/>',
    pause: '<path d="M7 5h3v14H7zM14 5h3v14h-3z" fill="currentColor" stroke="none"/>',
    trash: '<path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13"/>',
    sync: '<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/>',
    ab: '<path d="M8 4v16M16 4v16M4 8h8M12 16h8"/>',
  };
  function iconBtn(icon, title, onclick) {
    const b = h('button', { class: 'btn icon ghost', title, 'aria-label': title, onclick });
    b.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[icon]}</svg>`;
    return b;
  }
  const fileIcon = () => (state.mode === 'desktop' ? ['folder', 'Mostrar en carpeta'] : ['save', 'Descargar al dispositivo']);

  function badge(quality) {
    if (!quality) return null;
    const cls = ['badge', quality.tier, quality.lossless && 'lossless', quality.preview && 'preview'].filter(Boolean).join(' ');
    return h('span', { class: cls }, quality.label);
  }

  // Camelot wheel colours, as on a DJ's key wheel.
  function camelotFromKey(key) {
    if (!key) return null;
    const MAJ = { C: 8, G: 9, D: 10, A: 11, E: 12, B: 1, 'F#': 2, Gb: 2, Db: 3, 'C#': 3, Ab: 4, 'G#': 4, Eb: 5, 'D#': 5, Bb: 6, 'A#': 6, F: 7 };
    const MIN = { A: 8, E: 9, B: 10, 'F#': 11, Gb: 11, 'C#': 12, Db: 12, 'G#': 1, Ab: 1, 'D#': 2, Eb: 2, 'A#': 3, Bb: 3, F: 4, C: 5, G: 6, D: 7 };
    if (/^\d{1,2}[AB]$/.test(key)) return key;
    const m = /^([A-G][#b]?)(m|min|minor)?$/i.exec(key.trim());
    if (!m) return null;
    const note = m[1][0].toUpperCase() + m[1].slice(1);
    const n = m[2] ? MIN[note] : MAJ[note];
    return n ? `${n}${m[2] ? 'A' : 'B'}` : null;
  }
  function camChip(camelot, key) {
    const c = camelot || camelotFromKey(key);
    if (!c) return key ? h('span', { class: 'bpm' }, key) : null;
    const n = parseInt(c, 10);
    const minor = c.endsWith('A');
    const bg = `hsl(${((n - 1) * 30 + 75) % 360} ${minor ? 70 : 85}% ${minor ? 62 : 70}%)`;
    return h('span', { class: 'cam', style: `background:${bg}`, title: key || '' }, c);
  }
  const bpmChip = (bpm) => (bpm ? h('span', { class: 'bpm' }, `${Math.round(bpm * 10) / 10} BPM`) : null);

  const fmtBytes = (b) => (b == null ? '' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB/s' : (b / 1e3).toFixed(0) + ' kB/s');
  const num = (v, d = 1) => (v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d));
  const baseName = (p) => (p || '').split(/[\\/]/).pop();
  const art = (url, cls = 'art') => h('div', { class: cls + (url ? '' : ' empty'), style: url ? `background-image:url("${url.replace(/"/g, '%22')}")` : null });

  // ── Navigation ─────────────────────────────────────────────────────────

  function show(view) {
    $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
    $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === view));
    document.body.classList.remove('nav-open');
    $('#scrim').hidden = true;
    $('#content').scrollTop = 0;
    if (view === 'history') loadHistory();
    if (view === 'library') loadLibrary();
    try { localStorage.setItem('ftn.view', view); } catch (_) {}
  }
  $$('[data-view]').forEach((b) => b.tagName === 'BUTTON' && b.addEventListener('click', () => show(b.dataset.view)));
  $('#menu-btn').addEventListener('click', () => { document.body.classList.add('nav-open'); $('#scrim').hidden = false; });
  $('#scrim').addEventListener('click', () => { document.body.classList.remove('nav-open'); $('#scrim').hidden = true; });

  // ── Ticker ─────────────────────────────────────────────────────────────

  function renderTicker() {
    const jobs = [...state.jobs.values()];
    const active = jobs.filter((j) => ['queued', 'downloading', 'tagging'].includes(j.status)).length;
    const done = jobs.filter((j) => j.status === 'done').length;
    const sc = state.soundcloud;
    const items = [
      ['FREE THE NOIZE', `v${state.version}`],
      ['COLA', active ? `${active} activas` : 'en calma'],
      ['HECHAS', String(done)],
      ['SOUNDCLOUD', sc.logged_in ? (sc.username || 'conectado') : 'sin sesión'],
      ['SUSCRIPCIONES', String(state.subs.size)],
      ['YT-DLP', state.ytdlp],
      ['MODO', isServer() ? 'servicio web' : 'escritorio'],
      ['APOYA A LOS ARTISTAS', '♥'],
    ];
    const line = items.map(([k, v]) => `<span>${k} <b>${escapeHtml(v)}</b></span>`).join('');
    $('#ticker').innerHTML = line + line;
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  // ── Downloads ──────────────────────────────────────────────────────────

  const urlInput = $('#url-input');
  urlInput.addEventListener('input', () => {
    urlInput.style.height = 'auto';
    urlInput.style.height = urlInput.scrollHeight + 'px';
  });
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitUrls(); }
  });
  $('#download-btn').addEventListener('click', () => submitUrls());

  async function submitUrls(text) {
    const value = typeof text === 'string' ? text : urlInput.value;
    const res = await POST('/api/downloads', { text: value });
    if (!res.accepted) { toast('No he encontrado ningún enlace.', 'error'); return false; }
    if (typeof text !== 'string') { urlInput.value = ''; urlInput.style.height = 'auto'; }
    return true;
  }

  // Drag & drop: links go to the queue, audio files to the analyser/converter.
  let dragDepth = 0;
  document.addEventListener('dragenter', (e) => { e.preventDefault(); if (dragDepth++ === 0) $('#dropmask').hidden = false; });
  document.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('#dropmask').hidden = true; } });
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragDepth = 0;
    $('#dropmask').hidden = true;
    const files = [...(e.dataTransfer.files || [])].filter((f) => /\.(wav|flac|aiff?|mp3|m4a|aac|opus|ogg)$/i.test(f.name));
    if (files.length) {
      const current = $('.view.active').dataset.view;
      const paths = await uploadFiles(files);
      if (current === 'convert') { addConvertFiles(paths); return; }
      if (current === 'compare' && paths.length >= 2) { setSlot('a', paths[0]); setSlot('b', paths[1]); return; }
      show('analyze');
      analyzeFile(paths[0]);
      return;
    }
    const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
    if (text) { show('downloads'); submitUrls(text); }
  });

  function renderResolving() {
    const box = $('#resolving');
    box.innerHTML = '';
    for (const [url, r] of state.resolving) {
      box.append(h('span', { class: 'chip' + (r.error ? ' error' : '') },
        r.error ? null : h('span', { class: 'spin' }),
        r.error ? `✗ ${url}: ${r.error}` : `leyendo ${url}`));
    }
  }

  const STATUS = {
    queued: 'en cola', downloading: 'bajando', tagging: 'etiquetando', done: 'hecho',
    skipped: 'ya la tienes', error: 'error', cancelled: 'cancelada',
  };

  function jobRow(job) {
    const sub = job.error
      ? h('div', { class: 'sub err' }, job.error)
      : h('div', { class: 'sub' }, [job.artist || job.uploader, job.playlist].filter(Boolean).join(' · '));
    const meta = h('div', { class: 'meta' }, h('div', { class: 'title' }, job.title), sub);
    if (job.status === 'downloading' || job.status === 'tagging') {
      meta.append(h('div', { class: 'progress' + (job.status === 'tagging' || !job.progress ? ' indet' : '') },
        h('div', { style: `width:${(job.progress * 100).toFixed(1)}%` })));
    }
    if (job.warnings && job.warnings.length && job.status === 'done') {
      meta.append(h('div', { class: 'sub warn', title: job.warnings.join('\n') }, '⚠ ' + job.warnings[0]));
    }
    const actions = h('div', { class: 'actions' }, bpmChip(job.bpm), camChip(job.camelot, job.key), badge(job.quality));
    let status = STATUS[job.status] || job.status;
    if (job.status === 'downloading') {
      status = `${Math.round(job.progress * 100)}%` + (job.speed ? ` · ${fmtBytes(job.speed)}` : '');
    }
    actions.append(h('span', { class: 'status' }, status));
    if (job.status === 'queued' || job.status === 'downloading') actions.append(iconBtn('x', 'Cancelar', () => POST(`/api/downloads/${job.id}/cancel`)));
    if (job.status === 'error' || job.status === 'cancelled') actions.append(iconBtn('retry', 'Reintentar', () => POST(`/api/downloads/${job.id}/retry`)));
    if (job.status === 'done' && job.path) {
      actions.append(iconBtn('play', 'Escuchar', () => player.play({ path: job.path, title: job.title, sub: job.artist, cover: job.thumbnail })));
      actions.append(iconBtn('wave', 'Espectro', () => { show('analyze'); analyzeFile(job.path); }));
      actions.append(iconBtn(...fileIcon(), () => reveal(job.path)));
    }
    return h('div', { class: `row-item status-${job.status}`, 'data-job': job.id }, art(job.thumbnail), meta, actions);
  }

  function renderJob(job) {
    const list = $('#job-list');
    const old = list.querySelector(`[data-job="${job.id}"]`);
    const row = jobRow(job);
    if (old) old.replaceWith(row); else list.append(row);
    renderCounts();
  }

  function renderAllJobs() {
    const list = $('#job-list');
    list.innerHTML = '';
    for (const job of state.jobs.values()) list.append(jobRow(job));
    renderCounts();
  }

  let tickerTimer = null;
  function renderCounts() {
    const jobs = [...state.jobs.values()];
    const active = jobs.filter((j) => ['queued', 'downloading', 'tagging'].includes(j.status)).length;
    const done = jobs.filter((j) => j.status === 'done').length;
    const failed = jobs.filter((j) => j.status === 'error').length;
    $('#jobs-empty').hidden = jobs.length > 0;
    $('#job-counts').textContent = jobs.length
      ? [`${jobs.length} total`, active && `${active} pendientes`, done && `${done} hechas`, failed && `${failed} con error`].filter(Boolean).join(' / ')
      : '';
    const b = $('#badge-downloads');
    b.hidden = !active;
    b.textContent = active;
    clearTimeout(tickerTimer);
    tickerTimer = setTimeout(renderTicker, 500);
  }

  $('#clear-finished').addEventListener('click', () => POST('/api/downloads/clear'));
  $('#cancel-all').addEventListener('click', () => POST('/api/downloads/cancel-all'));

  // ── Pre-listen ─────────────────────────────────────────────────────────

  async function preview(url, btn) {
    if (btn) btn.classList.add('busy');
    const t = toast('Cargando pre-escucha…', '', 0);
    try {
      const p = await POST('/api/preview', { text: url });
      player.play({ stream: { url: p.url, duration: p.duration || 0 }, title: p.title,
        sub: [p.uploader, p.snippet ? 'solo fragmento de 30 s' : 'pre-escucha'].filter(Boolean).join(' · '),
        cover: p.thumbnail });
    } catch (_) { /* POST already showed the error */ }
    finally { t.remove && t.remove(); if (btn) btn.classList.remove('busy'); }
  }

  $('#preview-btn').addEventListener('click', (e) => {
    const url = (urlInput.value.match(/https?:\/\/\S+/) || [])[0];
    if (!url) { toast('Pega primero el enlace de un tema.', 'error'); return; }
    preview(url, e.currentTarget);
  });

  // ── Search ─────────────────────────────────────────────────────────────

  $('#search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = $('#search-input').value.trim();
    if (!query) return;
    const list = $('#search-results');
    list.innerHTML = '';
    list.append(h('div', { class: 'loading' }, h('span', { class: 'bars' }, h('i'), h('i'), h('i'), h('i')), 'Excavando…'));
    const results = await GET('/api/search?q=' + q(query)).catch(() => []);
    list.innerHTML = '';
    if (!results.length) list.append(h('div', { class: 'empty' }, h('p', {}, 'Nada por aquí.')));
    for (const r of results) {
      list.append(h('div', { class: 'row-item' },
        art(r.thumbnail),
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, r.title),
          h('div', { class: 'sub' }, [r.uploader, r.duration && fmtTime(r.duration)].filter(Boolean).join(' · '))),
        h('div', { class: 'actions' },
          iconBtn('play', 'Pre-escuchar', (ev) => preview(r.url, ev.currentTarget)),
          iconBtn('link', 'Abrir en SoundCloud', () => openUrl(r.url)),
          h('button', { class: 'btn small primary', onclick: async (ev) => {
            if (await submitUrls(r.url)) { ev.target.textContent = 'En cola'; ev.target.disabled = true; }
          } }, 'Descargar'))));
    }
  });

  // ── Subscriptions ──────────────────────────────────────────────────────

  function ago(ts) {
    if (!ts) return 'nunca';
    const s = Date.now() / 1000 - ts;
    if (s < 60) return 'ahora';
    if (s < 3600) return `hace ${Math.round(s / 60)} min`;
    if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
    return `hace ${Math.round(s / 86400)} d`;
  }
  function untilStr(ts) {
    if (!ts) return '';
    const s = ts - Date.now() / 1000;
    if (s <= 60) return 'en breve';
    if (s < 3600) return `en ${Math.round(s / 60)} min`;
    return `en ${Math.round(s / 3600)} h`;
  }

  function subRow(s) {
    const r = s.last_result;
    const result = !r ? 'sin revisar' : r.error ? `✗ ${r.error}` : `${r.new} nuevas · ${r.known} ya tenías`;
    const interval = h('select', { class: 'select', title: 'Frecuencia', onchange: (e) => PATCH(`/api/subscriptions/${s.id}`, { interval_hours: Number(e.target.value) }) },
      ...[1, 6, 12, 24, 168].map((v) => h('option', { value: v, selected: Number(s.interval_hours) === v }, v === 168 ? 'semanal' : v === 24 ? 'diaria' : `${v} h`)));
    const toggle = h('input', { type: 'checkbox', class: 'switch', title: 'Activa', checked: s.enabled, onchange: (e) => PATCH(`/api/subscriptions/${s.id}`, { enabled: e.target.checked }) });
    return h('div', { class: 'row-item', 'data-sub': s.id },
      h('div', { class: 'art empty' }),
      h('div', { class: 'meta' },
        h('div', { class: 'title' }, s.title),
        h('div', { class: 'sub' + (r && r.error ? ' err' : '') }, result),
        h('div', { class: 'sub mono dim' }, s.checking ? 'revisando…' : `revisada ${ago(s.last_check)}${s.enabled ? ' · próxima ' + untilStr(s.next_check) : ' · pausada'} · ${s.total_new} en total`)),
      h('div', { class: 'actions' },
        s.checking ? h('span', { class: 'spin' }) : iconBtn('sync', 'Revisar ahora', () => POST(`/api/subscriptions/${s.id}/check`)),
        interval, toggle,
        iconBtn('link', 'Abrir enlace', () => openUrl(s.url)),
        iconBtn('trash', 'Dejar de seguir', () => { if (confirm(`¿Dejar de seguir ${s.title}? Lo ya descargado se queda.`)) DEL(`/api/subscriptions/${s.id}`); })));
  }
  function renderSubs() {
    const list = $('#sub-list');
    list.innerHTML = '';
    for (const s of state.subs.values()) list.append(subRow(s));
    $('#subs-empty').hidden = state.subs.size > 0;
    const b = $('#badge-subs');
    b.hidden = !state.subs.size;
    b.textContent = state.subs.size;
  }
  $('#sub-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = $('#sub-url').value.trim();
    const s = await POST('/api/subscriptions', { url, interval_hours: Number($('#sub-interval').value) });
    state.subs.set(s.id, s);
    renderSubs();
    $('#sub-url').value = '';
    toast('Suscrito. Primera sincronización en marcha.', 'ok');
  });
  setInterval(() => { if ($('.view[data-view=subs]').classList.contains('active')) renderSubs(); }, 30000);

  // ── Library ────────────────────────────────────────────────────────────

  let libLoading = false;
  async function loadLibrary() {
    if (libLoading) return;
    libLoading = true;
    $('#lib-count').textContent = 'leyendo…';
    try {
      const r = await GET('/api/library');
      state.library = r.items;
      $('#lib-root').textContent = r.root;
      renderLibrary();
    } finally { libLoading = false; }
  }
  function renderLibrary() {
    const f = $('#lib-filter').value.trim().toLowerCase();
    const sort = $('#lib-sort').value;
    let items = state.library;
    if (f) {
      items = items.filter((it) => {
        const cam = camelotFromKey(it.key) || '';
        return [it.title, it.artist, it.album, it.name, cam, it.key, it.bpm && Math.round(it.bpm)].some((v) => v != null && String(v).toLowerCase().includes(f));
      });
    }
    const camSort = (k) => { const c = camelotFromKey(k); return c ? parseInt(c, 10) * 2 + (c.endsWith('B') ? 1 : 0) : 99; };
    const cmp = {
      mtime: (a, b) => b.mtime - a.mtime,
      title: (a, b) => a.title.localeCompare(b.title),
      artist: (a, b) => (a.artist || '').localeCompare(b.artist || ''),
      bpm: (a, b) => (a.bpm || 999) - (b.bpm || 999),
      key: (a, b) => camSort(a.key) - camSort(b.key),
    }[sort];
    items = [...items].sort(cmp);
    const body = $('#lib-body');
    body.innerHTML = '';
    const frag = document.createDocumentFragment();
    for (const it of items.slice(0, 1500)) {
      const fmt = [it.ext.toUpperCase(), it.bits && `${it.bits}b`, it.sample_rate && `${num(it.sample_rate / 1000, 1).replace(/\.0$/, '')}k`, !it.bits && it.bitrate && `${it.bitrate}k`].filter(Boolean).join(' ');
      const coverUrl = '/api/cover?path=' + q(it.path);
      const cover = h('div', { class: 'art', style: `background-image:url("${coverUrl}")`, title: 'Escuchar',
        onclick: () => player.play({ path: it.path, title: it.title, sub: it.artist, cover: coverUrl }) });
      const row = h('tr', { 'data-path': it.path, class: player.current === it.path ? 'playing' : null },
        h('td', {}, cover),
        h('td', { class: 'tt' }, h('div', { class: 'title' }, it.title), h('div', { class: 'sub' }, [it.artist, it.album].filter(Boolean).join(' · '))),
        h('td', { class: 'num' }, it.bpm ? Math.round(it.bpm * 10) / 10 : '—'),
        h('td', {}, camChip(null, it.key)),
        h('td', { class: 'fmt' }, fmt),
        h('td', { class: 'num' }, it.duration ? fmtTime(it.duration) : '—'),
        h('td', { class: 'act' },
          iconBtn('wave', 'Espectro', () => { show('analyze'); analyzeFile(it.path); }),
          iconBtn('ab', 'Mandar al comparador', () => { const slot = cmp_.a ? 'b' : 'a'; setSlot(slot, it.path); toast(`En el comparador como ${slot.toUpperCase()}.`, 'ok'); }),
          iconBtn(...fileIcon(), () => reveal(it.path)),
          iconBtn('trash', 'Borrar', async () => {
            if (!confirm(`¿Borrar ${it.name}? No se puede deshacer.`)) return;
            await DEL('/api/library?path=' + q(it.path));
            state.library = state.library.filter((x) => x.path !== it.path);
            renderLibrary();
          })));
      frag.append(row);
    }
    body.append(frag);
    $('#lib-empty').hidden = state.library.length > 0;
    $('#lib-count').textContent = `${items.length}${items.length !== state.library.length ? ' / ' + state.library.length : ''} temas`;
  }
  $('#lib-filter').addEventListener('input', renderLibrary);
  $('#lib-sort').addEventListener('change', renderLibrary);
  $('#lib-refresh').addEventListener('click', loadLibrary);

  // ── Player ─────────────────────────────────────────────────────────────

  const player = {
    audio: $('#pl-audio'),
    current: null,
    stream: null,
    play({ path, stream, title, sub, cover }) {
      anAudio.pause();
      ab.stop && ab.playing && ab.stop();
      this.stream = stream ? { ...stream, offset: 0 } : null;
      this.current = stream ? stream.url : path;
      $('#pl-title').textContent = title || baseName(path);
      this._sub = sub || '';
      $('#pl-sub').textContent = this._sub;
      this._load(path);
      const a = $('#pl-art');
      a.className = 'art small' + (cover ? '' : ' empty');
      a.style.backgroundImage = cover ? `url("${cover}")` : '';
      $('#player').hidden = false;
      document.body.classList.add('has-player');
      $$('#lib-body tr').forEach((tr) => tr.classList.toggle('playing', tr.dataset.path === path));
    },
    _streamAt(t) {
      this.stream.offset = t;
      this.audio.src = `${this.stream.url}?t=${t.toFixed(1)}`;
      this.audio.play().catch(() => {});
    },
    async _load(path) {
      if (this.stream) { this._streamAt(0); return; }
      // AIFF, Opus, FLAC… are transcoded on the server so every browser plays them.
      const direct = /\.(mp3|m4a|aac|wav)$/i.test(path);
      let url = '/api/stream?path=' + q(path);
      if (!direct) {
        $('#pl-sub').textContent = 'preparando…';
        try { url = (await GET('/api/playable?path=' + q(path))).url; } catch (_) { return; }
        if (this.current !== path) return;
        $('#pl-sub').textContent = this._sub;
      }
      this.audio.src = url;
      this.audio.play().catch(() => {});
    },
    close() {
      this.audio.pause();
      this.audio.removeAttribute('src');
      this.current = null;
      $('#player').hidden = true;
      document.body.classList.remove('has-player');
      $$('#lib-body tr.playing').forEach((tr) => tr.classList.remove('playing'));
    },
  };
  const plIcon = (icon) => { $('#pl-toggle').innerHTML = `<svg viewBox="0 0 24 24">${ICONS[icon]}</svg>`; };
  $('#pl-toggle').addEventListener('click', () => (player.audio.paused ? player.audio.play() : player.audio.pause()));
  $('#pl-close').addEventListener('click', () => player.close());
  player.audio.addEventListener('play', () => plIcon('pause'));
  player.audio.addEventListener('pause', () => plIcon('play'));
  // Pre-listening streams come from ffmpeg on the fly: no length, and seeking
  // asks the server to start again at that second.
  const plPos = () => {
    const a = player.audio, st = player.stream;
    return st ? { cur: st.offset + a.currentTime, dur: st.duration }
      : { cur: a.currentTime, dur: Number.isFinite(a.duration) ? a.duration : 0 };
  };
  player.audio.addEventListener('timeupdate', () => {
    const { cur, dur } = plPos();
    if (dur) $('#pl-seek').value = (cur / dur) * 1000;
    $('#pl-time').textContent = fmtTime(cur) + (dur ? ' / ' + fmtTime(dur) : '');
  });
  $('#pl-seek').addEventListener('change', (e) => {
    const { dur } = plPos();
    if (!dur) return;
    const t = (e.target.value / 1000) * dur;
    if (player.stream) player._streamAt(t); else player.audio.currentTime = t;
  });

  // ── Spectrogram view ───────────────────────────────────────────────────

  const cmapSelects = [$('#an-cmap'), $('#cmp-cmap')];
  for (const sel of cmapSelects) {
    for (const name of CMAP_NAMES) sel.append(h('option', { value: name }, name));
  }

  function bindSegmented(el, onChange) {
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b || b.disabled) return;
      $$('button', el).forEach((x) => x.classList.toggle('on', x === b));
      onChange(b.dataset.value ?? b.dataset.key);
    });
  }

  const anSpec = new SpectrogramView($('#an-spec'));
  const anAudio = $('#an-audio');
  bindSegmented($('#an-scale'), (v) => anSpec.set({ scale: v }));
  $('#an-cmap').addEventListener('change', (e) => { anSpec.set({ cmap: e.target.value }); saveSetting('colormap', e.target.value); });
  $('#an-floor').addEventListener('input', (e) => anSpec.set({ floor: +e.target.value }));
  $('#an-open').addEventListener('click', async () => {
    const files = await pickAudio(false);
    if (files.length) analyzeFile(files[0]);
  });
  anSpec.onSeek = (t) => { anAudio.currentTime = t; if (anAudio.paused) anAudio.play(); };
  $('#an-play').addEventListener('click', () => (anAudio.paused ? anAudio.play() : anAudio.pause()));
  anAudio.addEventListener('play', () => { player.audio.pause(); $('#an-play').textContent = '❚❚ Pausa'; });
  anAudio.addEventListener('pause', () => { $('#an-play').textContent = '▶ Play'; });
  anAudio.addEventListener('timeupdate', () => {
    anSpec.setPlayhead(anAudio.currentTime);
    $('#an-time').textContent = fmtTime(anAudio.currentTime);
  });

  function metric(k, v, hl = false) {
    return h('div', { class: 'metric' + (hl ? ' hl' : '') },
      h('div', { class: 'k' }, k),
      h('div', { class: 'v' }, Array.isArray(v) ? [v[0], h('small', {}, v[1])] : v));
  }

  function infoMetrics(info, loud, mus) {
    const items = [];
    if (mus) {
      items.push(metric('BPM', mus.bpm ? String(mus.bpm) : '—', !!mus.bpm));
      items.push(metric('Tonalidad', mus.camelot ? [mus.camelot, mus.key_long || mus.key] : '—', !!mus.camelot));
    }
    items.push(
      metric('Formato', (info.codec || info.ext || '').toString().toUpperCase()),
      metric('Frecuencia', info.sample_rate ? [num(info.sample_rate / 1000, 1), 'kHz'] : '—'),
      metric('Resolución', info.bits ? [info.bits, 'bit'] : '—'),
      metric('Bitrate', info.bitrate ? [info.bitrate, 'kbps'] : '—'),
      metric('Duración', info.duration ? fmtTime(info.duration) : '—'),
      metric('Loudness', loud.integrated_lufs != null ? [num(loud.integrated_lufs), 'LUFS'] : '—'),
      metric('True peak', loud.true_peak_dbtp != null ? [num(loud.true_peak_dbtp), 'dBTP'] : '—'),
      metric('Rango', loud.lra != null ? [num(loud.lra), 'LU'] : '—'),
      metric('PLR', loud.plr != null ? [num(loud.plr), 'dB'] : '—'),
    );
    return items;
  }

  function curveSvg(curve, cutoff, fMax) {
    const W = 1000, H = 100, lo = -110;
    const pts = curve.freqs.map((f, i) => {
      const x = (f / fMax) * W;
      const y = H * Math.min(1, Math.max(0, curve.db[i] / lo));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const cx = (cutoff / fMax) * W;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <polyline points="${pts} ${W},${H} 0,${H}" fill="var(--acid-dim)" stroke="none"/>
      <polyline points="${pts}" fill="none" stroke="var(--acid)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      ${cutoff && cutoff < fMax - 500 ? `<line x1="${cx}" x2="${cx}" y1="0" y2="${H}" stroke="var(--red)" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>` : ''}
    </svg>`;
  }

  async function analyzeFile(path) {
    $('#an-result').hidden = true;
    $('#an-loading').hidden = false;
    anAudio.pause();
    let r;
    try { r = await POST('/api/analyze', { path }); } finally { $('#an-loading').hidden = true; }
    const c = r.cutoff;
    $('#an-sub').textContent = r.info.name;
    const v = $('#an-verdict');
    v.className = 'verdict ' + c.level;
    v.innerHTML = '';
    v.append(c.verdict, h('small', {}, c.sharp
      ? `corte en ${fmtHz(c.cutoff_hz)}Hz${c.estimate ? ' · fuente ' + c.estimate : ''}${c.drop_db ? ` · caída de ${Math.round(c.drop_db)} dB` : ''}`
      : `contenido hasta ${fmtHz(c.cutoff_hz)}Hz (límite del archivo: ${fmtHz(r.info.sample_rate / 2)}Hz)`,
    r.truncated ? ` · analizados los primeros ${Math.round(r.analysed_seconds / 60)} min` : ''));
    const m = $('#an-metrics');
    m.innerHTML = '';
    m.append(...infoMetrics(r.info, r.loudness, r.musical));
    $('#an-result').hidden = false;
    anSpec.set({ cmap: $('#an-cmap').value });
    anSpec.setData(r.spectrogram);
    anSpec.setMarker(c.sharp ? c.cutoff_hz : null);
    anSpec.setPlayhead(0);
    $('#an-curve').innerHTML = curveSvg(c.curve, c.sharp ? c.cutoff_hz : 0, r.spectrogram.f_max);
    anAudio.src = r.audio_url;
  }

  // ── Compare ────────────────────────────────────────────────────────────

  const cmp_ = { a: null, b: null, results: {}, nullReport: null };
  const specA = new SpectrogramView($('#cmp-spec-a'), { scale: 'linear' });
  const specB = new SpectrogramView($('#cmp-spec-b'), { scale: 'linear' });
  const specN = new SpectrogramView($('#null-spec'), { scale: 'linear' });
  const cmpViews = [specA, specB, specN];
  bindSegmented($('#cmp-scale'), (v) => cmpViews.forEach((s) => s.set({ scale: v })));
  $('#cmp-cmap').addEventListener('change', (e) => { cmpViews.forEach((s) => s.set({ cmap: e.target.value })); saveSetting('colormap', e.target.value); });
  $('#cmp-floor').addEventListener('input', (e) => cmpViews.forEach((s) => s.set({ floor: +e.target.value })));

  function setSlot(key, path) {
    cmp_[key] = path;
    const slot = $(`.slot[data-slot="${key}"]`);
    slot.classList.add('filled');
    $('.slot-name', slot).textContent = baseName(path);
    if (cmp_.a && cmp_.b) { show('compare'); runCompare(); }
  }
  $$('.slot').forEach((slot) => slot.addEventListener('click', async () => {
    const files = await pickAudio(false);
    if (files.length) setSlot(slot.dataset.slot, files[0]);
  }));

  async function runCompare() {
    ab.stop();
    $('#cmp-result').hidden = true;
    $('#null-result').hidden = true;
    $('#cmp-loading').hidden = false;
    $('#cmp-loading-text').textContent = 'Analizando las dos versiones…';
    try {
      const [ra, rb] = await Promise.all([POST('/api/analyze', { path: cmp_.a }), POST('/api/analyze', { path: cmp_.b })]);
      cmp_.results = { a: ra, b: rb };
      $('#cmp-loading-text').textContent = 'Preparando la escucha A/B…';
      await ab.load({ a: ra.audio_url, b: rb.audio_url });
    } finally {
      $('#cmp-loading').hidden = true;
    }
    const { a: ra, b: rb } = cmp_.results;
    $('#cmp-name-a').textContent = ra.info.name;
    $('#cmp-name-b').textContent = rb.info.name;
    renderCompareTable(ra, rb);
    $('#cmp-result').hidden = false;
    cmpViews.forEach((v) => v.set({ cmap: $('#cmp-cmap').value }));
    specA.setData(ra.spectrogram); specA.setMarker(ra.cutoff.sharp ? ra.cutoff.cutoff_hz : null);
    specB.setData(rb.spectrogram); specB.setMarker(rb.cutoff.sharp ? rb.cutoff.cutoff_hz : null);
    $('#ab-switch [data-key=diff]').disabled = true;
    ab.select('a');
    ab.setGainMatch();
  }

  function renderCompareTable(ra, rb) {
    const fmtRate = (i) => `${num(i.sample_rate / 1000)} kHz${i.bits ? ' · ' + i.bits + ' bit' : ''}`;
    const rows = [
      ['Archivo', ra.info.name, rb.info.name],
      ['Formato', (ra.info.codec || ra.info.ext).toUpperCase(), (rb.info.codec || rb.info.ext).toUpperCase()],
      ['Frecuencia / bits', fmtRate(ra.info), fmtRate(rb.info)],
      ['Bitrate', ra.info.bitrate ? ra.info.bitrate + ' kbps' : '—', rb.info.bitrate ? rb.info.bitrate + ' kbps' : '—'],
      ['Corte', ra.cutoff.sharp ? fmtHz(ra.cutoff.cutoff_hz) + 'Hz' : 'sin corte', rb.cutoff.sharp ? fmtHz(rb.cutoff.cutoff_hz) + 'Hz' : 'sin corte', 'cut'],
      ['Veredicto', ra.cutoff.verdict, rb.cutoff.verdict],
      ['BPM / key', [ra.musical.bpm, ra.musical.camelot].filter(Boolean).join(' · ') || '—', [rb.musical.bpm, rb.musical.camelot].filter(Boolean).join(' · ') || '—'],
      ['Loudness', num(ra.loudness.integrated_lufs) + ' LUFS', num(rb.loudness.integrated_lufs) + ' LUFS'],
      ['True peak', num(ra.loudness.true_peak_dbtp) + ' dBTP', num(rb.loudness.true_peak_dbtp) + ' dBTP'],
      ['Rango (LRA)', num(ra.loudness.lra) + ' LU', num(rb.loudness.lra) + ' LU', 'high'],
      ['PLR', num(ra.loudness.plr) + ' dB', num(rb.loudness.plr) + ' dB', 'high'],
    ];
    const t = $('#cmp-table');
    t.innerHTML = '';
    t.append(h('tr', {}, h('th', {}, ''), h('th', {}, 'A'), h('th', {}, 'B')));
    const cutA = ra.cutoff.sharp ? ra.cutoff.cutoff_hz : 1e9, cutB = rb.cutoff.sharp ? rb.cutoff.cutoff_hz : 1e9;
    for (const [k, a, b, rule] of rows) {
      let betterA = false, betterB = false;
      if (rule === 'cut' && cutA !== cutB) { betterA = cutA > cutB; betterB = !betterA; }
      if (rule === 'high') {
        const va = parseFloat(a), vb = parseFloat(b);
        if (!Number.isNaN(va) && !Number.isNaN(vb) && va !== vb) { betterA = va > vb; betterB = !betterA; }
      }
      t.append(h('tr', {}, h('td', {}, k), h('td', { class: betterA ? 'better' : null }, a), h('td', { class: betterB ? 'better' : null }, b)));
    }
  }

  $('#null-run').addEventListener('click', async () => {
    if (!cmp_.a || !cmp_.b) return;
    const btn = $('#null-run');
    btn.disabled = true;
    btn.textContent = 'Calculando…';
    let r;
    try { r = await POST('/api/null-test', { a: cmp_.a, b: cmp_.b }); } finally { btn.disabled = false; btn.textContent = 'Ejecutar'; }
    cmp_.nullReport = r;
    const v = $('#null-verdict');
    v.className = 'verdict ' + r.level;
    v.innerHTML = '';
    v.append(r.verdict, h('small', {}, `profundidad del null: ${num(r.null_depth_db)} dB (más negativo = más parecidos)`));
    const m = $('#null-metrics');
    m.innerHTML = '';
    m.append(
      metric('Profundidad', [num(r.null_depth_db), 'dB'], true),
      metric('Desfase', [num(r.offset_ms, 2), 'ms']),
      metric('Ganancia', [num(r.gain_db, 2), 'dB']),
      metric('Correlación', num(r.correlation, 4)),
      metric('Polaridad', r.inverted ? 'Invertida' : 'Normal'),
    );
    $('#null-result').hidden = false;
    specN.setData(r.spectrogram);
    await ab.load({ diff: r.audio_url }, true);
    ab.offsets.b = r.offset_ms / 1000;
    if (ab.playing) ab.seek(ab.now());
    $('#ab-switch [data-key=diff]').disabled = false;
  });

  // A/B player on Web Audio: every version plays at once, only the selected
  // one is audible, so switching is instant and sample-aligned.
  const ab = {
    ctx: null, buffers: {}, sources: {}, gains: {}, offsets: {}, levels: {},
    active: 'a', playing: false, startedAt: 0, pos: 0, raf: null,

    async load(urls, keep = false) {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (!keep) { this.buffers = {}; this.offsets = {}; this.pos = 0; }
      await Promise.all(Object.entries(urls).map(async ([k, url]) => {
        const data = await (await fetch(url, { credentials: 'same-origin' })).arrayBuffer();
        this.buffers[k] = await this.ctx.decodeAudioData(data);
      }));
    },
    duration() { return Math.max(0, ...Object.values(this.buffers).map((b) => b.duration)); },
    now() { return this.playing ? this.pos + (this.ctx.currentTime - this.startedAt) : this.pos; },
    setGainMatch() {
      const { a, b } = cmp_.results;
      const la = a && a.loudness.integrated_lufs, lb = b && b.loudness.integrated_lufs;
      this.levels = { a: 1, b: 1, diff: 1 };
      if ($('#ab-match').checked && la != null && lb != null) {
        const target = Math.min(la, lb);
        this.levels.a = Math.pow(10, (target - la) / 20);
        this.levels.b = Math.pow(10, (target - lb) / 20);
      }
      this._applyGains(0.01);
    },
    _applyGains(ramp = 0.012) {
      if (!this.ctx) return;
      const t = this.ctx.currentTime;
      for (const [k, g] of Object.entries(this.gains)) {
        g.gain.cancelScheduledValues(t);
        g.gain.setTargetAtTime(k === this.active ? (this.levels[k] ?? 1) : 0, t, ramp);
      }
    },
    select(key) {
      if (!this.buffers[key]) return;
      this.active = key;
      $$('#ab-switch button').forEach((b) => b.classList.toggle('on', b.dataset.key === key));
      this._applyGains();
    },
    play() {
      if (!this.ctx || this.playing) return;
      player.audio.pause(); anAudio.pause();
      this.ctx.resume();
      const at = this.ctx.currentTime + 0.05;
      for (const [k, buf] of Object.entries(this.buffers)) {
        const src = this.ctx.createBufferSource();
        src.buffer = buf;
        const g = this.ctx.createGain();
        g.gain.value = k === this.active ? (this.levels[k] ?? 1) : 0;
        src.connect(g).connect(this.ctx.destination);
        const off = this.pos - (this.offsets[k] || 0);
        if (off >= 0) src.start(at, Math.min(off, buf.duration));
        else src.start(at - off, 0);
        this.sources[k] = src;
        this.gains[k] = g;
      }
      this.startedAt = at;
      this.playing = true;
      $('#ab-play').textContent = '❚❚';
      this._tick();
    },
    stop(keepPos = true) {
      if (this.playing) this.pos = this.now();
      for (const s of Object.values(this.sources)) { try { s.stop(); } catch (_) {} }
      this.sources = {}; this.gains = {};
      this.playing = false;
      if (!keepPos) this.pos = 0;
      $('#ab-play').textContent = '▶';
      cancelAnimationFrame(this.raf);
    },
    toggle() { this.playing ? this.stop() : this.play(); },
    seek(t) {
      const was = this.playing;
      this.stop();
      this.pos = Math.max(0, Math.min(t, this.duration()));
      this._updateUi();
      if (was) this.play();
    },
    _updateUi() {
      const t = this.now(), d = this.duration() || 1;
      $('#ab-seek').value = (t / d) * 1000;
      $('#ab-time').textContent = fmtTime(t);
      specA.setPlayhead(t); specB.setPlayhead(t - (this.offsets.b || 0)); specN.setPlayhead(t);
    },
    _tick() {
      this._updateUi();
      if (this.now() >= this.duration()) { this.stop(false); this._updateUi(); return; }
      this.raf = requestAnimationFrame(() => this._tick());
    },
  };

  $('#ab-play').addEventListener('click', () => ab.toggle());
  bindSegmented($('#ab-switch'), (k) => ab.select(k));
  $('#ab-seek').addEventListener('input', (e) => ab.seek((e.target.value / 1000) * ab.duration()));
  $('#ab-match').addEventListener('change', () => ab.setGainMatch());
  [specA, specB, specN].forEach((s) => { s.onSeek = (t) => ab.seek(t); });

  document.addEventListener('keydown', (e) => {
    if (!$('.view[data-view=compare]').classList.contains('active') || $('#cmp-result').hidden) return;
    if (e.target.matches('input, textarea, select')) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); ab.toggle(); }
    else if (k === 'a' || k === 'b') ab.select(k);
    else if (k === 'd') ab.select('diff');
  });

  // ── Converter ──────────────────────────────────────────────────────────

  const cv = { files: [], fmt: 'wav', dest: null, status: {}, batch: null };

  function renderConvert() {
    const list = $('#cv-list');
    list.innerHTML = '';
    cv.files.forEach((f, i) => {
      const st = cv.status[i] || {};
      const sub = st.error ? h('div', { class: 'sub err' }, st.error)
        : st.warning ? h('div', { class: 'sub warn' }, '⚠ ' + st.warning)
          : st.note ? h('div', { class: 'sub' }, st.note)
            : h('div', { class: 'sub mono dim' }, isServer() ? '' : f);
      list.append(h('div', { class: 'row-item' + (st.status === 'done' ? ' status-done' : st.status === 'error' ? ' status-error' : '') },
        h('div', { class: 'art empty' }),
        h('div', { class: 'meta' }, h('div', { class: 'title' }, baseName(f)), sub),
        h('div', { class: 'actions' },
          st.status === 'running' ? h('span', { class: 'spin' }) : null,
          st.status === 'done' ? h('span', { class: 'status' }, 'hecho') : null,
          st.status === 'done' ? iconBtn(...fileIcon(), () => reveal(st.dest)) : null,
          !st.status ? iconBtn('x', 'Quitar', () => { cv.files.splice(i, 1); renderConvert(); }) : null)));
    });
    $('#cv-empty').hidden = cv.files.length > 0;
    $('#cv-run').disabled = !cv.files.length;
  }
  function addConvertFiles(paths) {
    for (const f of paths) if (!cv.files.includes(f)) cv.files.push(f);
    cv.status = {};
    show('convert');
    renderConvert();
  }

  $('#cv-add').addEventListener('click', async () => addConvertFiles(await pickAudio(true)));
  $('#cv-same').addEventListener('change', (e) => { $('#cv-dest').disabled = e.target.checked; });
  $('#cv-norm').addEventListener('change', (e) => { $('#cv-lufs').disabled = !e.target.checked; });
  $('#cv-dest').addEventListener('click', async () => {
    const n = await native();
    if (!n) return;
    const d = await n.choose_folder('');
    if (d) { cv.dest = d; $('#cv-dest').textContent = baseName(d) || d; }
  });
  $('#cv-run').addEventListener('click', async () => {
    cv.status = {};
    $('#cv-run').disabled = true;
    const r = await POST('/api/convert', {
      files: cv.files, format: cv.fmt,
      out_dir: !isServer() && !$('#cv-same').checked ? cv.dest : null,
      normalize_lufs: $('#cv-norm').checked ? Number($('#cv-lufs').value) : null,
    }).catch((e) => { $('#cv-run').disabled = false; throw e; });
    cv.batch = r.batch;
    renderConvert();
  });

  // ── History ────────────────────────────────────────────────────────────

  async function loadHistory() {
    const items = await GET('/api/history');
    const list = $('#history-list');
    list.innerHTML = '';
    $('#history-empty').hidden = items.length > 0;
    for (const it of items) {
      const when = new Date(it.time * 1000).toLocaleString();
      list.append(h('div', { class: 'row-item' },
        art(it.thumbnail),
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, it.title),
          h('div', { class: 'sub' }, [it.artist, when].filter(Boolean).join(' · '))),
        h('div', { class: 'actions' },
          bpmChip(it.bpm), camChip(it.camelot, it.key), badge(it.quality),
          iconBtn('play', 'Escuchar', () => player.play({ path: it.path, title: it.title, sub: it.artist, cover: it.thumbnail })),
          iconBtn('wave', 'Espectro', () => { show('analyze'); analyzeFile(it.path); }),
          iconBtn(...fileIcon(), () => reveal(it.path)),
          iconBtn('link', 'Abrir el original', () => openUrl(it.url)))));
    }
  }

  // ── Settings ───────────────────────────────────────────────────────────

  async function saveSetting(key, value) {
    state.settings = await PATCH('/api/settings', { [key]: value });
    renderSettings();
  }

  function renderSettings() {
    const s = state.settings;
    $('#set-dir').textContent = s.download_dir;
    $$('[data-setting]').forEach((el) => {
      const v = s[el.dataset.setting];
      if (el.type === 'checkbox') el.checked = !!v;
      else if (document.activeElement !== el) el.value = v;
    });
    const sample = { artist: 'Artista', title: 'Título', uploader: 'usuario', playlist: 'Mi playlist', index: '01', date: '2026-01-31', id: '123456' };
    $('#template-preview').textContent = '→ ' + (s.filename_template || '').replace(/\{(\w+)\}/g, (_, k) => sample[k] ?? '') + '.wav';
    for (const sel of cmapSelects) sel.value = s.colormap || 'inferno';
  }

  $$('[data-setting]').forEach((el) => {
    el.addEventListener('change', () => {
      const v = el.type === 'checkbox' ? el.checked
        : el.type === 'number' || (el.tagName === 'SELECT' && /^\d+$/.test(el.value)) ? Number(el.value) : el.value;
      saveSetting(el.dataset.setting, v);
    });
  });
  $('#set-template').addEventListener('input', (e) => {
    state.settings.filename_template = e.target.value;
    renderSettings();
  });
  $('#set-dir-btn').addEventListener('click', async () => {
    const n = await native();
    if (!n) return;
    const d = await n.choose_folder(state.settings.download_dir);
    if (d) saveSetting('download_dir', d);
  });

  // Theme: per device, so it lives in localStorage.
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    $('meta[name=theme-color]').setAttribute('content', t === 'light' ? '#e8e6df' : '#0a0a0a');
    $$('#theme-switch button').forEach((b) => b.classList.toggle('on', b.dataset.value === t));
    try { localStorage.setItem('ftn.theme', t); } catch (_) {}
  }
  bindSegmented($('#theme-switch'), applyTheme);
  let savedTheme = null;
  try { savedTheme = localStorage.getItem('ftn.theme'); } catch (_) {}
  applyTheme(savedTheme || 'dark');

  function renderAccount() {
    const sc = state.soundcloud;
    $('#account-label').textContent = sc.logged_in ? `SC: ${sc.username || 'conectado'}` : 'SC: sin sesión';
    $('#account-pill').classList.toggle('on', sc.logged_in);
    $('#sc-status').textContent = sc.logged_in ? (sc.username ? `Conectado como ${sc.username}` : 'Conectado (token guardado)') : 'Sin sesión';
    $('#sc-login').hidden = sc.logged_in;
    $('#sc-logout').hidden = !sc.logged_in;
    $('#login-notice').hidden = sc.logged_in;
    renderTicker();
  }

  $$('[data-action=login]').forEach((b) => b.addEventListener('click', async () => {
    const n = await native();
    if (!n) { show('settings'); $('#sc-token').click(); return; }
    toast('Inicia sesión en la ventana de SoundCloud; se cerrará sola.');
    state.soundcloud = await n.soundcloud_login();
    renderAccount();
    if (state.soundcloud.logged_in) toast('Sesión iniciada.', 'ok');
  }));
  $('#sc-logout').addEventListener('click', async () => { state.soundcloud = await DEL('/api/soundcloud/token'); renderAccount(); });
  $('#sc-token').addEventListener('click', async () => {
    const token = prompt('Pega el token OAuth de SoundCloud (cabecera "Authorization: OAuth …" de las peticiones a api-v2.soundcloud.com):');
    if (!token) return;
    state.soundcloud = await POST('/api/soundcloud/token', { token });
    renderAccount();
    toast(state.soundcloud.username ? `Token válido: ${state.soundcloud.username}.` : 'Token guardado (no se ha podido verificar).', state.soundcloud.username ? 'ok' : '');
  });

  $('#ytdlp-update').addEventListener('click', async () => {
    const b = $('#ytdlp-update');
    b.disabled = true; b.textContent = 'Buscando…';
    try {
      const r = await POST('/api/ytdlp/update');
      toast(r.updated ? `yt-dlp ${r.version} descargado. Reinicia para usarlo.` : `Ya tienes la última (${r.version}).`, 'ok');
    } finally { b.disabled = false; b.textContent = 'Actualizar'; }
  });
  $('#app-logout').addEventListener('click', async () => { await POST('/api/logout'); location.reload(); });

  // ── Events from the server ─────────────────────────────────────────────

  function onEvent(kind, p) {
    if (kind === 'job') {
      state.jobs.set(p.id, p);
      renderJob(p);
      if (p.status === 'done' && state.library.length) loadLibrarySoon();
    } else if (kind === 'jobs') {
      state.jobs = new Map(p.jobs.map((j) => [j.id, j]));
      renderAllJobs();
    } else if (kind === 'resolving') {
      if (p.origin) return; // subscription checks report in their own view
      if (p.active) state.resolving.set(p.url, {});
      else if (p.error) {
        state.resolving.set(p.url, { error: p.error });
        setTimeout(() => { state.resolving.delete(p.url); renderResolving(); }, 8000);
      } else {
        state.resolving.delete(p.url);
        if (p.count > 1 || p.skipped) toast(`${p.title || 'Colección'}: ${p.count} en cola${p.skipped ? `, ${p.skipped} ya los tenías` : ''}.`, 'ok');
        else if (p.count === 0 && !p.skipped) toast('Ese enlace no contiene ningún tema.', 'error');
      }
      renderResolving();
    } else if (kind === 'subscription') {
      state.subs.set(p.id, p);
      renderSubs();
      renderTicker();
    } else if (kind === 'subscription_removed') {
      state.subs.delete(p.id);
      renderSubs();
    } else if (kind === 'soundcloud') {
      state.soundcloud = p;
      renderAccount();
    } else if (kind === 'settings') {
      state.settings = p;
      renderSettings();
    } else if (kind === 'convert') {
      if (p.batch !== cv.batch) return;
      if (p.status === 'finished') { $('#cv-run').disabled = false; toast('Conversión terminada.', 'ok'); return; }
      cv.status[p.index] = p;
      renderConvert();
    } else if (kind === 'library_changed') {
      loadLibrarySoon();
    }
  }
  let libTimer = null;
  function loadLibrarySoon() {
    clearTimeout(libTimer);
    libTimer = setTimeout(() => { if ($('.view[data-view=library]').classList.contains('active')) loadLibrary(); }, 1500);
  }

  let events = null;
  function connectEvents() {
    if (events) events.close();
    events = new EventSource('/api/events', { withCredentials: true });
    let wasDown = false;
    events.onmessage = (e) => {
      const { kind, payload } = JSON.parse(e.data);
      onEvent(kind, payload);
    };
    events.onerror = () => { wasDown = true; };
    events.onopen = () => { if (wasDown) { wasDown = false; refreshState(); } };
  }

  // ── Login gate ─────────────────────────────────────────────────────────

  function showGate() {
    $('#gate').hidden = false;
    setTimeout(() => $('#gate-pass').focus(), 50);
  }
  $('#gate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('#gate-err').textContent = '';
    try {
      await http('POST', '/api/login', { password: $('#gate-pass').value }, { quiet: true });
      $('#gate').hidden = true;
      $('#gate-pass').value = '';
      boot();
    } catch (err) {
      $('#gate-err').textContent = err.message || 'No se ha podido entrar.';
    }
  });

  // ── Boot ───────────────────────────────────────────────────────────────

  let formatsBuilt = false;
  async function refreshState() {
    const s = await GET('/api/state');
    state.mode = s.mode;
    state.version = s.version;
    state.ytdlp = s.ytdlp_version;
    document.body.classList.toggle('mode-server', s.mode === 'server');
    document.body.classList.toggle('mode-desktop', s.mode !== 'server');
    state.settings = s.settings;
    state.soundcloud = s.soundcloud;
    state.jobs = new Map(s.jobs.map((j) => [j.id, j]));
    state.subs = new Map(s.subscriptions.map((x) => [x.id, x]));
    $('#ytdlp-version').textContent = 'versión ' + s.ytdlp_version;
    $('#ffmpeg-path').textContent = s.ffmpeg === true ? 'disponible' : s.ffmpeg || 'no encontrado';
    $('#app-version').textContent = 'versión ' + s.version;
    $('#brand-ver').textContent = 'v' + s.version;
    $('#sc-where').textContent = s.mode === 'server'
      ? 'El token se guarda en el servidor, no en este navegador.'
      : 'El token se guarda en el llavero del sistema.';
    if (!formatsBuilt) {
      const seg = $('#cv-format');
      for (const [k, label] of Object.entries(s.formats)) seg.append(h('button', { 'data-value': k, class: k === cv.fmt ? 'on' : null }, label));
      bindSegmented(seg, (v) => { cv.fmt = v; });
      formatsBuilt = true;
    }
    renderSettings();
    renderAccount();
    renderAllJobs();
    renderSubs();
    renderConvert();
    renderTicker();
  }

  async function boot() {
    const session = await GET('/api/session');
    state.mode = session.mode;
    $('#logout-row').hidden = !session.password_required;
    if (!session.authenticated) { showGate(); return; }
    await refreshState();
    connectEvents();
    let view = null;
    try { view = localStorage.getItem('ftn.view'); } catch (_) {}
    if (view && $(`.view[data-view="${view}"]`)) show(view);
  }

  // Entry points for scripted UI tests (no native dialogs involved).
  window.FTN = {
    debug: {
      show, analyzeFile,
      compare(a, b) { cmp_.a = a; cmp_.b = b; return runCompare(); },
      nullTest: () => $('#null-run').click(),
    },
  };

  boot();
})();
