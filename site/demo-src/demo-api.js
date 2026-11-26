/* FreeTheNoize demo: the real interface with no backend.
 *
 * Loaded before kernel.js. Answers /api/* in the browser (fetch and
 * EventSource) with the data recorded from the real API by
 * tools/build_site.py (demo-data.js), and simulates what needs the internet
 * (downloads, search, pre-listening, subscriptions). Nothing is downloaded or
 * saved, and no request leaves the site.
 */
(function () {
  const D = window.FTN_DEMO_DATA;
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const state = clone(D.state);
  state.soundcloud = { logged_in: true, username: 'demo' };
  let library = clone(D.library);
  const tracks = D.tracks;
  const now = () => Date.now() / 1000;

  // ── Helpers ─────────────────────────────────────────────────────────────

  let lastNote = 0;
  function note(text = 'Demo: no descarga ni guarda nada.') {
    if (Date.now() - lastNote < 2500) return;
    lastNote = Date.now();
    setTimeout(() => window.FTN && FTN.toast(text), 0);
  }
  const hash = (s) => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  const trackOf = (path) => tracks.find((t) => t.path === path) || tracks[hash(path) % tracks.length];
  const slug = (url) => {
    const last = decodeURIComponent(String(url).split(/[?#]/)[0].replace(/\/+$/, '').split('/').pop() || 'tema');
    const words = last.replace(/[-_]+/g, ' ').trim();
    return words ? words[0].toUpperCase() + words.slice(1) : 'Tema';
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const realFetch = window.fetch.bind(window);
  const loadJson = async (url) => (await realFetch(url)).json();

  // ── Server events ───────────────────────────────────────────────────────

  const sources = new Set();
  function emit(kind, payload) {
    const data = JSON.stringify({ kind, payload });
    for (const s of sources) if (s.onmessage) s.onmessage({ data });
  }
  class DemoEventSource {
    constructor(url) {
      this.url = url; this.readyState = 1;
      this.onmessage = null; this.onerror = null; this.onopen = null;
      sources.add(this);
      setTimeout(() => this.onopen && this.onopen({}), 0);
    }
    close() { this.readyState = 2; sources.delete(this); }
    addEventListener() {}
  }
  const RealEventSource = window.EventSource;
  window.EventSource = function (url, opts) {
    return String(url).includes('/api/') ? new DemoEventSource(url) : new RealEventSource(url, opts);
  };

  // ── Downloads (simulated) ───────────────────────────────────────────────

  const jobs = new Map();
  let jobId = 100;
  const QUALITY = [
    { tier: 'original', lossless: true, label: 'Original FLAC', preview: false },
    { tier: 'original', lossless: true, label: 'Original WAV', preview: false },
    { tier: 'premium', lossless: false, label: 'AAC 256k · Go+', preview: false },
    { tier: 'standard', lossless: false, label: 'MP3 128k', preview: false },
  ];
  const history = tracks.map((t, i) => ({
    time: now() - (i + 1) * 5400, url: `https://soundcloud.com/demo/${encodeURIComponent(t.title)}`,
    path: t.path, title: t.title, artist: t.artist, quality: QUALITY[i % 3], thumbnail: t.cover,
    bpm: t.bpm, key: t.key, camelot: t.camelot,
  }));

  function newJob(fields) {
    const job = {
      url: '', title: '', uploader: '', playlist: null, index: null, id: ++jobId, status: 'queued',
      progress: 0, speed: null, eta: null, artist: '', thumbnail: null, quality: null, bpm: null, key: null,
      camelot: null, origin: null, path: null, error: null, warnings: [], ...fields,
    };
    jobs.set(job.id, job);
    return job;
  }
  const publish = (job) => emit('downloads.job', clone(job));

  async function runJob(job, { loop = false } = {}) {
    await sleep(900);
    while (true) {
      if (job.status === 'cancelled') return;
      job.status = 'downloading';
      for (let p = 0; p <= 1.0001; p += 0.04) {
        if (job.status !== 'downloading') return;
        job.progress = Math.min(p, 1); job.speed = 900000 + Math.random() * 1600000;
        publish(job);
        await sleep(160);
      }
      job.status = 'tagging'; job.speed = null; publish(job);
      await sleep(900);
      const t = trackOf(job.url);
      Object.assign(job, { status: 'done', progress: 1, bpm: t.bpm, key: t.key, camelot: t.camelot,
        quality: job.quality || QUALITY[hash(job.url) % QUALITY.length] });
      publish(job);
      if (!loop) return;
      await sleep(6000);
      Object.assign(job, { status: 'queued', progress: 0, bpm: null, key: null, camelot: null, quality: null });
      publish(job);
      await sleep(1500);
    }
  }

  // A queue that is alive from the start.
  tracks.slice(0, 3).forEach((t, i) => newJob({
    url: `https://soundcloud.com/demo/${i}`, title: t.title, artist: t.artist, uploader: t.artist,
    thumbnail: t.cover, status: 'done', progress: 1, quality: QUALITY[i], bpm: t.bpm, key: t.key,
    camelot: t.camelot, path: null,
  }));
  const looping = newJob({ url: 'https://soundcloud.com/demo/en-bucle', title: 'Fábrica de luz (extended)',
    artist: 'Nadia Ferro', uploader: 'Nadia Ferro', thumbnail: tracks[4].cover, playlist: 'Directo en el sótano' });
  setTimeout(() => runJob(looping, { loop: true }), 1200);

  async function addDownloads(text) {
    const urls = (String(text).match(/https?:\/\/\S+/g) || []);
    if (!urls.length) return { accepted: 0 };
    note('Demo: simula la descarga, no baja ni guarda nada.');
    for (const url of urls) {
      (async () => {
        emit('downloads.resolving', { url, active: true });
        await sleep(1100);
        const t = trackOf(url);
        emit('downloads.resolving', { url, active: false, count: 1, title: slug(url) });
        const job = newJob({ url, title: slug(url), artist: t.artist, uploader: t.artist, thumbnail: t.cover });
        publish(job);
        runJob(job);
      })();
    }
    return { accepted: urls.length };
  }

  // ── Subscriptions (simulated) ───────────────────────────────────────────

  const subs = new Map();
  function addSub(url, interval_hours = 6, title = null, checked = true) {
    const id = Math.random().toString(16).slice(2, 10);
    const s = { id, url, title: title || url, interval_hours, enabled: true, created: now(), last_check: null,
      last_result: null, total_new: 0, checking: false, next_check: null };
    if (checked) { s.last_check = now() - 2400; s.last_result = { new: 2, known: 41 }; s.total_new = 17; }
    s.next_check = (s.last_check || now()) + interval_hours * 3600;
    subs.set(id, s);
    return s;
  }
  addSub('https://soundcloud.com/demo/likes', 6, 'Mis likes');
  addSub('https://soundcloud.com/sala-oscura-demo', 24, 'Sala Oscura · perfil');
  state.plugins.subscriptions = { get items() { return [...subs.values()].map(clone); } };
  state.plugins.downloads = { get jobs() { return [...jobs.values()].map(clone); } };

  async function checkSub(s) {
    s.checking = true; emit('subscriptions.changed', clone(s));
    await sleep(2200);
    const fresh = hash(s.url + Date.now()) % 3;
    Object.assign(s, { checking: false, last_check: now(), last_result: { new: fresh, known: 41 },
      total_new: s.total_new + fresh, next_check: now() + s.interval_hours * 3600 });
    if (!s.title || s.title === s.url) s.title = slug(s.url);
    emit('subscriptions.changed', clone(s));
  }

  // ── Search results ──────────────────────────────────────────────────────

  function search(q) {
    const words = ['Sótano', 'Neón', 'Turno', 'Andén', 'Sirena', 'Polígono', 'Asfalto', 'Ruido'];
    return Array.from({ length: 8 }, (_, i) => {
      const t = tracks[(hash(q) + i) % tracks.length];
      const title = `${q.trim().slice(0, 40)} · ${words[(hash(q) + i * 3) % words.length]}`;
      return { url: `https://soundcloud.com/demo/${encodeURIComponent(title)}`, title, uploader: t.artist,
        duration: 300 + (hash(title) % 240), thumbnail: t.cover };
    });
  }

  // ── Convert (simulated) ─────────────────────────────────────────────────

  let batch = 0;
  async function runConvert(b, files, fmt) {
    for (let i = 0; i < files.length; i++) {
      emit('convert.progress', { batch: b, index: i, status: 'running' });
      await sleep(900);
      const dest = files[i].replace(/\.[^./]+$/, '.' + fmt);
      emit('convert.progress', { batch: b, index: i, status: 'done', dest, note: 'Demo: no se ha escrito ningún archivo.' });
    }
    emit('convert.progress', { batch: b, status: 'finished' });
  }

  // ── Routes ──────────────────────────────────────────────────────────────

  const ok = (body, status = 200) => new Response(JSON.stringify(body ?? null), {
    status, headers: { 'Content-Type': 'application/json' } });
  const fail = (status, error) => ok({ error }, status);

  async function route(method, path, params, body) {
    let m;
    switch (`${method} ${path}`) {
      case 'GET /api/session': return ok(D.session);
      case 'GET /api/state': return ok(clone({ ...state, plugins: { ...state.plugins,
        downloads: { jobs: state.plugins.downloads.jobs }, subscriptions: { items: state.plugins.subscriptions.items } } }));
      case 'PATCH /api/settings':
        if ('download_dir' in body) return fail(403, 'Demo: la carpeta de música la fija el servidor.');
        Object.assign(state.settings, body);
        note('Demo: el ajuste solo dura mientras tengas la página abierta.');
        emit('settings', clone(state.settings));
        return ok(clone(state.settings));
      case 'GET /api/library': return ok(clone(library));
      case 'DELETE /api/library':
        library.items = library.items.filter((x) => x.path !== params.get('path'));
        note(); return ok({});
      case 'GET /api/playable': return ok({ url: trackOf(params.get('path')).media });
      case 'POST /api/upload': {
        const f = body instanceof FormData ? body.get('file') : null;
        note('Demo: el archivo no sale de tu navegador; se analiza un tema de ejemplo.');
        return ok({ path: `/subidas/demo/${f ? f.name : 'audio.wav'}`, name: f ? f.name : 'audio.wav', size: f ? f.size : 0 });
      }
      case 'POST /api/analysis/analyze': {
        const known = tracks.find((t) => t.path === body.path);
        const r = await loadJson((known || tracks[0]).analysis);
        if (!known) { note('Demo: se muestra el análisis de un tema de ejemplo.'); r.info.name = body.path.split('/').pop(); }
        return ok(r);
      }
      case 'POST /api/analysis/null-test': {
        const r = await loadJson(D.nulltest.report);
        if (body.a !== D.nulltest.a || body.b !== D.nulltest.b) note('Demo: se muestra un null test de ejemplo (FLAC contra su MP3 128k).');
        return ok(r);
      }
      case 'POST /api/convert': {
        const b = ++batch;
        note(); runConvert(b, body.files || [], body.format || 'wav');
        return ok({ batch: b });
      }
      case 'GET /api/search': return ok(search(params.get('q') || ''));
      case 'POST /api/preview': {
        const t = trackOf(body.text);
        note('Demo: pre-escucha de un tema de ejemplo.');
        return ok({ id: 'demo', url: t.media, title: slug(body.text), uploader: t.artist, duration: 8, thumbnail: t.cover, snippet: false });
      }
      case 'POST /api/downloads': return ok(await addDownloads(body.text || ''));
      case 'POST /api/downloads/clear':
        for (const [id, j] of jobs) if (['done', 'skipped', 'error', 'cancelled'].includes(j.status) && j !== looping) jobs.delete(id);
        emit('downloads.jobs', { jobs: state.plugins.downloads.jobs }); return ok({});
      case 'POST /api/downloads/cancel-all':
        for (const j of jobs.values()) if (['queued', 'downloading'].includes(j.status)) { j.status = 'cancelled'; publish(j); }
        return ok({});
      case 'GET /api/downloads/history': return ok(clone(history));
      case 'GET /api/subscriptions': return ok(state.plugins.subscriptions.items);
      case 'POST /api/subscriptions': {
        const s = addSub(body.url, body.interval_hours || 6, null, false);
        note(); checkSub(s); return ok(clone(s));
      }
      case 'POST /api/soundcloud/token':
        note(); state.soundcloud = { logged_in: true, username: 'demo' }; return ok(state.soundcloud);
      case 'DELETE /api/soundcloud/token':
        note(); state.soundcloud = { logged_in: false, username: null }; return ok(state.soundcloud);
      case 'POST /api/update/check': return ok({ ...clone(state.update), info: { latest: state.version, newer: false } });
      case 'POST /api/update/skip': return ok(clone(state.update));
      case 'POST /api/ytdlp/update': return ok({ updated: false, version: state.ytdlp_version });
      case 'POST /api/logout': note(); return ok({});
    }
    if ((m = path.match(/^\/api\/downloads\/(\d+)\/(cancel|retry)$/)) && method === 'POST') {
      const j = jobs.get(Number(m[1]));
      if (!j) return fail(404, 'No existe.');
      if (m[2] === 'cancel') { j.status = 'cancelled'; publish(j); } else { j.status = 'queued'; j.progress = 0; publish(j); runJob(j); }
      return ok({});
    }
    if ((m = path.match(/^\/api\/subscriptions\/(\w+)(\/check)?$/))) {
      const s = subs.get(m[1]);
      if (!s) return fail(404, 'No existe.');
      if (m[2] && method === 'POST') { checkSub(s); return ok(clone(s)); }
      if (method === 'PATCH') {
        if ('enabled' in body) s.enabled = !!body.enabled;
        if ('interval_hours' in body) s.interval_hours = Number(body.interval_hours);
        s.next_check = s.enabled ? (s.last_check || now()) + s.interval_hours * 3600 : null;
        note(); emit('subscriptions.changed', clone(s)); return ok(clone(s));
      }
      if (method === 'DELETE') { subs.delete(s.id); note(); emit('subscriptions.removed', { id: s.id }); return ok({}); }
    }
    return fail(404, 'Demo: esto solo funciona en la app.');
  }

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const at = url.pathname.indexOf('/api/');
    if (url.origin !== location.origin || at < 0) return realFetch(input, init);
    const method = (init.method || 'GET').toUpperCase();
    let body = init.body;
    if (typeof body === 'string') { try { body = JSON.parse(body); } catch (_) { /* keep text */ } }
    await sleep(60 + Math.random() * 120);  // feels like a server
    return route(method, url.pathname.slice(at), url.searchParams, body ?? {});
  };

  // ── URLs the page uses outside fetch: <audio src>, covers, file links ────

  const mediaFor = (url) => {
    const u = new URL(url, location.href);
    if (u.pathname.endsWith('/api/stream') || u.pathname.endsWith('/api/files/download')) return trackOf(u.searchParams.get('path')).media;
    return null;
  };
  const srcDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
  Object.defineProperty(HTMLMediaElement.prototype, 'src', {
    configurable: true,
    get() { return srcDesc.get.call(this); },
    set(v) { srcDesc.set.call(this, (String(v).includes('/api/') && mediaFor(v)) || v); },
  });

  const COVER = /url\("?([^")]*\/api\/library\/cover\?path=([^")]*))"?\)/;
  function fixCover(el) {
    const bg = el.style && el.style.backgroundImage;
    const m = bg && bg.match(COVER);
    if (m) el.style.backgroundImage = `url("${trackOf(decodeURIComponent(m[2])).cover}")`;
  }
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'attributes') fixCover(r.target);
      for (const n of r.addedNodes || []) {
        if (n.nodeType !== 1) continue;
        fixCover(n);
        n.querySelectorAll('[style*="/api/"]').forEach(fixCover);
      }
    }
  }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['style'] });

  // "Show in folder" in a browser downloads the file: not in the demo.
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('a[href*="/api/"]');
    if (a) { e.preventDefault(); note('Demo: aquí bajarías el archivo de tu servidor.'); }
  }, true);
})();
