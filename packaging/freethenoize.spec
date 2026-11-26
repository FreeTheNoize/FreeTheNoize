# PyInstaller spec: desktop app for macOS (.app), Windows and Linux (folder + executable).
#   pyinstaller packaging/freethenoize.spec --noconfirm
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
APP = "FreeTheNoize"
# Single source of truth for the version: freethenoize/__init__.py (bumped by release-please).
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "freethenoize" / "__init__.py").read_text()).group(1)

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("yt_dlp")
    + collect_submodules("webview")
    # Plugins are imported by name at runtime (freethenoize.plugins.load).
    + collect_submodules("freethenoize.plugins")
    + ["keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService", "multipart"]
)
# Linux window = pywebview's Qt backend. Only the Qt modules it imports
# (webview/platforms/qt.py): collect_submodules("qtpy") pulled every Qt module
# (3D, Quick Controls, Designer, SQL drivers...) and made the zip ~380 MB.
QT_USED = ["QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtWebChannel", "QtWebEngineCore", "QtWebEngineWidgets"]
QT_UNUSED = [
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender", "QtBluetooth", "QtCharts",
    "QtDataVisualization", "QtDesigner", "QtGraphs", "QtHelp", "QtMultimedia", "QtMultimediaWidgets", "QtNfc",
    "QtPdf", "QtPdfWidgets", "QtQuick3D", "QtQuickWidgets", "QtRemoteObjects", "QtSensors", "QtSerialPort",
    "QtSpatialAudio", "QtSql", "QtStateMachine", "QtSvgWidgets", "QtTest", "QtTextToSpeech", "QtUiTools",
    "QtWebSockets", "QtXml", "uic",
]
excludes = ["tkinter", "matplotlib", "IPython", "pytest"]
if sys.platform.startswith("linux"):
    hidden += [f"qtpy.{m}" for m in QT_USED]
    excludes += [f"{pkg}.{m}" for pkg in ("qtpy", "PyQt6") for m in QT_UNUSED] + ["PyQt5", "PySide2", "PySide6"]
datas = [(str(ROOT / "freethenoize" / "ui"), "freethenoize/ui")]
datas += collect_data_files("freethenoize.plugins")  # each plugin's ui/ (js, css)
ICON = ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
datas += collect_data_files("imageio_ffmpeg")
binaries = []

# Windows: file version resource (Properties > Details). An exe without it looks
# more suspicious to SmartScreen and antivirus heuristics.
version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32 import versioninfo as vi

    nums = tuple(int(x) for x in VERSION.split(".")[:3]) + (0,)
    strings = {
        "CompanyName": "FreeTheNoize", "FileDescription": APP, "FileVersion": VERSION,
        "InternalName": APP, "OriginalFilename": f"{APP}.exe", "ProductName": APP,
        "ProductVersion": VERSION, "LegalCopyright": "GPL-2.0",
    }
    version_file = vi.VSVersionInfo(
        ffi=vi.FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            vi.StringFileInfo([vi.StringTable("040904B0", [vi.StringStruct(k, v) for k, v in strings.items()])]),
            vi.VarFileInfo([vi.VarStruct("Translation", [0x0409, 1200])]),
        ],
    )

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    console=False,
    upx=False,
    icon=str(ICON),
    version=version_file,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=str(ICON),
        bundle_identifier="io.github.quim-d.freethenoize",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.music",
        },
    )
