"""User settings (JSON) and the SoundCloud token.

The token lives in the system keychain on desktop. On a server (Docker, no
keychain) it goes to a 0600 file in the config dir, or comes from
`FTN_SOUNDCLOUD_TOKEN`.
"""
import json
import os
import threading

from . import runtime
from .paths import DEFAULT_DOWNLOAD_DIR, SETTINGS_FILE, TOKEN_FILE

DEFAULTS = {
    "download_dir": str(DEFAULT_DOWNLOAD_DIR),
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
    "colormap": "inferno",
}

# On a server the music folder is fixed by the deployment, not by the page.
SERVER_LOCKED = {"download_dir"}

_KEYRING_SERVICE = "FreeTheNoize"
_KEYRING_USER = "soundcloud-oauth"


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self._data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        if runtime.is_server():
            self._data["download_dir"] = DEFAULTS["download_dir"]

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    def update(self, patch: dict) -> dict:
        with self._lock:
            for key, value in patch.items():
                if key not in DEFAULTS:
                    continue
                if runtime.is_server() and key in SERVER_LOCKED:
                    continue
                expected = type(DEFAULTS[key])
                if expected is int:
                    value = int(value)
                elif expected is bool:
                    value = bool(value)
                else:
                    value = str(value)
                self._data[key] = value
            self._data["concurrency"] = min(max(self._data["concurrency"], 1), 8)
            SETTINGS_FILE.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            return dict(self._data)


def _use_keyring() -> bool:
    return not runtime.is_server()


def get_token() -> str | None:
    if env := os.environ.get("FTN_SOUNDCLOUD_TOKEN"):
        return env.strip()
    if _use_keyring():
        try:
            import keyring

            if token := keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER):
                return token
        except Exception:
            pass
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def set_token(token: str) -> None:
    if _use_keyring():
        try:
            import keyring

            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, token)
            return
        except Exception:
            pass
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def clear_token() -> None:
    if _use_keyring():
        try:
            import keyring

            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        except Exception:
            pass
    TOKEN_FILE.unlink(missing_ok=True)
