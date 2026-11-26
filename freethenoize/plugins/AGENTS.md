# Complementos

Cada carpeta es un complemento. Para uno nuevo: `python tools/new_plugin.py <id> --title "Nombre"` (crea todo
y lo añade a `BUILTIN` en `__init__.py`).

```
<id>/__init__.py   PLUGIN = Plugin(id, title, description, service, api, settings, limits, requires…)
<id>/service.py    la lógica: class XService: __init__(self, ctx); opcional start/stop/state()
<id>/api.py        routes(svc, ctx) -> APIRouter, montado en /api/<id>; rutas de archivo = LibraryPath
<id>/ui/<id>.js    FTN.registerView / FTN.registerSettings; JS plano, sin build
<id>/ui/<id>.css   opcional; selectores con prefijo <id>- o .view[data-view=<id>]
```

- Del kernel, solo `ctx` (ver la tabla de `Ctx` en [ARCHITECTURE.md](../../ARCHITECTURE.md#lo-que-da-el-kernel-ctx)).
  Bibliotecas permitidas: `freethenoize.audio`, `files`, `ytdlp`, `ffmpeg`.
- **Nunca** importes otro complemento: `requires` + `ctx.require`. Para la página, `FTN.provide`/`FTN.use`,
  y funciona aunque el otro esté apagado (`use` devuelve `undefined`).
- Errores: lanza `ValueError` (400), `PermissionError` (403), `FileNotFoundError` (404); el kernel responde `{"error"}`.
- Ajustes nuevos: valor por defecto en `settings={…}`; los números con `limits`; lo que no deba tocarse en modo
  servicio, en `server_locked`.
- Tests en `tests/test_<id>.py`; `tests/test_plugins.py` ya comprueba que se puede desactivar y que respeta prefijos.

Comprueba con `python tools/check_architecture.py` y `pytest`. Reglas completas: [AGENTS.md](../../AGENTS.md).
