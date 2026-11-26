# Web del proyecto

Lo que se publica en GitHub Pages (`.github/workflows/pages.yml`, desde `main`):

- `index.html`, `site.css`, `site.js`, `img/`: la web, estática, sin build ni CDN.
- `demo-src/`: lo que la **demo** añade a la interfaz real (`demo-api.js` responde a `/api/*` en el navegador con datos de
  ejemplo; `demo.css`, el distintivo «Demo»).

```sh
python tools/build_site.py --out _site     # necesita `pip install -e ".[dev]"` y ffmpeg
python -m http.server -d _site 8000        # http://localhost:8000
```

La demo es la página de verdad (`freethenoize/ui` + `ui/` de cada complemento, montada como en `web.py`), y sus datos
salen de la API real: `build_site.py` arranca un kernel en modo servicio con unos temas sintéticos y graba sus
respuestas. Si cambias la API o la interfaz, la demo cambia sola; si se rompe, el workflow falla en la PR.
Las capturas de `img/` se sacan de la demo.
