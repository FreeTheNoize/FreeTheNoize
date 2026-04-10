import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Recurs de sols-lectura: MEIPASS en bundle, arrel del projecte en dev."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent.parent)
    return Path(base) / relative


def writable_path(filename: str) -> Path:
    """Fitxer llegit/escrit: costat del .exe en bundle, arrel del projecte en dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / filename
    return Path(__file__).parent.parent / filename


ICON_PATH     = resource_path("assets/gkicks-icon.png")
FAVICON_PATH  = resource_path("assets/favicon.ico")
MP3_PATH      = resource_path("assets/1CliclDVDCopy4.2.1.5kg-keygen-chiptune.mp3")
CONFIG_PATH   = writable_path("gkicks-config.json")
DEFAULT_OUTPUT = str(Path.home() / "Downloads")
