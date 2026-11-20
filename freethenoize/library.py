"""Index of the music folder: tags, duration, BPM/key and cover thumbnails."""
import hashlib
import io
import os
import threading
from pathlib import Path

from .paths import COVER_CACHE_DIR

AUDIO_EXTS = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".m4a", ".aac", ".opus", ".ogg", ".alac"}
MAX_FILES = 20_000


class Library:
    def __init__(self):
        self._cache: dict[str, tuple[tuple, dict]] = {}
        self._lock = threading.Lock()
        COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def scan(self, root: str | Path) -> list[dict]:
        root = Path(root).expanduser()
        if not root.is_dir():
            return []
        out = []
        seen = set()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith(".") or ".part" in name:
                    continue
                p = Path(dirpath) / name
                if p.suffix.lower() not in AUDIO_EXTS:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                key = str(p)
                seen.add(key)
                sig = (st.st_mtime_ns, st.st_size)
                with self._lock:
                    hit = self._cache.get(key)
                if hit and hit[0] == sig:
                    entry = hit[1]
                else:
                    entry = _read_entry(p, st)
                    with self._lock:
                        self._cache[key] = (sig, entry)
                out.append({**entry, "rel": str(p.relative_to(root))})
                if len(out) >= MAX_FILES:
                    break
        with self._lock:
            for k in list(self._cache):
                if k not in seen and k.startswith(str(root)):
                    del self._cache[k]
        out.sort(key=lambda e: e["mtime"], reverse=True)
        return out

    def cover(self, path: str | Path, size: int = 300) -> Path | None:
        """A small JPEG of the embedded artwork, cached on disk."""
        p = Path(path)
        st = p.stat()
        key = hashlib.sha1(f"{p}|{st.st_mtime_ns}|{size}".encode()).hexdigest()[:24]
        target = COVER_CACHE_DIR / f"{key}.jpg"
        if target.exists():
            return target
        miss = target.with_suffix(".none")
        if miss.exists():
            return None
        from .downloads.tagging import read_tags

        try:
            _, data = read_tags(p)
        except Exception:
            data = None
        if not data:
            miss.touch()
            return None
        from PIL import Image

        try:
            with Image.open(io.BytesIO(data)) as img:
                img = img.convert("RGB")
                img.thumbnail((size, size), Image.LANCZOS)
                img.save(target, "JPEG", quality=85)
        except Exception:
            miss.touch()
            return None
        return target


def _read_entry(p: Path, st: os.stat_result) -> dict:
    entry = {
        "path": str(p), "name": p.name, "ext": p.suffix.lower().lstrip("."),
        "size": st.st_size, "mtime": st.st_mtime,
        "title": p.stem, "artist": "", "album": "", "duration": None,
        "bpm": None, "key": None, "bitrate": None, "sample_rate": None, "bits": None,
    }
    try:
        from mutagen import File as MutagenFile

        from .downloads.tagging import read_tags

        audio = MutagenFile(p)
        if audio is not None:
            a = audio.info
            entry["duration"] = getattr(a, "length", None)
            entry["sample_rate"] = getattr(a, "sample_rate", None)
            entry["bits"] = getattr(a, "bits_per_sample", None) or None
            br = getattr(a, "bitrate", 0)
            entry["bitrate"] = round(br / 1000) if br else None
        meta, _ = read_tags(p)
        for k in ("title", "artist", "album", "key"):
            if meta.get(k):
                entry[k] = meta[k]
        if meta.get("bpm"):
            try:
                entry["bpm"] = float(meta["bpm"])
            except ValueError:
                pass
    except Exception:
        pass
    return entry
