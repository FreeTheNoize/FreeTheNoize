"""Download queue: resolves links, downloads in parallel, tags the results."""
import itertools
import json
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ...plugin import Ctx

from ...audio import tagging
from . import naming
from .resolve import resolve, source_of

LOSSLESS_EXTS = {"wav", "flac", "aif", "aiff", "alac"}

# Order matters: the original upload always wins over any stream.
FORMAT_SELECTOR = "download/bestaudio/best"
# After yt-dlp's own "quality" (original > Go+ > 160k+), prefer higher bitrate:
# a free SoundCloud track offers MP3 128k and AAC 96k.
FORMAT_SORT = ["quality", "abr"]

_ids = itertools.count(1)


class Cancelled(Exception):
    pass


@dataclass
class Job:
    url: str
    title: str
    uploader: str = ""
    playlist: str | None = None
    index: int | None = None
    id: int = field(default_factory=lambda: next(_ids))
    status: str = "queued"  # queued|downloading|tagging|done|skipped|error|cancelled
    progress: float = 0.0
    speed: float | None = None
    eta: int | None = None
    artist: str = ""
    thumbnail: str | None = None
    quality: dict | None = None
    bpm: float | None = None
    key: str | None = None
    camelot: str | None = None
    origin: str | None = None
    path: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")}


def describe_quality(info: dict) -> dict:
    """What we actually got, so the UI can show an honest badge."""
    fmt = info.get("format_id") or ""
    ext = (info.get("ext") or "").lower()
    acodec = (info.get("acodec") or "").split(".")[0]
    abr = info.get("abr")
    if fmt == "download":
        lossless = ext in LOSSLESS_EXTS
        return {"tier": "original", "lossless": lossless,
                "label": f"Original {ext.upper()}", "preview": False}
    preview = "preview" in fmt
    codec = {"mp4a": "AAC", "opus": "Opus", "mp3": "MP3"}.get(acodec, acodec.upper() or ext.upper())
    label = f"{codec} {int(abr)}k" if abr else codec
    if info.get("format_note") == "Premium":
        tier = "premium"
        label += " · Go+"
    elif abr and abr >= 160:
        tier = "high"
    else:
        tier = "standard"
    if preview:
        label = "Preview 30 s"
    return {"tier": tier, "lossless": False, "label": label, "preview": preview}


def _best_thumbnail(info: dict) -> tuple[str | None, str | None]:
    """(url for embedding, small url for the UI)."""
    thumbs = info.get("thumbnails") or []
    by_id = {t.get("id"): t["url"] for t in thumbs if t.get("url")}
    best = by_id.get("original") or info.get("thumbnail")
    small = by_id.get("t300x300") or by_id.get("large") or info.get("thumbnail")
    return best, small


class _Logger:
    def __init__(self, job: Job):
        self.job = job

    def debug(self, msg):
        pass

    info = debug

    def warning(self, msg):
        # The desktop builds ship ffmpeg without ffprobe. yt-dlp then can't
        # probe an HLS download, assumes it needs fixing and remuxes it with
        # ffmpeg anyway, so the result is the same: not worth showing.
        if "ffprobe" in str(msg):
            return
        if len(self.job.warnings) < 5:
            self.job.warnings.append(str(msg).removeprefix("WARNING: "))

    def error(self, msg):
        self.job.error = str(msg).removeprefix("ERROR: ")


class Archive:
    """IDs of everything already downloaded, in yt-dlp's archive format."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        try:
            self._ids = set(path.read_text(encoding="utf-8").split("\n"))
        except OSError:
            self._ids = set()

    def __contains__(self, key: str) -> bool:
        return key in self._ids

    def add(self, key: str):
        with self._lock:
            if key not in self._ids:
                self._ids.add(key)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(key + "\n")


class History:
    """One JSON line per finished download."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def append(self, record: dict):
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, limit: int = 500) -> list[dict]:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in reversed(lines[-limit:]):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


