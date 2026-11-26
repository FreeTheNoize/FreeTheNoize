# Esto es el kernel

Los ficheros de esta carpeta (fuera de `plugins/`) y `ui/index.html`, `ui/kernel.js`, `ui/style.css` son el **kernel**:
cargan complementos y les dan ajustes, eventos, rutas seguras, audio reproducible, la sesión de SoundCloud,
yt-dlp y actualizaciones. **No añadas funciones aquí: crea un complemento** (`python tools/new_plugin.py <id>`).

- El kernel nunca importa ni nombra un complemento; la única lista es `plugins/__init__.py` (`BUILTIN`).
- `audio/`, `files.py`, `ytdlp.py`, `ffmpeg.py` son bibliotecas compartidas sin estado: se pueden ampliar si
  sirven a varios complementos.
- Cambiar `plugin.py` (`Plugin`, `Ctx`, `LibraryPath`) o la API `window.FTN` es cambiar el contrato de todos:
  PR aparte, compatible hacia atrás, y actualiza [ARCHITECTURE.md](../ARCHITECTURE.md).
- Seguridad del modo servicio (`web.py`: auth, CSRF, sandbox de rutas) se revisa con lupa.

Reglas y comprobación: [AGENTS.md](../AGENTS.md).
