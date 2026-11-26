"""Batch conversion to WAV, AIFF, FLAC, MP3 320 and AAC 256, keeping tags and
artwork, with optional loudness normalisation.

The smallest complete plugin: read it first if you are writing your own
(service.py → logic, api.py → routes, ui/convert.js → view).

Events: convert.progress.
"""
from ...plugin import Plugin
from .api import routes
from .service import ConvertService

PLUGIN = Plugin(
    id="convert",
    title="Convertir",
    description="Convierte por lotes conservando etiquetas y carátula; normaliza el loudness si quieres.",
    service=ConvertService,
    api=routes,
)
