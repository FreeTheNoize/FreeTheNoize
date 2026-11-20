"""Subscriptions: playlists, likes or profiles that are re-checked on a timer.

Each check feeds the link to the download queue; the archive makes sure only
tracks that are new since the last check get downloaded.
"""
import json
import secrets
import threading
import time
from typing import Callable

from .downloads.manager import DownloadManager
from .paths import SUBSCRIPTIONS_FILE

TICK_SECONDS = 60
MIN_INTERVAL_H = 0.25


class Subscriptions:
    def __init__(self, downloads: DownloadManager, emit: Callable[[str, dict], None]):
        self.downloads = downloads
        self.emit = emit
        self._lock = threading.Lock()
        self._checking: set[str] = set()
        try:
            self._items: dict[str, dict] = {
                s["id"]: s for s in json.loads(SUBSCRIPTIONS_FILE.read_text(encoding="utf-8"))
            }
        except (OSError, ValueError, KeyError, TypeError):
            self._items = {}
        self._stop = threading.Event()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self):
        tmp = SUBSCRIPTIONS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(self._items.values()), indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(SUBSCRIPTIONS_FILE)

    def _public(self, sub: dict) -> dict:
        return {**sub, "checking": sub["id"] in self._checking,
                "next_check": (sub.get("last_check") or 0) + sub["interval_hours"] * 3600
                if sub["enabled"] else None}

    def _changed(self, sub: dict):
        self.emit("subscription", self._public(sub))

    # ── API ──────────────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        with self._lock:
            return [self._public(s) for s in self._items.values()]

    def add(self, url: str, interval_hours: float = 6, title: str | None = None) -> dict:
        url = url.strip()
        if not url.startswith(("https://", "http://")):
            raise ValueError("Eso no parece un enlace.")
        with self._lock:
            if any(s["url"] == url for s in self._items.values()):
                raise ValueError("Ya estás suscrito a ese enlace.")
            sub = {
                "id": secrets.token_hex(4), "url": url, "title": title or url,
                "interval_hours": max(float(interval_hours), MIN_INTERVAL_H),
                "enabled": True, "created": time.time(), "last_check": None,
                "last_result": None, "total_new": 0,
            }
            self._items[sub["id"]] = sub
            self._save()
        self.check(sub["id"])  # first sync right away
        return self._public(sub)

    def update(self, sub_id: str, patch: dict) -> dict:
        with self._lock:
            sub = self._items[sub_id]
            if "enabled" in patch:
                sub["enabled"] = bool(patch["enabled"])
            if "interval_hours" in patch:
                sub["interval_hours"] = max(float(patch["interval_hours"]), MIN_INTERVAL_H)
            if patch.get("title"):
                sub["title"] = str(patch["title"])[:200]
            self._save()
        self._changed(sub)
        return self._public(sub)

    def remove(self, sub_id: str) -> None:
        with self._lock:
            self._items.pop(sub_id, None)
            self._save()
        self.emit("subscription_removed", {"id": sub_id})

    def check(self, sub_id: str) -> None:
        with self._lock:
            sub = self._items.get(sub_id)
            if not sub or sub_id in self._checking:
                return
            self._checking.add(sub_id)
        self._changed(sub)

        def done(summary: dict):
            with self._lock:
                self._checking.discard(sub_id)
                sub["last_check"] = time.time()
                if summary.get("title") and sub["title"] == sub["url"]:
                    sub["title"] = summary["title"]
                sub["last_result"] = {
                    "new": summary["count"], "known": summary["skipped"],
                    "error": summary["error"],
                }
                sub["total_new"] += summary["count"]
                self._save()
            self._changed(sub)

        self.downloads.add([sub["url"]], origin=f"sub:{sub_id}", on_resolved=done)

    # ── Scheduler ────────────────────────────────────────────────────────────

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="subscriptions").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(TICK_SECONDS):
            now = time.time()
            with self._lock:
                due = [s["id"] for s in self._items.values()
                       if s["enabled"] and s["id"] not in self._checking
                       and now - (s.get("last_check") or 0) >= s["interval_hours"] * 3600]
            for sub_id in due:
                self.check(sub_id)
