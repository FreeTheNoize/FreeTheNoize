"""The plugin contract: everything a plugin can use from the kernel.

A plugin is a package in `freethenoize/plugins/<id>/` whose `__init__.py`
defines `PLUGIN = Plugin(...)`. It talks to the kernel only through the
`Ctx` it receives and the shared libraries (`freethenoize.audio`,
`freethenoize.files`, `freethenoize.ytdlp`, `freethenoize.ffmpeg`). It never
imports another plugin: if it needs one, it lists it in `requires` and gets
its service with `ctx.require(id)`.

    PLUGIN = Plugin(
        id="convert",
        title="Convertir",
        service=ConvertService,          # ConvertService(ctx)
        api=routes,                      # routes(service, ctx) -> APIRouter, mounted at /api/convert
        settings={"normalize": False},   # ctx.settings["normalize"], "convert.normalize" for the page
    )

The service may define `start()`, `stop()` and `state() -> dict` (added to
/api/state under plugins.<id>). UI files in `<plugin>/ui/` (`<id>.js`,
`<id>.css`) are served at /plugins/<id>/ and loaded by the page.

See ARCHITECTURE.md for the whole picture.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Callable

from pydantic import AfterValidator

from . import paths, runtime, ytdlp

if TYPE_CHECKING:
    import numpy as np
    from fastapi import APIRouter

    from .kernel import Kernel

PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
MODES = frozenset({"desktop", "server"})


@dataclass(frozen=True)
class Plugin:
    id: str
    title: str
    version: str = "1.0"
    description: str = ""
    service: Callable[[Ctx], Any] | None = None
    api: Callable[[Any, Ctx], APIRouter] | None = None
    settings: dict = field(default_factory=dict)
    server_locked: frozenset[str] = frozenset()
    limits: dict[str, tuple[float, float]] = field(default_factory=dict)
    requires: tuple[str, ...] = ()
    modes: frozenset[str] = MODES

    def __post_init__(self):
        if not PLUGIN_ID.match(self.id):
            raise ValueError(f"plugin id {self.id!r}: lowercase letters, digits and _, starting with a letter")
        if not self.modes or not self.modes <= MODES:
            raise ValueError(f"plugin {self.id}: modes must be a subset of {sorted(MODES)}")
        unknown = (set(self.server_locked) | set(self.limits)) - set(self.settings)
        if unknown:
            raise ValueError(f"plugin {self.id}: {sorted(unknown)} are not in settings")


class Ctx:
    """What the kernel gives a plugin. One per plugin."""

    def __init__(self, kernel: Kernel, plugin: Plugin):
        self._kernel = kernel
        self.plugin = plugin
        self.id = plugin.id
        self.settings = kernel.settings.scoped(plugin.id)
        self.log = logging.getLogger(f"freethenoize.{plugin.id}")

    # ── Events ───────────────────────────────────────────────────────────────

    def emit(self, kind: str, payload: dict) -> None:
        """Send "<plugin>.<kind>" to every open page and in-process listener."""
        self._kernel.emit(f"{self.id}.{kind}", payload)

    def on(self, kind: str, fn: Callable[[dict], None]) -> Callable[[], None]:
        """Listen to an event by full name ("downloads.job", "settings"…)."""
        return self._kernel.bus.listen(lambda k, p: fn(p) if k == kind else None)

    # ── Other plugins ────────────────────────────────────────────────────────

    def require(self, plugin_id: str) -> Any:
        """The service of a plugin listed in `requires`."""
        if plugin_id not in self.plugin.requires:
            raise RuntimeError(f"{self.id}: add {plugin_id!r} to requires before using it")
        return self._kernel.service(plugin_id)

    # ── Mode, folders, files ─────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return runtime.mode()

    def is_server(self) -> bool:
        return runtime.is_server()

    def music_dir(self) -> Path:
        return Path(self._kernel.settings["download_dir"]).expanduser()

    @property
    def data_dir(self) -> Path:
        d = paths.DATA_DIR / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def cache_dir(self) -> Path:
        d = paths.CACHE_DIR / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def data_file(self, name: str, legacy: str | None = None) -> Path:
        """DATA_DIR/<plugin>/<name>. `legacy`: where 3.x kept it (relative to
        DATA_DIR); it is moved here the first time."""
        target = self.data_dir / name
        if legacy and not target.exists():
            old = paths.DATA_DIR / legacy
            if old.is_file():
                shutil.move(str(old), str(target))
        return target

    def check_path(self, raw: str, must_exist: bool = True) -> Path:
        """Validate a path from the page (on a server: only the music folder
        and uploads). In routes, prefer the `LibraryPath` type."""
        return self._kernel.check_path(raw, must_exist)

    # ── Audio for the page ───────────────────────────────────────────────────

    def playable_url(self, path: Path) -> str:
        """URL the page can play for any audio file (transcoded if needed)."""
        return self._kernel.playable_url(path)

    def samples_url(self, samples: np.ndarray, sr: int) -> str:
        """URL of a temporary WAV made from float samples (frames, channels)."""
        return self._kernel.samples_url(samples, sr)

    # ── yt-dlp ───────────────────────────────────────────────────────────────

    def ytdlp_params(self, url: str = "") -> dict:
        """Base YoutubeDL params (ffmpeg, retries, SoundCloud session)."""
        return ytdlp.base_params(url)


# ── Path type for routes ──────────────────────────────────────────────────────

_active: Kernel | None = None


def _check(raw: str) -> Path:
    if _active is None:
        raise RuntimeError("kernel not started")
    return _active.check_path(raw)


# A path from the page, already checked: it exists and, on a server, lives in
# the music folder or the upload area (otherwise 403). Use it for every path a
# route receives, in bodies and query strings alike:
#     def analyze(body: PathBody): ...   with   class PathBody(BaseModel): path: LibraryPath
#     def cover(path: LibraryPath): ...
LibraryPath = Annotated[str, AfterValidator(_check)]
