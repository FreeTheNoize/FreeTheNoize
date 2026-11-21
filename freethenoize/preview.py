"""Listen to a track before downloading it.

yt-dlp resolves the stream (with the SoundCloud session, so Go+ users hear
the full track), and ffmpeg re-encodes it on the fly to MP3, which every
browser can play, whatever SoundCloud serves (progressive MP3, HLS AAC/Opus).
Seeking restarts ffmpeg at the requested second (`?t=`).
"""
import secrets
import subprocess
import threading
import time
from typing import Callable, Iterator

from . import ffmpeg

# Progressive HTTP first: it starts and seeks faster than HLS.
FORMAT = "bestaudio[protocol=http]/bestaudio[protocol=https]/bestaudio/best"
STREAM_TTL = 240     # SoundCloud's signed stream URLs expire; re-resolve after this
ENTRY_TTL = 3600     # forget previews nobody has played for an hour
CHUNK = 32 * 1024


class Previews:
    def __init__(self, params_for: Callable[[str], dict]):
        self._params_for = params_for
        self._entries: dict[str, dict] = {}
        self._lock = threading.Lock()

    def resolve(self, page_url: str) -> dict:
        page_url = (page_url or "").strip()
        if not page_url.startswith(("https://", "http://")):
            raise ValueError("Pega el enlace de un tema.")
        info = self._extract(page_url)
        pid = secrets.token_urlsafe(9)
        with self._lock:
            now = time.monotonic()
            for k in [k for k, e in self._entries.items() if now - e["used"] > ENTRY_TTL]:
                del self._entries[k]
            self._entries[pid] = {"page": page_url, "info": info, "at": now, "used": now}
        thumbs = info.get("thumbnails") or []
        return {
            "id": pid,
            "url": f"/api/preview/{pid}.mp3",
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail") or (thumbs[-1]["url"] if thumbs else None),
            "snippet": bool(info.get("_ftn_snippet")),
        }

    def _extract(self, page_url: str) -> dict:
        from yt_dlp import YoutubeDL

        params = {**self._params_for(page_url), "format": FORMAT, "noplaylist": True, "extract_flat": "in_playlist",
                  "quiet": True, "no_warnings": True}
        from yt_dlp.utils import DownloadError

        try:
            with YoutubeDL(params) as ydl:
                info = ydl.extract_info(page_url, download=False)
        except DownloadError as e:
            raise ValueError(str(e).removeprefix("ERROR: ")[:200]) from None
        if info.get("_type") == "playlist" or info.get("entries") is not None:
            raise ValueError("Solo se pueden pre-escuchar temas sueltos, no listas.")
        fmt = info.get("requested_formats", [info])[0] if info.get("requested_formats") else info
        if not fmt.get("url"):
            raise ValueError("SoundCloud no da audio para este tema.")
        info["_ftn_stream"] = fmt["url"]
        info["_ftn_headers"] = fmt.get("http_headers") or info.get("http_headers") or {}
        info["_ftn_snippet"] = "preview" in (fmt.get("format_id") or "")
        return info

    def stream(self, pid: str, start: float = 0.0) -> Iterator[bytes]:
        with self._lock:
            entry = self._entries.get(pid)
        if not entry:
            raise KeyError(pid)
        if time.monotonic() - entry["at"] > STREAM_TTL:
            entry["info"] = self._extract(entry["page"])
            entry["at"] = time.monotonic()
        entry["used"] = time.monotonic()
        info = entry["info"]
        headers = "".join(f"{k}: {v}\r\n" for k, v in info["_ftn_headers"].items())
        args = [ffmpeg.require_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error"]
        if start > 0:
            args += ["-ss", f"{start:.2f}"]
        if headers:
            args += ["-headers", headers]
        args += ["-i", info["_ftn_stream"], "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
                 "-f", "mp3", "pipe:1"]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=ffmpeg.NO_WINDOW)
        return self._pump(proc)

    @staticmethod
    def _pump(proc: subprocess.Popen) -> Iterator[bytes]:
        try:
            while chunk := proc.stdout.read(CHUNK):
                yield chunk
        finally:  # also runs when the browser stops listening
            proc.kill()
            proc.wait()
