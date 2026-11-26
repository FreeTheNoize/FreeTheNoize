LIMIT = 24


class Search:
    def __init__(self, ctx):
        self.ctx = ctx

    def search(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        from yt_dlp import YoutubeDL

        params = {**self.ctx.ytdlp_params("https://soundcloud.com/"), "no_warnings": True,
                  "extract_flat": "in_playlist", "skip_download": True}
        with YoutubeDL(params) as ydl:
            info = ydl.extract_info(f"scsearch{LIMIT}:{query}", download=False)
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
