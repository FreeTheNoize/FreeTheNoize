"""Listen to a track before downloading it (streamed through ffmpeg as MP3).

No view of its own: the page gets `FTN.use("preview")(url)`, which the
Descargas and Buscar views call. Only listening, nothing is saved.
"""
from ...plugin import Plugin
from .api import routes
from .service import Previews

PLUGIN = Plugin(
    id="preview",
    title="Pre-escucha",
    description="Escucha un tema de SoundCloud antes de descargarlo.",
    service=Previews,
    api=routes,
)
