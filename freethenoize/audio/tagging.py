"""Read and write tags + cover art with mutagen, for every format we produce.

ffmpeg cannot put artwork in WAV and gets M4A covers wrong, so all tagging is
done here instead.
"""
import base64
import io
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, ID3, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TPE2, WOAS, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

TAG_KEYS = ("title", "artist", "album", "album_artist", "genre", "date", "comment", "url", "bpm", "key")

_ID3_FRAMES = {
    "title": TIT2, "artist": TPE1, "album": TALB, "album_artist": TPE2,
    "genre": TCON, "date": TDRC, "bpm": TBPM, "key": TKEY,
}
_MP4_KEYS = {
    "title": "©nam", "artist": "©ART", "album": "©alb", "album_artist": "aART",
    "genre": "©gen", "date": "©day", "comment": "©cmt",
}
_MP4_KEY_ATOM = "----:com.apple.iTunes:initialkey"
_VORBIS_KEYS = {
    "title": "TITLE", "artist": "ARTIST", "album": "ALBUM", "album_artist": "ALBUMARTIST",
    "genre": "GENRE", "date": "DATE", "comment": "COMMENT", "url": "WEBSITE",
    "bpm": "BPM", "key": "INITIALKEY",
}


def image_mime(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def shrink_cover(data: bytes, max_px: int) -> bytes:
    """Resize to max_px on the long side and re-encode as JPEG.

    SoundCloud "original" artwork can be a 3000px 10 MB PNG; embedding that in
    every file makes DJ software choke.
    """
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        if max(img.size) <= max_px and image_mime(data) == "image/jpeg":
            return data
        img = img.convert("RGB")
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=92, optimize=True)
        return out.getvalue()


def _text(meta: dict, key: str) -> str | None:
    v = meta.get(key)
    if v in (None, ""):
        return None
    if key == "bpm":
        return str(int(round(float(v))))
    return str(v)


def _fill_id3(tags: ID3, meta: dict, cover: bytes | None):
    for key, frame in _ID3_FRAMES.items():
        if (text := _text(meta, key)) is not None:
            tags.setall(frame.__name__, [frame(encoding=3, text=text)])
    if meta.get("comment"):
        tags.setall("COMM", [COMM(encoding=3, lang="eng", desc="", text=meta["comment"])])
    if meta.get("url"):
        tags.setall("WOAS", [WOAS(url=meta["url"])])
    if cover:
        tags.setall("APIC", [APIC(encoding=3, mime=image_mime(cover), type=3, desc="Cover", data=cover)])


def _flac_picture(cover: bytes) -> Picture:
    pic = Picture()
    pic.type = 3
    pic.mime = image_mime(cover)
    pic.data = cover
    return pic


def write_tags(path: str | Path, meta: dict, cover: bytes | None = None) -> bool:
    """Returns False for containers that cannot carry tags (e.g. raw .aac)."""
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".mp3":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        _fill_id3(tags, meta, cover)
        tags.save(path, v2_version=3)
    elif ext in (".wav", ".aif", ".aiff"):
        audio = WAVE(path) if ext == ".wav" else AIFF(path)
        if audio.tags is None:
            audio.add_tags()
        _fill_id3(audio.tags, meta, cover)
        audio.save(v2_version=3)
    elif ext in (".m4a", ".mp4", ".alac"):
        audio = MP4(path)
        for key, atom in _MP4_KEYS.items():
            if (text := _text(meta, key)) is not None:
                audio[atom] = [text]
        if (bpm := _text(meta, "bpm")) is not None:
            audio["tmpo"] = [int(bpm)]
        if (key := _text(meta, "key")) is not None:
            audio[_MP4_KEY_ATOM] = [MP4FreeForm(key.encode())]
        if cover:
            fmt = MP4Cover.FORMAT_PNG if image_mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(cover, imageformat=fmt)]
        audio.save()
    elif ext in (".flac", ".opus", ".ogg"):
        audio = {".flac": FLAC, ".opus": OggOpus, ".ogg": OggVorbis}[ext](path)
        if audio.tags is None:
            audio.add_tags()
        for key, name in _VORBIS_KEYS.items():
            if (text := _text(meta, key)) is not None:
                audio[name] = [text]
        if cover:
            if ext == ".flac":
                audio.clear_pictures()
                audio.add_picture(_flac_picture(cover))
            else:
                audio["METADATA_BLOCK_PICTURE"] = [
                    base64.b64encode(_flac_picture(cover).write()).decode("ascii")
                ]
        audio.save()
    else:
        return False
    return True


def read_tags(path: str | Path) -> tuple[dict, bytes | None]:
    """Best-effort inverse of write_tags, used to carry tags across conversions."""
    path = Path(path)
    ext = path.suffix.lower()
    meta: dict = {}
    cover = None
    audio = MutagenFile(path)
    if audio is None or audio.tags is None:
        return meta, cover

    tags = audio.tags
    if isinstance(tags, ID3):
        for key, frame in _ID3_FRAMES.items():
            if frame.__name__ in tags:
                meta[key] = str(tags[frame.__name__].text[0])
        if comms := tags.getall("COMM"):
            meta["comment"] = str(comms[0].text[0])
        if woas := tags.getall("WOAS"):
            meta["url"] = woas[0].url
        if apics := tags.getall("APIC"):
            cover = apics[0].data
    elif ext in (".m4a", ".mp4"):
        for key, atom in _MP4_KEYS.items():
            if atom in tags:
                meta[key] = str(tags[atom][0])
        if "tmpo" in tags:
            meta["bpm"] = str(tags["tmpo"][0])
        if _MP4_KEY_ATOM in tags:
            meta["key"] = bytes(tags[_MP4_KEY_ATOM][0]).decode("utf-8", "replace")
        if "covr" in tags:
            cover = bytes(tags["covr"][0])
    else:
        for key, name in _VORBIS_KEYS.items():
            if name in tags:
                meta[key] = str(tags[name][0])
        if ext == ".flac" and audio.pictures:
            cover = audio.pictures[0].data
        elif "METADATA_BLOCK_PICTURE" in tags:
            cover = Picture(base64.b64decode(tags["METADATA_BLOCK_PICTURE"][0])).data
    return meta, cover
