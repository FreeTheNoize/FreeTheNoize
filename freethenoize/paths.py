"""Where the app keeps its files.

Nothing is ever written next to the executable: on Windows the app lives in
Program Files and on macOS inside a signed .app bundle, both read-only.

`FTN_DATA_DIR` puts config, data and cache under one directory (Docker
volume); `FTN_MUSIC_DIR` sets the default download folder.

Plugins never use these constants directly: they get their own folders from
`ctx.data_dir` / `ctx.cache_dir` (DATA_DIR/<plugin>, CACHE_DIR/<plugin>).
Kernel code reads them as `paths.X` at call time, so tests only have to
reload this module after changing the environment.
"""
import os
from pathlib import Path

from platformdirs import (
    user_cache_path,
    user_config_path,
    user_data_path,
    user_downloads_path,
)

APP_NAME = "FreeTheNoize"


def _dirs() -> tuple[Path, Path, Path]:
    if root := os.environ.get("FTN_DATA_DIR"):
        root = Path(root).expanduser()
        dirs = (root / "config", root / "data", root / "cache")
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        return dirs
    return (
        user_config_path(APP_NAME, appauthor=False, ensure_exists=True),
        user_data_path(APP_NAME, appauthor=False, ensure_exists=True),
        user_cache_path(APP_NAME, appauthor=False, ensure_exists=True),
    )


CONFIG_DIR, DATA_DIR, CACHE_DIR = _dirs()

SETTINGS_FILE = CONFIG_DIR / "settings.json"
TOKEN_FILE = CONFIG_DIR / "soundcloud-token"
SECRET_FILE = CONFIG_DIR / "session-secret"
YTDLP_ZIP = DATA_DIR / "yt-dlp.zip"
AUDIO_CACHE_DIR = CACHE_DIR / "audio"
UPLOAD_DIR = CACHE_DIR / "uploads"

# PyInstaller keeps package data next to the modules, so this works frozen too.
UI_DIR = Path(__file__).parent / "ui"

DEFAULT_DOWNLOAD_DIR = (
    Path(os.environ["FTN_MUSIC_DIR"]).expanduser()
    if os.environ.get("FTN_MUSIC_DIR")
    else user_downloads_path() / APP_NAME
)
