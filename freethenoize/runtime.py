"""How this process is running: desktop app or web service.

- desktop: one user, the page runs in a local pywebview window. Any path on
  the machine can be opened; native dialogs and "show in folder" exist.
- server: possibly remote users through a browser. Files are confined to the
  music folder and the upload area, and access can require a password.
"""
import os
import sys

_mode = os.environ.get("FTN_MODE", "desktop")


def set_mode(mode: str) -> None:
    global _mode
    if mode not in ("desktop", "server"):
        raise ValueError(mode)
    _mode = mode
    os.environ["FTN_MODE"] = mode


def mode() -> str:
    return _mode


def is_server() -> bool:
    return _mode == "server"


_redirected = False


def streams_redirected() -> bool:
    """True when stdout/stderr point to output.log instead of a terminal."""
    return _redirected


def ensure_std_streams() -> None:
    """Give the process a stdout/stderr when it has none.

    A windowed build (PyInstaller console=False) gets sys.stdout/sys.stderr =
    None. uvicorn's log formatter calls sys.stdout.isatty() and the app died
    before the window opened, without a message. Send them to output.log in
    the log dir.
    """
    global _redirected
    if sys.stdout is not None and sys.stderr is not None:
        return
    from platformdirs import user_log_path

    try:
        log_dir = user_log_path("FreeTheNoize", appauthor=False, ensure_exists=True)
        stream = open(log_dir / "output.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    _redirected = True


def unblock_bundled_dlls() -> None:
    """Remove the Mark of the Web from the app's own DLLs (Windows build).

    Explorer copies the "downloaded from the Internet" mark (Zone.Identifier)
    from a downloaded zip to every file it extracts. .NET Framework refuses to
    load marked assemblies, so pythonnet and WebView2 fail ("Failed to resolve
    Python.Runtime.Loader.Initialize") and there is no native window. The user
    already chose to run this app; its bundled DLLs get the same trust.
    """
    base = getattr(sys, "_MEIPASS", None)
    if sys.platform != "win32" or not base:
        return
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name.lower().endswith(".dll"):
                try:
                    os.remove(os.path.join(root, name) + ":Zone.Identifier")
                except OSError:
                    pass  # not marked, or read-only install: nothing to do


def alert(title: str, text: str) -> None:
    """Tell the user, even without a terminal (Windows message box)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 | 0x10000)  # MB_ICONERROR | MB_SETFOREGROUND
    else:
        print(f"{title}: {text}", file=sys.stderr)
