import re
from pathlib import Path

import numpy as np

from .. import ffmpeg

MAX_SECONDS = 20 * 60  # analysis cap; keeps memory under ~500 MB for stereo 48 kHz

LOSSLESS_CODECS = {"pcm", "flac", "alac", "aiff", "wav", "wavpack", "ape", "tta"}


def probe(path: str | Path) -> dict:
    """Container/codec facts. mutagen first (exact), ffmpeg's banner as fallback."""
    path = Path(path)
    info = {
        "path": str(path), "name": path.name, "ext": path.suffix.lower().lstrip("."),
        "size": path.stat().st_size, "codec": None, "sample_rate": None,
        "channels": None, "bits": None, "bitrate": None, "duration": None,
    }
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
        if audio is not None:
            a = audio.info
            info["codec"] = getattr(a, "codec", None) or type(audio).__name__.upper()
            info["sample_rate"] = getattr(a, "sample_rate", None)
            info["channels"] = getattr(a, "channels", None)
            info["bits"] = getattr(a, "bits_per_sample", None) or None
            info["bitrate"] = round(a.bitrate / 1000) if getattr(a, "bitrate", 0) else None
            info["duration"] = getattr(a, "length", None)
    except Exception:
        pass

    if not info["sample_rate"] or not info["duration"]:
        out = ffmpeg.run(["-i", str(path)]).stderr.decode("utf-8", "replace")
        if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", out):
            h, mnt, s = m.groups()
            info["duration"] = int(h) * 3600 + int(mnt) * 60 + float(s)
        if m := re.search(r"Audio: (\w+)[^,]*, (\d+) Hz, ([^,]+)", out):
            info["codec"] = info["codec"] or m.group(1).upper()
            info["sample_rate"] = int(m.group(2))
            info["channels"] = info["channels"] or (1 if "mono" in m.group(3) else 2)
        if m := re.search(r"Audio:.*?(\d+) kb/s", out):
            info["bitrate"] = info["bitrate"] or int(m.group(1))

    codec = (info["codec"] or "").lower()
    info["lossless_container"] = info["ext"] in {"wav", "flac", "aif", "aiff"} or any(
        c in codec for c in LOSSLESS_CODECS
    )
    return info


def decode(path: str | Path, sample_rate: int, channels: int = 2,
           max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Decode anything ffmpeg understands to float32, shape (frames, channels)."""
    res = ffmpeg.run([
        "-v", "error", "-i", str(path), "-t", str(max_seconds),
        "-map", "0:a:0", "-ac", str(channels), "-ar", str(sample_rate),
        "-f", "f32le", "pipe:1",
    ])
    if res.returncode != 0 and not res.stdout:
        raise RuntimeError(res.stderr.decode("utf-8", "replace").strip() or "ffmpeg no ha podido leer el archivo.")
    return np.frombuffer(res.stdout, dtype=np.float32).reshape(-1, channels)
