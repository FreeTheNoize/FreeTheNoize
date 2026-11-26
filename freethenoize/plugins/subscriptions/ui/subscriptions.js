/* Plugin subscriptions: playlists, likes or profiles checked on a timer. */
(function () {
  const { $, h, POST, PATCH, DEL, toast, iconBtn, openUrl } = FTN;

  const subs = new Map();

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

  function render() {
    const list = $('#sub-list');
    list.textContent = '';
    for (const s of subs.values()) list.append(subRow(s));
    $('#subs-empty').hidden = subs.size > 0;
    FTN.setBadge('subs', subs.size, true);
    FTN.renderTicker();
  }

  FTN.addTicker(() => [['SUSCRIPCIONES', String(subs.size)]]);

  FTN.registerView({
    id: 'subs',
    group: 'fuente',
    order: 30,
    title: 'Suscripciones',
    heading: 'Vigila',
    intro: 'Playlists, likes o perfiles que se revisan solos cada cierto tiempo. Solo se descarga lo nuevo.',
    html: `
      <form class="drop" id="sub-form">
        <span class="prompt mono">+</span>
        <input id="sub-url" type="url" placeholder="https://soundcloud.com/usuario/likes" autocomplete="off" required>
        <select class="select" id="sub-interval" title="Cada cuánto">
          <option value="1">cada 1 h</option>
          <option value="6" selected>cada 6 h</option>
          <option value="12">cada 12 h</option>
          <option value="24">cada día</option>
          <option value="168">cada semana</option>
        </select>
        <button class="btn primary" type="submit">Seguir</button>
      </form>
      <div class="list" id="sub-list"></div>
      <div class="empty" id="subs-empty">
        <div class="empty-glyph">( · )</div>
        <p>No sigues nada todavía. Tus likes son un buen comienzo.</p>
      </div>`,
    init(el) {
      $('#sub-form', el).addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = $('#sub-url').value.trim();
        const s = await POST('/api/subscriptions', { url, interval_hours: Number($('#sub-interval').value) });
        subs.set(s.id, s);
        render();
        $('#sub-url').value = '';
        toast('Suscrito. Primera sincronización en marcha.', 'ok');
      });
      // "hace 5 min" / "en 2 h" go stale: refresh while the view is open.
      setInterval(() => { if (FTN.isShown('subs')) render(); }, 30000);
    },
  });

  FTN.on('state', (s) => {
    subs.clear();
    for (const x of s.plugins.subscriptions.items) subs.set(x.id, x);
    render();
  });
  FTN.on('subscriptions.changed', (p) => { subs.set(p.id, p); render(); });
  FTN.on('subscriptions.removed', (p) => { subs.delete(p.id); render(); });
})();
