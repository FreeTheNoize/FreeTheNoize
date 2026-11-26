"""Logging for every entry point (app, serve, get).

- Console (stderr): warnings, when there is a terminal.
- File: always, so a user can attach it to a bug report:
  <user log dir>/freethenoize.log, rotated.
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from platformdirs import user_log_path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_level = logging.WARNING


def default_file() -> Path:
    return user_log_path("FreeTheNoize", appauthor=False, ensure_exists=True) / "freethenoize.log"


def setup(verbose: int = 0, quiet: bool = False, log_file: str | None = None) -> Path | None:
    """Configure logging; returns the log file in use (None if it can't be opened)."""
    global _level
    _level = logging.ERROR if quiet else (logging.WARNING, logging.INFO, logging.DEBUG)[min(verbose, 2)]
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    from . import runtime

    # When stderr is already that log file (windowed build without console),
    # a console handler would only write every line twice.
    if sys.stderr is not None and not runtime.streams_redirected():
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(_level)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(console)

    path = Path(log_file).expanduser() if log_file else default_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    fh.setLevel(logging.DEBUG if verbose >= 2 else logging.INFO)
    fh.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(fh)
    for noisy in ("urllib3", "asyncio", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return path


def uvicorn_level() -> str:
    return logging.getLevelName(_level).lower()
