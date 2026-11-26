"""One desktop app per user.

Double-clicking the app again must not start a second server and window: the
second launch asks the running one to show its window and exits.

- Lock: a named mutex on Windows, flock() elsewhere. The OS releases it when
  the process dies, so a crash never leaves a stale lock behind.
- Signal: the first instance listens on a random 127.0.0.1 port and writes
  {port, token} to instance.json in the data dir; the second one connects,
  sends the token and gets out of the way.
- The listener starts right after the lock, before the window exists, so a
  launch during start-up is answered too (the window shows when ready). While
  the app is closing it answers "closing" and the new launch waits for the lock
  to be free and then starts normally. There is never an error dialog.
"""
import hashlib
import json
import os
import secrets
import socket
import sys
import threading
import time

from .paths import DATA_DIR

INFO_FILE = DATA_DIR / "instance.json"
_LOCK_FILE = DATA_DIR / "desktop.lock"
_held = None  # keeps the mutex handle / lock file open for the process lifetime
# Fixed name the Windows installer checks (AppMutex in freethenoize.iss) to ask
# for the app to be closed before replacing or removing its files.
APP_MUTEX = "FreeTheNoizeApp"
_app_mutex = None


def acquire() -> bool:
    """True if this is the only desktop instance for this data dir."""
    global _held, _app_mutex
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        name = "Local\\FreeTheNoize-" + hashlib.sha1(str(DATA_DIR).lower().encode()).hexdigest()[:16]
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True  # can't tell: better a second window than no app at all
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return False
        _held = handle
        _app_mutex = kernel32.CreateMutexW(None, False, APP_MUTEX)
        return True
    import fcntl

    f = open(_LOCK_FILE, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _held = f
    return True


def serve(on_show) -> None:
    """Listen for "show yourself" requests from later launches. `on_show()`
    returns "ok" or "closing"."""
    token = secrets.token_urlsafe(24)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)
    INFO_FILE.write_text(json.dumps({"port": sock.getsockname()[1], "token": token, "pid": os.getpid()}))
    try:
        os.chmod(INFO_FILE, 0o600)
    except OSError:
        pass

    def loop():
        while True:
            conn, _ = sock.accept()
            with conn:
                conn.settimeout(2)
                try:
                    if conn.recv(256).decode().strip() == token:
                        conn.sendall((on_show() or "ok").encode())
                except Exception:
                    pass

    threading.Thread(target=loop, daemon=True, name="instance").start()


def show_running() -> str | None:
    """Ask the running instance to show its window: "ok", "closing" or None
    (no answer)."""
    try:
        info = json.loads(INFO_FILE.read_text())
        if sys.platform == "win32":
            # Let the running process take the foreground: Windows only allows
            # it to the process the user just interacted with (this one).
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(int(info["pid"]))
        with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=3) as s:
            s.sendall(info["token"].encode())
            answer = s.recv(16).decode()
            return answer if answer in ("ok", "closing") else None
    except Exception:
        return None


def hand_over(timeout: float = 30) -> bool:
    """Another instance holds the lock. Returns True if this launch should go
    on and start the app (the other one finished closing), False to just exit
    (the other one was told to show its window, or never answered)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if acquire():
            return True            # it finished closing: start normally
        answer = show_running()
        if answer == "ok":
            return False           # its window is coming to the front
        time.sleep(0.3)            # closing, or still starting up: wait
    return False                   # stuck: never a dialog, just leave it be
