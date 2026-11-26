/* Plugin downloads: the queue (Descargas), Historial and their settings.
 * Provides: 'links.add' (drop/paste links), 'downloads.add' (other views). */
(function () {
  const { $, h, GET, POST, toast, iconBtn, fileIcon, badge, camChip, bpmChip, art, fmtBytes, player, reveal, openUrl, use } = FTN;

  const jobs = new Map();
  const resolving = new Map();

  // ── Queue ──────────────────────────────────────────────────────────────

  async function submitUrls(text) {
    const input = $('#url-input');
    const value = typeof text === 'string' ? text : input.value;
    const res = await POST('/api/downloads', { text: value });
    if (!res.accepted) { toast('No he encontrado ningún enlace.', 'error'); return false; }
    if (typeof text !== 'string') { input.value = ''; input.style.height = 'auto'; }
    return true;
  }

  FTN.provide('downloads.add', submitUrls);
  FTN.provide('links.add', (text) => { FTN.show('downloads'); submitUrls(text); });

  function renderResolving() {
    const box = $('#resolving');
    box.textContent = '';
    for (const [url, r] of resolving) {
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
    if (job.status === 'done' && job.path) actions.append(...fileActions(job));
    return h('div', { class: `row-item status-${job.status}`, 'data-job': job.id }, art(job.thumbnail), meta, actions);
  }

  // Play / spectrum / folder for a finished download (also used by Historial).
  function fileActions(it) {
    const analyse = use('analysis.open');
    return [
      iconBtn('play', 'Escuchar', () => player.play({ path: it.path, title: it.title, sub: it.artist, cover: it.thumbnail })),
      analyse ? iconBtn('wave', 'Espectro', () => analyse(it.path)) : null,
      iconBtn(...fileIcon(), () => reveal(it.path)),
    ];
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
    list.textContent = '';
    for (const job of jobs.values()) list.append(jobRow(job));
    renderCounts();
  }

  function counts() {
    const all = [...jobs.values()];
    return {
      total: all.length,
      active: all.filter((j) => ['queued', 'downloading', 'tagging'].includes(j.status)).length,
      done: all.filter((j) => j.status === 'done').length,
      failed: all.filter((j) => j.status === 'error').length,
    };
  }

  function renderCounts() {
    const c = counts();
    $('#jobs-empty').hidden = c.total > 0;
    $('#job-counts').textContent = c.total
      ? [`${c.total} total`, c.active && `${c.active} pendientes`, c.done && `${c.done} hechas`, c.failed && `${c.failed} con error`].filter(Boolean).join(' / ')
      : '';
    FTN.setBadge('downloads', c.active);
    FTN.renderTicker();
  }

  FTN.addTicker(() => {
    const c = counts();
    return [['COLA', c.active ? `${c.active} activas` : 'en calma'], ['HECHAS', String(c.done)]];
  });

  function renderLoginNotice() {
    const n = $('#login-notice');
    if (n) n.hidden = FTN.state.soundcloud.logged_in;
  }

  FTN.registerView({
    id: 'downloads',
    group: 'fuente',
    order: 10,
    title: 'Descargas',
    heading: 'Libera el ruido',
    intro: 'Pega enlaces de SoundCloud (tema, playlist, álbum, perfil, likes…) o YouTube. Primero se intenta siempre el archivo original.',
    html: `
      <div class="drop" id="drop-zone">
        <span class="prompt mono">&gt;</span>
        <textarea id="url-input" rows="1" placeholder="https://soundcloud.com/…" spellcheck="false" autocomplete="off"></textarea>
        <button class="btn ghost" id="preview-btn" title="Escuchar el tema antes de descargarlo">Escuchar</button>
        <button class="btn primary" id="download-btn">Descargar</button>
      </div>
      <div class="chips" id="resolving"></div>
      <div class="hazard" id="login-notice" hidden>
        <div class="hazard-body">
          <strong>Sin sesión de SoundCloud.</strong>
          Solo MP3 128k. Inicia sesión para los originales (cuando el artista los permite) y, con Go+, el AAC 256.
        </div>
        <button class="btn" id="login-notice-btn">Conectar</button>
      </div>
      <div class="toolbar">
        <div class="counts mono" id="job-counts"></div>
        <div class="spacer"></div>
        <button class="btn ghost small" id="clear-finished">Limpiar</button>
        <button class="btn ghost small danger" id="cancel-all">Cancelar todo</button>
      </div>
      <div class="list" id="job-list"></div>
      <div class="empty" id="jobs-empty">
        <div class="empty-glyph">[ ]</div>
        <p>Cola vacía. Pega un enlace o arrástralo a la ventana.</p>
      </div>`,
    init(el) {

      const input = $('#url-input', el);
      input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = input.scrollHeight + 'px';
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitUrls(); }
      });
      $('#download-btn', el).addEventListener('click', () => submitUrls());
      $('#clear-finished', el).addEventListener('click', () => POST('/api/downloads/clear'));
      $('#cancel-all', el).addEventListener('click', () => POST('/api/downloads/cancel-all'));
      $('#login-notice-btn', el).addEventListener('click', () => FTN.soundcloudLogin());
      const preview = use('preview');
      const pbtn = $('#preview-btn', el);
      pbtn.hidden = !preview;
      pbtn.addEventListener('click', (e) => {
        const url = (input.value.match(/https?:\/\/\S+/) || [])[0];
        if (!url) { toast('Pega primero el enlace de un tema.', 'error'); return; }
        preview(url, e.currentTarget);
      });
    },
  });

  // ── Historial ──────────────────────────────────────────────────────────

  async function loadHistory() {
    const items = await GET('/api/downloads/history');
    const list = $('#history-list');
    list.textContent = '';
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
          ...fileActions(it),
          iconBtn('link', 'Abrir el original', () => openUrl(it.url)))));
    }
  }

  FTN.registerView({
    id: 'history',
    group: 'archivo',
    order: 50,
    title: 'Historial',
    heading: 'Registro',
    html: `
      <div class="list" id="history-list"></div>
      <div class="empty" id="history-empty"><div class="empty-glyph">--:--</div><p>Aún no has descargado nada.</p></div>`,
    onShow: loadHistory,
  });

  // ── Settings ───────────────────────────────────────────────────────────

  const SAMPLE = { artist: 'Artista', title: 'Título', uploader: 'usuario', playlist: 'Mi playlist', index: '01', date: '2026-01-31', id: '123456' };
  function renderTemplatePreview(value) {
    const t = value ?? FTN.state.settings['downloads.filename_template'] ?? '';
    $('#template-preview').textContent = '→ ' + t.replace(/\{(\w+)\}/g, (_, k) => SAMPLE[k] ?? '') + '.wav';
  }

  FTN.registerSettings({
    id: 'downloads',
    order: 10,
    title: 'descargas',
    html: `
      <div class="group-row">
        <div class="label">Nombre de archivo<small>Campos: {artist} {title} {uploader} {playlist} {index} {date} {id}</small></div>
        <div class="controls col">
          <input class="text" id="set-template" data-setting="downloads.filename_template">
          <small class="mono dim" id="template-preview"></small>
        </div>
      </div>
      <div class="group-row"><div class="label">Subcarpeta por playlist</div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.playlist_subfolder"></div></div>
      <div class="group-row"><div class="label">Descargas simultáneas</div><div class="controls"><input type="number" class="text narrow" min="1" max="8" data-setting="downloads.concurrency"></div></div>
      <div class="group-row"><div class="label">No volver a bajar lo que ya tengo</div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.skip_downloaded"></div></div>`,
    init(el) {
      // Echo while typing (it is saved on change), so a settings event does not undo it.
      $('#set-template', el).addEventListener('input', (e) => {
        FTN.state.settings['downloads.filename_template'] = e.target.value;
        renderTemplatePreview();
      });
    },
  });

  FTN.registerSettings({
    id: 'downloads-meta',
    order: 11,
    title: 'metadatos',
    html: `
      <div class="group-row"><div class="label">Limpiar títulos<small>Quita "[FREE DL]", "(Out Now)", "Premiere"…</small></div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.clean_titles"></div></div>
      <div class="group-row"><div class="label">Separar "Artista - Título"<small>Si no, el artista es quien sube el tema.</small></div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.split_artist_title"></div></div>
      <div class="group-row"><div class="label">Detectar BPM y tonalidad<small>Se escriben en las etiquetas (Rekordbox, Traktor, Serato los leen).</small></div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.detect_bpm_key"></div></div>
      <div class="group-row"><div class="label">Incrustar carátula</div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.embed_artwork"></div></div>
      <div class="group-row">
        <div class="label">Tamaño máximo de la carátula<small>Las originales pueden pesar 10 MB; el software de DJ lo agradece.</small></div>
        <div class="controls">
          <select class="select" data-setting="downloads.artwork_max_px">
            <option value="500">500 px</option><option value="1000">1000 px</option>
            <option value="1400">1400 px</option><option value="3000">3000 px</option>
          </select>
        </div>
      </div>
      <div class="group-row"><div class="label">Guardar la carátula original aparte</div><div class="controls"><input type="checkbox" class="switch" data-setting="downloads.save_artwork_file"></div></div>`,
  });

  // ── Events ─────────────────────────────────────────────────────────────

  FTN.on('state', (s) => {
    jobs.clear();
    for (const j of s.plugins.downloads.jobs) jobs.set(j.id, j);
    renderAllJobs();
    renderLoginNotice();
    renderTemplatePreview();
  });
  FTN.on('settings', () => renderTemplatePreview());
  FTN.on('soundcloud', renderLoginNotice);
  FTN.on('downloads.job', (p) => { jobs.set(p.id, p); renderJob(p); });
  FTN.on('downloads.jobs', (p) => {
    jobs.clear();
    for (const j of p.jobs) jobs.set(j.id, j);
    renderAllJobs();
  });
  FTN.on('downloads.resolving', (p) => {
    if (p.origin) return; // subscription checks report in their own view
    if (p.active) resolving.set(p.url, {});
    else if (p.error) {
      resolving.set(p.url, { error: p.error });
      setTimeout(() => { resolving.delete(p.url); renderResolving(); }, 8000);
    } else {
      resolving.delete(p.url);
      if (p.count > 1 || p.skipped) toast(`${p.title || 'Colección'}: ${p.count} en cola${p.skipped ? `, ${p.skipped} ya los tenías` : ''}.`, 'ok');
      else if (p.count === 0 && !p.skipped) toast('Ese enlace no contiene ningún tema.', 'error');
    }
    renderResolving();
  });
})();
