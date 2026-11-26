"""File-name helpers shared by the kernel and the plugins."""
import re

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

AUDIO_EXTS = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".m4a", ".aac", ".opus", ".ogg", ".alac"}


def safe_filename(name: str, max_len: int = 180) -> str:
    """A file name that is valid on macOS, Windows and Linux."""
    name = _ILLEGAL.sub("_", name)
    name = re.sub(r"\s{2,}", " ", name).strip().rstrip(". ")
    if name.lower() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:max_len].rstrip(". ") or "untitled"
