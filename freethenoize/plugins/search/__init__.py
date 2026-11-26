"""Search SoundCloud and send results to the queue or to pre-listening."""
from ...plugin import Plugin
from .api import routes
from .service import Search

PLUGIN = Plugin(
    id="search",
    title="Buscar",
    description="Busca en SoundCloud y manda lo que quieras a la cola.",
    service=Search,
    api=routes,
)
