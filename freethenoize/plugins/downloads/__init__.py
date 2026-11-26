"""Download queue: links → tracks → best source → tags, BPM and key.

Views: Descargas, Historial. Other plugins use its service
(`ctx.require("downloads")`): add(urls, origin, on_resolved), snapshot().
Events: downloads.job, downloads.jobs, downloads.resolving.
"""
from ...plugin import Plugin
from .api import routes
from .service import DownloadManager

PLUGIN = Plugin(
    id="downloads",
    title="Descargas",
    description="Cola de descargas de SoundCloud y YouTube a la mejor calidad, con etiquetas, BPM y tonalidad.",
    service=DownloadManager,
    api=routes,
    settings={
        "filename_template": "{artist} - {title}",
        "playlist_subfolder": True,
        "concurrency": 3,
        "clean_titles": True,
        "split_artist_title": True,
        "embed_artwork": True,
        "artwork_max_px": 1400,
        "save_artwork_file": False,
        "skip_downloaded": True,
        "detect_bpm_key": True,
    },
    limits={"concurrency": (1, 8), "artwork_max_px": (300, 5000)},
)
