import sys
import multiprocessing


# ── Frozen-bundle scdl passthrough ────────────────────────────────────────────
# PyInstaller calls this exe with "___RUN_SCDL___" as first argument
# when the download process spawns a subprocess of itself.
if getattr(sys, "frozen", False) and len(sys.argv) > 1 and sys.argv[1] == "___RUN_SCDL___":
    import scdl.scdl
    sys.argv.pop(1)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        sys.exit(scdl.scdl._main())
    except KeyboardInterrupt:
        sys.exit(1)


# ── Auto-install dependencies (dev mode only) ─────────────────────────────────
if not getattr(sys, "frozen", False):
    import subprocess, os
    needed = []
    for pkg, mod in [
        ("scdl",           "scdl"),
        ("Pillow",         "PIL"),
        ("imageio-ffmpeg", "imageio_ffmpeg"),
        ("pygame-ce",      "pygame"),
        ("psutil",         "psutil"),
        ("yt-dlp",         "yt_dlp"),
        ("numpy",          "numpy"),
        ("scipy",          "scipy"),
        ("matplotlib",     "matplotlib"),
        ("soundfile",      "soundfile"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            needed.append(pkg)
    if needed:
        print(f"Installing dependencies: {', '.join(needed)} …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + needed,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        os.execv(sys.executable, [sys.executable] + sys.argv)


# ── GUI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.freeze_support()
    from gkicks.gui.window import App
    App().mainloop()
