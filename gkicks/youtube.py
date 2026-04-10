"""YouTube / YouTube Music downloader using yt-dlp."""
import sys
import subprocess
import threading
from pathlib import Path

from .downloader import FFMPEG_EXE, build_env


def get_ytdlp_cmd() -> list:
    if getattr(sys, "frozen", False):
        ytdlp = Path(sys._MEIPASS) / "yt-dlp.exe"
        if ytdlp.exists():
            return [str(ytdlp)]
    return [sys.executable, "-m", "yt_dlp"]


def build_ytdlp_cmd(state: dict) -> list:
    url    = state["url"].get().strip()
    dest   = state["dest"].get().strip()
    source = state["source"].get()
    fmt    = state["fmt"].get()

    cmd = get_ytdlp_cmd()

    # Output template: "Artist - Title.ext" or fall back to title
    out_tmpl = str(Path(dest) / "%(artist,uploader)s - %(title)s.%(ext)s")
    cmd += ["--output", out_tmpl]

    if FFMPEG_EXE:
        cmd += ["--ffmpeg-location", FFMPEG_EXE.replace("\\", "/")]

    # YouTube Music: request the music client for better metadata
    if source == "ytmusic":
        cmd += ["--extractor-args", "youtube:player-client=web_music"]

    # Audio format
    if fmt in ("onlymp3",):
        cmd += ["-x", "--audio-format", "mp3"]
        q = state.get("mp3_quality")
        if q and q.get() not in ("0", ""):
            cmd += ["--audio-quality", q.get()]
    elif fmt == "wav":
        cmd += ["-x", "--audio-format", "wav", "--audio-quality", "0"]
    elif fmt == "flac":
        cmd += ["-x", "--audio-format", "flac"]
    elif fmt == "opus":
        cmd += ["-x", "--audio-format", "opus"]
    elif fmt in ("m4a", "alac"):
        cmd += ["-x", "--audio-format", "m4a"]
    else:
        # default / only_original / no_original → best audio, keep container
        cmd += ["-f", "bestaudio/best"]

    # Artwork
    if state.get("embed_thumbnail") and state["embed_thumbnail"].get():
        cmd += ["--embed-thumbnail", "--convert-thumbnails", "png"]
    if state.get("write_thumbnail") and state["write_thumbnail"].get():
        cmd += ["--write-thumbnail"]

    # Metadata
    if state.get("embed_metadata") and state["embed_metadata"].get():
        cmd += ["--embed-metadata"]
    if state.get("addtimestamp") and state["addtimestamp"].get():
        cmd += ["--add-metadata"]

    # Download archive
    if state.get("dl_archive") and state["dl_archive"].get().strip():
        cmd += ["--download-archive", state["dl_archive"].get().strip()]

    # Extra yt-dlp args from the Advanced tab
    if state.get("ytdlp_args") and state["ytdlp_args"].get().strip():
        import shlex
        cmd += shlex.split(state["ytdlp_args"].get().strip())

    # No-overwite / continue flags
    if state.get("continue_dl") and state["continue_dl"].get():
        cmd += ["--no-overwrites"]
    if state.get("overwrite") and state["overwrite"].get():
        cmd += ["--force-overwrites"]

    cmd.append(url)
    return cmd


def run_ytdlp(cmd: list, on_line, on_done, on_proc=None):
    def _worker():
        msg = "Unknown error."
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
            msg = ("Download completed."
                   if proc.returncode == 0
                   else f"Process exited with code {proc.returncode}.")
        except FileNotFoundError:
            msg = "yt-dlp not found — install with: pip install yt-dlp"
            on_line(msg)
        except Exception as e:
            msg = f"Error: {e}"
            on_line(msg)
        finally:
            if on_proc:
                on_proc(None)
        on_done(msg)

    threading.Thread(target=_worker, daemon=True).start()
