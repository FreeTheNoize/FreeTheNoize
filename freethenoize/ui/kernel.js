/* FreeTheNoize UI kernel.
 *
 * The page is a shell: sidebar, settings, player, update dialog, login gate,
 * toasts. Every other screen comes from a plugin script
 * (/plugins/<id>/<id>.js) that registers itself through window.FTN:
 *
 *   FTN.registerView({ id, group, order, title, kicker, heading, intro, html, init, onShow, onFiles })
 *   FTN.registerSettings({ id, order, title, html, init })
 *   FTN.on('<plugin>.<event>' | 'state' | 'settings' | 'soundcloud' | …, fn)
 *   FTN.provide(name, fn) / FTN.use(name)      — actions other plugins may offer
 *   FTN.GET/POST/PATCH/DEL, FTN.h, FTN.toast, FTN.player, FTN.pickAudio…
 *
 * Same page for the desktop window and for browsers: everything goes through
 * the HTTP API (/api/*) and live updates arrive over Server-Sent Events. In
 * the desktop window, window.pywebview.api adds native dialogs, "show in
 * folder" and the SoundCloud sign-in window.
 */
(function () {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const { fmtHz, fmtTime } = window.Spectro;

  const state = {
    mode: 'desktop',
    settings: {},
    soundcloud: { logged_in: false },
    ytdlp: '',
    version: '',
    plugins: {},
    plugin_list: [],
  };
  const isServer = () => state.mode === 'server';

  // ── Events (server SSE + local) ────────────────────────────────────────

  const handlers = new Map();
  function on(kind, fn) {
    if (!handlers.has(kind)) handlers.set(kind, []);
    handlers.get(kind).push(fn);
  }
  function fire(kind, payload) {
    for (const fn of handlers.get(kind) || []) {
      try { fn(payload); } catch (e) { console.error(`FTN handler for ${kind}`, e); }
    }
  }

  // ── Actions other plugins may provide ──────────────────────────────────

  const provided = new Map();
  const provide = (name, fn) => provided.set(name, fn);
  const use = (name) => provided.get(name) || null;

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
  // Binary responses (audio for Web Audio…): same session, error shown as a toast.
  async function getBytes(url) {
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) { toast(res.statusText || 'No se ha podido leer el archivo.', 'error'); throw new HttpError(res.status, res.statusText); }
    return res.arrayBuffer();
  }
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

  async function pickFolder(start = '') {
    const n = await native();
    return n ? n.choose_folder(start) : null;
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

  // Build DOM. Text children are always escaped; never build HTML strings
  // from data (innerHTML only for static templates and the ICONS below).
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
    ear: '<path d="M7 5v14l12-7z" fill="currentColor" stroke="none"/>',
  };
  function iconBtn(icon, title, onclick) {
    const b = h('button', { class: 'btn icon ghost', title, 'aria-label': title, onclick });
    b.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[icon] || ''}</svg>`;
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
  const loadingBars = (text) => h('div', { class: 'loading' }, h('span', { class: 'bars' }, h('i'), h('i'), h('i'), h('i')), text);

  function bindSegmented(el, onChange) {
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b || b.disabled) return;
      $$('button', el).forEach((x) => x.classList.toggle('on', x === b));
      onChange(b.dataset.value ?? b.dataset.key);
    });
  }

  // ── Views (registered by plugins) ──────────────────────────────────────

  const GROUPS = ['fuente', 'archivo', 'laboratorio'];
  const views = new Map();
  let current = null;

  function registerView(v) {
    if (!v || !v.id || views.has(v.id) || v.id === 'settings') {
      console.error('FTN.registerView: id missing or repeated', v);
      return;
    }
    views.set(v.id, { group: 'laboratorio', order: 100, ...v });
  }

  function buildViews() {
    const sorted = [...views.values()].sort((a, b) => {
      const ga = GROUPS.indexOf(a.group), gb = GROUPS.indexOf(b.group);
      return (ga < 0 ? 99 : ga) - (gb < 0 ? 99 : gb) || a.order - b.order;
    });
    const nav = $('#nav');
    const content = $('#content');
    const settingsSection = $('.view[data-view=settings]');
    let group = null;
    sorted.forEach((v, i) => {
      const n = String(i + 1).padStart(2, '0');
      if (v.group !== group) {
        group = v.group;
        nav.append(h('div', { class: 'nav-section' }, `// ${group}`));
      }
      nav.append(h('button', { class: 'nav-item', 'data-view': v.id, onclick: () => show(v.id) },
        h('i', {}, n), h('span', {}, v.title), h('b', { class: 'nav-badge', id: `badge-${v.id}`, hidden: true })));
      // actions: buttons on the right of the heading, [{ id, label, primary }]
      const actions = (v.actions || []).map((a) => h('button', { class: 'btn' + (a.primary ? ' primary' : ''), id: a.id }, a.label));
      const section = h('section', { class: `view view-${v.id}`, 'data-view': v.id },
        h('header', { class: 'view-head' + (actions.length ? ' row' : '') },
          h('div', {},
            h('div', { class: 'kicker' }, `${n} / ${v.kicker || v.title.toLowerCase()}`),
            h('h1', {}, v.heading || v.title),
            v.intro != null ? h('p', { class: v.introClass || null, id: v.introId || null }, v.intro) : null),
          ...actions));
      const body = h('div', { class: 'view-body' });
      if (v.html) body.innerHTML = v.html;   // static template from the plugin, no data
      section.append(body);
      content.insertBefore(section, settingsSection);
      v.el = section;
      try { v.init && v.init(section); } catch (e) { console.error(`view ${v.id}: init failed`, e); }
    });
    $('#settings-kicker').textContent = `${String(sorted.length + 1).padStart(2, '0')} / ajustes`;
    $('#nav-settings i').textContent = String(sorted.length + 1).padStart(2, '0');
  }

  function show(id) {
    if (id !== 'settings' && !views.has(id)) id = views.keys().next().value || 'settings';
    $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === id));
    $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === id));
    document.body.classList.remove('nav-open');
    $('#scrim').hidden = true;
    $('#content').scrollTop = 0;
    current = id;
    const v = views.get(id);
    if (v && v.onShow) { try { v.onShow(); } catch (e) { console.error(e); } }
    try { localStorage.setItem('ftn.view', id); } catch (_) {}
  }
  const isShown = (id) => current === id;

  function setBadge(viewId, value, dim = false) {
    const b = $(`#badge-${viewId}`);
    if (!b) return;
    b.hidden = !value;
    b.textContent = value || '';
    b.classList.toggle('dim', dim);
  }

  $$('.sidebar-foot [data-view=settings]').forEach((b) => b.addEventListener('click', () => show('settings')));
  $('#menu-btn').addEventListener('click', () => { document.body.classList.add('nav-open'); $('#scrim').hidden = false; });
  $('#scrim').addEventListener('click', () => { document.body.classList.remove('nav-open'); $('#scrim').hidden = true; });

  // ── Ticker (plugins add items with FTN.addTicker(() => [[label, value], …])) ──

  const tickerSources = [];
  const addTicker = (fn) => tickerSources.push(fn);
  let tickerTimer = null;
  function renderTicker() {
    clearTimeout(tickerTimer);
    tickerTimer = setTimeout(() => {
      const sc = state.soundcloud;
      const items = [['FREE THE NOIZE', `v${state.version}`]];
      for (const fn of tickerSources) { try { items.push(...fn()); } catch (_) {} }
      items.push(
        ['SOUNDCLOUD', sc.logged_in ? (sc.username || 'conectado') : 'sin sesión'],
        ['YT-DLP', state.ytdlp],
        ['MODO', isServer() ? 'servicio web' : 'escritorio'],
        ['APOYA A LOS ARTISTAS', '♥'],
      );
      const track = $('#ticker');
      track.textContent = '';
      for (let i = 0; i < 2; i++) {
        for (const [k, v] of items) track.append(h('span', {}, `${k} `, h('b', {}, v)));
      }
    }, 300);
  }

  // ── Drag & drop: audio files to the current view, links to whoever adds them ──

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
      const target = views.get(current);
      const fallback = use('files.open');
      if (!(target && target.onFiles) && !fallback) { toast('Ninguna pantalla abre archivos de audio.', 'error'); return; }
      const paths = await uploadFiles(files);
      if (target && target.onFiles) target.onFiles(paths);
      else fallback(paths);
      return;
    }
    const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
    const addLinks = use('links.add');
    if (text && addLinks) addLinks(text);
  });

  // ── Player (shared: library, history, downloads, pre-listening) ────────

  // Only one thing sounds at a time: whoever starts playing calls
  // FTN.takeAudio(owner) and everyone else pauses on the 'audio.focus' event.
  const takeAudio = (owner) => fire('audio.focus', { owner });

  const player = {
    audio: $('#pl-audio'),
    current: null,
    stream: null,
    play({ path, stream, title, sub, cover }) {
      takeAudio('player');
      this.stream = stream ? { ...stream, offset: 0 } : null;
      this.current = stream ? stream.url : path;
      $('#pl-title').textContent = title || baseName(path);
      this._sub = sub || '';
      $('#pl-sub').textContent = this._sub;
      this._load(path);
      const a = $('#pl-art');
      a.className = 'art small' + (cover ? '' : ' empty');
      a.style.backgroundImage = cover ? `url("${cover.replace(/"/g, '%22')}")` : '';
      $('#player').hidden = false;
      document.body.classList.add('has-player');
      fire('player', { path: this.current });
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
      fire('player', { path: null });
    },
  };
  const plIcon = (icon) => { $('#pl-toggle').innerHTML = `<svg viewBox="0 0 24 24">${ICONS[icon]}</svg>`; };
  $('#pl-toggle').addEventListener('click', () => (player.audio.paused ? player.audio.play() : player.audio.pause()));
  $('#pl-close').addEventListener('click', () => player.close());
  player.audio.addEventListener('play', () => { plIcon('pause'); takeAudio('player'); });
  player.audio.addEventListener('pause', () => plIcon('play'));
  on('audio.focus', ({ owner }) => { if (owner !== 'player') player.audio.pause(); });
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

  // ── Settings ───────────────────────────────────────────────────────────

  const settingSections = [];
  function registerSettings(s) { settingSections.push({ order: 100, ...s }); }

  function buildSettings() {
    const box = $('#settings-plugins');
    for (const s of settingSections.sort((a, b) => a.order - b.order)) {
      box.append(h('h2', { class: 'group-title' }, `// ${s.title}`));
      const group = h('div', { class: 'group', 'data-plugin': s.id });
      if (s.html) group.innerHTML = s.html;   // static template, no data
      box.append(group);
      try { s.init && s.init(group); } catch (e) { console.error(`settings ${s.id}: init failed`, e); }
    }
    // Every [data-setting] (kernel or plugin) saves itself on change.
    $$('[data-setting]').forEach((el) => {
      el.addEventListener('change', () => {
        const v = el.type === 'checkbox' ? el.checked
          : el.type === 'number' || (el.tagName === 'SELECT' && /^-?\d+(\.\d+)?$/.test(el.value)) ? Number(el.value) : el.value;
        saveSetting(el.dataset.setting, v);
      });
    });
  }

  async function saveSetting(key, value) {
    state.settings = await PATCH('/api/settings', { [key]: value });
    renderSettings();
    fire('settings', state.settings);
  }

  function renderSettings() {
    const s = state.settings;
    $('#set-dir').textContent = s.download_dir;
    $$('[data-setting]').forEach((el) => {
      const v = s[el.dataset.setting];
      if (v === undefined) return;
      if (el.type === 'checkbox') el.checked = !!v;
      else if (document.activeElement !== el) el.value = v;
    });
    renderPluginList();
  }

  function renderPluginList() {
    const box = $('#plugin-list');
    box.textContent = '';
    const off = new Set(state.settings.disabled_plugins || []);
    for (const p of state.plugin_list) {
      const enabled = !off.has(p.id);
      const note = p.status === 'active' ? (enabled ? p.description : 'Se desactivará al reiniciar.')
        : enabled && p.status === 'disabled' ? 'Se activará al reiniciar.' : p.reason;
      const sw = h('input', { type: 'checkbox', class: 'switch', title: enabled ? 'Activado' : 'Desactivado', checked: enabled,
        onchange: (e) => {
          const next = new Set(state.settings.disabled_plugins || []);
          if (e.target.checked) next.delete(p.id); else next.add(p.id);
          saveSetting('disabled_plugins', [...next]);
          toast(isServer() ? 'Reinicia el servicio para aplicarlo.' : 'Reinicia la app para aplicarlo.');
        } });
      box.append(h('div', { class: 'group-row' },
        h('div', { class: 'label' }, `${p.title} `, h('span', { class: 'mono dim' }, `${p.id} ${p.version}`),
          h('small', {}, note || '')),
        h('div', { class: 'controls' }, sw)));
    }
  }

  $('#set-dir-btn').addEventListener('click', async () => {
    const d = await pickFolder(state.settings.download_dir);
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

  // ── SoundCloud session (kernel: downloads, preview and search use it) ──

  function renderAccount() {
    const sc = state.soundcloud;
    $('#account-label').textContent = sc.logged_in ? `SC: ${sc.username || 'conectado'}` : 'SC: sin sesión';
    $('#account-pill').classList.toggle('on', sc.logged_in);
    $('#sc-status').textContent = sc.logged_in ? (sc.username ? `Conectado como ${sc.username}` : 'Conectado (token guardado)') : 'Sin sesión';
    $('#sc-login').hidden = sc.logged_in;
    $('#sc-logout').hidden = !sc.logged_in;
    renderTicker();
  }

  async function soundcloudLogin() {
    const n = await native();
    if (!n) { show('settings'); $('#sc-token').click(); return; }
    toast('Inicia sesión en la ventana de SoundCloud; se cerrará sola.');
    state.soundcloud = await n.soundcloud_login();
    renderAccount();
    fire('soundcloud', state.soundcloud);
    if (state.soundcloud.logged_in) toast('Sesión iniciada.', 'ok');
  }
  $('#sc-login').addEventListener('click', soundcloudLogin);
  $('#sc-logout').addEventListener('click', async () => {
    state.soundcloud = await DEL('/api/soundcloud/token');
    renderAccount();
    fire('soundcloud', state.soundcloud);
  });
  $('#sc-token').addEventListener('click', async () => {
    const token = prompt('Pega el token OAuth de SoundCloud (cabecera "Authorization: OAuth …" de las peticiones a api-v2.soundcloud.com):');
    if (!token) return;
    state.soundcloud = await POST('/api/soundcloud/token', { token });
    renderAccount();
    fire('soundcloud', state.soundcloud);
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

  // ── App updates ────────────────────────────────────────────────────────

  const upd = { status: null, shown: false };
  (() => { const eq = $('#upd-eq'); for (let i = 0; i < 9; i++) eq.append(h('i', { style: `animation-delay:${(-i * 0.13).toFixed(2)}s;animation-duration:${(0.5 + (i * 37 % 7) / 10).toFixed(2)}s` })); })();

  function showUpdate(st, { force = false } = {}) {
    upd.status = st;
    const info = st && st.info;
    if (!info || !info.newer) { if (force) toast(`Estás en la última versión (${st ? st.current : state.version}).`, 'ok'); return; }
    if (info.skipped && !force) return;
    $('#upd-old').textContent = 'v' + st.current;
    $('#upd-new').textContent = 'v' + info.latest;
    $('#upd-notes').textContent = info.notes || '';
    $('#upd-page').href = info.page || '#';
    $('#upd-go').hidden = !st.can_download;
    renderUpdateProgress(st.download);
    const box = $('#upd');
    if (box.hidden) { box.hidden = false; box.querySelector('.upd-flash').style.animation = 'none'; void box.offsetWidth; box.querySelector('.upd-flash').style.animation = ''; }
    upd.shown = true;
  }

  function renderUpdateProgress(d) {
    if (!d) return;
    const bar = $('#upd-progress'), go = $('#upd-go'), card = $('#upd .upd-card');
    card.classList.toggle('ready', d.state === 'ready');
    if (d.state === 'downloading') {
      const pct = d.total ? Math.floor((d.done / d.total) * 100) : 0;
      bar.hidden = false; $('#upd-bar').style.width = pct + '%';
      $('#upd-pct').textContent = d.total ? `${pct}% · ${(d.done / 1048576).toFixed(0)} / ${(d.total / 1048576).toFixed(0)} MB` : 'descargando…';
      go.disabled = true; go.textContent = 'Descargando…';
    } else if (d.state === 'ready') {
      bar.hidden = false; $('#upd-bar').style.width = '100%'; $('#upd-pct').textContent = 'LISTO';
      $('#upd-title').textContent = 'LISTO'; $('#upd-title').dataset.text = 'LISTO';
      go.disabled = false; go.textContent = 'Abrir en la carpeta';
    } else if (d.state === 'error') {
      bar.hidden = true; go.disabled = false; go.textContent = 'Reintentar';
      toast('No se ha podido descargar la actualización: ' + d.error, 'error');
    } else {
      bar.hidden = true; go.disabled = false; go.textContent = 'Descargar';
    }
  }

  $('#upd-go').addEventListener('click', async () => {
    const d = upd.status && upd.status.download;
    if (d && d.state === 'ready') { reveal(d.path); return; }
    const st = await POST('/api/update/download').catch(() => null);
    if (st) { upd.status = st; renderUpdateProgress(st.download); }
  });
  $('#upd-later').addEventListener('click', () => { $('#upd').hidden = true; });
  $('#upd-skip').addEventListener('click', async () => { await POST('/api/update/skip').catch(() => {}); $('#upd').hidden = true; });
  $('#upd').addEventListener('click', (e) => { if (e.target.id === 'upd') $('#upd').hidden = true; });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#upd').hidden) $('#upd').hidden = true; });
  $('#update-check').addEventListener('click', async (e) => {
    e.currentTarget.classList.add('busy');
    try { showUpdate(await POST('/api/update/check'), { force: true }); } catch (_) {}
    finally { e.currentTarget.classList.remove('busy'); }
  });

  on('update_available', (p) => { if (!upd.shown || !$('#upd').hidden) showUpdate(p); });
  on('update_progress', (p) => {
    if (upd.status) upd.status.download = p;
    if (!$('#upd').hidden) renderUpdateProgress(p);
    else if (p.state === 'ready') toast('Actualización descargada. Ábrela desde Ajustes o tu carpeta de Descargas.', 'ok');
  });
  on('soundcloud', (p) => { state.soundcloud = p; renderAccount(); });

  // ── Server events ──────────────────────────────────────────────────────

  let events = null;
  function connectEvents() {
    if (events) events.close();
    events = new EventSource('/api/events', { withCredentials: true });
    let wasDown = false;
    events.onmessage = (e) => {
      const { kind, payload } = JSON.parse(e.data);
      if (kind === 'settings') { state.settings = payload; renderSettings(); }
      fire(kind, payload);
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

  async function refreshState() {
    const s = await GET('/api/state');
    Object.assign(state, {
      mode: s.mode, version: s.version, ytdlp: s.ytdlp_version, settings: s.settings,
      soundcloud: s.soundcloud, plugins: s.plugins, plugin_list: s.plugin_list,
    });
    document.body.classList.toggle('mode-server', s.mode === 'server');
    document.body.classList.toggle('mode-desktop', s.mode !== 'server');
    $('#ytdlp-version').textContent = 'versión ' + s.ytdlp_version;
    $('#ffmpeg-path').textContent = s.ffmpeg === true ? 'disponible' : s.ffmpeg || 'no encontrado';
    $('#app-version').textContent = 'versión ' + s.version;
    if (s.update && s.update.info && !upd.shown) showUpdate(s.update);
    $('#brand-ver').textContent = 'v' + s.version;
    $('#sc-where').textContent = s.mode === 'server'
      ? 'El token se guarda en el servidor, no en este navegador.'
      : 'El token se guarda en el llavero del sistema.';
    renderSettings();
    renderAccount();
    fire('state', s);
    renderTicker();
  }

  let built = false;
  async function boot() {
    const session = await GET('/api/session');
    state.mode = session.mode;
    $('#logout-row').hidden = !session.password_required;
    if (!session.authenticated) { showGate(); return; }
    if (!built) { buildViews(); buildSettings(); built = true; }
    await refreshState();
    connectEvents();
    let view = null;
    try { view = localStorage.getItem('ftn.view'); } catch (_) {}
    show(view || views.keys().next().value || 'settings');
  }

  // ── Public API for plugins ─────────────────────────────────────────────

  window.FTN = {
    // registration
    registerView, registerSettings, on, fire, provide, use, addTicker,
    // state & navigation
    state, isServer, show, isShown, setBadge, saveSetting, renderTicker,
    // HTTP & desktop bridge
    http, GET, POST, PATCH, DEL, getBytes, q, native, pickAudio, pickFolder, uploadFiles, reveal, openUrl,
    // UI pieces
    $, $$, h, toast, ICONS, iconBtn, fileIcon, badge, camelotFromKey, camChip, bpmChip, art, loadingBars,
    bindSegmented, fmtBytes, num, baseName, fmtHz, fmtTime,
    // shared audio
    player, takeAudio, soundcloudLogin,
    // entry points for scripted UI tests; plugins add theirs
    debug: { show },
  };

  // Plugin scripts come right after this one; boot once they have registered.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);
})();
