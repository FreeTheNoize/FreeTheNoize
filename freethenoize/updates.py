"""New-version check against the GitHub releases of the project.

Desktop: finds the download for this OS/CPU (asking first, or on its own if
`auto_download_updates` is on) and checks it against the release SHA256SUMS.
- Windows, installed with the installer: downloads the new installer to the
  cache and "install and restart" runs it silently; it replaces the files
  in place and opens the app again.
- Otherwise (portable zip, macOS, Linux): saves it to the Downloads folder.
Server: only reports the new version; updating means pulling the new image.
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

from platformdirs import user_downloads_path

from . import __version__, runtime

REPO = "FreeTheNoize/FreeTheNoize"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 6 * 3600
FIRST_CHECK_DELAY = 8


def version_tuple(v: str) -> tuple:
    parts = []
    for p in (v or "").lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{53AEF833-7AED-4A46-A2C1-DEF78E1A0189}_is1"
SUMS = "SHA256SUMS.txt"


def installed_with_setup() -> bool:
    """Windows: this exe is the one the installer put there (not a portable zip)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            location = winreg.QueryValueEx(k, "InstallLocation")[0]
    except OSError:
        return False
    return os.path.normcase(os.path.abspath(location)).rstrip("\\") == \
        os.path.normcase(os.path.dirname(os.path.abspath(sys.executable)))


def asset_name() -> str | None:
    """Name of the release file that updates this install."""
    machine = platform.machine().lower()
    if installed_with_setup():
        return "FreeTheNoize-Windows-x64-Setup.exe"
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
        self.on_quit: Callable[[], None] | None = None  # set by the desktop app
        self.pending_install: str | None = None

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
                "can_download": not runtime.is_server() and bool(self.info and self.info.get("asset")),
                "can_install": self.download.get("state") == "ready" and bool(self.download.get("installer"))}

    def install(self) -> dict:
        """Run the downloaded installer once the app has closed (Windows)."""
        if not self.status()["can_install"]:
            raise ValueError("No hay ninguna actualización lista para instalar.")
        self.pending_install = self.download["path"]
        if self.on_quit:
            threading.Timer(0.3, self.on_quit).start()  # let the HTTP answer go first
        return self.status()

    def run_pending_install(self) -> bool:
        """Called by the desktop app after its window closed and it let go of
        its single-instance lock. Setup closes what is left (Restart Manager),
        replaces the files and opens the app again (/UPDATE=1)."""
        path = getattr(self, "pending_install", None)
        if not path or sys.platform != "win32":
            return False
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
                          "/FORCECLOSEAPPLICATIONS", "/UPDATE=1"], creationflags=flags, close_fds=True)
        return True

    def check(self) -> dict:
        req = urllib.request.Request(API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"FreeTheNoize/{__version__}",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.load(r)
        latest = rel.get("tag_name", "").lstrip("vV")
        want = asset_name()
        assets = rel.get("assets") or []
        asset = next(({"name": a["name"], "url": a["browser_download_url"], "size": a.get("size")}
                      for a in assets if a.get("name") == want), None)
        sums = next((a["browser_download_url"] for a in assets if a.get("name") == SUMS), None)
        self.info = {
            "latest": latest,
            "newer": version_tuple(latest) > version_tuple(__version__),
            "notes": (rel.get("body") or "").strip()[:4000],
            "page": rel.get("html_url"),
            "published": rel.get("published_at"),
            "asset": asset,
            "sums": sums,
            "installer": installed_with_setup(),
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

    def _expected_sha256(self, name: str) -> str | None:
        if not self.info.get("sums"):
            return None
        req = urllib.request.Request(self.info["sums"], headers={"User-Agent": f"FreeTheNoize/{__version__}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == name:
                    return parts[0].lower()
        return None

    def _download(self):
        asset = self.info["asset"]
        installer = bool(self.info.get("installer"))
        if installer:
            from .paths import CACHE_DIR

            folder = CACHE_DIR / "updates"  # never run from Downloads: no download mark, no clutter
        else:
            folder = user_downloads_path()
        folder.mkdir(parents=True, exist_ok=True)
        name = Path(asset["name"])
        dest = folder / f"{name.stem}-{self.info['latest']}{name.suffix}"
        part = dest.with_name(dest.name + ".part")
        try:
            req = urllib.request.Request(asset["url"], headers={"User-Agent": f"FreeTheNoize/{__version__}"})
            sha = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or asset["size"] or 0)
                done, last = 0, 0.0
                while chunk := r.read(256 * 1024):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.25:
                        last = now
                        self.download = {"state": "downloading", "done": done, "total": total}
                        self.emit("update_progress", self.download)
            expected = self._expected_sha256(asset["name"])
            if expected and expected != sha.hexdigest():
                raise ValueError("la descarga no coincide con el SHA256 publicado en la release")
            if installer and not expected:
                raise ValueError("la release no publica el SHA256 del instalador")
            part.replace(dest)
            self.download = {"state": "ready", "path": str(dest), "done": done, "total": total,
                             "installer": installer}
        except Exception as e:
            part.unlink(missing_ok=True)
            self.download = {"state": "error", "error": str(e)[:200]}
        self.emit("update_progress", self.download)
