# Arquitectura

FreeTheNoize es un **kernel pequeño** y un conjunto de **complementos** (plugins). El kernel no sabe descargar,
analizar ni convertir nada: da a cada complemento lo que necesita (ajustes, eventos, rutas seguras, audio
reproducible, la sesión de SoundCloud…) y los monta en la API y en la página. Cada función que ves en el menú
es un complemento, y añadir una nueva es crear una carpeta.

```
                 ┌───────────── página (ui/index.html + kernel.js) ──────────────┐
                 │  FTN.registerView · registerSettings · on · provide/use · h()  │
                 └───────▲───────────────────────────────────────▲───────────────┘
        /plugins/<id>/<id>.js|css                       /api/… + eventos SSE
                         │                                       │
 ┌───────────────────────┴──────────── kernel ─────────────────────┴──────────────────┐
 │ kernel.py   carga complementos, ajustes, eventos, sandbox de rutas, subidas,         │
 │             audio reproducible, sesión SoundCloud, yt-dlp, actualizaciones          │
 │ web.py      API HTTP del kernel + monta /api/<id> y /plugins/<id> de cada uno        │
 │ plugin.py   el contrato: Plugin, Ctx, LibraryPath                                   │
 └──────────▲───────────────▲───────────────▲───────────────▲──────────────────────────┘
            │ Ctx           │ Ctx           │ Ctx           │ Ctx
      downloads ◀── requires ── subscriptions    library   analysis   convert   preview   search
            │
   bibliotecas compartidas: freethenoize.audio · files · ytdlp · ffmpeg
```

## Qué es kernel y qué es complemento

| Va en el **kernel** | Va en un **complemento** |
|---|---|
| Lo que usan varios complementos o la propia app: ajustes, eventos, rutas, subidas, reproducción, sesión de SoundCloud, yt-dlp, actualizaciones, ventana de escritorio, login | Cualquier función que el usuario reconoce como tal: descargar, buscar, suscripciones, biblioteca, análisis, conversión… |
| Cambia poco y se revisa con lupa | Cambia a menudo; si falla, solo cae ese complemento |
| **Nunca** importa un complemento por nombre (`plugins.BUILTIN` es la única lista) | **Nunca** importa otro complemento: lo pide con `requires` |

Las **bibliotecas compartidas** (`freethenoize/audio/`, `files.py`, `ytdlp.py`, `ffmpeg.py`) son código sin
estado que cualquiera puede importar: decodificar, espectro, loudness, BPM/tonalidad, etiquetas, nombres de
archivo seguros.

## Un complemento

```
freethenoize/plugins/<id>/
  __init__.py     PLUGIN = Plugin(...)       — la ficha
  service.py      la lógica; recibe ctx      — sin FastAPI
  api.py          routes(service, ctx)       — se monta en /api/<id>
  ui/<id>.js      vista(s) y ajustes         — se carga sola en la página
  ui/<id>.css     estilos propios (opcional)
```