class DownloadManager:
    """Public API for other plugins (declare requires=("downloads",)):
    add(urls, origin, on_resolved), snapshot(), cancel_all()."""

    def __init__(self, ctx: "Ctx"):
        self.ctx = ctx
        self.settings = ctx.settings
        self.emit = ctx.emit
        self.archive = Archive(ctx.data_file("archive.txt", legacy="archive.txt"))
        self.history = History(ctx.data_file("history.jsonl", legacy="history.jsonl"))
        self.jobs: dict[int, Job] = {}
        self._pending: deque[Job] = deque()
        self._lock = threading.Lock()
        self._workers = 0
        self._last_emit: dict[int, float] = {}

    def state(self) -> dict:
        return {"jobs": self.snapshot()}

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, urls: list[str], origin: str | None = None,
            on_resolved: Callable[[dict], None] | None = None) -> None:
        """origin: where the request came from (e.g. a subscription id).
        on_resolved({"title", "count", "skipped", "error"}) runs once the link
        has been expanded into tracks."""
        for url in urls:
            threading.Thread(target=self._resolve_and_queue, args=(url, origin, on_resolved),
                             daemon=True).start()

    def cancel(self, job_id: int):
        job = self.jobs.get(job_id)
        if not job:
            return
        job._cancel.set()
        with self._lock:
            if job in self._pending:
                self._pending.remove(job)
                job.status = "cancelled"
        self._emit_job(job, force=True)

    def cancel_all(self):
        for job in list(self.jobs.values()):
            if job.status in ("queued", "downloading"):
                self.cancel(job.id)

    def retry(self, job_id: int):
        old = self.jobs.get(job_id)
        if not old or old.status not in ("error", "cancelled"):
            return
        job = Job(url=old.url, title=old.title, uploader=old.uploader,
                  playlist=old.playlist, index=old.index, id=old.id, origin=old.origin)
        self.jobs[job.id] = job
        self._enqueue([job])

    def clear_finished(self):
        for job_id, job in list(self.jobs.items()):
            if job.status in ("done", "skipped", "error", "cancelled"):
                del self.jobs[job_id]
        self.emit("jobs", {"jobs": [j.public() for j in self.jobs.values()]})

    def snapshot(self) -> list[dict]:
        return [j.public() for j in self.jobs.values()]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _resolve_and_queue(self, url: str, origin: str | None = None,
                           on_resolved: Callable[[dict], None] | None = None):
        self.emit("resolving", {"url": url, "active": True, "origin": origin})
        try:
            title, refs = resolve(url, {**self.ctx.ytdlp_params(url), "no_warnings": True})
        except Exception as e:
            err = _short_error(e)
            self.emit("resolving", {"url": url, "active": False, "error": err, "origin": origin})
            if on_resolved:
                on_resolved({"title": None, "count": 0, "skipped": 0, "error": err})
            return
        refs = [r for r in refs if r.url]
        skipped = 0
        if self.settings["skip_downloaded"]:
            # Cheap pre-check on the flat listing: re-syncing a 500-track
            # playlist should not hit SoundCloud 500 times.
            before = len(refs)
            refs = [r for r in refs if not (r.archive_id and r.archive_id in self.archive)]
            skipped = before - len(refs)
        summary = {"title": title, "count": len(refs), "skipped": skipped, "error": None}
        self.emit("resolving", {"url": url, "active": False, "origin": origin, **summary})
        if on_resolved:
            on_resolved(summary)
        use_folder = self.settings["playlist_subfolder"]
        jobs = [
            Job(url=r.url, title=r.title, uploader=r.uploader,
                playlist=r.playlist if use_folder else None, index=r.index, origin=origin)
            for r in refs
        ]
        for job in jobs:
            self.jobs[job.id] = job
        self._enqueue(jobs)

    def _enqueue(self, jobs: list[Job]):
        with self._lock:
            self._pending.extend(jobs)
        for job in jobs:
            self._emit_job(job, force=True)
        self._spawn_workers()

    def _spawn_workers(self):
        with self._lock:
            wanted = min(self.settings["concurrency"], len(self._pending))
            to_start = max(0, wanted - self._workers)
            self._workers += to_start
        for _ in range(to_start):
            threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            with self._lock:
                if not self._pending or self._workers > self.settings["concurrency"]:
                    self._workers -= 1
                    return
                job = self._pending.popleft()
            try:
                self._run(job)
            except Cancelled:
                job.status = "cancelled"
            except Exception as e:
                job.status = "error"
                job.error = job.error or _short_error(e)
                traceback.print_exc()
            self._emit_job(job, force=True)

    def _emit_job(self, job: Job, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_emit.get(job.id, 0) < 0.25:
            return
        self._last_emit[job.id] = now
        self.emit("job", job.public())

    def _run(self, job: Job):
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadCancelled

        if job._cancel.is_set():
            raise Cancelled
        job.status = "downloading"
        self._emit_job(job, force=True)

        params = {**self.ctx.ytdlp_params(job.url), "format": FORMAT_SELECTOR,
                  "format_sort": FORMAT_SORT, "logger": _Logger(job)}
        with YoutubeDL(params) as ydl:
            info = ydl.extract_info(job.url, download=False)
            if info.get("_type") == "playlist":
                raise RuntimeError("Enlace inesperado de playlist dentro de la cola.")

            archive_id = f"{info.get('extractor_key', '').lower()} {info.get('id')}"
            meta = self._metadata(info, job)
            job.artist = meta["artist"]
            job.title = meta["title"]
            job.quality = describe_quality(info)
            cover_url, job.thumbnail = _best_thumbnail(info)

            if self.settings["skip_downloaded"] and archive_id in self.archive:
                job.status = "skipped"
                job.progress = 1.0
                return

            dest_dir = self.ctx.music_dir()
            if job.playlist:
                dest_dir /= naming.safe_filename(job.playlist)
            dest_dir.mkdir(parents=True, exist_ok=True)
            stem = naming.render_template(self.settings["filename_template"], {
                "artist": meta["artist"], "title": meta["title"],
                "uploader": info.get("uploader") or "",
                "playlist": job.playlist or "",
                "index": f"{job.index:02d}" if job.index else "",
                "date": meta.get("date") or "",
                "id": info.get("id") or "",
            })
            self._emit_job(job, force=True)

            final_paths: list[str] = []

            def on_progress(d):
                if job._cancel.is_set():
                    raise DownloadCancelled()
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if total:
                        job.progress = min(d.get("downloaded_bytes", 0) / total, 1.0)
                    elif d.get("fragment_count"):
                        job.progress = (d.get("fragment_index") or 0) / d["fragment_count"]
                    job.speed = d.get("speed")
                    job.eta = d.get("eta")
                    self._emit_job(job)

            ydl.params["outtmpl"]["default"] = str(dest_dir / (stem.replace("%", "%%") + ".%(ext)s"))
            ydl.params["overwrites"] = True
            ydl.add_progress_hook(on_progress)
            ydl.add_post_hook(final_paths.append)
            if source_of(job.url) != "soundcloud":
                # YouTube serves opus-in-webm; remux (no re-encode) to a taggable file.
                from yt_dlp.postprocessor import FFmpegExtractAudioPP
                ydl.add_post_processor(FFmpegExtractAudioPP(ydl, preferredcodec="best"), when="post_process")
            try:
                ydl.process_ie_result(info, download=True)
            except DownloadCancelled:
                raise Cancelled

        if not final_paths:
            raise RuntimeError(job.error or "yt-dlp no ha generado ningún archivo.")
        path = Path(final_paths[-1])

        job.status = "tagging"
        job.progress = 1.0
        self._emit_job(job, force=True)
        if self.settings["detect_bpm_key"]:
            try:
                from ...audio import bpm_key

                mk = bpm_key(path)
                job.bpm, job.key, job.camelot = mk["bpm"], mk["key"], mk["camelot"]
                meta["bpm"], meta["key"] = mk["bpm"], mk["key"]
            except Exception as e:
                job.warnings.append(f"No se ha podido calcular BPM/tonalidad: {_short_error(e)}")
        self._tag(path, meta, cover_url, job)

        job.path = str(path)
        job.status = "done"
        self.archive.add(archive_id)
        self.history.append({
            "time": time.time(), "url": job.url, "path": job.path,
            "title": job.title, "artist": job.artist, "quality": job.quality,
            "thumbnail": job.thumbnail, "bpm": job.bpm, "key": job.key, "camelot": job.camelot,
        })

    def _metadata(self, info: dict, job: Job) -> dict:
        uploader = info.get("uploader") or job.uploader or ""
        title = info.get("track") or info.get("title") or job.title
        if self.settings["clean_titles"]:
            title = naming.clean_title(title)
        artist = info.get("artist") or ""
        if not artist:
            if self.settings["split_artist_title"]:
                artist, title = naming.split_artist_title(title, uploader)
            else:
                artist = uploader
        date = info.get("upload_date") or ""
        return {
            "title": title,
            "artist": artist,
            "album": job.playlist or info.get("album") or "",
            "album_artist": uploader if job.playlist else "",
            "genre": info.get("genre") or "",
            "date": f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else "",
            "comment": info.get("webpage_url") or job.url,
            "url": info.get("webpage_url") or job.url,
        }

    def _tag(self, path: Path, meta: dict, cover_url: str | None, job: Job):
        cover = None
        if cover_url and (self.settings["embed_artwork"] or self.settings["save_artwork_file"]):
            cover = _fetch(cover_url) or _fetch(cover_url.replace("-original.", "-t500x500."))
        if cover and self.settings["save_artwork_file"]:
            ext = ".png" if tagging.image_mime(cover) == "image/png" else ".jpg"
            path.with_suffix(ext).write_bytes(cover)
        embedded = None
        if cover and self.settings["embed_artwork"]:
            try:
                embedded = tagging.shrink_cover(cover, self.settings["artwork_max_px"])
            except Exception:
                embedded = cover
        try:
            if not tagging.write_tags(path, meta, embedded):
                job.warnings.append(f"El formato {path.suffix} no admite etiquetas.")
        except Exception as e:
            job.warnings.append(f"No se han podido escribir las etiquetas: {e}")


def _fetch(url: str) -> bytes | None:
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except Exception:
        return None


def _short_error(e: Exception) -> str:
    msg = str(e).removeprefix("ERROR: ")
    return msg.splitlines()[0][:300] if msg else type(e).__name__
