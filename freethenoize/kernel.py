"""The kernel: what every plugin relies on, independent of how it is shown.

It loads the plugins, gives each one its `Ctx`, and owns what is shared:
settings, events, the path sandbox of the web service, uploads, playable
audio, the SoundCloud session, yt-dlp and app updates. It never imports a
plugin by name (`plugins.BUILTIN` is the only list) and has no feature logic.

Both front doors use it: the HTTP API (web.py) for browsers and the desktop
window, and the native bridge (desktop.py) for dialogs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from . import __version__, ffmpeg, paths, plugin as plugin_mod, plugins, runtime, ytdlp
from . import settings as settings_mod
from .events import EventBus
from .files import AUDIO_EXTS, safe_filename
from .plugin import Ctx, Plugin
from .updates import Updater

log = logging.getLogger("freethenoize")

# Played straight from disk; anything else is transcoded to WAV first so it
# works on WebKit, WebView2 and every browser, also inside Web Audio.
DIRECT_PLAY = {".mp3", ".m4a", ".aac", ".wav"}
UPLOAD_TTL = 24 * 3600


class LoadedPlugin:
    def __init__(self, pid: str, plugin: Plugin | None):
        self.id = pid
        self.plugin = plugin
        self.ctx: Ctx | None = None
        self.service: Any = None
        self.status = "active"       # active | disabled | unavailable
        self.reason = ""

    def info(self) -> dict:
        p = self.plugin
        return {"id": self.id, "title": p.title if p else self.id, "version": p.version if p else "",
                "description": p.description if p else "", "requires": list(p.requires) if p else [],
                "status": self.status, "reason": self.reason}


class Kernel:
    def __init__(self, plugin_ids: Iterable[str] | None = None):
        plugin_mod._active = self
        self.bus = EventBus()
        self.emit = self.bus.emit
        self.settings = settings_mod.Settings()
        self.updates = Updater(self.settings, self.emit)
        self._audio: dict[str, Path] = {}
        self._audio_lock = threading.Lock()
        self._sc_username: str | None = None
        paths.AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        paths.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for old in paths.AUDIO_CACHE_DIR.glob("*.wav"):
            old.unlink(missing_ok=True)
        self._clean_uploads()
        self.plugins: dict[str, LoadedPlugin] = {}
        self._load_plugins(plugins.BUILTIN if plugin_ids is None else plugin_ids)

    # ── Plugins ──────────────────────────────────────────────────────────────

    def _load_plugins(self, ids: Iterable[str]) -> None:
        disabled = set(self.settings["disabled_plugins"])
        for pid in ids:
            try:
                lp = LoadedPlugin(pid, plugins.load(pid))
            except Exception as e:
                log.exception("plugin %s failed to load", pid)
                lp = LoadedPlugin(pid, None)
                lp.status, lp.reason = "unavailable", f"no carga: {e}"
            else:
                if runtime.mode() not in lp.plugin.modes:
                    lp.status, lp.reason = "unavailable", "no disponible en este modo"
                elif pid in disabled:
                    lp.status, lp.reason = "disabled", "desactivado en Ajustes"
            self.plugins[pid] = lp

        # A plugin whose requirements are off is off too (repeat: chains).
        changed = True
        while changed:
            changed = False
            for lp in self.plugins.values():
                if lp.status != "active":
                    continue
                missing = [r for r in lp.plugin.requires
                           if r not in self.plugins or self.plugins[r].status != "active"]
                if missing:
                    lp.status, lp.reason = "unavailable", "necesita " + ", ".join(missing)
                    changed = True

        for pid in self._dependency_order():
            lp = self.plugins[pid]
            p = lp.plugin
            try:
                self.settings.register(p.id, p.settings, server_locked=p.server_locked, limits=p.limits)
                lp.ctx = Ctx(self, p)
                lp.service = p.service(lp.ctx) if p.service else None
            except Exception as e:
                log.exception("plugin %s failed to start", pid)
                lp.status, lp.reason, lp.service = "unavailable", f"error al arrancar: {e}", None

    def _dependency_order(self) -> list[str]:
        order: list[str] = []

        def visit(pid: str):
            if pid in order:
                return
            for req in self.plugins[pid].plugin.requires:
                visit(req)
            order.append(pid)

        for pid, lp in self.plugins.items():
            if lp.status == "active":
                visit(pid)
        return order

    def active(self) -> list[LoadedPlugin]:
        return [lp for lp in self.plugins.values() if lp.status == "active"]

    def service(self, plugin_id: str) -> Any:
        lp = self.plugins.get(plugin_id)
        if not lp or lp.status != "active":
            raise KeyError(f"plugin {plugin_id} is not active")
        return lp.service

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        for lp in self.active():
            if hasattr(lp.service, "start"):
                try:
                    lp.service.start()
                except Exception:
                    log.exception("plugin %s: start() failed", lp.plugin.id)
        self.updates.start()
        threading.Thread(target=self._refresh_username, daemon=True).start()

    def stop(self):
        self.updates.stop()
        for lp in reversed(self.active()):
            if hasattr(lp.service, "stop"):
                try:
                    lp.service.stop()
                except Exception:
                    log.exception("plugin %s: stop() failed", lp.plugin.id)

    # ── State ────────────────────────────────────────────────────────────────

    def state(self) -> dict:
        plugin_state = {}
        for lp in self.active():
            try:
                plugin_state[lp.plugin.id] = lp.service.state() if hasattr(lp.service, "state") else {}
            except Exception:
                log.exception("plugin %s: state() failed", lp.plugin.id)
                plugin_state[lp.plugin.id] = {}
        return {
            "version": __version__,
            "mode": runtime.mode(),
            "ytdlp_version": ytdlp.current_version(),
            "ffmpeg": ffmpeg.FFMPEG if not runtime.is_server() else bool(ffmpeg.FFMPEG),
            "platform": sys.platform,
            "settings": self.settings.as_dict(),
            "locked_settings": self.settings.locked(),
            "soundcloud": self.soundcloud_status(),
            "update": self.updates.status(),
            "plugins": plugin_state,
            "plugin_list": [lp.info() for lp in self.plugins.values()],
        }

    def update_settings(self, patch: dict) -> dict:
        data = self.settings.update(patch)
        self.emit("settings", data)
        return data

    # ── Paths ────────────────────────────────────────────────────────────────

    def roots(self) -> list[Path]:
        return [Path(self.settings["download_dir"]).expanduser().resolve(), paths.UPLOAD_DIR.resolve()]

    def check_path(self, raw: str, must_exist: bool = True) -> Path:
        """Validate a path coming from the page. On a server it must live in
        the music folder or the upload area."""
        if not raw:
            raise ValueError("Falta la ruta.")
        path = Path(raw).expanduser().resolve()
        if runtime.is_server() and not any(path.is_relative_to(r) for r in self.roots()):
            raise PermissionError("Esa ruta está fuera de la biblioteca.")
        if must_exist and not path.exists():
            raise FileNotFoundError(raw)
        return path

    def save_upload(self, filename: str, stream) -> dict:
        name = safe_filename(Path(filename or "audio").name)
        if Path(name).suffix.lower() not in AUDIO_EXTS:
            raise ValueError("Formato de audio no admitido.")
        folder = paths.UPLOAD_DIR / secrets.token_hex(6)
        folder.mkdir(parents=True)
        target = folder / name
        with target.open("wb") as f:
            shutil.copyfileobj(stream, f, 1 << 20)
        return {"path": str(target), "name": name, "size": target.stat().st_size}

    def _clean_uploads(self):
        cutoff = time.time() - UPLOAD_TTL
        for d in paths.UPLOAD_DIR.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass

    # ── Playback ─────────────────────────────────────────────────────────────

    def playable_url(self, path: Path) -> str:
        if path.suffix.lower() in DIRECT_PLAY:
            return f"/api/stream?path={quote(str(path))}"
        st = path.stat()
        key = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20]
        target = paths.AUDIO_CACHE_DIR / f"{key}.wav"
        if not target.exists():
            tmp = target.with_suffix(".part.wav")
            res = ffmpeg.run(["-v", "error", "-y", "-i", str(path), "-map", "0:a:0",
                              "-ac", "2", "-c:a", "pcm_s16le", str(tmp)])
            if res.returncode != 0:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(res.stderr.decode("utf-8", "replace").strip())
            tmp.replace(target)
        with self._audio_lock:
            self._audio[key] = target
        return f"/api/audio/{key}.wav"

    def samples_url(self, samples, sr: int) -> str:
        """Write float samples (frames, channels) as a WAV normalised to -1 dBFS."""
        import numpy as np

        peak = float(np.abs(samples).max()) or 1.0
        pcm = (samples / peak * 0.89 * 32767).astype("<i2")
        key = secrets.token_hex(10)
        target = paths.AUDIO_CACHE_DIR / f"{key}.wav"
        with wave.open(str(target), "wb") as w:
            w.setnchannels(samples.shape[1])
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        with self._audio_lock:
            self._audio[key] = target
        return f"/api/audio/{key}.wav"

    def cached_audio(self, key: str) -> Path | None:
        with self._audio_lock:
            return self._audio.get(key)

    # ── SoundCloud session (shared by downloads, preview and search) ─────────

    def soundcloud_status(self) -> dict:
        token = settings_mod.get_token()
        return {"logged_in": bool(token), "username": self._sc_username if token else None}

    @staticmethod
    def _check_token(token: str) -> str | None:
        req = urllib.request.Request(
            "https://api-v2.soundcloud.com/me",
            headers={"Authorization": f"OAuth {token}", "User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("username")
        except Exception:
            return None

    def _refresh_username(self):
        if token := settings_mod.get_token():
            self._sc_username = self._check_token(token)
            self.emit("soundcloud", self.soundcloud_status())

    def soundcloud_set_token(self, token: str) -> dict:
        token = (token or "").strip().removeprefix("OAuth ").strip()
        if not re.fullmatch(r"[\w\-.]{10,}", token):
            raise ValueError("Eso no parece un token de SoundCloud.")
        settings_mod.set_token(token)
        self._sc_username = self._check_token(token)
        status = self.soundcloud_status()
        self.emit("soundcloud", status)
        return status

    def soundcloud_logout(self) -> dict:
        settings_mod.clear_token()
        self._sc_username = None
        status = self.soundcloud_status()
        self.emit("soundcloud", status)
        return status

    # ── Maintenance ──────────────────────────────────────────────────────────

    def update_ytdlp(self) -> dict:
        return ytdlp.update()
