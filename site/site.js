/* FreeTheNoize website: theme switch (shared with the demo) and copy buttons. */
(function () {
  const root = document.documentElement;
  const systemLight = window.matchMedia('(prefers-color-scheme: light)');
  const current = () => root.dataset.theme || (systemLight.matches ? 'light' : 'dark');

  function apply(theme, save) {
    root.dataset.theme = theme;
    document.querySelector('meta[name=theme-color]').setAttribute('content', theme === 'light' ? '#e8e6df' : '#0a0a0a');
    for (const img of document.querySelectorAll('img.themed')) img.src = img.dataset[theme];
    if (save) { try { localStorage.setItem('ftn.theme', theme); } catch (_) { /* private mode */ } }
  }
  apply(current(), false);
  systemLight.addEventListener('change', () => { let saved = null; try { saved = localStorage.getItem('ftn.theme'); } catch (_) {} if (!saved) apply(current(), false); });
  document.getElementById('theme').addEventListener('click', () => apply(current() === 'light' ? 'dark' : 'light', true));

  for (const btn of document.querySelectorAll('.copy')) {
    btn.addEventListener('click', async () => {
      const text = document.getElementById(btn.dataset.copy).textContent;
      try { await navigator.clipboard.writeText(text); btn.textContent = 'Copiado'; }
      catch (_) { btn.textContent = 'Selecciónalo'; }
      setTimeout(() => { btn.textContent = 'Copiar'; }, 1600);
    });
  }
})();
