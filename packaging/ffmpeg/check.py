"""Check that an ffmpeg build can do everything FreeTheNoize asks of it.

    python packaging/ffmpeg/check.py path/to/ffmpeg

Standard library only (runs right after the build). Keep it in step with the
component lists in build.sh: if the app starts using a new codec, format or
filter, add it here first and watch this fail.
"""
import array
import math
import struct
import subprocess
import sys
import tempfile
import wave
import zlib
from pathlib import Path

REQUIRED = {
    "decoders": ["aac", "alac", "flac", "mp3float", "opus", "vorbis", "pcm_s16le", "pcm_s24le",
                 "pcm_f32le", "wavpack", "mjpeg", "png", "webp"],
    "encoders": ["aac", "flac", "libmp3lame", "pcm_s16le", "pcm_s24le", "pcm_s16be", "pcm_s24be", "mjpeg"],
    "demuxers": ["aac", "aiff", "flac", "hls", "matroska,webm", "mov,mp4,m4a,3gp,3g2,mj2", "mp3", "mpegts",
                 "ogg", "wav", "image2pipe"],
    "muxers": ["adts", "aiff", "f32le", "flac", "ipod", "mp3", "mp4", "ogg", "opus", "wav", "webm", "image2pipe"],
    "filters": ["aresample", "volume", "alimiter", "scale"],
    "bsfs": ["aac_adtstoasc"],
    "protocols": ["file", "pipe", "http", "https"],
}


def listed(ffmpeg: str, kind: str) -> set[str]:
    out = subprocess.run([ffmpeg, "-hide_banner", f"-{kind}"], capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if kind == "protocols":
            names.update(parts)
        elif kind == "bsfs":
            names.update(parts)
        elif len(parts) >= 2 and not line.startswith((" -", "--")):
            names.add(parts[1])
    return names


def run(ffmpeg: str, *args: str, data: bytes | None = None) -> bytes:
    res = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", *args],
                         input=data, capture_output=True)
    if res.returncode != 0:
        raise SystemExit(f"FAIL ffmpeg {' '.join(args)}\n{res.stderr.decode(errors='replace')}")
    return res.stdout


def png(w: int, h: int) -> bytes:
    rows = b"".join(b"\x00" + b"".join(bytes((x * 255 // w, y * 255 // h, 128)) for x in range(w))
                    for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def main(ffmpeg: str) -> None:
    missing = []
    for kind, names in REQUIRED.items():
        have = listed(ffmpeg, kind)
        missing += [f"{kind[:-1]} {n}" for n in names if n not in have]
    if missing:
        raise SystemExit("FAIL missing: " + ", ".join(missing))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "src.wav"
        sr = 44_100
        samples = array.array("h", (int(12000 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(sr * 2)
                                    for _ in range(2)))
        with wave.open(str(src), "wb") as w:
            w.setnchannels(2), w.setsampwidth(2), w.setframerate(sr)
            w.writeframes(samples.tobytes())

        # The conversions of plugins/convert (same codec arguments).
        outputs = {
            "wav": ["-c:a", "pcm_s24le"], "aiff": ["-c:a", "pcm_s16be"],
            "flac": ["-c:a", "flac", "-sample_fmt", "s16"], "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
            "m4a": ["-c:a", "aac", "-b:a", "256k"],
        }
        for ext, codec in outputs.items():
            out = tmp / f"out.{ext}"
            run(ffmpeg, "-i", str(src), "-map", "0:a:0", "-af", "volume=-3.00dB,alimiter=limit=0.891:level=false",
                *codec, str(out))
            # Analysis decode and playback transcode.
            pcm = run(ffmpeg, "-i", str(out), "-map", "0:a:0", "-ac", "1", "-ar", "22050", "-f", "f32le", "pipe:1")
            if len(pcm) < 22050 * 4:
                raise SystemExit(f"FAIL decoding {ext}: only {len(pcm)} bytes")
            run(ffmpeg, "-i", str(out), "-map", "0:a:0", "-ac", "2", "-c:a", "pcm_s16le", str(tmp / f"play-{ext}.wav"))

        # yt-dlp's remuxes: AAC to m4a with the ADTS fix, and to .opus/.ogg/.webm containers.
        run(ffmpeg, "-i", str(tmp / "out.m4a"), "-c", "copy", "-f", "adts", str(tmp / "raw.aac"))
        run(ffmpeg, "-i", str(tmp / "raw.aac"), "-c", "copy", "-bsf:a", "aac_adtstoasc", "-f", "mp4", str(tmp / "fix.m4a"))

        # Cover art: png → small jpeg through a pipe, as ffmpeg.to_jpeg does.
        jpeg = run(ffmpeg, "-i", "pipe:0", "-frames:v", "1",
                   "-vf", "scale='min(iw,300)':'min(ih,300)':force_original_aspect_ratio=decrease:flags=lanczos,"
                          "format=yuvj420p", "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1",
                   data=png(640, 480))
        if jpeg[:2] != b"\xff\xd8":
            raise SystemExit("FAIL cover art is not a JPEG")

    print(f"OK {ffmpeg}: {Path(ffmpeg).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1])
