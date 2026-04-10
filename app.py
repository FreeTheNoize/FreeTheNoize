import sys
import multiprocessing


# ── Mode CLI de scdl intern (bundle frozen) ───────────────────────────────────
# PyInstaller crida aquest exe amb "___RUN_SCDL___" com a primer argument
# quan el procés de descàrrega inicia un subprocés de si mateix.
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


# ── Auto-instal·lar dependències en mode dev ──────────────────────────────────
if not getattr(sys, "frozen", False):
    import subprocess, os
    needed = []
    for pkg, mod in [
        ("scdl",           "scdl"),
        ("Pillow",         "PIL"),
        ("imageio-ffmpeg", "imageio_ffmpeg"),
        ("pygame-ce",      "pygame"),
        ("psutil",         "psutil"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            needed.append(pkg)
    if needed:
        print(f"Instal·lant dependències: {', '.join(needed)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + needed,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        os.execv(sys.executable, [sys.executable] + sys.argv)


# ── Punt d'entrada GUI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.freeze_support()
    from gkicks.gui.window import App
    App().mainloop()
