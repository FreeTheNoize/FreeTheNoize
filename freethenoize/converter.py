"""Batch conversion, keeping tags and artwork."""
from pathlib import Path

from . import ffmpeg
from .analysis.decode import probe
from .downloads import tagging

FORMATS = {
    "wav":  {"label": "WAV",  "ext": ".wav",  "lossless": True},
    "aiff": {"label": "AIFF", "ext": ".aiff", "lossless": True},
    "flac": {"label": "FLAC", "ext": ".flac", "lossless": True},
    "mp3":  {"label": "MP3 320", "ext": ".mp3", "lossless": False},
    "m4a":  {"label": "AAC 256", "ext": ".m4a", "lossless": False},
}


def _codec_args(fmt: str, bits: int | None) -> list[str]:
    pcm = "24" if bits and bits > 16 else "16"
    return {
        "wav":  ["-c:a", f"pcm_s{pcm}le"],
        "aiff": ["-c:a", f"pcm_s{pcm}be"],
        "flac": ["-c:a", "flac", "-sample_fmt", "s32" if pcm == "24" else "s16"],
        "mp3":  ["-c:a", "libmp3lame", "-b:a", "320k"],
        "m4a":  ["-c:a", "aac", "-b:a", "256k"],
    }[fmt]


def convert_one(src: str, fmt: str, out_dir: str | None) -> dict:
    src_path = Path(src)
    spec = FORMATS[fmt]
    info = probe(src_path)
    dest_dir = Path(out_dir) if out_dir else src_path.parent
    dest = dest_dir / (src_path.stem + spec["ext"])
    if dest.resolve() == src_path.resolve():
        dest = dest_dir / f"{src_path.stem} (convertido){spec['ext']}"

    warning = None
    if spec["lossless"] and not info["lossless_container"]:
        warning = ("El original tiene pérdida: el archivo ocupará más, "
                   "pero no sonará mejor.")

    tmp = dest.with_name(dest.stem + ".part" + dest.suffix)
    res = ffmpeg.run(["-v", "error", "-y", "-i", str(src_path), "-map", "0:a:0",
                      "-map_metadata", "-1", *_codec_args(fmt, info.get("bits")), str(tmp)])
    if res.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(res.stderr.decode("utf-8", "replace").strip() or "ffmpeg ha fallado")
    try:
        meta, cover = tagging.read_tags(src_path)
        if meta or cover:
            tagging.write_tags(tmp, meta, cover)
    except Exception as e:
        warning = f"{warning + ' ' if warning else ''}No se han copiado las etiquetas: {e}"
    tmp.replace(dest)
    return {"src": str(src_path), "dest": str(dest), "warning": warning}
