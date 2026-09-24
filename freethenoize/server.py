"""Loopback HTTP server for the UI and for audio playback.

Serving the UI and the audio from the same origin lets the page fetch audio
for Web Audio (A/B switching) without CORS. Audio is always transcoded to
16-bit WAV first so playback works whatever the codec, on WebKit and WebView2.
"""
import hashlib
import mimetypes
import re
import secrets
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from . import ffmpeg
from .paths import AUDIO_CACHE_DIR, UI_DIR

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class LocalServer:
    def __init__(self):
        self.token = secrets.token_urlsafe(16)
        self._audio: dict[str, Path] = {}
        self._lock = threading.Lock()
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for old in AUDIO_CACHE_DIR.glob("*.wav"):
            old.unlink(missing_ok=True)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.httpd.daemon_threads = True

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()

    # ── Audio registry ────────────────────────────────────────────────────────

    def audio_url_for(self, source: str | Path) -> str:
        source = Path(source)
        st = source.stat()
        key = hashlib.sha1(f"{source}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20]
        target = AUDIO_CACHE_DIR / f"{key}.wav"
        if not target.exists():
            tmp = target.with_suffix(".part.wav")
            res = ffmpeg.run(["-v", "error", "-y", "-i", str(source), "-map", "0:a:0",
                              "-ac", "2", "-c:a", "pcm_s16le", str(tmp)])
            if res.returncode != 0:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(res.stderr.decode("utf-8", "replace").strip())
            tmp.replace(target)
        with self._lock:
            self._audio[key] = target
        return f"{self.url}/audio/{self.token}/{key}.wav"

    def audio_url_for_samples(self, samples: np.ndarray, sr: int, name: str) -> str:
        """Write float samples (frames, channels) as a WAV normalised to -1 dBFS."""
        peak = float(np.abs(samples).max()) or 1.0
        pcm = (samples / peak * 0.89 * 32767).astype("<i2")
        key = hashlib.sha1(f"{name}|{secrets.token_hex(4)}".encode()).hexdigest()[:20]
        target = AUDIO_CACHE_DIR / f"{key}.wav"
        with wave.open(str(target), "wb") as w:
            w.setnchannels(samples.shape[1])
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        with self._lock:
            self._audio[key] = target
        return f"{self.url}/audio/{self.token}/{key}.wav"

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[0] == "audio":
                    if not secrets.compare_digest(parts[1], server.token):
                        return self.send_error(403)
                    with server._lock:
                        file = server._audio.get(parts[2].removesuffix(".wav"))
                    return self._send_file(file, "audio/wav") if file else self.send_error(404)

                rel = path.lstrip("/") or "index.html"
                file = (UI_DIR / rel).resolve()
                if not file.is_relative_to(UI_DIR.resolve()) or not file.is_file():
                    return self.send_error(404)
                ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                self._send_file(file, ctype, cache=False)

            def _send_file(self, file: Path, ctype: str, cache: bool = True):
                size = file.stat().st_size
                start, end = 0, size - 1
                if m := _RANGE.fullmatch(self.headers.get("Range", "")):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else end
                    elif m.group(2):
                        start = size - int(m.group(2))
                    end = min(end, size - 1)
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        return self.end_headers()
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                else:
                    self.send_response(200)
                length = end - start + 1
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
                self.end_headers()
                with file.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(1 << 16, remaining))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        remaining -= len(chunk)

        return Handler
