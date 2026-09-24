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


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [require_ffmpeg(), "-hide_banner", "-nostdin", *args],
        capture_output=True,
        creationflags=NO_WINDOW,
        **kwargs,
    )
