"""Playlists, likes or profiles re-checked on a timer; only new tracks are
downloaded (through the downloads plugin and its archive).

Events: subscriptions.changed, subscriptions.removed.
"""
from ...plugin import Plugin
from .api import routes
from .service import Subscriptions

PLUGIN = Plugin(
    id="subscriptions",
    title="Suscripciones",
    description="Sigue playlists, likes o perfiles y baja solo lo nuevo.",
    service=Subscriptions,
    api=routes,
    requires=("downloads",),
)
