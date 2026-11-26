"""Batch conversion, keeping tags and artwork. The only place where audio is
re-encoded on purpose (see CONTRIBUTING › principios)."""
import secrets
import threading
from pathlib import Path

from ... import ffmpeg
from ...audio import tagging
from ...audio.decode import probe

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


def _normalize_filter(src: Path, info: dict, target_lufs: float) -> tuple[list[str], str]:
    """Static gain to hit target_lufs; a limiter only if the peaks would clip."""
    from ...audio import decode, loudness

    sr = min(info.get("sample_rate") or 44_100, 96_000)
    m = loudness.measure(decode.decode(src, sr, channels=2), sr)
    if m["integrated_lufs"] is None:
        return [], "No se ha podido medir el loudness; se convierte sin normalizar."
    gain = target_lufs - m["integrated_lufs"]
    chain = [f"volume={gain:.2f}dB"]
    note = f"Normalizado de {m['integrated_lufs']:.1f} a {target_lufs:.1f} LUFS ({gain:+.1f} dB)"
    if m["true_peak_dbtp"] is not None and m["true_peak_dbtp"] + gain > -1.0:
        chain.append("alimiter=limit=0.891:level=false:attack=1:release=50")
        note += "; limitador a -1 dBTP"
    return ["-af", ",".join(chain)], note


def convert_one(src: str, fmt: str, out_dir: str | None, normalize_lufs: float | None = None) -> dict:
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

    filters, note = [], None
    if normalize_lufs is not None:
        filters, note = _normalize_filter(src_path, info, float(normalize_lufs))
        if not filters:
            warning, note = f"{warning + ' ' if warning else ''}{note}", None

    tmp = dest.with_name(dest.stem + ".part" + dest.suffix)
    res = ffmpeg.run(["-v", "error", "-y", "-i", str(src_path), "-map", "0:a:0",
                      "-map_metadata", "-1", *filters, *_codec_args(fmt, info.get("bits")), str(tmp)])
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
    return {"src": str(src_path), "dest": str(dest), "warning": warning, "note": note}


class ConvertService:
    def __init__(self, ctx):
        self.ctx = ctx

    def state(self) -> dict:
        return {"formats": {k: v["label"] for k, v in FORMATS.items()}}

    def convert(self, paths: list[Path], fmt: str, dest: Path | None = None,
                normalize_lufs: float | None = None) -> dict:
        """Runs in the background; reports convert.progress events per file
        and one with status "finished" for the batch."""
        if fmt not in FORMATS:
            raise ValueError(f"Formato desconocido: {fmt}")
        batch = secrets.token_hex(4)
        emit = self.ctx.emit

        def work():
            for i, src in enumerate(paths):
                emit("progress", {"batch": batch, "index": i, "src": str(src), "status": "running"})
                try:
                    res = convert_one(str(src), fmt, str(dest) if dest else None, normalize_lufs)
                    emit("progress", {"batch": batch, "index": i, "status": "done", **res})
                except Exception as e:
                    emit("progress", {"batch": batch, "index": i, "src": str(src),
                                      "status": "error", "error": str(e)})
            emit("progress", {"batch": batch, "status": "finished"})

        threading.Thread(target=work, daemon=True, name=f"convert-{batch}").start()
        return {"started": len(paths), "batch": batch}
