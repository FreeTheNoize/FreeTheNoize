/* Plugin library: the music folder as a sortable, filterable table. */
(function () {
  const { $, $$, h, GET, DEL, q, toast, iconBtn, fileIcon, camChip, camelotFromKey, num, fmtTime, player, reveal, use } = FTN;

  let items = [];
  let loading = false;
  let timer = null;

  async function load() {
    if (loading) return;
    loading = true;
    $('#lib-count').textContent = 'leyendo…';
    try {
      const r = await GET('/api/library');
      items = r.items;
      $('#lib-root').textContent = r.root;
      render();
    } finally { loading = false; }
  }

  // Reload a bit later, and only if someone is looking.
  function loadSoon() {
    clearTimeout(timer);
    timer = setTimeout(() => { if (FTN.isShown('library')) load(); }, 1500);
  }

  function render() {
    const f = $('#lib-filter').value.trim().toLowerCase();
    const sort = $('#lib-sort').value;
    let shown = items;
    if (f) {
      shown = shown.filter((it) => {
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
    shown = [...shown].sort(cmp);
    const analyse = use('analysis.open');
    const compare = use('compare.add');
    const body = $('#lib-body');
    body.textContent = '';
    const frag = document.createDocumentFragment();
    for (const it of shown.slice(0, 1500)) {
      const fmt = [it.ext.toUpperCase(), it.bits && `${it.bits}b`, it.sample_rate && `${num(it.sample_rate / 1000, 1).replace(/\.0$/, '')}k`, !it.bits && it.bitrate && `${it.bitrate}k`].filter(Boolean).join(' ');
      const coverUrl = '/api/library/cover?path=' + q(it.path);
      const cover = h('div', { class: 'art', style: `background-image:url("${coverUrl}")`, title: 'Escuchar',
        onclick: () => player.play({ path: it.path, title: it.title, sub: it.artist, cover: coverUrl }) });
      frag.append(h('tr', { 'data-path': it.path, class: player.current === it.path ? 'playing' : null },
        h('td', {}, cover),
        h('td', { class: 'tt' }, h('div', { class: 'title' }, it.title), h('div', { class: 'sub' }, [it.artist, it.album].filter(Boolean).join(' · '))),
        h('td', { class: 'num' }, it.bpm ? Math.round(it.bpm * 10) / 10 : '—'),
        h('td', {}, camChip(null, it.key)),
        h('td', { class: 'fmt' }, fmt),
        h('td', { class: 'num' }, it.duration ? fmtTime(it.duration) : '—'),
        h('td', { class: 'act' },
          analyse ? iconBtn('wave', 'Espectro', () => analyse(it.path)) : null,
          compare ? iconBtn('ab', 'Mandar al comparador', () => compare(it.path)) : null,
          iconBtn(...fileIcon(), () => reveal(it.path)),
          iconBtn('trash', 'Borrar', async () => {
            if (!confirm(`¿Borrar ${it.name}? No se puede deshacer.`)) return;
            await DEL('/api/library?path=' + q(it.path));
            items = items.filter((x) => x.path !== it.path);
            render();
          }))));
    }
    body.append(frag);
    $('#lib-empty').hidden = items.length > 0;
    $('#lib-count').textContent = `${shown.length}${shown.length !== items.length ? ' / ' + items.length : ''} temas`;
  }

  FTN.registerView({
    id: 'library',
    group: 'archivo',
    order: 40,
    title: 'Biblioteca',
    heading: 'Archivo',
    intro: '',
    introId: 'lib-root',
    introClass: 'mono dim',
    actions: [{ id: 'lib-refresh', label: 'Releer' }],
    html: `
      <div class="filters">
        <input class="text grow" id="lib-filter" type="search" placeholder="filtrar: título, artista, 8A, 128…" autocomplete="off">
        <select class="select" id="lib-sort">
          <option value="mtime">Recientes</option>
          <option value="title">Título</option>
          <option value="artist">Artista</option>
          <option value="bpm">BPM</option>
          <option value="key">Tonalidad (Camelot)</option>
        </select>
        <span class="counts mono" id="lib-count"></span>
      </div>
      <div class="table-wrap">
        <table class="lib" id="lib-table">
          <thead><tr><th></th><th>Tema</th><th class="num">BPM</th><th>Key</th><th>Formato</th><th class="num">Dur.</th><th></th></tr></thead>
          <tbody id="lib-body"></tbody>
        </table>
      </div>
      <div class="empty" id="lib-empty" hidden><div class="empty-glyph">∅</div><p>Aquí aparecerá lo que descargues.</p></div>`,
    init(el) {
      $('#lib-filter').addEventListener('input', render);
      $('#lib-sort').addEventListener('change', render);
      $('#lib-refresh').addEventListener('click', load);
    },
    onShow: load,
  });

  FTN.on('player', ({ path }) => $$('#lib-body tr').forEach((tr) => tr.classList.toggle('playing', tr.dataset.path === path)));
  FTN.on('library.changed', loadSoon);
  FTN.on('downloads.job', (p) => { if (p.status === 'done' && items.length) loadSoon(); });
})();
