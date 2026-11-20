# FreeTheNoize

Descarga música de SoundCloud a la **máxima calidad disponible**, comprueba qué calidad tiene de verdad y organízala para pinchar.
Funciona como **app de escritorio** (macOS, Windows) o como **servicio web** (Docker, para tenerlo en un servidor o NAS y usarlo desde el móvil).

## Qué hace

- **Descargas** de temas, playlists, álbumes, perfiles, likes y reposts de SoundCloud (y enlaces de YouTube). Descargas en paralelo, cancelar y reintentar, y no vuelve a bajar lo que ya tienes (sin pedírselo de nuevo a SoundCloud).
- **Siempre la mejor fuente**, sin recodificar:
  1. **Original** que subió el artista (WAV/FLAC/AIFF/MP3), si tiene las descargas activadas. Requiere sesión.
  2. **AAC 256 kbps**, con cuenta Go+.
  3. **MP3 128 / AAC 160**, sin cuenta.

  Cada descarga lleva una etiqueta con la calidad real conseguida.
- **BPM y tonalidad** (con notación Camelot) de cada descarga, escritos en las etiquetas para Rekordbox, Traktor y Serato.
- **Metadatos completos**: título, artista, álbum, género, fecha, enlace y carátula en todos los formatos (WAV y AIFF incluidos). Limpia títulos ("[FREE DL]", "Out Now"…) y separa "Artista - Título".
- **Suscripciones**: sigue playlists, likes o perfiles; se revisan solos cada cierto tiempo y bajan solo lo nuevo.
- **Biblioteca** con carátulas, filtro por título/artista/BPM/Camelot y reproductor.
- **Espectro**: espectrograma log/lineal, detección del corte de frecuencias (**falsos lossless**), loudness (LUFS), true peak, LRA y PLR.
- **A/B · Null**: dos versiones lado a lado, escucha A/B instantánea con el volumen igualado y null test (alinea, iguala ganancia y resta; puedes escuchar la diferencia).
- **Conversor** a WAV, AIFF, FLAC, MP3 320 y AAC 256, conservando etiquetas y carátula, con normalización opcional de loudness (−14, −9, −23 LUFS…).
- **Búsqueda** en SoundCloud e **historial**.
- yt-dlp **se actualiza desde la propia app**.

## Escritorio

Descarga la build de [Releases](../../releases) o, desde el código:

```sh
uv venv && uv pip install -e ".[desktop,dev]"
.venv/bin/freethenoize            # FTN_DEBUG=1 abre el inspector web
```

El inicio de sesión de SoundCloud se hace en una ventana integrada; el token se guarda en el llavero del sistema.

## Servicio web (Docker)

```sh
FTN_PASSWORD=algo-largo docker compose up -d
# → http://localhost:8765
```

o sin compose:

```sh
docker run -d -p 8765:8765 -e FTN_PASSWORD=algo-largo \
  -v ./data:/data -v ./music:/music ghcr.io/quim-d/freethenoize
```

Sin Docker: `freethenoize serve --host 0.0.0.0 --port 8765 --music-dir ~/Música`.

| Variable | Para qué |
|---|---|
| `FTN_PASSWORD` | Contraseña de acceso. **Ponla siempre** si el servicio es accesible desde la red. |
| `FTN_MUSIC_DIR` | Carpeta de música (en Docker, `/music`). En modo servicio no se puede cambiar desde la página. |
| `FTN_DATA_DIR` | Ajustes, historial, archivo de descargas, suscripciones y caché (en Docker, `/data`). |
| `FTN_SOUNDCLOUD_TOKEN` | Token OAuth de SoundCloud (opcional; también se puede pegar en Ajustes). |
| `FTN_HOST`, `FTN_PORT` | Dónde escucha (por defecto `127.0.0.1:8765`; en Docker `0.0.0.0`). |
| `FTN_TRUSTED_PROXIES` | IPs de tu proxy inverso, para que respete `X-Forwarded-*`. |

En modo servicio solo se puede abrir lo que hay en la carpeta de música y lo que subas desde el navegador (arrastrar archivos funciona). Los resultados se descargan al dispositivo. Para exponerlo fuera de casa, ponlo detrás de un proxy con HTTPS (Caddy, Traefik, Tailscale…).

## Terminal

```sh
freethenoize get https://soundcloud.com/usuario/sets/playlist -o ~/Música
```

## Desarrollo

```sh
uv venv && uv pip install -e ".[desktop,dev]"
.venv/bin/python -m pytest
.venv/bin/pyinstaller packaging/freethenoize.spec --noconfirm   # build de escritorio
```

```
freethenoize/
  app.py            CLI: app | serve | get
  desktop.py        ventana pywebview + diálogos nativos
  web.py            API HTTP (FastAPI), eventos SSE, auth
  core.py           lógica común a escritorio y servicio
  downloads/        cola, resolución de enlaces, nombres, etiquetas (mutagen)
  analysis/         decodificación, espectrograma, corte, loudness, BPM/tonalidad, null test
  subscriptions.py  sincronización periódica
  library.py        índice de la carpeta de música y carátulas
  converter.py      conversión por lotes y normalización
  ytdlp_loader.py   actualización de yt-dlp en caliente
  ui/               HTML/CSS/JS sin build
```

## Aviso

Para uso personal. Descargar contenido que el artista no ha puesto para descargar, o el audio de Go+, puede ir contra los términos de SoundCloud. Apoya a los artistas.
