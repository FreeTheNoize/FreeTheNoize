"""How this process is running: desktop app or web service.

- desktop: one user, the page runs in a local pywebview window. Any path on
  the machine can be opened; native dialogs and "show in folder" exist.
- server: possibly remote users through a browser. Files are confined to the
  music folder and the upload area, and access can require a password.
"""
import os

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
