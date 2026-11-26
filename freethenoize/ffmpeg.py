import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _find_ffmpeg() -> str | None:
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    if getattr(sys, "frozen", False):
        for base in (Path(getattr(sys, "_MEIPASS", "")), Path(sys.executable).parent):
            if (base / name).is_file():
                return str(base / name)
    if found := shutil.which("ffmpeg"):
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = _find_ffmpeg()


def require_ffmpeg() -> str:
    if not FFMPEG:
        raise RuntimeError("No se ha encontrado ffmpeg.")
    return FFMPEG


def to_jpeg(data: bytes, max_px: int, quality: int = 2) -> bytes:
    """Re-encode an image (jpeg, png, webp, gif, bmp) as JPEG, no larger
    than max_px on its long side. quality: ffmpeg's -q:v, 2 (best) … 31."""
    box = f"'min(iw,{max_px})':'min(ih,{max_px})'"
    res = run(["-v", "error", "-i", "pipe:0", "-frames:v", "1",
               "-vf", f"scale={box}:force_original_aspect_ratio=decrease:flags=lanczos,format=yuvj420p",
               "-c:v", "mjpeg", "-q:v", str(quality), "-f", "image2pipe", "pipe:1"], input=data)
    if res.returncode != 0 or not res.stdout:
        raise ValueError(res.stderr.decode("utf-8", "replace").strip() or "imagen no válida")
    return res.stdout


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [require_ffmpeg(), "-hide_banner", "-nostdin", *args],
        capture_output=True,
        creationflags=NO_WINDOW,
        **kwargs,
    )
