"""Build the project website and the demo of the real interface.

    python tools/build_site.py [--out _site]

- `site/` (hand-written, static) is copied as is.
- `demo/` is the app's own page: freethenoize/ui plus every plugin's ui/,
  assembled like web.py does, with `demo-api.js` in front of the kernel. That
  script answers /api/* in the browser with sample data, so the demo needs no
  backend and makes no request outside the site.
- The sample data is real: a server-mode kernel runs here on a few synthetic
  tracks and its HTTP API is recorded (library, analysis, null test, state).
  When the API changes, the demo changes with it.

Needs the package with its dev extras (`pip install -e ".[dev]"`) and ffmpeg.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DEMO_SRC = SITE / "demo-src"   # demo-api.js, demo.css: only for the demo build

# Fictional music for the demo: (title, artist, bpm, root Hz of the minor chord, bits)
TRACKS = [
    ("Turno de noche", "Sala Oscura", 124, 220.00, 24),
    ("Polígono", "Nadia Ferro", 128, 174.61, 16),
    ("Luz de sodio", "Hormigón", 122, 196.00, 24),
    ("Fotocopia", "Paloma Estática", 132, 261.63, 16),
    ("Sin permiso", "Colectivo Ruido", 118, 164.81, 16),
    ("Hormigón armado", "Sala Oscura", 126, 146.83, 24),
]
ALBUM = "Demo FreeTheNoize"
SECONDS = 10          # analysed length
PREVIEW_SECONDS = 8   # what the demo plays (small files)
COVER_RULES = (30, 90, 110, 150, 45, 60)
# Ink for each cover, from the app's palette: acid, hazard red, amber, bone, violet, cyan.
COVER_INK = ((0.78, 1.0, 0.0), (1.0, 0.23, 0.18), (1.0, 0.69, 0.0), (0.93, 0.92, 0.89), (0.6, 0.45, 1.0), (0.2, 0.85, 1.0))


def _ffmpeg() -> str:
    from freethenoize import ffmpeg

    if not ffmpeg.FFMPEG:
        sys.exit("build_site: hace falta ffmpeg")
    return ffmpeg.FFMPEG


def _run(args: list[str]) -> None:
    subprocess.run([_ffmpeg(), "-v", "error", "-y", *args], check=True)


def _synth(path: Path, bpm: float, root: float) -> None:
    """Kick on the beat, hat and bass off the beat, a minor chord pad."""
    b = 60 / bpm
    m3, p5 = 1.1892, 1.4983
    voice = (f"0.9*sin(2*PI*t*(42+110*exp(-mod(t,{b})*28)))*exp(-mod(t,{b})*5)"
             f"+0.12*(random(N)*2-1)*exp(-mod(t+{b}/2,{b})*45)"
             f"+0.22*sin(2*PI*{root / 4}*t)*lt(mod(t+{b}/2,{b}),{b}*0.45)"
             f"+0.05*(sin(2*PI*{root}*t)+sin(2*PI*{root * m3}*t)+sin(2*PI*{root * p5}*t))")
    expr = voice.replace("N", "0") + "|" + voice.replace("N", "1")
    _run(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={SECONDS}",
          "-af", "volume=-3dB", "-c:a", "pcm_s24le", str(path)])


def _cover(path: Path, rule: int, i: int) -> None:
    r, g, b = COVER_INK[i % len(COVER_INK)]
    _run(["-f", "lavfi", "-i", f"cellauto=rule={rule}:s=60x60:random_seed={i + 1}",
          "-frames:v", "1", "-vf",
          f"scale=240:240:flags=neighbor,format=rgb24,colorchannelmixer=rr={r}:gg={g}:bb={b}",
          "-q:v", "6", str(path)])


# ── Capture (runs in a child process with its own data and music folders) ───


def capture(out: Path) -> None:
    from fastapi.testclient import TestClient

    from freethenoize import audio, paths
    from freethenoize.kernel import Kernel
    from freethenoize.web import Auth, create_app

    music = Path(os.environ["FTN_MUSIC_DIR"])
    media = out / "media"
    media.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    tracks = []
    now = time.time()
    for i, (title, artist, bpm, root, bits) in enumerate(TRACKS):
        wav = work / f"{i}.wav"
        _synth(wav, bpm, root)
        mk = audio.bpm_key(wav)
        name = f"{artist} - {title}.flac"
        dest = music / name
        _run(["-i", str(wav), "-c:a", "flac", "-sample_fmt", "s32" if bits == 24 else "s16",
              *(["-bits_per_raw_sample", "24"] if bits == 24 else []),
              "-metadata", f"title={title}", "-metadata", f"artist={artist}", "-metadata", f"album={ALBUM}",
              "-metadata", f"BPM={mk['bpm']}", "-metadata", f"INITIALKEY={mk['key']}", str(dest)])
        os.utime(dest, (now - i * 3600, now - i * 3600))
        _run(["-i", str(wav), "-t", str(PREVIEW_SECONDS), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "40k",
              str(media / f"track-{i}.mp3")])
        _cover(media / f"cover-{i}.jpg", COVER_RULES[i % len(COVER_RULES)], i)
        tracks.append({"path": str(dest), "title": title, "artist": artist,
                       "media": f"media/track-{i}.mp3", "cover": f"media/cover-{i}.jpg",
                       "analysis": f"media/analysis-{i}.json", "bpm": mk["bpm"], "key": mk["key"],
                       "camelot": mk["camelot"]})

    c = TestClient(create_app(Kernel(), Auth(password=None, desktop=False)))

    def get(url, **kw):
        r = c.get(url, **kw)
        r.raise_for_status()
        return r.json()

    def post(url, body):
        r = c.post(url, json=body)
        r.raise_for_status()
        return r.json()

    data = {"session": get("/api/session"), "state": get("/api/state"), "library": get("/api/library"),
            "tracks": tracks}

    for i, t in enumerate(tracks):
        r = post("/api/analysis/analyze", {"path": t["path"]})
        r["audio_url"] = t["media"]
        (media / f"analysis-{i}.json").write_text(json.dumps(r), encoding="utf-8")

    # Null test: the lossless file against an MP3 of itself (the classic
    # "is this download really lossless?" check).
    lossy = work / "lossy.mp3"
    _run(["-i", tracks[0]["path"], "-c:a", "libmp3lame", "-b:a", "128k", str(lossy)])
    with lossy.open("rb") as f:
        up = c.post("/api/upload", files={"file": (f"{TRACKS[0][1]} - {TRACKS[0][0]} (128k).mp3", f, "audio/mpeg")})
    up.raise_for_status()
    lossy_path = up.json()["path"]
    report = post("/api/analysis/null-test", {"a": tracks[0]["path"], "b": lossy_path})
    diff = c.get(report["audio_url"])
    diff.raise_for_status()
    (work / "diff.wav").write_bytes(diff.content)
    _run(["-i", str(work / "diff.wav"), "-t", str(PREVIEW_SECONDS), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "40k",
          str(media / "nulltest-diff.mp3")])
    report["audio_url"] = "media/nulltest-diff.mp3"
    (media / "nulltest.json").write_text(json.dumps(report), encoding="utf-8")
    data["nulltest"] = {"a": tracks[0]["path"], "b": lossy_path, "report": "media/nulltest.json"}

    # Paths of this machine never reach the site (also as resolved, e.g. /private/var on macOS).
    swaps = []
    for real, shown in ((paths.UPLOAD_DIR, "/subidas"), (music, "/música")):
        for variant in {str(real.resolve()), str(real)}:
            swaps.append((variant, shown))
    swaps.sort(key=lambda s: -len(s[0]))

    def scrub(text: str) -> str:
        for real, shown in swaps:
            text = text.replace(real, shown)
        return text

    text = scrub(json.dumps(data, ensure_ascii=False))
    for f in media.glob("*.json"):
        f.write_text(scrub(json.dumps(json.loads(f.read_text(encoding="utf-8")), ensure_ascii=False)),
                     encoding="utf-8")
    (out / "demo-data.js").write_text(
        "/* Recorded from the real API by tools/build_site.py. */\nwindow.FTN_DEMO_DATA = " + text + ";\n",
        encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    tmp = str(Path(tempfile.gettempdir()).resolve())
    for f in [out / "demo-data.js", *media.glob("*.json")]:
        t = f.read_text(encoding="utf-8")
        if tmp in t or any(real in t for real, _ in swaps):
            sys.exit(f"build_site: {f.name} contiene una ruta de esta máquina")


def _capture_in_child(demo: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "FTN_MODE": "server", "FTN_DATA_DIR": str(Path(tmp) / "data"),
               "FTN_MUSIC_DIR": str(Path(tmp) / "music")}
        (Path(tmp) / "music").mkdir()
        subprocess.run([sys.executable, __file__, "--capture", str(demo)], env=env, check=True)


# ── Assembly ────────────────────────────────────────────────────────────────


def build_demo(out: Path) -> None:
    from freethenoize import __version__, plugins
    from freethenoize.paths import UI_DIR

    demo = out / "demo"
    shutil.copytree(UI_DIR, demo, ignore=shutil.ignore_patterns("index.html"))
    # Same as web.py, with relative URLs: the site lives under /<repo>/demo/.
    tags = []
    for pid in plugins.BUILTIN:
        p = plugins.load(pid)
        ui = plugins.folder(pid) / "ui"
        if not ui.is_dir():
            continue
        shutil.copytree(ui, demo / "plugins" / pid)
        v = html.escape(f"{__version__}-{p.version}")
        if (ui / f"{pid}.css").is_file():
            tags.append(f'<link rel="stylesheet" href="plugins/{pid}/{pid}.css?v={v}">')
        if (ui / f"{pid}.js").is_file():
            tags.append(f'<script src="plugins/{pid}/{pid}.js?v={v}"></script>')
    for f in DEMO_SRC.iterdir():
        shutil.copy2(f, demo / f.name)

    v = html.escape(__version__)
    page = (UI_DIR / "index.html").read_text(encoding="utf-8")
    page = page.replace("<!-- plugins -->", "\n".join(tags)).replace("{{version}}", v)
    page = page.replace("<title>FreeTheNoize</title>",
                        "<title>FreeTheNoize · demo</title>\n"
                        '<meta name="description" content="La interfaz real de FreeTheNoize con datos de ejemplo.">\n'
                        f'<link rel="stylesheet" href="demo.css?v={v}">')
    page = page.replace('<script src="spectrogram.js',
                        f'<script src="demo-data.js?v={v}"></script>\n'
                        f'<script src="demo-api.js?v={v}"></script>\n<script src="spectrogram.js', 1)
    page = page.replace('<div class="grain" aria-hidden="true"></div>',
                        '<div class="grain" aria-hidden="true"></div>\n'
                        '<a class="demo-banner" href="../#descargar" title="Esto es una demo: datos de ejemplo, no descarga ni guarda nada">'
                        '<b>DEMO</b><span> · datos de ejemplo</span> · Descargar →</a>', 1)
    for needle in ('src="demo-api.js', 'class="demo-banner"', "plugins/downloads/downloads.js"):
        if needle not in page:
            sys.exit(f"build_site: index.html ha cambiado, no encuentro dónde poner {needle}")
    (demo / "index.html").write_text(page, encoding="utf-8")
    _capture_in_child(demo)


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out, ignore=shutil.ignore_patterns("demo-src", "README.md", ".DS_Store"))
    for icon in (ROOT / "assets" / "icons").iterdir():   # favicons, one copy in the repo
        shutil.copy2(icon, out / icon.name)
    build_demo(out)
    from freethenoize import __version__

    index = out / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("{{version}}", html.escape(__version__)),
                     encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"Web en {out} ({size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "_site"), help="carpeta de salida (por defecto _site/)")
    ap.add_argument("--capture", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.capture:
        capture(Path(args.capture))
    else:
        build(Path(args.out).resolve())


if __name__ == "__main__":
    main()
