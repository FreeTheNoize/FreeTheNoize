"""User settings (one JSON file) and the SoundCloud token.

The kernel owns a few settings (music folder, update checks, which plugins
are off). Each plugin registers its own under a namespace: the plugin
`downloads` declaring `concurrency` is stored and exposed to the page as
`downloads.concurrency`; inside the plugin it is just `ctx.settings["concurrency"]`.

The token lives in the system keychain on desktop. On a server (Docker, no
keychain) it goes to a 0600 file in the config dir, or comes from
`FTN_SOUNDCLOUD_TOKEN`.
"""
import json
import os
import threading

from . import paths, runtime

KERNEL_DEFAULTS = {
    "download_dir": "",          # filled with paths.DEFAULT_DOWNLOAD_DIR at load time
    "check_updates": True,
    "auto_download_updates": False,
    "skipped_version": "",
    "disabled_plugins": [],
}
# On a server the music folder is fixed by the deployment, not by the page.
KERNEL_SERVER_LOCKED = {"download_dir"}

_KEYRING_SERVICE = "FreeTheNoize"
_KEYRING_USER = "soundcloud-oauth"


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._defaults: dict = {}
        self._locked: set[str] = set()
        self._limits: dict[str, tuple[float, float]] = {}
        try:
            self._stored = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(self._stored, dict):
                self._stored = {}
        except (OSError, ValueError):
            self._stored = {}
        self._data: dict = {}
        self.register("", {**KERNEL_DEFAULTS, "download_dir": str(paths.DEFAULT_DOWNLOAD_DIR)},
                      server_locked=KERNEL_SERVER_LOCKED)

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, namespace: str, defaults: dict, server_locked=(), limits: dict | None = None) -> None:
        """Declare a group of settings. Values saved by older versions under
        the bare name (before plugins had namespaces) are picked up once."""
        full = lambda k: f"{namespace}.{k}" if namespace else k  # noqa: E731
        with self._lock:
            for key, default in defaults.items():
                name = full(key)
                self._defaults[name] = default
                if name in self._stored:
                    value = self._stored[name]
                elif namespace and key in self._stored and key not in KERNEL_DEFAULTS:
                    value = self._stored[key]  # 3.x flat key
                else:
                    value = default
                try:
                    self._data[name] = _coerce(default, value)
                except (TypeError, ValueError):
                    self._data[name] = default
            self._locked |= {full(k) for k in server_locked}
            for key, (lo, hi) in (limits or {}).items():
                self._limits[full(key)] = (lo, hi)
                self._data[full(key)] = min(max(self._data[full(key)], lo), hi)
            if runtime.is_server():
                for name in self._locked:
                    if name in self._defaults:
                        self._data[name] = self._defaults[name]

    def scoped(self, namespace: str) -> "ScopedSettings":
        return ScopedSettings(self, namespace)

    # ── Access ───────────────────────────────────────────────────────────────

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    def locked(self) -> list[str]:
        return sorted(self._locked) if runtime.is_server() else []

    def override(self, key: str, value) -> None:
        """Change a value for this process only, without saving it."""
        with self._lock:
            self._data[key] = value

    def update(self, patch: dict) -> dict:
        """Apply a patch from the page. Unknown keys are ignored, values are
        coerced to the type of their default and clamped to their limits."""
        with self._lock:
            for key, value in patch.items():
                if key not in self._defaults:
                    continue
                if runtime.is_server() and key in self._locked:
                    continue
                value = _coerce(self._defaults[key], value)
                if key in self._limits:
                    lo, hi = self._limits[key]
                    value = min(max(value, lo), hi)
                self._data[key] = value
            self._save()
            return dict(self._data)

    def _save(self) -> None:
        # Keep values of plugins that are switched off right now.
        out = {k: v for k, v in self._stored.items() if k not in self._data and "." in k}
        out.update(self._data)
        tmp = paths.SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(paths.SETTINGS_FILE)
        self._stored = out


class ScopedSettings:
    """What a plugin sees: its own keys, without the namespace."""

    def __init__(self, settings: Settings, namespace: str):
        self._s = settings
        self._ns = namespace

    def __getitem__(self, key):
        return self._s[f"{self._ns}.{key}"]

    def update(self, patch: dict) -> dict:
        data = self._s.update({f"{self._ns}.{k}": v for k, v in patch.items()})
        prefix = self._ns + "."
        return {k[len(prefix):]: v for k, v in data.items() if k.startswith(prefix)}

    def override(self, key: str, value) -> None:
        self._s.override(f"{self._ns}.{key}", value)


def _coerce(default, value):
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, list):
        if not isinstance(value, list):
            raise TypeError("expected a list")
        return [str(v) for v in value]
    return str(value)


# ── SoundCloud token ──────────────────────────────────────────────────────────

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
        return paths.TOKEN_FILE.read_text(encoding="utf-8").strip() or None
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
    paths.TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        os.chmod(paths.TOKEN_FILE, 0o600)
    except OSError:
        pass


def clear_token() -> None:
    if _use_keyring():
        try:
            import keyring

            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        except Exception:
            pass
    paths.TOKEN_FILE.unlink(missing_ok=True)
