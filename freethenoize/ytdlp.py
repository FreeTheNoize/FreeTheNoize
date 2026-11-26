"""yt-dlp for the whole app: kept up to date without shipping a new version,
and the base parameters every plugin uses (SoundCloud session included).

SoundCloud and YouTube change often and break yt-dlp. yt-dlp publishes a
pure-Python zipapp on every release; we download it into the user data
directory and, if it is newer than the bundled copy, put it first on
sys.path *before* anything imports yt_dlp.
"""
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from urllib.parse import urlparse

from . import paths

_RELEASES = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version))


def _zip_version(path) -> str | None:
    try:
        with zipfile.ZipFile(path) as z:
            text = z.read("yt_dlp/version.py").decode()
        return re.search(r"__version__\s*=\s*'([^']+)'", text).group(1)
    except Exception:
        return None


class _ZipFirstFinder:
    """Serves every `yt_dlp` module from the downloaded zipapp.

    A plain sys.path entry is not enough: in a PyInstaller build the frozen
    importer sits in sys.meta_path ahead of the path finder and would keep
    returning the bundled (old) copy.
    """

    def __init__(self, zip_path: str):
        self.zip_path = zip_path

    def find_spec(self, name, path=None, target=None):
        if name != "yt_dlp" and not name.startswith("yt_dlp."):
            return None
        from importlib.machinery import PathFinder

        return PathFinder.find_spec(name, path if path else [self.zip_path], target)


def activate() -> None:
    """Call once at startup, before importing yt_dlp anywhere."""
    if "yt_dlp" in sys.modules:
        raise RuntimeError("activate() must run before yt_dlp is imported")
    downloaded = _zip_version(paths.YTDLP_ZIP) if paths.YTDLP_ZIP.exists() else None
    if not downloaded:
        return
    try:
        from importlib.metadata import version

        bundled = version("yt-dlp")
    except Exception:
        bundled = "0"
    if _version_key(downloaded) > _version_key(bundled):
        sys.meta_path.insert(0, _ZipFirstFinder(str(paths.YTDLP_ZIP)))


def current_version() -> str:
    import yt_dlp.version

    return yt_dlp.version.__version__


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "FreeTheNoize"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def update() -> dict:
    """Download the latest yt-dlp zipapp. Takes effect on the next launch."""
    release = json.loads(_get(_RELEASES))
    latest = release["tag_name"]
    if _version_key(latest) <= _version_key(current_version()):
        return {"updated": False, "version": current_version()}

    assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
    payload = _get(assets["yt-dlp"])
    sums = _get(assets["SHA2-256SUMS"]).decode()
    expected = next(
        line.split()[0] for line in sums.splitlines() if line.split()[-1] == "yt-dlp"
    )
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError("La descarga de yt-dlp no coincide con su checksum.")

    tmp = paths.YTDLP_ZIP.with_suffix(".tmp")
    tmp.write_bytes(payload)
    if _zip_version(tmp) is None:
        tmp.unlink()
        raise RuntimeError("El archivo de yt-dlp descargado no es válido.")
    tmp.replace(paths.YTDLP_ZIP)
    return {"updated": True, "version": latest, "restart_required": True}


# ── Parameters shared by every plugin ────────────────────────────────────────

def _on_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def source_of(url: str) -> str:
    """Which site a URL belongs to, by its real hostname (not a substring:
    evil.com/?soundcloud.com and soundcloud.com.evil.com are "other")."""
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return "other"
    if _on_domain(host, "soundcloud.com") or host == "snd.sc":
        return "soundcloud"
    if _on_domain(host, "youtube.com") or host == "youtu.be":
        return "youtube"
    return "other"


def base_params(url: str = "") -> dict:
    """YoutubeDL params with ffmpeg and, for SoundCloud, the user's session."""
    from . import ffmpeg, settings

    params = {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "ffmpeg_location": ffmpeg.FFMPEG,
        "retries": 5,
        "fragment_retries": 10,
        "socket_timeout": 30,
    }
    if source_of(url) == "soundcloud" and (token := settings.get_token()):
        params["username"] = "oauth"
        params["password"] = token
    return params
