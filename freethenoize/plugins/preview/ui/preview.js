/* Plugin preview: no view of its own. Provides 'preview' → FTN.use('preview')(url, button). */
(function () {
  const { POST, toast, player } = FTN;

  async function preview(url, btn) {
    if (btn) btn.classList.add('busy');
    const t = toast('Cargando pre-escucha…', '', 0);
    try {
      const p = await POST('/api/preview', { text: url });
      player.play({
        stream: { url: p.url, duration: p.duration || 0 }, title: p.title,
        sub: [p.uploader, p.snippet ? 'solo fragmento de 30 s' : 'pre-escucha'].filter(Boolean).join(' · '),
        cover: p.thumbnail,
      });
    } catch (_) { /* POST already showed the error */ }
    finally { t.remove(); if (btn) btn.classList.remove('busy'); }
  }

  FTN.provide('preview', preview);
})();
