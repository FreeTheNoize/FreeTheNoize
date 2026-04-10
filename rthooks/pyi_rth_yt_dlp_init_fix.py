"""
Runtime hook — executa ABANS de app.py.

scdl.patches.trim_filenames fa dos usos de yt_dlp.__init__:

  1. import yt_dlp.__init__                         ← lookup via sys.modules
  2. yt_dlp.__init__.validate_options = x            ← lookup via atribut del mòdul

PyInstaller trenca ambdós casos. Fixes:

  1. sys.modules['yt_dlp.__init__'] = yt_dlp   → fix per a l'import statement
  2. yt_dlp.__dict__['__init__'] = yt_dlp       → fix per a l'accés d'atribut
     (Python busca __dict__ ABANS del slot/method-wrapper de la classe)
"""
try:
    import sys
    import yt_dlp as _yt_dlp

    # Fix 1: import statement usa sys.modules
    sys.modules.setdefault("yt_dlp.__init__", _yt_dlp)

    # Fix 2: accés d'atribut usa __dict__ (prioritat sobre el method-wrapper del tipus)
    _yt_dlp.__dict__["__init__"] = _yt_dlp

except Exception:
    pass
