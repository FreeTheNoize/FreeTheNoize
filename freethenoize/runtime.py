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


def ensure_std_streams() -> None:
    """Give the process a stdout/stderr when it has none.

    A windowed build (PyInstaller console=False) started from Explorer on
    Windows gets sys.stdout/sys.stderr = None. uvicorn's log formatter calls
    sys.stdout.isatty() and the app dies before the window opens, without a
    message. Point the missing streams to a log file so it starts and leaves
    a trace to debug with.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    from platformdirs import user_log_path

    try:
        log_dir = user_log_path("FreeTheNoize", appauthor=False, ensure_exists=True)
        stream = open(log_dir / "freethenoize.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
