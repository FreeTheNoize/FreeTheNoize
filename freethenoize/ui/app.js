/* FreeTheNoize UI. Talks to Python through window.pywebview.api; Python
 * pushes updates through FTN.onEvent(kind, payload). */
(function () {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const { SpectrogramView, CMAP_NAMES, fmtHz, fmtTime } = window.Spectro;

  const state = {
    settings: {},
    jobs: new Map(),
    resolving: new Map(),
    soundcloud: { logged_in: false },
  };

  // ── Helpers ────────────────────────────────────────────────────────────

  async function api(name, ...args) {
    try {
      return await window.pywebview.api[name](...args);
    } catch (e) {
      toast(e && e.message ? e.message : String(e), 'error');
      throw e;
    }
  }

  function toast(text, kind = '') {
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.textContent = text;
    $('#toasts').append(el);
    setTimeout(() => el.remove(), kind === 'error' ? 7000 : 3500);
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
    wave: '<path d="M4 18V9m4 9V5m4 13v-7m4 7V7m4 11v-4"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    down: '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/>',
  };
  function iconBtn(icon, title, onclick) {
    const b = h('button', { class: 'btn icon ghost', title, onclick });
    b.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[icon]}</svg>`;
    return b;
  }

  function badge(quality) {
    if (!quality) return null;
    const cls = ['badge', quality.tier, quality.lossless && 'lossless', quality.preview && 'preview'].filter(Boolean).join(' ');
    return h('span', { class: cls }, quality.label);
  }

  const fmtBytes = (b) => b == null ? '' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB/s' : (b / 1e3).toFixed(0) + ' kB/s';
  const num = (v, d = 1) => v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d);

  // ── Navigation ─────────────────────────────────────────────────────────

  function show(view) {
    $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
    $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === view));
    if (view === 'history') loadHistory();
  }
  $$('[data-view]').forEach((b) => b.tagName === 'BUTTON' && b.addEventListener('click', () => show(b.dataset.view)));

  // ── Downloads ──────────────────────────────────────────────────────────

  const urlInput = $('#url-input');
  urlInput.addEventListener('input', () => {
    urlInput.style.height = 'auto';
    urlInput.style.height = urlInput.scrollHeight + 'px';
  });
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitUrls(); }
  });
  $('#download-btn').addEventListener('click', submitUrls);

  async function submitUrls(text) {
    const value = typeof text === 'string' ? text : urlInput.value;
    const res = await api('add_downloads', value);
    if (!res.accepted) { toast('No he encontrado ningún enlace.', 'error'); return; }
    if (typeof text !== 'string') { urlInput.value = ''; urlInput.style.height = 'auto'; }
  }

  // Drag & drop links anywhere on the window.
  const zone = $('#drop-zone');
  document.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag'); });
  document.addEventListener('dragleave', (e) => { if (!e.relatedTarget) zone.classList.remove('drag'); });
  document.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag');
    const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
    if (text) { show('downloads'); submitUrls(text); }
  });

  function renderResolving() {
    const box = $('#resolving');
    box.innerHTML = '';
    for (const [url, r] of state.resolving) {
      box.append(h('span', { class: 'chip' + (r.error ? ' error' : '') },
        r.error ? null : h('span', { class: 'spinner' }),
        r.error ? `No se ha podido leer ${url}: ${r.error}` : `Leyendo ${url}…`));
    }
  }

  const STATUS = {
    queued: 'En cola', downloading: 'Descargando', tagging: 'Etiquetando', done: 'Hecho',
    skipped: 'Ya descargada', error: 'Error', cancelled: 'Cancelada',
  };

  function jobRow(job) {
    const sub = job.error
      ? h('div', { class: 'sub err' }, job.error)
      : h('div', { class: 'sub' }, [job.artist || job.uploader, job.playlist].filter(Boolean).join(' · '));
    const meta = h('div', { class: 'meta' },
      h('div', { class: 'title' }, job.title), sub);
    if (job.status === 'downloading') {
      meta.append(h('div', { class: 'progress' }, h('div', { style: `width:${(job.progress * 100).toFixed(1)}%` })));
    }
    if (job.warnings && job.warnings.length && job.status === 'done') {
      meta.append(h('div', { class: 'sub', title: job.warnings.join('\n') }, '⚠︎ ' + job.warnings[0]));
    }
    const actions = h('div', { class: 'actions' }, badge(job.quality));
    let status = STATUS[job.status] || job.status;
    if (job.status === 'downloading') {
      status = `${Math.round(job.progress * 100)}%` + (job.speed ? ` · ${fmtBytes(job.speed)}` : '');
    }
    actions.append(h('span', { class: 'status' }, status));
    if (job.status === 'queued' || job.status === 'downloading') actions.append(iconBtn('x', 'Cancelar', () => api('cancel_job', job.id)));
    if (job.status === 'error' || job.status === 'cancelled') actions.append(iconBtn('retry', 'Reintentar', () => api('retry_job', job.id)));
    if (job.status === 'done' && job.path) {
      actions.append(iconBtn('wave', 'Espectrograma', () => { show('analyze'); analyzeFile(job.path); }));
      actions.append(iconBtn('folder', 'Mostrar en carpeta', () => api('reveal', job.path)));
    }
    return h('div', { class: 'row-item', 'data-job': job.id },
      h('div', { class: 'art', style: job.thumbnail ? `background-image:url("${job.thumbnail}")` : null }),
      meta, actions);
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

  function renderCounts() {
    const jobs = [...state.jobs.values()];
    const active = jobs.filter((j) => j.status === 'queued' || j.status === 'downloading' || j.status === 'tagging').length;
    const done = jobs.filter((j) => j.status === 'done').length;
    const failed = jobs.filter((j) => j.status === 'error').length;
    $('#jobs-empty').hidden = jobs.length > 0;
    $('#job-counts').textContent = jobs.length
      ? [`${jobs.length} en total`, active && `${active} pendientes`, done && `${done} hechas`, failed && `${failed} con error`].filter(Boolean).join(' · ')
      : '';
    const b = $('#badge-downloads');
    b.hidden = !active;
    b.textContent = active;
  }

  $('#clear-finished').addEventListener('click', () => api('clear_finished'));
  $('#cancel-all').addEventListener('click', () => api('cancel_all'));

  // ── Search ─────────────────────────────────────────────────────────────

  $('#search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = $('#search-input').value.trim();
    if (!q) return;
    const list = $('#search-results');
    list.innerHTML = '';
    list.append(h('div', { class: 'loading' }, h('div', { class: 'spinner' }), 'Buscando…'));
    const results = await api('search', q).catch(() => []);
    list.innerHTML = '';
    if (!results.length) list.append(h('div', { class: 'empty' }, h('p', {}, 'Sin resultados.')));
    for (const r of results) {
      list.append(h('div', { class: 'row-item' },
        h('div', { class: 'art', style: r.thumbnail ? `background-image:url("${r.thumbnail}")` : null }),
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, r.title),
          h('div', { class: 'sub' }, [r.uploader, r.duration && fmtTime(r.duration)].filter(Boolean).join(' · '))),
        h('div', { class: 'actions' },
          h('button', { class: 'btn small primary', onclick: () => { submitUrls(r.url); toast('Añadida a la cola.', 'ok'); } }, 'Descargar'))));
    }
  });

  // ── Spectrogram view ───────────────────────────────────────────────────

  const cmapSelects = [$('#an-cmap'), $('#cmp-cmap')];
  for (const sel of cmapSelects) {
    for (const name of CMAP_NAMES) sel.append(h('option', { value: name }, name[0].toUpperCase() + name.slice(1)));
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
    const files = await api('choose_audio_files', false);
    if (files.length) analyzeFile(files[0]);
  });
  anSpec.onSeek = (t) => { anAudio.currentTime = t; };
  $('#an-play').addEventListener('click', () => (anAudio.paused ? anAudio.play() : anAudio.pause()));
  anAudio.addEventListener('play', () => { $('#an-play').textContent = '❚❚ Pausa'; });
  anAudio.addEventListener('pause', () => { $('#an-play').textContent = '▶︎ Reproducir'; });
  anAudio.addEventListener('timeupdate', () => {
    anSpec.setPlayhead(anAudio.currentTime);
    $('#an-time').textContent = fmtTime(anAudio.currentTime);
  });

  function infoMetrics(info, loud) {
    const items = [
      ['Formato', (info.codec || info.ext || '').toString().toUpperCase()],
      ['Frecuencia', info.sample_rate ? [num(info.sample_rate / 1000, 1), 'kHz'] : '—'],
      ['Resolución', info.bits ? [info.bits, 'bit'] : '—'],
      ['Bitrate', info.bitrate ? [info.bitrate, 'kbps'] : '—'],
      ['Duración', info.duration ? fmtTime(info.duration) : '—'],
      ['Loudness', loud.integrated_lufs != null ? [num(loud.integrated_lufs), 'LUFS'] : '—'],
      ['True peak', loud.true_peak_dbtp != null ? [num(loud.true_peak_dbtp), 'dBTP'] : '—'],
      ['Rango (LRA)', loud.lra != null ? [num(loud.lra), 'LU'] : '—'],
      ['PLR', loud.plr != null ? [num(loud.plr), 'dB'] : '—'],
    ];
    return items.map(([k, v]) => h('div', { class: 'metric' },
      h('div', { class: 'k' }, k),
      h('div', { class: 'v' }, Array.isArray(v) ? [v[0], h('small', {}, v[1])] : v)));
  }

  function curveSvg(curve, cutoff, fMax) {
    const W = 1000, H = 100;
    const lo = -110;
    const pts = curve.freqs.map((f, i) => {
      const x = (f / fMax) * W;
      const y = H * Math.min(1, Math.max(0, curve.db[i] / lo));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const cx = (cutoff / fMax) * W;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      ${cutoff && cutoff < fMax - 500 ? `<line x1="${cx}" x2="${cx}" y1="0" y2="${H}" stroke="var(--warn)" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>` : ''}
    </svg>`;
  }

  async function analyzeFile(path) {
    $('#an-result').hidden = true;
    $('#an-loading').hidden = false;
    anAudio.pause();
    let r;
    try { r = await api('analyze', path); } finally { $('#an-loading').hidden = true; }
    const c = r.cutoff;
    $('#an-sub').textContent = r.info.name;
    const v = $('#an-verdict');
    v.className = 'verdict glass ' + c.level;
    v.innerHTML = '';
    v.append(h('div', {}, c.verdict,
      h('small', {}, c.sharp
        ? `Corte en ${fmtHz(c.cutoff_hz)}Hz${c.estimate ? ' · fuente ' + c.estimate : ''}${c.drop_db ? ` · caída de ${Math.round(c.drop_db)} dB` : ''}`
        : `Hay contenido hasta ${fmtHz(c.cutoff_hz)}Hz (límite del archivo: ${fmtHz(r.info.sample_rate / 2)}Hz)`,
        r.truncated ? ` · analizados los primeros ${Math.round(r.analysed_seconds / 60)} min` : '')));
    const m = $('#an-metrics');
    m.innerHTML = '';
    m.append(...infoMetrics(r.info, r.loudness));
    $('#an-result').hidden = false;
    anSpec.set({ cmap: $('#an-cmap').value });
    anSpec.setData(r.spectrogram);
    anSpec.setMarker(c.sharp ? c.cutoff_hz : null);
    anSpec.setPlayhead(0);
    $('#an-curve').innerHTML = curveSvg(c.curve, c.sharp ? c.cutoff_hz : 0, r.spectrogram.f_max);
    anAudio.src = r.audio_url;
  }

  // ── Compare ────────────────────────────────────────────────────────────

  const cmp = { a: null, b: null, results: {}, nullReport: null };
  const specA = new SpectrogramView($('#cmp-spec-a'), { scale: 'linear' });
  const specB = new SpectrogramView($('#cmp-spec-b'), { scale: 'linear' });
  const specN = new SpectrogramView($('#null-spec'), { scale: 'linear' });
  const cmpViews = [specA, specB, specN];
  bindSegmented($('#cmp-scale'), (v) => cmpViews.forEach((s) => s.set({ scale: v })));
  $('#cmp-cmap').addEventListener('change', (e) => { cmpViews.forEach((s) => s.set({ cmap: e.target.value })); saveSetting('colormap', e.target.value); });
  $('#cmp-floor').addEventListener('input', (e) => cmpViews.forEach((s) => s.set({ floor: +e.target.value })));

  $$('.slot').forEach((slot) => slot.addEventListener('click', async () => {
    const files = await api('choose_audio_files', false);
    if (!files.length) return;
    const key = slot.dataset.slot;
    cmp[key] = files[0];
    slot.classList.add('filled');
    $('.slot-name', slot).textContent = files[0].split(/[\\/]/).pop();
    if (cmp.a && cmp.b) runCompare();
  }));

  async function runCompare() {
    ab.stop();
    $('#cmp-result').hidden = true;
    $('#null-result').hidden = true;
    $('#cmp-loading').hidden = false;
    $('#cmp-loading-text').textContent = 'Analizando las dos versiones…';
    try {
      const [ra, rb] = await Promise.all([api('analyze', cmp.a), api('analyze', cmp.b)]);
      cmp.results = { a: ra, b: rb };
      $('#cmp-loading-text').textContent = 'Preparando la escucha A/B…';
      await ab.load({ a: ra.audio_url, b: rb.audio_url });
    } finally {
      $('#cmp-loading').hidden = true;
    }
    const { a: ra, b: rb } = cmp.results;
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
    const rows = [
      ['Archivo', ra.info.name, rb.info.name],
      ['Formato', (ra.info.codec || ra.info.ext).toUpperCase(), (rb.info.codec || rb.info.ext).toUpperCase()],
      ['Frecuencia / bits', `${num(ra.info.sample_rate / 1000)} kHz${ra.info.bits ? ' · ' + ra.info.bits + ' bit' : ''}`,
        `${num(rb.info.sample_rate / 1000)} kHz${rb.info.bits ? ' · ' + rb.info.bits + ' bit' : ''}`],
      ['Bitrate', ra.info.bitrate ? ra.info.bitrate + ' kbps' : '—', rb.info.bitrate ? rb.info.bitrate + ' kbps' : '—'],
      ['Corte de frecuencias', ra.cutoff.sharp ? fmtHz(ra.cutoff.cutoff_hz) + 'Hz' : 'Sin corte', rb.cutoff.sharp ? fmtHz(rb.cutoff.cutoff_hz) + 'Hz' : 'Sin corte', 'cut'],
      ['Veredicto', ra.cutoff.verdict, rb.cutoff.verdict],
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
    if (!cmp.a || !cmp.b) return;
    const btn = $('#null-run');
    btn.disabled = true;
    btn.textContent = 'Calculando…';
    let r;
    try { r = await api('null_test', cmp.a, cmp.b); } finally { btn.disabled = false; btn.textContent = 'Ejecutar'; }
    cmp.nullReport = r;
    const v = $('#null-verdict');
    v.className = 'verdict ' + r.level;
    v.innerHTML = '';
    v.append(h('div', {}, r.verdict, h('small', {}, `Profundidad del null: ${num(r.null_depth_db)} dB (más negativo = más parecidos)`)));
    const m = $('#null-metrics');
    m.innerHTML = '';
    m.append(...[
      ['Profundidad', [num(r.null_depth_db), 'dB']],
      ['Desfase', [num(r.offset_ms, 2), 'ms']],
      ['Diferencia de ganancia', [num(r.gain_db, 2), 'dB']],
      ['Correlación', num(r.correlation, 4)],
      ['Polaridad', r.inverted ? 'Invertida' : 'Normal'],
    ].map(([k, val]) => h('div', { class: 'metric' }, h('div', { class: 'k' }, k),
      h('div', { class: 'v' }, Array.isArray(val) ? [val[0], h('small', {}, val[1])] : val))));
    $('#null-result').hidden = false;
    specN.setData(r.spectrogram);
    await ab.load({ diff: r.audio_url }, true);
    ab.offsets.b = r.offset_ms / 1000;
    if (ab.playing) ab.seek(ab.now());  // restart so the new sources line up
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
        const data = await (await fetch(url)).arrayBuffer();
        this.buffers[k] = await this.ctx.decodeAudioData(data);
      }));
    },
    duration() { return Math.max(0, ...Object.values(this.buffers).map((b) => b.duration)); },
    now() { return this.playing ? this.pos + (this.ctx.currentTime - this.startedAt) : this.pos; },
    setGainMatch() {
      const { a, b } = cmp.results;
      const la = a && a.loudness.integrated_lufs, lb = b && b.loudness.integrated_lufs;
      this.levels = { a: 1, b: 1, diff: 1 };
      if ($('#ab-match').checked && la != null && lb != null) {
        // Bring the louder one down to the quieter one.
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
      this.ctx.resume();
      const at = this.ctx.currentTime + 0.05;
      for (const [k, buf] of Object.entries(this.buffers)) {
        const src = this.ctx.createBufferSource();
        src.buffer = buf;
        const g = this.ctx.createGain();
        g.gain.value = k === this.active ? (this.levels[k] ?? 1) : 0;
        src.connect(g).connect(this.ctx.destination);
        // The null test tells us how far B is shifted relative to A.
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
      $('#ab-play').textContent = '▶︎';
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
    if (e.target.matches('input[type=text], input[type=search], textarea')) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); ab.toggle(); }
    else if (k === 'a' || k === 'b') ab.select(k);
    else if (k === 'd') ab.select('diff');
  });

  // ── Converter ──────────────────────────────────────────────────────────

  const cv = { files: [], fmt: 'wav', dest: null, status: {} };

  function renderConvert() {
    const list = $('#cv-list');
    list.innerHTML = '';
    cv.files.forEach((f, i) => {
      const st = cv.status[i] || {};
      list.append(h('div', { class: 'row-item', style: 'grid-template-columns: 1fr auto' },
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, f.split(/[\\/]/).pop()),
          st.error ? h('div', { class: 'sub err' }, st.error)
            : st.warning ? h('div', { class: 'sub' }, '⚠︎ ' + st.warning)
              : h('div', { class: 'sub' }, f)),
        h('div', { class: 'actions' },
          st.status === 'running' ? h('div', { class: 'spinner' }) : null,
          st.status === 'done' ? h('span', { class: 'status' }, 'Hecho') : null,
          st.status === 'done' ? iconBtn('folder', 'Mostrar', () => api('reveal', st.dest)) : null,
          !st.status ? iconBtn('x', 'Quitar', () => { cv.files.splice(i, 1); renderConvert(); }) : null)));
    });
    $('#cv-empty').hidden = cv.files.length > 0;
    $('#cv-run').disabled = !cv.files.length;
  }

  $('#cv-add').addEventListener('click', async () => {
    const files = await api('choose_audio_files', true);
    for (const f of files) if (!cv.files.includes(f)) cv.files.push(f);
    cv.status = {};
    renderConvert();
  });
  $('#cv-same').addEventListener('change', (e) => { $('#cv-dest').disabled = e.target.checked; });
  $('#cv-dest').addEventListener('click', async () => {
    const d = await api('choose_folder', '');
    if (d) { cv.dest = d; $('#cv-dest').textContent = d.split(/[\\/]/).pop() || d; }
  });
  $('#cv-run').addEventListener('click', async () => {
    cv.status = {};
    $('#cv-run').disabled = true;
    await api('convert', cv.files, cv.fmt, $('#cv-same').checked ? null : cv.dest);
  });

  // ── History ────────────────────────────────────────────────────────────

  async function loadHistory() {
    const items = await api('history');
    const list = $('#history-list');
    list.innerHTML = '';
    $('#history-empty').hidden = items.length > 0;
    for (const it of items) {
      const when = new Date(it.time * 1000).toLocaleString();
      list.append(h('div', { class: 'row-item' },
        h('div', { class: 'art', style: it.thumbnail ? `background-image:url("${it.thumbnail}")` : null }),
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, it.title),
          h('div', { class: 'sub' }, [it.artist, when].filter(Boolean).join(' · '))),
        h('div', { class: 'actions' },
          badge(it.quality),
          iconBtn('wave', 'Espectrograma', () => { show('analyze'); analyzeFile(it.path); }),
          iconBtn('folder', 'Mostrar en carpeta', () => api('reveal', it.path)),
          iconBtn('link', 'Abrir en el navegador', () => api('open_url', it.url)))));
    }
  }

  // ── Settings ───────────────────────────────────────────────────────────

  async function saveSetting(key, value) {
    state.settings = await api('update_settings', { [key]: value });
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
    $('#template-preview').textContent = (s.filename_template || '').replace(/\{(\w+)\}/g, (_, k) => sample[k] ?? '') + '.wav';
    for (const sel of cmapSelects) sel.value = s.colormap || 'inferno';
  }

  $$('[data-setting]').forEach((el) => {
    el.addEventListener('change', () => {
      const v = el.type === 'checkbox' ? el.checked : el.type === 'number' || el.tagName === 'SELECT' && /^\d+$/.test(el.value) ? Number(el.value) : el.value;
      saveSetting(el.dataset.setting, v);
    });
  });
  $('#set-template').addEventListener('input', (e) => {
    state.settings.filename_template = e.target.value;
    renderSettings();
  });
  $('#set-dir-btn').addEventListener('click', async () => {
    const d = await api('choose_folder', state.settings.download_dir);
    if (d) saveSetting('download_dir', d);
  });

  function renderAccount() {
    const sc = state.soundcloud;
    const label = sc.logged_in ? (sc.username ? `SoundCloud: ${sc.username}` : 'SoundCloud: conectado') : 'Sin sesión';
    $('#account-label').textContent = label;
    $('#account-pill').classList.toggle('on', sc.logged_in);
    $('#sc-status').textContent = sc.logged_in ? (sc.username ? `Conectado como ${sc.username}` : 'Conectado (token guardado)') : 'Sin sesión';
    $('#sc-login').hidden = sc.logged_in;
    $('#sc-logout').hidden = !sc.logged_in;
    $('#login-notice').hidden = sc.logged_in;
  }

  $$('[data-action=login]').forEach((b) => b.addEventListener('click', async () => {
    toast('Inicia sesión en la ventana de SoundCloud; se cerrará sola.');
    state.soundcloud = await api('soundcloud_login');
    renderAccount();
    if (state.soundcloud.logged_in) toast('Sesión iniciada.', 'ok');
  }));
  $('#sc-logout').addEventListener('click', async () => { state.soundcloud = await api('soundcloud_logout'); renderAccount(); });
  $('#sc-token').addEventListener('click', async () => {
    const token = prompt('Pega el token OAuth de SoundCloud (cabecera "Authorization: OAuth …" en las peticiones a api-v2.soundcloud.com):');
    if (!token) return;
    state.soundcloud = await api('soundcloud_set_token', token);
    renderAccount();
    toast(state.soundcloud.username ? 'Token válido.' : 'Token guardado (no se ha podido verificar).', state.soundcloud.username ? 'ok' : '');
  });

  $('#ytdlp-update').addEventListener('click', async () => {
    const b = $('#ytdlp-update');
    b.disabled = true; b.textContent = 'Buscando…';
    try {
      const r = await api('update_ytdlp');
      toast(r.updated ? `yt-dlp ${r.version} descargado. Reinicia la app para usarlo.` : `Ya tienes la última versión (${r.version}).`, 'ok');
    } finally { b.disabled = false; b.textContent = 'Buscar actualización'; }
  });

  // ── Events from Python ─────────────────────────────────────────────────

  window.FTN = {
    // Entry points for scripted UI tests (no native dialogs involved).
    debug: {
      show,
      analyzeFile,
      compare(a, b) { cmp.a = a; cmp.b = b; return runCompare(); },
      nullTest: () => $('#null-run').click(),
    },
    onEvent(kind, p) {
      if (kind === 'job') {
        state.jobs.set(p.id, p);
        renderJob(p);
      } else if (kind === 'jobs') {
        state.jobs = new Map(p.jobs.map((j) => [j.id, j]));
        renderAllJobs();
      } else if (kind === 'resolving') {
        if (p.active) state.resolving.set(p.url, {});
        else if (p.error) {
          state.resolving.set(p.url, { error: p.error });
          setTimeout(() => { state.resolving.delete(p.url); renderResolving(); }, 8000);
        } else {
          state.resolving.delete(p.url);
          if (p.count > 1) toast(`${p.title || 'Colección'}: ${p.count} temas en cola.`, 'ok');
          if (p.count === 0) toast('Ese enlace no contiene ningún tema.', 'error');
        }
        renderResolving();
      } else if (kind === 'soundcloud') {
        state.soundcloud = p;
        renderAccount();
      } else if (kind === 'convert') {
        if (p.status === 'finished') { $('#cv-run').disabled = false; toast('Conversión terminada.', 'ok'); return; }
        cv.status[p.index] = p;
        renderConvert();
      }
    },
  };

  // ── Boot ───────────────────────────────────────────────────────────────

  async function boot() {
    const s = await api('get_state');
    if (s.platform === 'darwin') document.body.classList.add('vibrant');
    state.settings = s.settings;
    state.soundcloud = s.soundcloud;
    state.jobs = new Map(s.jobs.map((j) => [j.id, j]));
    $('#ytdlp-version').textContent = 'Versión ' + s.ytdlp_version;
    $('#ffmpeg-path').textContent = s.ffmpeg || 'No encontrado';
    $('#app-version').textContent = 'Versión ' + s.version;
    const seg = $('#cv-format');
    for (const [k, label] of Object.entries(s.formats)) seg.append(h('button', { 'data-value': k, class: k === cv.fmt ? 'on' : null }, label));
    bindSegmented(seg, (v) => { cv.fmt = v; });
    renderSettings();
    renderAccount();
    renderAllJobs();
    renderConvert();
  }

  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener('pywebviewready', boot);
})();
