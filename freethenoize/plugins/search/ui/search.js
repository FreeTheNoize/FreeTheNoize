/* Plugin search: search SoundCloud, pre-listen, open or queue a result. */
(function () {
  const { $, h, GET, q, iconBtn, art, openUrl, fmtTime, loadingBars, use } = FTN;

  async function search(e) {
    e.preventDefault();
    const query = $('#search-input').value.trim();
    if (!query) return;
    const list = $('#search-results');
    list.textContent = '';
    list.append(loadingBars('Excavando…'));
    const results = await GET('/api/search?q=' + q(query)).catch(() => []);
    list.textContent = '';
    if (!results.length) list.append(h('div', { class: 'empty' }, h('p', {}, 'Nada por aquí.')));
    const preview = use('preview');
    const add = use('downloads.add');
    for (const r of results) {
      list.append(h('div', { class: 'row-item' },
        art(r.thumbnail),
        h('div', { class: 'meta' },
          h('div', { class: 'title' }, r.title),
          h('div', { class: 'sub' }, [r.uploader, r.duration && fmtTime(r.duration)].filter(Boolean).join(' · '))),
        h('div', { class: 'actions' },
          preview ? iconBtn('play', 'Pre-escuchar', (ev) => preview(r.url, ev.currentTarget)) : null,
          iconBtn('link', 'Abrir en SoundCloud', () => openUrl(r.url)),
          add ? h('button', { class: 'btn small primary', onclick: async (ev) => {
            if (await add(r.url)) { ev.target.textContent = 'En cola'; ev.target.disabled = true; }
          } }, 'Descargar') : null)));
    }
  }

  FTN.registerView({
    id: 'search',
    group: 'fuente',
    order: 20,
    title: 'Buscar',
    heading: 'Excava',
    intro: 'Busca en SoundCloud y manda lo que quieras a la cola.',
    html: `
      <form class="drop" id="search-form">
        <span class="prompt mono">?</span>
        <input id="search-input" type="search" placeholder="artista, tema, sello…" autocomplete="off">
        <button class="btn primary" type="submit">Buscar</button>
      </form>
      <div class="list" id="search-results"></div>`,
    init(el) {
      $('#search-form', el).addEventListener('submit', search);
    },
  });
})();
