"""Command line entry point.

    freethenoize                 desktop app (default)
    freethenoize serve           web service (browser UI + HTTP API)
    freethenoize get URL [URL…]  download from the terminal, no UI
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__, runtime


def _serve(args):
    import uvicorn

    from . import logs

    from .core import Core
    from .web import Auth, create_app

    password = args.password or os.environ.get("FTN_PASSWORD")
    if not password and args.host not in ("127.0.0.1", "localhost", "::1"):
        print("AVISO: escuchando en la red sin contraseña. Define FTN_PASSWORD.", file=sys.stderr)
    core = Core()
    core.start()
    app = create_app(core, Auth(password=password, desktop=False))
    print(f"FreeTheNoize {__version__} en http://{args.host}:{args.port}  "
          f"(música: {core.settings['download_dir']})", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level=logs.uvicorn_level(),
                proxy_headers=True, forwarded_allow_ips=os.environ.get("FTN_TRUSTED_PROXIES", "127.0.0.1"))


def _get(args):
    import threading
    import time

    from .core import Core

    core = Core()
    if args.out:
        core.settings.override("download_dir", str(Path(args.out).expanduser().resolve()))
    lock = threading.Lock()
    pending_links = len(args.urls)
    finished = {}

    def on_event(kind, p):
        nonlocal pending_links
        with lock:
            if kind == "resolving" and not p.get("active"):
                pending_links -= 1
                if p.get("error"):
                    print(f"✗ {p['url']}: {p['error']}", file=sys.stderr)
                elif p.get("skipped"):
                    print(f"· {p.get('title') or p['url']}: {p['count']} nuevas, {p['skipped']} ya descargadas")
            elif kind == "job" and p["status"] in ("done", "skipped", "error", "cancelled"):
                if p["id"] not in finished:
                    finished[p["id"]] = p["status"]
                    q = (p.get("quality") or {}).get("label", "")
                    extra = " · ".join(x for x in (q, p.get("camelot"), f"{p['bpm']:g} BPM" if p.get("bpm") else "") if x)
                    mark = {"done": "✓", "skipped": "=", "error": "✗", "cancelled": "-"}[p["status"]]
                    line = f"{mark} {p.get('artist') or p.get('uploader')} - {p['title']}"
                    if extra:
                        line += f"  [{extra}]"
                    if p.get("error"):
                        line += f"  {p['error']}"
                    print(line, flush=True)

    core.downloads.emit = on_event
    core.downloads.add(args.urls)
    try:
        while True:
            time.sleep(0.3)
            with lock:
                busy = pending_links > 0 or any(
                    j["status"] in ("queued", "downloading", "tagging") for j in core.downloads.snapshot())
            if not busy:
                break
    except KeyboardInterrupt:
        core.downloads.cancel_all()
        return 130
    return 1 if any(s == "error" for s in finished.values()) else 0


def _common() -> argparse.ArgumentParser:
    """Options valid before or after the subcommand: `-v app`, `get -v URL`."""
    c = argparse.ArgumentParser(add_help=False)
    c.add_argument("-v", "--verbose", action="count", default=argparse.SUPPRESS,
                   help="más detalle en la terminal (-v info, -vv depuración)")
    c.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
                   help="solo errores en la terminal")
    c.add_argument("--log-file", metavar="RUTA", default=argparse.SUPPRESS,
                   help="fichero de log (por defecto, el de la carpeta de logs del usuario)")
    c.add_argument("-i", "--info", action="store_true", default=argparse.SUPPRESS,
                   help="muestra versión, rutas y componentes, y sale")
    return c


def _info(log_path) -> int:
    from . import ffmpeg, paths, ytdlp_loader

    try:
        import webview

        gui = f"pywebview {webview.__version__ if hasattr(webview, '__version__') else ''}".strip()
    except Exception as exc:  # noqa: BLE001
        gui = f"no disponible ({exc})"
    rows = {
        "versión": __version__,
        "plataforma": f"{sys.platform} · Python {sys.version.split()[0]}"
                      + (" · build congelada" if getattr(sys, "frozen", False) else ""),
        "ejecutable": sys.executable,
        "config": paths.CONFIG_DIR,
        "datos": paths.DATA_DIR,
        "caché": paths.CACHE_DIR,
        "log": log_path or "-",
        "ffmpeg": ffmpeg.FFMPEG or "no encontrado",
        "yt-dlp": ytdlp_loader.current_version(),
        "ventana": gui,
    }
    width = max(map(len, rows))
    for k, v in rows.items():
        print(f"{k:<{width}}  {v}")
    return 0


def main(argv=None):
    common = _common()
    parser = argparse.ArgumentParser(prog="freethenoize", description="FreeTheNoize " + __version__,
                                     parents=[common])
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("app", parents=[common], help="abre la app de escritorio (por defecto)")
    s = sub.add_parser("serve", parents=[common], help="arranca el servicio web")
    s.add_argument("--host", default=os.environ.get("FTN_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("FTN_PORT", "8765")))
    s.add_argument("--password", help="contraseña de acceso (o FTN_PASSWORD)")
    s.add_argument("--music-dir", help="carpeta de música (o FTN_MUSIC_DIR)")
    s.add_argument("--data-dir", help="carpeta de datos (o FTN_DATA_DIR)")
    g = sub.add_parser("get", parents=[common], help="descarga enlaces desde la terminal")
    g.add_argument("urls", nargs="+")
    g.add_argument("-o", "--out", help="carpeta de destino")
    args = parser.parse_args(argv)

    # Everything below reads these at import time (paths.py).
    if args.cmd == "serve":
        runtime.set_mode("server")
        if args.music_dir:
            os.environ["FTN_MUSIC_DIR"] = args.music_dir
        if args.data_dir:
            os.environ["FTN_DATA_DIR"] = args.data_dir

    from . import logs

    verbose = getattr(args, "verbose", 0)
    log_path = logs.setup(verbose, getattr(args, "quiet", False), getattr(args, "log_file", None))
    if verbose >= 2:
        os.environ.setdefault("FTN_DEBUG", "1")  # pywebview DevTools
    logging.getLogger("freethenoize").info("FreeTheNoize %s %s, log %s", __version__, args.cmd or "app", log_path)

    from . import ytdlp_loader

    # Must happen before anything imports yt_dlp.
    ytdlp_loader.activate()

    if getattr(args, "info", False):
        return _info(log_path)
    if args.cmd == "serve":
        return _serve(args)
    if args.cmd == "get":
        return _get(args)
    from .desktop import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