Para empezar: `python tools/new_plugin.py <id> --title "Nombre"` crea todo esto ya cableado y lo añade a
`plugins.BUILTIN`. Guía paso a paso en [CONTRIBUTING.md › Crear un complemento](CONTRIBUTING.md#crear-un-complemento).

### La ficha: `Plugin`

```python
PLUGIN = Plugin(
    id="convert",                        # minúsculas, cifras y _; es el prefijo de todo lo suyo
    title="Convertir",                   # nombre en el menú y en Ajustes › complementos
    version="1.0",
    description="Pasa audio a otros formatos…",
    service=ConvertService,              # ConvertService(ctx)
    api=routes,                          # routes(service, ctx) -> APIRouter
    settings={"normalize": False},       # valores por defecto; el tipo manda al validar
    limits={"concurrency": (1, 8)},      # números: se recortan a [min, max]
    server_locked={"…"},                 # no editables desde la página en modo servicio
    requires=("downloads",),             # otros complementos que necesita
    modes=frozenset({"desktop", "server"}),
)
```

El servicio puede tener `start()`, `stop()` y `state() -> dict`. Lo que devuelve `state()` aparece en
`/api/state` como `plugins.<id>` (en la página, `FTN.state.plugins.<id>`).

### Lo que da el kernel: `Ctx`

| | |
|---|---|
| `ctx.settings["clave"]` | Ajustes del complemento. En la página y en el fichero se llaman `<id>.clave`. |
| `ctx.emit("evento", {...})` | Evento `<id>.evento` a todas las páginas abiertas (SSE) y a los oyentes del proceso. |
| `ctx.on("otro.evento", fn)` | Escuchar un evento por su nombre completo (`downloads.job`, `settings`…). |
| `ctx.require("downloads")` | El servicio de otro complemento. Solo si está en `requires`. |
| `ctx.data_dir`, `ctx.cache_dir` | `DATA_DIR/<id>/` y `CACHE_DIR/<id>/`, propias. `ctx.data_file(nombre, legacy=…)` mueve el fichero de 3.x/0.4 la primera vez. |
| `ctx.music_dir()` | La carpeta de música. |
| `ctx.mode`, `ctx.is_server()` | `desktop` o `server`. |
| `ctx.check_path(raw)` | Valida una ruta que viene de la página (ver abajo). |
| `ctx.playable_url(path)` | URL que la página puede reproducir (transcodifica a WAV si hace falta). |
| `ctx.samples_url(samples, sr)` | URL de un WAV temporal hecho con muestras (null test, diferencias…). |
| `ctx.ytdlp_params(url)` | Parámetros base de yt-dlp: ffmpeg, reintentos y la sesión de SoundCloud. |
| `ctx.log` | Logger `freethenoize.<id>`. |

### Lo que comprueban los tests

`tests/test_plugins.py` arranca el kernel y falla si:

- Algún complemento no se puede desactivar (Ajustes › complementos): al apagarlo, sus rutas y su UI desaparecen,
  los que lo necesitan quedan «no disponible» y el resto sigue funcionando.
- Un complemento que no carga o que revienta al arrancar tumba la app.
- Hay rutas fuera de `/api/<id>/…` o UI fuera de `/plugins/<id>/…`.
- Los eventos no llevan el prefijo `<id>.`, los ajustes no van en su espacio `<id>.` o no se aplican los límites.
- Los ajustes y ficheros de versiones anteriores no se migran solos.

Las reglas sobre el código (quién importa a quién, prefijos, rutas, la página…) las comprueba
`tools/check_architecture.py`: ver [Reglas del framework](#reglas-del-framework).

### Rutas que vienen de la página: `LibraryPath`

En modo servicio la página solo puede tocar la carpeta de música y las subidas. Toda ruta que reciba una
API se declara como `LibraryPath` y llega ya validada (existe y está dentro; si no, 403/404):

```python
from ...plugin import LibraryPath

class Body(BaseModel):
    path: LibraryPath

@r.post("/analyze")
def analyze(body: Body): ...

@r.get("/cover")
def cover(path: LibraryPath): ...
```

Errores: lanza `ValueError` (400), `PermissionError` (403), `FileNotFoundError`/`KeyError` (404) o
`RuntimeError` (500); el kernel los convierte en `{"error": "…"}`.

## La página: `window.FTN`

La UI es HTML/CSS/JS **sin build, sin frameworks y sin CDN**. `ui/index.html` es la carcasa (menú, ajustes,
reproductor, avisos) y `ui/kernel.js` publica `window.FTN`. Cada complemento añade su `ui/<id>.js`, que el
kernel inserta en la página después de `kernel.js`.

```js
(function () {
  const { $, h, GET, POST, toast } = FTN;

  FTN.registerView({
    id: 'convert', group: 'laboratorio', order: 80,   // grupo: fuente | archivo | laboratorio
    title: 'Convertir', heading: 'Convierte', intro: 'Una frase.',
    html: `<div class="list" id="convert-list"></div>`, // plantilla ESTÁTICA
    init(el) { … },             // una vez, al arrancar
    onShow() { … },             // cada vez que se abre
    onFiles(paths) { … },       // archivos arrastrados sobre esta vista
  });

  FTN.registerSettings({ id: 'convert', order: 50, title: '// conversión', html: `…`, init(el) { … } });
  FTN.on('convert.progress', (p) => …);   // eventos del servidor y locales
})();
```

| | |
|---|---|
| `registerView`, `registerSettings` | Pantallas del menú (numeradas solas) y secciones de Ajustes. |
| `on(evento, fn)`, `fire(evento, datos)` | Eventos: `<id>.<evento>` del servidor, `state`, `settings`, `soundcloud`, `player`… |
| `provide(nombre, fn)`, `use(nombre)` | Acciones que un complemento ofrece a otros sin importarlos: `downloads.add`, `preview`, `analysis.open`, `files.open`, `links.add`. `use` devuelve `undefined` si nadie la ofrece: la UI debe funcionar igual. |
| `addTicker(fn)`, `setBadge(vista, n)` | Contadores de la barra superior y del menú. |
| `state`, `saveSetting(clave, valor)` | Estado de `/api/state` y guardar un ajuste (`'<id>.clave'`). |
| `GET/POST/PATCH/DEL`, `getBytes`, `q` | HTTP con el error del servidor ya mostrado como aviso (`getBytes`: respuestas binarias, p. ej. audio para Web Audio). |
| `native`, `pickAudio`, `pickFolder`, `uploadFiles`, `reveal`, `openUrl` | Diálogos nativos en escritorio y su equivalente en el navegador. |
| `player`, `takeAudio(dueño)` | El reproductor común; `takeAudio` pausa el resto antes de sonar. |
| `h`, `toast`, `iconBtn`, `art`, `badge`, `camChip`, `bpmChip`, `loadingBars`, `fmt*`… | Piezas de UI del sistema de diseño. |

**Seguridad en la página**: `innerHTML` solo para plantillas estáticas (las `html:` de las vistas) e iconos
de `FTN.ICONS`. Todo lo que venga del usuario, del servidor o de SoundCloud se pinta con `h()`, que escapa el
texto. CSS propio con prefijo de la vista (`.view[data-view=<id>] …`) o clases `<id>-…`.

## Reglas del framework

`tools/check_architecture.py` las comprueba sin dependencias (AST para Python, expresiones regulares para el JS
de los complementos) y dice dónde y qué hacer:

```
freethenoize/plugins/convert/service.py:3: un complemento importa otro [plugin-imports-plugin] → ponlo en requires=(…) … (ARCHITECTURE.md#un-complemento-no-importa-otro)
```

Se ejecuta en tres sitios: en CI (check **architecture**, obligatorio para fusionar), tras cada edición de un
agente de Claude Code (hook en `.claude/settings.json`) y, si quieres, antes de cada commit
(`pre-commit install`). A mano: `python tools/check_architecture.py [archivos…]`.

### Un complemento no importa otro

Ni `from ..downloads import …` ni `import freethenoize.plugins.<otro>`. Si necesitas otro complemento, ponlo en
`requires=("downloads",)` y pide su servicio con `ctx.require("downloads")`; así el kernel lo arranca antes y,
si está apagado, el tuyo queda «no disponible» en vez de romperse. En la página, `FTN.provide` / `FTN.use`.

### El kernel no conoce los complementos

Los ficheros de `freethenoize/` fuera de `plugins/` no importan ningún complemento ni escriben su nombre
(`"downloads"`, `"downloads.job"`). La única lista es `plugins.BUILTIN`. Si una función necesita algo del kernel,
se añade a `Ctx` (o a `FTN`) de forma genérica, en una PR aparte.

### Eventos y ajustes con tu prefijo

`ctx.emit("progress", …)` ya sale como `convert.progress`: no escribas el prefijo, ni el de otro. `ctx.settings`
solo ve tus ajustes y sin prefijo (`ctx.settings["concurrency"]`); en la página se llaman `downloads.concurrency`.
Para escuchar a otro complemento, `ctx.on("downloads.job", fn)`.

### Tus ficheros en tu carpeta

Lo que guarde un complemento va en `ctx.data_dir`, `ctx.cache_dir` o `ctx.data_file(nombre)`; la música, en
`ctx.music_dir()` o donde diga el usuario. Nada de `freethenoize.paths`, `Path.home()` ni rutas escritas a mano.

### Rutas de archivo con LibraryPath

Todo campo o parámetro de una API que sea una ruta (`path`, `files`, `out_dir`, `dest`…) se declara
`LibraryPath`, que la valida antes de llegar a tu código (ver [arriba](#rutas-que-vienen-de-la-página-librarypath)).

### HTTP y DOM por FTN

En la página, nada de `fetch()` directo: `FTN.GET/POST/PATCH/DEL` (o `FTN.getBytes`) ya llevan la sesión, el
login y los avisos de error. Nada de `document.querySelector`/`getElementById`: busca dentro de tu vista con
`FTN.$(selector, el)`, el `el` que recibe `init(el)`.

### Nada de HTML con datos

`innerHTML`, `outerHTML` e `insertAdjacentHTML` solo con plantillas fijas (sin `${…}`). Lo que lleve datos del
usuario, del servidor o de SoundCloud se pinta con `FTN.h()`, que escapa el texto.

### Sin scripts externos

Ni CDN, ni `<script src="https://…">`, ni `import` de URLs: la app funciona sin conexión y no llama a terceros.

### Vistas con id propio

Cada vista tiene un id único en toda la app; no uses el id de otro complemento ni `settings`.

### Excepciones

Si una línea tiene un buen motivo para saltarse una regla, se dice en esa línea o en la de encima, y se explica
en la PR:

```python
# ftn-arch: allow kernel-names-plugin — `get` vive aquí hasta que los complementos aporten sus comandos
```

## Puertas de entrada

- `app.py`: línea de órdenes (`app`, `serve`, `get`).
- `desktop.py`: ventana pywebview con el mismo servidor HTTP en `127.0.0.1` y un puente nativo para diálogos.
- `web.py`: la API HTTP, para el navegador y para la ventana de escritorio.

Escritorio y servicio ejecutan exactamente el mismo kernel y los mismos complementos; lo que cambia es el modo
(`runtime.mode()`), que decide el sandbox de rutas y qué ajustes se pueden tocar.
