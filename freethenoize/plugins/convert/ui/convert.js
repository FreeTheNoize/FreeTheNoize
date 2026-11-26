/* Plugin convert: batch conversion keeping tags and artwork.
 * The smallest complete view; copy it to start a new plugin. */
(function () {
  const { $, h, POST, toast, iconBtn, fileIcon, baseName, bindSegmented, isServer, pickAudio, pickFolder, reveal } = FTN;

  const cv = { files: [], fmt: 'wav', dest: null, status: {}, batch: null };

  function render() {
    const list = $('#cv-list');
    list.textContent = '';
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
          !st.status ? iconBtn('x', 'Quitar', () => { cv.files.splice(i, 1); render(); }) : null)));
    });
    $('#cv-empty').hidden = cv.files.length > 0;
    $('#cv-run').disabled = !cv.files.length;
  }

  function addFiles(paths) {
    for (const f of paths) if (!cv.files.includes(f)) cv.files.push(f);
    cv.status = {};
    FTN.show('convert');
    render();
  }

  async function run() {
    cv.status = {};
    $('#cv-run').disabled = true;
    const r = await POST('/api/convert', {
      files: cv.files, format: cv.fmt,
      out_dir: !isServer() && !$('#cv-same').checked ? cv.dest : null,
      normalize_lufs: $('#cv-norm').checked ? Number($('#cv-lufs').value) : null,
    }).catch((e) => { $('#cv-run').disabled = false; throw e; });
    cv.batch = r.batch;
    render();
  }

  FTN.registerView({
    id: 'convert',
    group: 'laboratorio',
    order: 80,
    title: 'Convertir',
    heading: 'Transcodifica',
    intro: 'Conserva etiquetas y carátula. Pasar de un formato con pérdida a WAV o AIFF no mejora el sonido.',
    actions: [{ id: 'cv-add', label: 'Añadir archivos' }],
    html: `
      <div class="list" id="cv-list"></div>
      <div class="empty" id="cv-empty"><div class="empty-glyph">→</div><p>Añade archivos (o arrástralos aquí).</p></div>
      <div class="panel form-row">
        <span class="field-label">formato</span>
        <div class="segmented" id="cv-format"></div>
        <label class="check"><input type="checkbox" id="cv-norm"> normalizar a</label>
        <select class="select" id="cv-lufs" disabled>
          <option value="-14">−14 LUFS · streaming</option>
          <option value="-9">−9 LUFS · club</option>
          <option value="-8">−8 LUFS · fuerte</option>
          <option value="-16">−16 LUFS · podcast</option>
          <option value="-23">−23 LUFS · EBU R128</option>
        </select>
        <div class="spacer"></div>
        <label class="check desktop-only"><input type="checkbox" id="cv-same" checked> misma carpeta</label>
        <button class="btn small desktop-only" id="cv-dest" disabled>Carpeta…</button>
        <button class="btn primary" id="cv-run">Convertir</button>
      </div>`,
    init(el) {
      $('#cv-add', el).addEventListener('click', async () => addFiles(await pickAudio(true)));
      $('#cv-same', el).addEventListener('change', (e) => { $('#cv-dest').disabled = e.target.checked; });
      $('#cv-norm', el).addEventListener('change', (e) => { $('#cv-lufs').disabled = !e.target.checked; });
      $('#cv-dest', el).addEventListener('click', async () => {
        const d = await pickFolder('');
        if (d) { cv.dest = d; $('#cv-dest').textContent = baseName(d) || d; }
      });
      $('#cv-run', el).addEventListener('click', run);
      bindSegmented($('#cv-format', el), (v) => { cv.fmt = v; });
      render();
    },
    onFiles: addFiles,
  });

  // The formats come from the server (plugin state), once.
  FTN.on('state', (s) => {
    const seg = $('#cv-format');
    if (seg.childElementCount) return;
    for (const [k, label] of Object.entries(s.plugins.convert.formats)) {
      seg.append(h('button', { 'data-value': k, class: k === cv.fmt ? 'on' : null }, label));
    }
  });

  FTN.on('convert.progress', (p) => {
    if (p.batch !== cv.batch) return;
    if (p.status === 'finished') { $('#cv-run').disabled = false; toast('Conversión terminada.', 'ok'); return; }
    cv.status[p.index] = p;
    render();
  });
})();
