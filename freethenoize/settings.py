"""User settings (JSON) and the SoundCloud token (system keychain)."""
import json
import threading

from .paths import DEFAULT_DOWNLOAD_DIR, SETTINGS_FILE

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
    "colormap": "inferno",
}

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


def get_token() -> str | None:
    import keyring

    try:
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        return None


def set_token(token: str) -> None:
    import keyring

    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, token)


def clear_token() -> None:
    import keyring

    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        pass
