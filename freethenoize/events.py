"""Fan-out of server events to every connected page (Server-Sent Events).

Producers are plain threads (downloads, conversions); consumers are asyncio
queues, one per open page.
"""
import asyncio
import json
import threading


class EventBus:
    def __init__(self, maxsize: int = 1000):
        self._subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._maxsize)
        with self._lock:
            self._subs.add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = {s for s in self._subs if s[1] is not q}

    def emit(self, kind: str, payload: dict) -> None:
        data = json.dumps({"kind": kind, "payload": payload}, default=str, ensure_ascii=False)
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(_put, q, data)
            except RuntimeError:  # loop closed
                self.unsubscribe(q)


def _put(q: asyncio.Queue, data: str) -> None:
    try:
        q.put_nowait(data)
    except asyncio.QueueFull:
        pass  # a stalled page will resync from /api/state on reconnect
