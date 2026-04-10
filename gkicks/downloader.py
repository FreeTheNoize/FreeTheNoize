import sys
import os
import subprocess
from pathlib import Path


def _find_ffmpeg() -> tuple[str | None, str | None, str | None]:
    """Returns (exe_path, dir_path, error_str)."""
    # Frozen bundle: ffmpeg.exe is in _MEIPASS root
    if getattr(sys, "frozen", False):
        exe = Path(sys._MEIPASS) / "ffmpeg.exe"
        if exe.exists():
            return str(exe), str(exe.parent), None
        return None, None, f"ffmpeg.exe not found in {sys._MEIPASS}"
    # Dev: use imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe, str(Path(exe).parent), None
    except Exception as e:
        return None, None, str(e)


FFMPEG_EXE, FFMPEG_DIR, FFMPEG_ERR = _find_ffmpeg()


def get_scdl_cmd() -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable, "___RUN_SCDL___"]
    return [sys.executable, "-m", "scdl"]


SCDL_EXE = get_scdl_cmd()


def build_env() -> dict:
    env = os.environ.copy()
    if FFMPEG_DIR:
        env["PATH"] = FFMPEG_DIR + os.pathsep + env.get("PATH", "")
    return env


def run_download(cmd: list, on_line, on_done, on_proc=None):
    import threading

    def _worker():
        msg = "Error desconegut."
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=build_env(),
            )
            if on_proc:
                on_proc(proc)
            for line in proc.stdout:
                on_line(line.rstrip())
            proc.wait()
            msg = ("Descàrrega completada."
                   if proc.returncode == 0
                   else f"El procés ha acabat amb el codi {proc.returncode}.")
        except FileNotFoundError:
            msg = "scdl no trobat."
            on_line(msg)
        except Exception as e:
            msg = f"Error: {e}"
            on_line(msg)
        finally:
            if on_proc:
                on_proc(None)
        on_done(msg)

    threading.Thread(target=_worker, daemon=True).start()
