"""Turn whatever the user pasted into a flat list of tracks."""
from dataclasses import dataclass
from urllib.parse import urlparse

MAX_DEPTH = 3


@dataclass
class TrackRef:
    url: str
    title: str
    uploader: str
    playlist: str | None
    index: int | None
    archive_id: str | None = None


def archive_key(extractor: str | None, video_id: str | None) -> str | None:
    """Same format as yt-dlp's --download-archive."""
    if extractor and video_id:
        return f"{extractor.lower()} {video_id}"
    return None


def source_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("soundcloud.com") or host == "snd.sc":
        return "soundcloud"
    if host.endswith("youtube.com") or host == "youtu.be":
        return "youtube"
    return "other"


def _is_container(entry: dict) -> bool:
    ie = entry.get("ie_key") or ""
    url = entry.get("url") or ""
    return ie.endswith(("Set", "Playlist", "Tab", "User", "Related")) or "/sets/" in url


def resolve(url: str, ydl_params: dict) -> tuple[str | None, list[TrackRef]]:
    """Returns (collection title or None for a single track, tracks)."""
    from yt_dlp import YoutubeDL

    params = {**ydl_params, "extract_flat": "in_playlist", "skip_download": True}
    with YoutubeDL(params) as ydl:
        info = ydl.extract_info(url, download=False, process=True)
        if info.get("_type") not in ("playlist", "multi_video"):
            return None, [TrackRef(
                url=info.get("webpage_url") or url,
                title=info.get("title") or url,
                uploader=info.get("uploader") or "",
                playlist=None,
                index=None,
                archive_id=archive_key(info.get("extractor_key"), info.get("id")),
            )]

        tracks: list[TrackRef] = []

        def walk(container: dict, folder: str | None, depth: int):
            for i, entry in enumerate(container.get("entries") or [], 1):
                if not entry:
                    continue
                if _is_container(entry) and depth < MAX_DEPTH:
                    sub = ydl.extract_info(entry["url"], download=False, process=True)
                    walk(sub, sub.get("title") or folder, depth + 1)
                    continue
                tracks.append(TrackRef(
                    url=entry.get("url") or entry.get("webpage_url"),
                    title=entry.get("title") or entry.get("url"),
                    uploader=entry.get("uploader") or "",
                    playlist=folder,
                    index=i,
                    archive_id=archive_key(entry.get("ie_key"), entry.get("id")),
                ))

        title = info.get("title")
        walk(info, title, 0)
        return title, tracks


def search_soundcloud(query: str, limit: int, ydl_params: dict) -> list[dict]:
    from yt_dlp import YoutubeDL

    params = {**ydl_params, "extract_flat": "in_playlist", "skip_download": True}
    with YoutubeDL(params) as ydl:
        info = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
    results = []
    for e in info.get("entries") or []:
        thumbs = e.get("thumbnails") or []
        results.append({
            "url": e.get("url"),
            "title": e.get("title"),
            "uploader": e.get("uploader"),
            "duration": e.get("duration"),
            "thumbnail": next(
                (t["url"] for t in thumbs if t.get("id") == "t300x300"),
                thumbs[-1]["url"] if thumbs else None,
            ),
        })
    return results
