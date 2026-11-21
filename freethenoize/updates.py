"""New-version check against the GitHub releases of the project.

Desktop: finds the zip for this OS/CPU and downloads it (asking first, or on
its own if `auto_download_updates` is on) into the Downloads folder.
Server: only reports the new version; updating means pulling the new image.
"""
import json
import platform
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

from platformdirs import user_downloads_path

from . import __version__, runtime

REPO = "quim-d/FreeTheNoize"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 6 * 3600
FIRST_CHECK_DELAY = 8


def version_tuple(v: str) -> tuple:
    parts = []
    for p in (v or "").lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def asset_name() -> str | None:
    """Name of the release zip that runs on this machine."""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "FreeTheNoize-macOS-AppleSilicon.zip" if machine in ("arm64", "aarch64") \
            else "FreeTheNoize-macOS-Intel.zip"
    if sys.platform == "win32":
        return "FreeTheNoize-Windows-x64.zip"
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "FreeTheNoize-Linux-x64.zip"
    return None


class Updater:
    def __init__(self, settings, emit: Callable[[str, dict], None]):
        self.settings = settings
        self.emit = emit
        self.info: dict | None = None          # last successful check
        self.download: dict = {"state": "idle"}  # idle | downloading | ready | error
        self._stop = threading.Event()
        self._dl_lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="updates").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        if self._stop.wait(FIRST_CHECK_DELAY):
            return
        while True:
            if self.settings["check_updates"]:
                try:
                    self.check()
                except Exception:
                    pass
            if self._stop.wait(CHECK_EVERY):
                return

    # ── Public ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {"current": __version__, "info": self.info, "download": self.download,
                "can_download": not runtime.is_server() and bool(self.info and self.info.get("asset"))}

    def check(self) -> dict:
        req = urllib.request.Request(API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"FreeTheNoize/{__version__}",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.load(r)
        latest = rel.get("tag_name", "").lstrip("vV")
        want = asset_name()
        asset = next(({"name": a["name"], "url": a["browser_download_url"], "size": a.get("size")}
                      for a in rel.get("assets") or [] if a.get("name") == want), None)
        self.info = {
            "latest": latest,
            "newer": version_tuple(latest) > version_tuple(__version__),
            "notes": (rel.get("body") or "").strip()[:4000],
            "page": rel.get("html_url"),
            "published": rel.get("published_at"),
            "asset": asset,
            "checked": time.time(),
            "skipped": self.settings["skipped_version"] == latest,
        }
        if self.info["newer"]:
            self.emit("update_available", self.status())
            if (self.settings["auto_download_updates"] and not runtime.is_server()
                    and asset and not self.info["skipped"]):
                self.start_download()
        return self.status()

    def skip(self) -> dict:
        if self.info:
            self.settings.update({"skipped_version": self.info["latest"]})
            self.info["skipped"] = True
        return self.status()

    def start_download(self) -> dict:
        if runtime.is_server():
            raise ValueError("En el servicio web se actualiza la imagen de Docker, no la app.")
        if not (self.info and self.info.get("newer") and self.info.get("asset")):
            raise ValueError("No hay ninguna versión nueva para este sistema.")
        with self._dl_lock:
            if self.download["state"] == "downloading":
                return self.status()
            self.download = {"state": "downloading", "done": 0, "total": self.info["asset"]["size"]}
        threading.Thread(target=self._download, daemon=True, name="update-dl").start()
        return self.status()

    # ── Internals ────────────────────────────────────────────────────────────

    def _download(self):
        asset = self.info["asset"]
        folder = user_downloads_path()
        folder.mkdir(parents=True, exist_ok=True)
        stem = Path(asset["name"]).stem
        dest = folder / f"{stem}-{self.info['latest']}.zip"
        part = dest.with_suffix(".zip.part")
        try:
            req = urllib.request.Request(asset["url"], headers={"User-Agent": f"FreeTheNoize/{__version__}"})
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or asset["size"] or 0)
                done, last = 0, 0.0
                while chunk := r.read(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.25:
                        last = now
                        self.download = {"state": "downloading", "done": done, "total": total}
                        self.emit("update_progress", self.download)
            part.replace(dest)
            self.download = {"state": "ready", "path": str(dest), "done": done, "total": total}
        except Exception as e:
            part.unlink(missing_ok=True)
            self.download = {"state": "error", "error": str(e)[:200]}
        self.emit("update_progress", self.download)
