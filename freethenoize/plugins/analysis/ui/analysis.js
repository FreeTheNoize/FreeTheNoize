/* Plugin analysis: Espectro (one file) and A/B · Null (two versions).
 * Provides: 'analysis.open'(path), 'compare.add'(path), 'files.open'(paths) for dropped audio. */
(function () {
  const { $, $$, h, POST, getBytes, toast, num, fmtHz, fmtTime, bindSegmented, baseName, pickAudio, saveSetting } = FTN;
  const { SpectrogramView, CMAP_NAMES } = window.Spectro;

  const anAudio = h('audio', { preload: 'auto' });
  document.body.append(anAudio);
  let anSpec;

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

  // Frequency curve under the spectrogram. Only numbers go into this string.
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

  const analyzeApi = (path) => POST('/api/analysis/analyze', { path });

  // ── Espectro ───────────────────────────────────────────────────────────

  async function analyzeFile(path) {
    $('#an-result').hidden = true;
    $('#an-loading').hidden = false;
    anAudio.pause();
    let r;
    try { r = await analyzeApi(path); } finally { $('#an-loading').hidden = true; }
    const c = r.cutoff;
    $('#an-sub').textContent = r.info.name;
    const v = $('#an-verdict');
    v.className = 'verdict ' + c.level;
    v.textContent = '';
    v.append(c.verdict, h('small', {}, c.sharp
      ? `corte en ${fmtHz(c.cutoff_hz)}Hz${c.estimate ? ' · fuente ' + c.estimate : ''}${c.drop_db ? ` · caída de ${Math.round(c.drop_db)} dB` : ''}`
      : `contenido hasta ${fmtHz(c.cutoff_hz)}Hz (límite del archivo: ${fmtHz(r.info.sample_rate / 2)}Hz)`,
    r.truncated ? ` · analizados los primeros ${Math.round(r.analysed_seconds / 60)} min` : ''));
    const m = $('#an-metrics');
    m.textContent = '';
    m.append(...infoMetrics(r.info, r.loudness, r.musical));
    $('#an-result').hidden = false;
    anSpec.set({ cmap: $('#an-cmap').value });
    anSpec.setData(r.spectrogram);
    anSpec.setMarker(c.sharp ? c.cutoff_hz : null);
    anSpec.setPlayhead(0);
    $('#an-curve').innerHTML = curveSvg(c.curve, c.sharp ? c.cutoff_hz : 0, r.spectrogram.f_max);
    anAudio.src = r.audio_url;
  }

  const openAnalysis = (path) => { FTN.show('analyze'); return analyzeFile(path); };
  FTN.provide('analysis.open', openAnalysis);
  FTN.provide('files.open', (paths) => openAnalysis(paths[0]));

  function fillCmaps(sel) {
    for (const name of CMAP_NAMES) sel.append(h('option', { value: name }, name));
    sel.value = FTN.state.settings['analysis.colormap'] || 'inferno';
  }

  FTN.registerView({
    id: 'analyze',
    group: 'laboratorio',
    order: 60,
    title: 'Espectro',
    heading: 'Radiografía',
    intro: 'Calidad real de un archivo: corte de frecuencias, falsos lossless, loudness, BPM y tonalidad.',
    introId: 'an-sub',
    actions: [{ id: 'an-open', label: 'Abrir archivo', primary: true }],
    html: `
      <div id="an-result" hidden>
        <div class="verdict" id="an-verdict"></div>
        <div class="metrics" id="an-metrics"></div>
        <div class="panel spec-card">
          <div class="spec-toolbar">
            <div class="segmented" id="an-scale">
              <button data-value="log" class="on">Log</button>
              <button data-value="linear">Lin</button>
            </div>
            <select id="an-cmap" class="select"></select>
            <label class="slider mono">contraste <input type="range" id="an-floor" min="-120" max="-40" step="1" value="-100"></label>
            <div class="spacer"></div>
            <button class="btn small" id="an-play">▶ Play</button>
            <span class="mono" id="an-time">0:00</span>
          </div>
          <div class="spec" id="an-spec"></div>
          <div class="curve" id="an-curve"></div>
        </div>
      </div>
      <div class="loading" id="an-loading" hidden><span class="bars"><i></i><i></i><i></i><i></i></span>Analizando…</div>`,
    init(el) {
      anSpec = new SpectrogramView($('#an-spec', el));
      fillCmaps($('#an-cmap', el));
      bindSegmented($('#an-scale', el), (v) => anSpec.set({ scale: v }));
      $('#an-cmap', el).addEventListener('change', (e) => { anSpec.set({ cmap: e.target.value }); saveSetting('analysis.colormap', e.target.value); });
      $('#an-floor', el).addEventListener('input', (e) => anSpec.set({ floor: +e.target.value }));
      $('#an-open', el).addEventListener('click', async () => {
        const files = await pickAudio(false);
        if (files.length) analyzeFile(files[0]);
      });
      anSpec.onSeek = (t) => { anAudio.currentTime = t; if (anAudio.paused) anAudio.play(); };
      $('#an-play', el).addEventListener('click', () => (anAudio.paused ? anAudio.play() : anAudio.pause()));
      anAudio.addEventListener('play', () => { FTN.takeAudio('analyze'); $('#an-play').textContent = '❚❚ Pausa'; });
      anAudio.addEventListener('pause', () => { $('#an-play').textContent = '▶ Play'; });
      anAudio.addEventListener('timeupdate', () => {
        anSpec.setPlayhead(anAudio.currentTime);
        $('#an-time').textContent = fmtTime(anAudio.currentTime);
      });
    },
    onFiles: (paths) => analyzeFile(paths[0]),
  });

  // ── A/B · Null ─────────────────────────────────────────────────────────

  const cmp = { a: null, b: null, results: {}, nullReport: null };
  let specA, specB, specN, cmpViews = [];

  function setSlot(key, path) {
    cmp[key] = path;
    const slot = $(`.slot[data-slot="${key}"]`);
    slot.classList.add('filled');
    $('.slot-name', slot).textContent = baseName(path);
    if (cmp.a && cmp.b) { FTN.show('compare'); runCompare(); }
  }

  FTN.provide('compare.add', (path) => {
    const slot = cmp.a ? 'b' : 'a';
    setSlot(slot, path);
    if (!(cmp.a && cmp.b)) toast(`En el comparador como ${slot.toUpperCase()}.`, 'ok');
  });

  async function runCompare() {
    ab.stop();
    $('#cmp-result').hidden = true;
    $('#null-result').hidden = true;
    $('#cmp-loading').hidden = false;
    $('#cmp-loading-text').textContent = 'Analizando las dos versiones…';
    try {
      const [ra, rb] = await Promise.all([analyzeApi(cmp.a), analyzeApi(cmp.b)]);
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
    t.textContent = '';
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

  async function runNullTest() {
    if (!cmp.a || !cmp.b) return;
    const btn = $('#null-run');
    btn.disabled = true;
    btn.textContent = 'Calculando…';
    let r;
    try { r = await POST('/api/analysis/null-test', { a: cmp.a, b: cmp.b }); } finally { btn.disabled = false; btn.textContent = 'Ejecutar'; }
    cmp.nullReport = r;
    const v = $('#null-verdict');
    v.className = 'verdict ' + r.level;
    v.textContent = '';
    v.append(r.verdict, h('small', {}, `profundidad del null: ${num(r.null_depth_db)} dB (más negativo = más parecidos)`));
    const m = $('#null-metrics');
    m.textContent = '';
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
  }

  // A/B player on Web Audio: every version plays at once, only the selected
  // one is audible, so switching is instant and sample-aligned.
  const ab = {
    ctx: null, buffers: {}, sources: {}, gains: {}, offsets: {}, levels: {},
    active: 'a', playing: false, startedAt: 0, pos: 0, raf: null,

    async load(urls, keep = false) {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (!keep) { this.buffers = {}; this.offsets = {}; this.pos = 0; }
      await Promise.all(Object.entries(urls).map(async ([k, url]) => {
        const data = await getBytes(url);
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
      FTN.takeAudio('compare');
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

  FTN.on('audio.focus', ({ owner }) => {
    if (owner !== 'analyze') anAudio.pause();
    if (owner !== 'compare' && ab.playing) ab.stop();
  });

  FTN.registerView({
    id: 'compare',
    group: 'laboratorio',
    order: 70,
    title: 'A/B · Null',
    kicker: 'a·b · null',
    heading: 'Careo',
    intro: 'Dos versiones del mismo tema: espectros lado a lado, escucha A/B con el volumen igualado y null test.',
    html: `
      <div class="slots">
        <button class="slot" data-slot="a"><span class="slot-key">A</span><span class="slot-name">Elegir archivo…</span></button>
        <button class="slot" data-slot="b"><span class="slot-key">B</span><span class="slot-name">Elegir archivo…</span></button>
      </div>
      <div class="loading" id="cmp-loading" hidden><span class="bars"><i></i><i></i><i></i><i></i></span><span id="cmp-loading-text">Analizando…</span></div>
      <div id="cmp-result" hidden>
        <div class="panel ab-bar">
          <button class="btn primary square" id="ab-play" title="Espacio">▶</button>
          <div class="segmented big" id="ab-switch">
            <button data-key="a" class="on">A</button>
            <button data-key="b">B</button>
            <button data-key="diff" disabled>Δ</button>
          </div>
          <input type="range" id="ab-seek" min="0" max="1000" value="0" class="seek">
          <span class="mono" id="ab-time">0:00</span>
          <label class="check"><input type="checkbox" id="ab-match" checked> igualar volumen</label>
        </div>
        <div class="hint mono"><kbd>espacio</kbd> play · <kbd>A</kbd>/<kbd>B</kbd> cambiar · <kbd>D</kbd> diferencia</div>
        <div class="table-wrap"><table class="panel cmp-table" id="cmp-table"></table></div>
        <div class="panel spec-card">
          <div class="spec-toolbar">
            <div class="segmented" id="cmp-scale">
              <button data-value="log">Log</button>
              <button data-value="linear" class="on">Lin</button>
            </div>
            <select id="cmp-cmap" class="select"></select>
            <label class="slider mono">contraste <input type="range" id="cmp-floor" min="-120" max="-40" step="1" value="-100"></label>
          </div>
          <div class="spec-label mono">A · <span id="cmp-name-a"></span></div>
          <div class="spec" id="cmp-spec-a"></div>
          <div class="spec-label mono">B · <span id="cmp-name-b"></span></div>
          <div class="spec" id="cmp-spec-b"></div>
        </div>
        <div class="panel null-card">
          <div class="null-head">
            <div>
              <h3>Null test</h3>
              <p>Alinea las dos versiones, iguala la ganancia y resta una de otra. Lo que queda es exactamente lo que cambia.</p>
            </div>
            <button class="btn" id="null-run">Ejecutar</button>
          </div>
          <div id="null-result" hidden>
            <div class="verdict" id="null-verdict"></div>
            <div class="metrics" id="null-metrics"></div>
            <div class="spec-label mono">Diferencia (A − B)</div>
            <div class="spec" id="null-spec"></div>
          </div>
        </div>
      </div>`,
    init(el) {
      specA = new SpectrogramView($('#cmp-spec-a', el), { scale: 'linear' });
      specB = new SpectrogramView($('#cmp-spec-b', el), { scale: 'linear' });
      specN = new SpectrogramView($('#null-spec', el), { scale: 'linear' });
      cmpViews = [specA, specB, specN];
      fillCmaps($('#cmp-cmap', el));
      bindSegmented($('#cmp-scale', el), (v) => cmpViews.forEach((s) => s.set({ scale: v })));
      $('#cmp-cmap', el).addEventListener('change', (e) => { cmpViews.forEach((s) => s.set({ cmap: e.target.value })); saveSetting('analysis.colormap', e.target.value); });
      $('#cmp-floor', el).addEventListener('input', (e) => cmpViews.forEach((s) => s.set({ floor: +e.target.value })));
      $$('.slot', el).forEach((slot) => slot.addEventListener('click', async () => {
        const files = await pickAudio(false);
        if (files.length) setSlot(slot.dataset.slot, files[0]);
      }));
      $('#null-run', el).addEventListener('click', runNullTest);
      $('#ab-play', el).addEventListener('click', () => ab.toggle());
      bindSegmented($('#ab-switch', el), (k) => ab.select(k));
      $('#ab-seek', el).addEventListener('input', (e) => ab.seek((e.target.value / 1000) * ab.duration()));
      $('#ab-match', el).addEventListener('change', () => ab.setGainMatch());
      cmpViews.forEach((s) => { s.onSeek = (t) => ab.seek(t); });
      document.addEventListener('keydown', (e) => {
        if (!FTN.isShown('compare') || $('#cmp-result').hidden) return;
        if (e.target.matches('input, textarea, select')) return;
        const k = e.key.toLowerCase();
        if (k === ' ') { e.preventDefault(); ab.toggle(); }
        else if (k === 'a' || k === 'b') ab.select(k);
        else if (k === 'd') ab.select('diff');
      });
    },
    onFiles(paths) {
      if (paths.length >= 2) { setSlot('a', paths[0]); setSlot('b', paths[1]); }
      else setSlot(cmp.a ? 'b' : 'a', paths[0]);
    },
  });

  function syncCmap(settings) {
    const c = settings['analysis.colormap'];
    if (!c) return;
    for (const id of ['#an-cmap', '#cmp-cmap']) { const sel = $(id); if (sel) sel.value = c; }
  }
  FTN.on('settings', syncCmap);
  FTN.on('state', (s) => syncCmap(s.settings));

  Object.assign(FTN.debug, {
    analyzeFile,
    compare(a, b) { cmp.a = a; cmp.b = b; return runCompare(); },
    nullTest: () => $('#null-run').click(),
  });
})();
