"""The bridge exposed to JavaScript as `window.pywebview.api`.

pywebview runs every call on its own thread, so slow work (analysis, search)
can simply block here. Anything that must reach the page later goes through
`emit`, which calls `FTN.onEvent(type, payload)` in the page.
"""
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview

from . import __version__, analysis, converter, settings as settings_mod, ytdlp_loader
from .downloads import manager as dl
from .downloads.resolve import search_soundcloud
from .ffmpeg import FFMPEG
from .server import LocalServer

AUDIO_TYPES = ("Audio (*.wav;*.flac;*.aif;*.aiff;*.mp3;*.m4a;*.aac;*.opus;*.ogg)", "Todos (*.*)")
_URL = re.compile(r"https?://\S+")


class Api:
    def __init__(self, server: LocalServer):
        self._server = server
        self._window: webview.Window | None = None
        self._settings = settings_mod.Settings()
        self._downloads = dl.DownloadManager(self._settings, self._emit)
        self._sc_username: str | None = None

    def _attach(self, window: webview.Window):
        self._window = window

    def _emit(self, kind: str, payload: dict):
        if self._window:
            self._window.run_js(
                f"window.FTN && FTN.onEvent({json.dumps(kind)}, {json.dumps(payload, default=str)})"
            )

    # ── App state ─────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "version": __version__,
            "ytdlp_version": ytdlp_loader.current_version(),
            "ffmpeg": FFMPEG,
            "platform": sys.platform,
            "settings": self._settings.as_dict(),
            "soundcloud": self.soundcloud_status(),
            "jobs": self._downloads.snapshot(),
            "formats": {k: v["label"] for k, v in converter.FORMATS.items()},
        }

    def update_settings(self, patch: dict) -> dict:
        return self._settings.update(patch)

    # ── Dialogs & OS integration ──────────────────────────────────────────────

    def choose_folder(self, start: str = "") -> str | None:
        res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start or "")
        return res[0] if res else None

    def choose_audio_files(self, multiple: bool = False) -> list[str]:
        res = self._window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=multiple, file_types=AUDIO_TYPES)
        return list(res or [])

    def reveal(self, path: str):
        p = Path(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)])
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(p)])
        else:
            subprocess.run(["xdg-open", str(p.parent)])

    def open_url(self, url: str):
        if url.startswith(("https://", "http://")):
            import webbrowser

            webbrowser.open(url)

    # ── Downloads ─────────────────────────────────────────────────────────────

    def add_downloads(self, text: str) -> dict:
        urls = list(dict.fromkeys(u.rstrip(").,;]") for u in _URL.findall(text or "")))
        if urls:
            self._downloads.add(urls)
        return {"accepted": len(urls)}

    def cancel_job(self, job_id: int):
        self._downloads.cancel(int(job_id))

    def cancel_all(self):
        self._downloads.cancel_all()

    def retry_job(self, job_id: int):
        self._downloads.retry(int(job_id))

    def clear_finished(self):
        self._downloads.clear_finished()

    def history(self) -> list[dict]:
        return dl.read_history()

    def search(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        return search_soundcloud(query, 20, {"quiet": True, "no_warnings": True})

    # ── SoundCloud account ────────────────────────────────────────────────────

    def soundcloud_status(self) -> dict:
        token = settings_mod.get_token()
        return {"logged_in": bool(token), "username": self._sc_username if token else None}

    def _check_token(self, token: str) -> str | None:
        req = urllib.request.Request(
            "https://api-v2.soundcloud.com/me",
            headers={"Authorization": f"OAuth {token}", "User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("username")
        except Exception:
            return None

    def soundcloud_set_token(self, token: str) -> dict:
        token = (token or "").strip().removeprefix("OAuth ").strip()
        if not re.fullmatch(r"[\w\-.]{10,}", token):
            raise ValueError("Eso no parece un token de SoundCloud.")
        settings_mod.set_token(token)
        self._sc_username = self._check_token(token)
        status = self.soundcloud_status()
        self._emit("soundcloud", status)
        return status

    def soundcloud_login(self) -> dict:
        """Open SoundCloud's sign-in page and grab the oauth_token cookie."""
        login = webview.create_window(
            "Iniciar sesión en SoundCloud", "https://soundcloud.com/signin",
            width=520, height=720)
        closed = threading.Event()
        login.events.closed += lambda *_: closed.set()
        deadline = time.monotonic() + 600
        while not closed.is_set() and time.monotonic() < deadline:
            time.sleep(1.5)
            try:
                cookies = login.get_cookies() or []
            except Exception:
                continue
            for jar in cookies:
                if "oauth_token" in jar:
                    status = self.soundcloud_set_token(jar["oauth_token"].value)
                    login.destroy()
                    return status
        if not closed.is_set():
            login.destroy()
        return self.soundcloud_status()

    def soundcloud_logout(self) -> dict:
        settings_mod.clear_token()
        self._sc_username = None
        status = self.soundcloud_status()
        self._emit("soundcloud", status)
        return status

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze(self, path: str) -> dict:
        result = analysis.analyze(path)
        result["audio_url"] = self._server.audio_url_for(path)
        return result

    def null_test(self, path_a: str, path_b: str) -> dict:
        report, diff, sr = analysis.null_test(path_a, path_b)
        report["audio_url"] = self._server.audio_url_for_samples(diff, sr, "diff")
        return report

    # ── Converter ─────────────────────────────────────────────────────────────

    def convert(self, files: list[str], fmt: str, out_dir: str | None = None) -> dict:
        if fmt not in converter.FORMATS:
            raise ValueError(fmt)

        def work():
            for i, src in enumerate(files):
                self._emit("convert", {"index": i, "src": src, "status": "running"})
                try:
                    res = converter.convert_one(src, fmt, out_dir or None)
                    self._emit("convert", {"index": i, "status": "done", **res})
                except Exception as e:
                    self._emit("convert", {"index": i, "src": src, "status": "error", "error": str(e)})
            self._emit("convert", {"status": "finished"})

        threading.Thread(target=work, daemon=True).start()
        return {"started": len(files)}

    # ── Maintenance ───────────────────────────────────────────────────────────

    def update_ytdlp(self) -> dict:
        return ytdlp_loader.update()
