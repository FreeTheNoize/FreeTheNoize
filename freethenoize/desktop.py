"""Desktop window: the web UI in a native pywebview window.

The page talks to the same HTTP API as in a browser. pywebview's js_api is
used only for what a browser cannot do: native file dialogs, "show in
folder" and the SoundCloud sign-in window.
"""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

AUDIO_TYPES = ("Audio (*.wav;*.flac;*.aif;*.aiff;*.mp3;*.m4a;*.aac;*.opus;*.ogg)", "Todos (*.*)")


class NativeBridge:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self, core):
        self._core = core
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
                    status = self._core.soundcloud_set_token(jar["oauth_token"].value)
                    login.destroy()
                    return status
        if not closed.is_set():
            login.destroy()
        return self._core.soundcloud_status()


def run():
    import logging

    from . import instance, logs, runtime

    log = logging.getLogger("freethenoize.desktop")
    t0 = time.monotonic()

    def step(what):
        log.info("arranque %5.2fs  %s", time.monotonic() - t0, what)


    # Already open: bring that window to the front instead of a second app.
    if not instance.acquire():
        if instance.show_running():
            return 0
        print("FreeTheNoize ya está abierto, pero no responde.")
        return 1

    runtime.unblock_bundled_dlls()  # before pywebview loads .NET (Windows)
    step("instancia única + DLL desbloqueadas")

    import uvicorn
    import webview

    from .core import Core
    from .web import Auth, create_app

    step("imports")
    core = Core()
    core.start()
    auth = Auth(password=None, desktop=True)
    app = create_app(core, auth)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level=logs.uvicorn_level(), lifespan="off"))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    step(f"servidor en 127.0.0.1:{port}")

    bridge = NativeBridge(core)
    window = webview.create_window(
        "FreeTheNoize",
        f"http://127.0.0.1:{port}/auth/desktop?key={auth.desktop_key}",
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#0a0a0a",
    )
    bridge._window = window
    window.events.shown += lambda *_: step("ventana visible")
    window.events.loaded += lambda *_: step("interfaz cargada")
    from . import popups

    url = f"http://127.0.0.1:{port}/auth/desktop?key={auth.desktop_key}"
    in_browser = threading.Event()

    def on_show():
        if in_browser.is_set():
            import webbrowser

            webbrowser.open(url)
            return
        window.restore()
        window.show()
        window.on_top = True  # raise above other windows, then behave normally
        window.on_top = False

    instance.serve(on_show)
    popups.install()
    step("ventana creada, arrancando el motor web")
    try:
        # The icon argument is only for Linux (GTK/Qt). On Windows pywebview
        # loads it with System.Drawing.Icon, which rejects a PNG and kills the
        # process from .NET; the window takes the exe's icon there anyway.
        icon = str(Path(__file__).parent / "ui" / "icon-512.png") if sys.platform.startswith("linux") else None
        webview.start(debug=os.environ.get("FTN_DEBUG") == "1", private_mode=False, icon=icon)
    except Exception as exc:
        log.exception("no se pudo abrir la ventana")
        # No usable GUI backend (e.g. a Linux box without Qt/GTK libraries):
        # keep the server running and use the default browser instead.
        import webbrowser

        in_browser.set()
        print(f"No se pudo abrir la ventana ({exc}). Abriendo en el navegador: {url}")
        print("Ctrl+C para salir.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    server.should_exit = True
    core.stop()
