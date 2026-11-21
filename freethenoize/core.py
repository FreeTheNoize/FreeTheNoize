"""Everything the UI can ask for, independent of how it is shown.

Both front doors use this: the HTTP API (web.py) for browsers and the
desktop window, and the native bridge (desktop.py) for dialogs.
"""
import hashlib
import json
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from urllib.parse import quote

import numpy as np

from . import __version__, analysis, converter, ffmpeg, runtime, ytdlp_loader
from . import settings as settings_mod
from .downloads import manager as dl
from .downloads.naming import safe_filename
from .downloads.resolve import search_soundcloud
from .events import EventBus
from .library import AUDIO_EXTS, Library
from .paths import AUDIO_CACHE_DIR, UPLOAD_DIR
from .preview import Previews
from .subscriptions import Subscriptions
from .updates import Updater

_URL = re.compile(r"https?://\S+")
# Played straight from disk; anything else is transcoded to WAV first so it
# works on WebKit, WebView2 and every browser, also inside Web Audio.
DIRECT_PLAY = {".mp3", ".m4a", ".aac", ".wav"}
UPLOAD_TTL = 24 * 3600


class Core:
    def __init__(self):
        self.bus = EventBus()
        self.emit = self.bus.emit
        self.settings = settings_mod.Settings()
        self.downloads = dl.DownloadManager(self.settings, self.emit)
        self.subscriptions = Subscriptions(self.downloads, self.emit)
        self.library = Library()
        self.previews = Previews(self.downloads.base_params)
        self.updates = Updater(self.settings, self.emit)
        self._audio: dict[str, Path] = {}
        self._audio_lock = threading.Lock()
        self._sc_username: str | None = None
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for old in AUDIO_CACHE_DIR.glob("*.wav"):
            old.unlink(missing_ok=True)
        self._clean_uploads()

    def start(self):
        self.subscriptions.start()
        self.updates.start()
        threading.Thread(target=self._refresh_username, daemon=True).start()

    def stop(self):
        self.subscriptions.stop()
        self.updates.stop()

    # ── State ────────────────────────────────────────────────────────────────

    def state(self) -> dict:
        return {
            "version": __version__,
            "mode": runtime.mode(),
            "ytdlp_version": ytdlp_loader.current_version(),
            "ffmpeg": ffmpeg.FFMPEG if not runtime.is_server() else bool(ffmpeg.FFMPEG),
            "platform": sys.platform,
            "settings": self.settings.as_dict(),
            "locked_settings": sorted(settings_mod.SERVER_LOCKED) if runtime.is_server() else [],
            "soundcloud": self.soundcloud_status(),
            "update": self.updates.status(),
            "jobs": self.downloads.snapshot(),
            "subscriptions": self.subscriptions.list(),
            "formats": {k: v["label"] for k, v in converter.FORMATS.items()},
        }

    def update_settings(self, patch: dict) -> dict:
        data = self.settings.update(patch)
        self.emit("settings", data)
        return data

    # ── Paths ────────────────────────────────────────────────────────────────

    def roots(self) -> list[Path]:
        return [Path(self.settings["download_dir"]).expanduser().resolve(), UPLOAD_DIR.resolve()]

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
        folder = UPLOAD_DIR / secrets.token_hex(6)
        folder.mkdir(parents=True)
        target = folder / name
        with target.open("wb") as f:
            shutil.copyfileobj(stream, f, 1 << 20)
        return {"path": str(target), "name": name, "size": target.stat().st_size}

    def _clean_uploads(self):
        cutoff = time.time() - UPLOAD_TTL
        for d in UPLOAD_DIR.iterdir():
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
        target = AUDIO_CACHE_DIR / f"{key}.wav"
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

    def samples_url(self, samples: np.ndarray, sr: int) -> str:
        """Write float samples (frames, channels) as a WAV normalised to -1 dBFS."""
        peak = float(np.abs(samples).max()) or 1.0
        pcm = (samples / peak * 0.89 * 32767).astype("<i2")
        key = secrets.token_hex(10)
        target = AUDIO_CACHE_DIR / f"{key}.wav"
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

    # ── Downloads ────────────────────────────────────────────────────────────

    def add_downloads(self, text: str) -> dict:
        urls = list(dict.fromkeys(u.rstrip(").,;]") for u in _URL.findall(text or "")))
        if urls:
            self.downloads.add(urls)
        return {"accepted": len(urls)}

    def search(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        return search_soundcloud(query, 24, {"quiet": True, "no_warnings": True})

    def preview(self, url: str) -> dict:
        return self.previews.resolve(url)

    def history(self) -> list[dict]:
        return dl.read_history()

    # ── Library ──────────────────────────────────────────────────────────────

    def library_list(self) -> dict:
        root = Path(self.settings["download_dir"]).expanduser()
        return {"root": str(root) if not runtime.is_server() else "", "items": self.library.scan(root)}

    def delete_file(self, raw: str) -> None:
        path = self.check_path(raw)
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            raise ValueError("Solo se pueden borrar archivos de audio.")
        path.unlink()
        self.emit("library_changed", {"removed": str(path)})

    # ── SoundCloud account ───────────────────────────────────────────────────

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

    # ── Analysis ─────────────────────────────────────────────────────────────

    def analyze(self, raw: str) -> dict:
        path = self.check_path(raw)
        result = analysis.analyze(path)
        result["audio_url"] = self.playable_url(path)
        return result

    def null_test(self, raw_a: str, raw_b: str) -> dict:
        a, b = self.check_path(raw_a), self.check_path(raw_b)
        report, diff, sr = analysis.null_test(a, b)
        report["audio_url"] = self.samples_url(diff, sr)
        return report

    # ── Converter ────────────────────────────────────────────────────────────

    def convert(self, files: list[str], fmt: str, out_dir: str | None = None,
                normalize_lufs: float | None = None) -> dict:
        if fmt not in converter.FORMATS:
            raise ValueError(fmt)
        paths = [self.check_path(f) for f in files]
        dest = str(self.check_path(out_dir)) if out_dir else None
        batch = secrets.token_hex(4)

        def work():
            for i, src in enumerate(paths):
                self.emit("convert", {"batch": batch, "index": i, "src": str(src), "status": "running"})
                try:
                    res = converter.convert_one(str(src), fmt, dest, normalize_lufs)
                    self.emit("convert", {"batch": batch, "index": i, "status": "done", **res})
                except Exception as e:
                    self.emit("convert", {"batch": batch, "index": i, "src": str(src),
                                          "status": "error", "error": str(e)})
            self.emit("convert", {"batch": batch, "status": "finished"})

        threading.Thread(target=work, daemon=True).start()
        return {"started": len(paths), "batch": batch}

    # ── Maintenance ──────────────────────────────────────────────────────────

    def update_ytdlp(self) -> dict:
        return ytdlp_loader.update()
