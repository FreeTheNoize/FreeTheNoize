# PyInstaller spec: desktop app for macOS (.app), Windows and Linux (folder + executable).
#   pyinstaller packaging/freethenoize.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
APP = "FreeTheNoize"

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("yt_dlp")
    + collect_submodules("webview")
    + ["keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService", "multipart"]
)
if sys.platform.startswith("linux"):
    hidden += collect_submodules("qtpy")
datas = [(str(ROOT / "freethenoize" / "ui"), "freethenoize/ui")]
datas += collect_data_files("imageio_ffmpeg")
binaries = []

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        bundle_identifier="io.github.quim-d.freethenoize",
        info_plist={
            "CFBundleShortVersionString": "3.0.1",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.music",
        },
    )
