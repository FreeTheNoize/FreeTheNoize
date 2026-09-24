# FreeTheNoize

Descarga música de SoundCloud a la **máxima calidad disponible** y comprueba qué calidad tiene de verdad.

## Qué hace

- **Descargas** de canciones, playlists, álbumes, perfiles, likes y reposts de SoundCloud (y enlaces de YouTube). Cola con descargas en paralelo, cancelar y reintentar, y no vuelve a bajar lo que ya tienes.
- **Siempre la mejor fuente**, en este orden, y sin recodificar:
  1. **Original**: el archivo que subió el artista (WAV/FLAC/AIFF/MP3), si tiene las descargas activadas. Requiere iniciar sesión.
  2. **AAC 256 kbps**, con una cuenta Go+.
  3. **MP3 128 kbps**, sin cuenta.

  Cada descarga muestra una etiqueta con la calidad que se ha conseguido realmente.
- **Metadatos**: título, artista, álbum (playlist), género, fecha, enlace y carátula en alta resolución, en todos los formatos (WAV y AIFF incluidos). Limpia títulos ("[FREE DL]", "Out Now"…) y separa "Artista - Título".
- **Espectrograma** con escala logarítmica o lineal, detección del corte de frecuencias (para detectar **falsos lossless**), loudness integrado (LUFS), true peak, LRA y PLR.
- **Comparador**: dos versiones lado a lado, escucha **A/B instantánea con el volumen igualado** y **null test** (alinea, iguala la ganancia y resta las dos versiones; puedes escuchar la diferencia).
- **Conversor** a WAV, AIFF, FLAC, MP3 320 y AAC 256, que conserva etiquetas y carátula.
- **Búsqueda** en SoundCloud e **historial** de descargas.
- yt-dlp **se actualiza desde la propia app**, sin tener que esperar a una versión nueva de FreeTheNoize.

## Desarrollo

Requiere Python 3.11+ y [uv](https://docs.astral.sh/uv/). ffmpeg se toma del PATH y, si no está, de `imageio-ffmpeg`.

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m freethenoize        # FTN_DEBUG=1 abre el inspector web
.venv/bin/python -m pytest
```

## Estructura

```
freethenoize/
  app.py            ventana (pywebview) + servidor local
  api.py            puente Python ⇄ JavaScript
  server.py         sirve la UI y el audio (WAV) en 127.0.0.1
  downloads/        cola, resolución de enlaces, nombres, etiquetas (mutagen)
  analysis/         decodificación, espectrograma, corte, loudness, null test
  converter.py      conversión por lotes
  ytdlp_loader.py   actualización de yt-dlp en caliente
  ui/               HTML/CSS/JS sin build
```

Los datos del usuario (ajustes, historial, archivo de descargas, yt-dlp actualizado) van a la carpeta de datos del sistema: `~/Library/Application Support/FreeTheNoize` en macOS y `%LOCALAPPDATA%\FreeTheNoize` en Windows. El token de SoundCloud se guarda en el llavero del sistema.

## Aviso

Para uso personal. Descargar contenido que el artista no ha puesto para descargar, o el audio de Go+, puede ir contra los términos de SoundCloud. Apoya a los artistas.
