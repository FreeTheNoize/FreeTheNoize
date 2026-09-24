"""Where the app keeps its files.

Nothing is ever written next to the executable: on Windows the app lives in
Program Files and on macOS inside a signed .app bundle, both read-only.
"""
from pathlib import Path

from platformdirs import (
    user_cache_path,
    user_config_path,
    user_data_path,
    user_downloads_path,
)

APP_NAME = "FreeTheNoize"

CONFIG_DIR = user_config_path(APP_NAME, appauthor=False, ensure_exists=True)
DATA_DIR = user_data_path(APP_NAME, appauthor=False, ensure_exists=True)
CACHE_DIR = user_cache_path(APP_NAME, appauthor=False, ensure_exists=True)

SETTINGS_FILE = CONFIG_DIR / "settings.json"
ARCHIVE_FILE = DATA_DIR / "archive.txt"
HISTORY_FILE = DATA_DIR / "history.jsonl"
YTDLP_ZIP = DATA_DIR / "yt-dlp.zip"
AUDIO_CACHE_DIR = CACHE_DIR / "audio"

# PyInstaller keeps package data next to the modules, so this works frozen too.
UI_DIR = Path(__file__).parent / "ui"

DEFAULT_DOWNLOAD_DIR = user_downloads_path() / APP_NAME
