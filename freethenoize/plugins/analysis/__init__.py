"""Lab: real quality of a file (spectrogram, cutoff, loudness, BPM/key) and
A/B comparison with null test.

Views: Espectro, A/B · Null. The page gets `FTN.use("analysis.open")(path)`
and `FTN.use("compare.add")(path)` for the other views' buttons.
"""
from ...plugin import Plugin
from .api import routes
from .service import Analysis

PLUGIN = Plugin(
    id="analysis",
    title="Laboratorio",
    description="Espectrograma, falsos lossless, loudness, BPM, tonalidad y comparador A/B con null test.",
    service=Analysis,
    api=routes,
    settings={"colormap": "inferno"},
)
