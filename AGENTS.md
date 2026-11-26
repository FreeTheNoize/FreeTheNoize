# FreeTheNoize: instrucciones para agentes

Esto es un **kernel pequeño con complementos**. Cada función (descargas, biblioteca, espectro, conversor…) es una
carpeta en `freethenoize/plugins/<id>/`. Antes de tocar nada, lee [ARCHITECTURE.md](ARCHITECTURE.md).

## Reglas (las comprueba `tools/check_architecture.py`)

1. **Una función nueva = un complemento nuevo.** Genéralo con `python tools/new_plugin.py <id> --title "Nombre"`;
   no añadas funciones al kernel (`freethenoize/*.py`, `freethenoize/ui/`).
2. **Un complemento no importa otro.** Declara `requires=("otro",)` y usa `ctx.require("otro")`; en la página,
   `FTN.provide` / `FTN.use`.
3. **El kernel no nombra complementos** (ni imports ni `"downloads"`). Si falta algo, se añade genérico a `Ctx`/`FTN` en otra PR.
4. **Del kernel solo se usa `ctx`**: ajustes `ctx.settings["clave"]` (sin prefijo), eventos `ctx.emit("evento")`
   (el kernel añade `<id>.`), ficheros en `ctx.data_dir` / `ctx.cache_dir` / `ctx.data_file()`.
5. **Rutas que llegan a la API: `LibraryPath`.** Nunca `str`/`Path` para un archivo de la página.
6. **Todo lo tuyo con tu id**: `/api/<id>/…`, eventos `<id>.…`, ajustes `<id>.…`, CSS e ids con prefijo `<id>-`.
7. **Página sin build, sin frameworks, sin CDN.** Solo JS plano y `window.FTN`: `FTN.registerView`, `FTN.registerSettings`,
   `FTN.on`, `FTN.GET/POST` (nunca `fetch` directo), `FTN.$(sel, el)` (nunca `document.querySelector`).
8. **`innerHTML` solo con plantillas fijas.** Datos de usuario, servidor o SoundCloud, siempre con `FTN.h()`.
9. **Escritorio y servicio**: el mismo código corre en los dos; en servicio solo se toca la carpeta de música y las subidas.
10. **Principios**: nunca recodificar el audio, decir la verdad sobre la calidad, sin telemetría ni llamadas nuevas a terceros.

## Cómo comprobar

```sh
python tools/check_architecture.py        # arquitectura (también corre solo tras cada edición en Claude Code y en CI)
.venv/bin/python -m pytest                # tests, incluido el contrato de complementos
```

Si el comprobador se queja, arregla el código; no lo silencies. Una excepción justificada se marca en la línea
(`# ftn-arch: allow <regla> — motivo`) y se explica en la PR.

## Flujo

Rama desde `develop`, PR contra `develop`, título Conventional Commits (`feat:`, `fix:`…). Detalles en
[CONTRIBUTING.md](CONTRIBUTING.md). Más contexto: `freethenoize/AGENTS.md` (kernel) y
`freethenoize/plugins/AGENTS.md` (complementos).
