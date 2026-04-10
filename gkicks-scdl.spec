# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files, collect_dynamic_libs

# ── Assets ────────────────────────────────────────────────────────────────────
added_files = [
    ("assets/gkicks-icon.png",                             "assets"),
    ("assets/favicon.ico",                                 "assets"),
    ("assets/1CliclDVDCopy4.2.1.5kg-keygen-chiptune.mp3",  "assets"),
]

# ── scdl ──────────────────────────────────────────────────────────────────────
scdl_datas, scdl_bins, scdl_hidden = collect_all("scdl")

# ── yt_dlp ────────────────────────────────────────────────────────────────────
yt_datas, yt_bins, yt_hidden = collect_all("yt_dlp")

# ── pygame (sense tests/examples/docs) ───────────────────────────────────────
pygame_bins  = collect_dynamic_libs("pygame")
pygame_datas = [
    (src, dst) for src, dst in collect_data_files("pygame")
    if not any(x in src.replace("\\", "/")
               for x in ["/examples", "/tests", "/docs", "/__pycache__"])
]
pygame_hidden = collect_submodules("pygame")

# ── psutil ────────────────────────────────────────────────────────────────────
psutil_datas, psutil_bins, psutil_hidden = collect_all("psutil")

# ── ffmpeg estàtic (copiat a assets/ des d'imageio_ffmpeg) ───────────────────
ffmpeg_bin = [("assets/ffmpeg.exe", ".")]   # => _internal/ffmpeg.exe

# ── Combinar ──────────────────────────────────────────────────────────────────
added_files += scdl_datas + yt_datas + pygame_datas + psutil_datas
added_bins   = scdl_bins + yt_bins + pygame_bins + psutil_bins + ffmpeg_bin

hidden_imports = [
    "tkinter", "_tkinter", "tkinter.ttk",
    "tkinter.filedialog", "tkinter.scrolledtext",
    "PIL._tkinter_finder", "PIL.Image", "PIL.ImageTk",
    "gkicks", "gkicks.paths", "gkicks.config", "gkicks.music",
    "gkicks.downloader", "gkicks.converter", "gkicks.styles",
    "gkicks.gui", "gkicks.gui.window", "gkicks.gui.tabs",
    "yt_dlp.cookies", "yt_dlp.utils", "yt_dlp.postprocessor",
    "yt_dlp.extractor", "yt_dlp.downloader",
    "yt_dlp.networking", "yt_dlp.networking.common", "yt_dlp.networking._urllib",
] + scdl_hidden + yt_hidden + pygame_hidden + psutil_hidden

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=added_bins,
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthooks/pyi_rth_yt_dlp_init_fix.py"],
    excludes=[
        "tkinter.test",
        "pygame.tests", "pygame.examples", "pygame.docs",
        "imageio_ffmpeg",
        "secretstorage", "jeepney",
        "unittest", "doctest", "pdb", "pydoc",
        "xmlrpc", "ftplib", "imaplib", "smtplib", "poplib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gkicks-scdl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/favicon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gkicks-scdl",
    contents_directory="_internal",
)
