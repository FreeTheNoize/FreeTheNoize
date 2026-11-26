"""Desktop window: the web UI in a native pywebview window.

The page talks to the same HTTP API as in a browser. pywebview's js_api is
used only for what a browser cannot do: native file dialogs, "show in
folder" and the SoundCloud sign-in window.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .paths import DATA_DIR

AUDIO_TYPES = ("Audio (*.wav;*.flac;*.aif;*.aiff;*.mp3;*.m4a;*.aac;*.opus;*.ogg)", "Todos (*.*)")


class NativeBridge:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self, kernel):
        self._kernel = kernel
        self._window = None

    def choose_folder(self, start: str = "") -> str | None:
        import webview

        res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start or "")
        return res[0] if res else None

    def choose_audio_files(self, multiple: bool = False) -> list[str]:
        import webview

        res = self._window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=multiple, file_types=AUDIO_TYPES)
        return list(res or [])

    def reveal(self, path: str):
        p = Path(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)])
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(p)])
        else:
            subprocess.run(["xdg-open", str(p.parent)])

    def open_url(self, url: str):
        if url.startswith(("https://", "http://")):
            import webbrowser

            webbrowser.open(url)

    def soundcloud_login(self) -> dict:
        """Open SoundCloud's sign-in page and grab the oauth_token cookie."""
        import webview

        login = webview.create_window(
            "Iniciar sesión en SoundCloud", "https://soundcloud.com/signin",
            width=520, height=720)
        from . import popups

        popups.allow_popups(login)
        closed = threading.Event()
        login.events.closed += lambda *_: (closed.set(), popups.forget(login))
        deadline = time.monotonic() + 600
        while not closed.is_set() and time.monotonic() < deadline:
            time.sleep(1.5)
            try:
                cookies = login.get_cookies() or []
            except Exception:
                continue
            for jar in cookies:
                if "oauth_token" in jar:
                    status = self._kernel.soundcloud_set_token(jar["oauth_token"].value)
                    login.destroy()
                    return status
        if not closed.is_set():
            login.destroy()
        return self._kernel.soundcloud_status()


GEOMETRY_FILE = DATA_DIR / "window.json"


def _load_geometry() -> dict:
    """Last window size; no file yet (first launch) = maximized."""
    geometry = {"width": 1280, "height": 820, "maximized": True}
    try:
        stored = json.loads(GEOMETRY_FILE.read_text(encoding="utf-8"))
        geometry.update({
            "width": max(960, int(stored["width"])),
            "height": max(640, int(stored["height"])),
            "maximized": bool(stored["maximized"]),
        })
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return geometry


def _track_geometry(window, geometry: dict) -> None:
    def maximized(*_):
        geometry["maximized"] = True

    def restored(*_):
        geometry["maximized"] = False

    def resized(width, height):
        if not geometry["maximized"]:
            geometry["width"], geometry["height"] = width, height

    def save(*_):
        try:
            GEOMETRY_FILE.write_text(json.dumps(geometry), encoding="utf-8")
        except OSError:
            pass

    window.events.maximized += maximized
    window.events.restored += restored
    window.events.resized += resized
    window.events.closing += save


def run():
    import logging

    from . import instance, logs, runtime

    log = logging.getLogger("freethenoize.desktop")
    t0 = time.monotonic()

    def step(what):
        log.info("arranque %5.2fs  %s", time.monotonic() - t0, what)


    # Already open: bring that window to the front instead of a second app.
    # If it is closing, wait for it and start; never an error dialog.
    if not instance.acquire() and not instance.hand_over():
        log.info("ya había una instancia abierta: se le pide que se muestre")
        return 0

    # Answer later launches from now on, also while starting and closing.
    ui = {"window": None, "kernel": None, "pending": False, "closing": False}

    def on_show():
        if ui["closing"]:
            return "closing"
        if ui["window"] is None:
            ui["pending"] = True   # shown as soon as it exists
            return "ok"
        _bring_to_front()
        return "ok"

    def _bring_to_front():
        if ui["kernel"]:
            ui["kernel"].emit("reopened", {})   # page shows "ya estaba abierto"
        if in_browser.is_set():
            import webbrowser

            webbrowser.open(url)
            return
        w = ui["window"]
        w.restore()
        w.show()
        w.on_top = True  # raise above other windows, then behave normally
        w.on_top = False

    in_browser = threading.Event()
    url = ""
    instance.serve(on_show)

    runtime.unblock_bundled_dlls()  # before pywebview loads .NET (Windows)
    step("instancia única + DLL desbloqueadas")

    import uvicorn
    import webview

    from .kernel import Kernel
    from .web import Auth, create_app

    step("imports")
    kernel = Kernel()
    kernel.start()
    ui["kernel"] = kernel
    auth = Auth(password=None, desktop=True)
    app = create_app(kernel, auth)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level=logs.uvicorn_level(), lifespan="off"))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    step(f"servidor en 127.0.0.1:{port}")

    bridge = NativeBridge(kernel)
    geometry = _load_geometry()
    window = webview.create_window(
        "FreeTheNoize",
        f"http://127.0.0.1:{port}/auth/desktop?key={auth.desktop_key}",
        js_api=bridge,
        width=geometry["width"],
        height=geometry["height"],
        maximized=geometry["maximized"],  # maximized the first time
        min_size=(960, 640),
        background_color="#0a0a0a",
    )
    bridge._window = window
    _track_geometry(window, geometry)
    window.events.shown += lambda *_: step("ventana visible")
    window.events.loaded += lambda *_: step("interfaz cargada")
    from . import popups

    url = f"http://127.0.0.1:{port}/auth/desktop?key={auth.desktop_key}"
    window.events.closing += lambda *_: ui.update(closing=True)

    def ready(*_):
        ui["window"] = window
        if ui.pop("pending", False):
            _bring_to_front()

    window.events.shown += ready
    popups.install()
    step("ventana creada, arrancando el motor web")
    try:
        # The icon argument is only for Linux (GTK/Qt). On Windows pywebview
        # loads it with System.Drawing.Icon, which rejects a PNG and kills the
        # process from .NET; the window takes the exe's icon there anyway.
        icon = str(Path(__file__).parent / "ui" / "icon-512.png") if sys.platform.startswith("linux") else None
        # WebView2/WebKit profile inside our data dir (default: a pywebview
        # folder shared by every pywebview app), so uninstall can remove it.
        webview.start(debug=os.environ.get("FTN_DEBUG") == "1", private_mode=False, icon=icon,
                      storage_path=str(DATA_DIR / "webview"))
    except Exception as exc:
        log.exception("no se pudo abrir la ventana")
        # No usable GUI backend (e.g. a Linux box without Qt/GTK libraries):
        # keep the server running and use the default browser instead.
        import webbrowser

        in_browser.set()
        ui["window"] = window
        print(f"No se pudo abrir la ventana ({exc}). Abriendo en el navegador: {url}")
        print("Ctrl+C para salir.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    # Closing: the window is already gone. Stop what we own and leave at once;
    # waiting for the interpreter and the web engine to tear down took seconds
    # (and kept the lock, so a quick relaunch looked like a hung app).
    ui["closing"] = True
    t_close = time.monotonic()
    server.should_exit = True
    kernel.stop()
    log.info("cierre en %.2fs", time.monotonic() - t_close)
    logging.shutdown()
    os._exit(0)
