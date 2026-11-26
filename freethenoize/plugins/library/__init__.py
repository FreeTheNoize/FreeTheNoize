"""Index of the music folder: tags, duration, BPM/key, covers; play, delete.

Events: library.changed. Refreshes itself when downloads.job reports a
finished download (in the page).
"""
from ...plugin import Plugin
from .api import routes
from .service import Library

PLUGIN = Plugin(
    id="library",
    title="Biblioteca",
    description="Tu carpeta de música con carátulas, BPM, tonalidad y filtros.",
    service=Library,
    api=routes,
)
