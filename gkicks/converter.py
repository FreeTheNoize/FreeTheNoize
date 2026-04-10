import subprocess
import threading
from pathlib import Path

from .downloader import FFMPEG_EXE, build_env


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"}

FORMATS = [
    ("mp3",  "MP3"),
    ("wav",  "WAV"),
    ("flac", "FLAC"),
    ("m4a",  "M4A  (AAC)"),
    ("opus", "Opus"),
    ("mp4",  "MP4  (video)"),
]


def _build_cmd(input_path: str, output_path: str, fmt: str, mp3_quality: str) -> list:
    is_video = Path(input_path).suffix.lower() in VIDEO_EXTS
    cmd = [FFMPEG_EXE, "-y"]

    if fmt == "mp4":
        if is_video:
            cmd += ["-i", input_path,
                    "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p"]
        else:
            # audio → MP4 with black video (useful for YouTube uploads, etc.)
            cmd += [
                "-f", "lavfi", "-i", "color=c=black:size=1280x720:rate=25",
                "-i", input_path,
                "-c:v", "libx264", "-c:a", "aac",
                "-shortest", "-pix_fmt", "yuv420p",
            ]
    elif fmt == "mp3":
        cmd += ["-i", input_path, "-vn"]
        cmd += (["-q:a", "0"] if mp3_quality == "0" else ["-b:a", mp3_quality])
    elif fmt == "wav":
        cmd += ["-i", input_path, "-vn"]
    elif fmt == "flac":
        cmd += ["-i", input_path, "-vn", "-c:a", "flac"]
    elif fmt == "m4a":
        cmd += ["-i", input_path, "-vn", "-c:a", "aac", "-b:a", "256k"]
    elif fmt == "opus":
        cmd += ["-i", input_path, "-vn", "-c:a", "libopus", "-b:a", "192k"]

    cmd.append(output_path)
    return cmd


def embed_cover_art(
    files: list,
    image_path: str | None,   # None = auto-detect (same stem, .jpg/.png/…)
    on_line,
    on_done,
):
    """Embed cover art into audio files in-place via ffmpeg ID3/metadata tags.
    Works with WAV (ID3v2), MP3 (ID3v2), FLAC (native), M4A (iTunes).
    Compatible with Traktor, Rekordbox, VirtualDJ.
    """
    def _worker():
        total  = len(files)
        errors = 0
        for i, inp in enumerate(files, 1):
            inp_path = Path(inp)

            if image_path:
                img = Path(image_path)
            else:
                img = None
                for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    candidate = inp_path.with_suffix(ext)
                    if candidate.exists():
                        img = candidate
                        break

            if not img or not img.exists():
                on_line(f"\n[{i}/{total}]  {inp_path.name}")
                on_line("  ✗  Image not found — try selecting it manually.")
                errors += 1
                continue

            on_line(f"\n[{i}/{total}]  {inp_path.name}  ←  {img.name}")

            tmp = inp_path.with_name(inp_path.stem + "__arttmp" + inp_path.suffix)
            ext = inp_path.suffix.lower()
            cmd = [FFMPEG_EXE, "-y",
                   "-i", str(inp_path),
                   "-i", str(img),
                   "-map", "0", "-map", "1",
                   "-c", "copy"]
            if ext != ".flac":
                cmd += ["-id3v2_version", "3"]
            cmd.append(str(tmp))

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
                for line in proc.stdout:
                    stripped = line.rstrip()
                    if stripped:
                        on_line(stripped)
                proc.wait()
                if proc.returncode == 0:
                    inp_path.unlink()
                    tmp.rename(inp_path)
                    on_line(f"  ✓  {inp_path.name}")
                else:
                    on_line(f"  ✗  Error (code {proc.returncode})")
                    if tmp.exists():
                        tmp.unlink()
                    errors += 1
            except Exception as e:
                on_line(f"  ✗  {e}")
                if tmp.exists():
                    tmp.unlink()
                errors += 1

        ok  = total - errors
        msg = (f"Cover art embedded — {ok}/{total} file(s)."
               if ok > 0 else "All files failed.")
        on_done(msg)

    threading.Thread(target=_worker, daemon=True).start()


def run_conversion(
    files: list,
    out_dir: str | None,       # None = same folder as each input file
    fmt: str,
    mp3_quality: str,
    on_line,
    on_done,
):
    def _worker():
        total  = len(files)
        errors = 0
        for i, inp in enumerate(files, 1):
            inp_path = Path(inp)
            dest     = Path(out_dir) if out_dir else inp_path.parent
            out      = str(dest / (inp_path.stem + f".{fmt}"))
            on_line(f"\n[{i}/{total}]  {inp_path.name}  →  {inp_path.stem}.{fmt}")
            cmd = _build_cmd(inp, out, fmt, mp3_quality)
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
                for line in proc.stdout:
                    stripped = line.rstrip()
                    if stripped:
                        on_line(stripped)
                proc.wait()
                if proc.returncode == 0:
                    on_line(f"  ✓  {out}")
                else:
                    on_line(f"  ✗  Error (code {proc.returncode})")
                    errors += 1
            except Exception as e:
                on_line(f"  ✗  {e}")
                errors += 1

        ok  = total - errors
        msg = (f"Conversion complete — {ok}/{total} file(s)."
               if ok > 0 else "All files failed.")
        on_done(msg)

    threading.Thread(target=_worker, daemon=True).start()
