"""HTTP API + the UI, for the desktop window and for browsers alike.

Auth
- desktop: the window gets a one-time key in its first URL, exchanged for a
  session cookie; other local processes and web pages cannot use the API.
- server: if FTN_PASSWORD is set, a password exchanges for the cookie.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import runtime
from .core import Core
from .paths import SECRET_FILE, UI_DIR

log = logging.getLogger("freethenoize")

COOKIE = "ftn_session"
SESSION_TTL = 30 * 24 * 3600
OPEN_PATHS = {"/api/health", "/api/session", "/api/login", "/auth/desktop"}


class Auth:
    def __init__(self, password: str | None, desktop: bool):
        self.password = password or None
        self.desktop = desktop
        self.desktop_key = secrets.token_urlsafe(24) if desktop else None
        self.secret = self._secret()

    @staticmethod
    def _secret() -> bytes:
        try:
            data = SECRET_FILE.read_bytes()
            if len(data) >= 32:
                return data
        except OSError:
            pass
        data = secrets.token_bytes(32)
        SECRET_FILE.write_bytes(data)
        try:
            os.chmod(SECRET_FILE, 0o600)
        except OSError:
            pass
        return data

    @property
    def required(self) -> bool:
        return self.desktop or bool(self.password)

    def _sign(self, issued: str) -> str:
        # Changing the password invalidates every session.
        salt = (self.password or self.desktop_key or "").encode()
        return hmac.new(self.secret + salt, issued.encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        issued = str(int(time.time()))
        return f"{issued}.{self._sign(issued)}"

    def valid(self, cookie: str | None) -> bool:
        if not self.required:
            return True
        if not cookie or "." not in cookie:
            return False
        issued, sig = cookie.split(".", 1)
        if not issued.isdigit() or time.time() - int(issued) > SESSION_TTL:
            return False
        return hmac.compare_digest(sig, self._sign(issued))


# ── Request bodies ──────────────────────────────────────────────────────────

class Text(BaseModel):
    text: str


class PathBody(BaseModel):
    path: str


class Pair(BaseModel):
    a: str
    b: str


class ConvertBody(BaseModel):
    files: list[str]
    format: str
    out_dir: str | None = None
    normalize_lufs: float | None = None


class SubBody(BaseModel):
    url: str
    interval_hours: float = 6


def create_app(core: Core, auth: Auth) -> FastAPI:
    app = FastAPI(title="FreeTheNoize", docs_url=None, redoc_url=None, openapi_url=None)

    # ── Errors ────────────────────────────────────────────────────────────

    def _err(status: int):
        async def handler(_req, exc):
            return JSONResponse({"error": str(exc) or type(exc).__name__}, status_code=status)
        return handler

    app.add_exception_handler(ValueError, _err(400))
    app.add_exception_handler(PermissionError, _err(403))
    app.add_exception_handler(FileNotFoundError, _err(404))
    app.add_exception_handler(KeyError, _err(404))
    app.add_exception_handler(RuntimeError, _err(500))

    # ── Auth & CSRF ───────────────────────────────────────────────────────

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "Origen no permitido."}, status_code=403)
        if path.startswith("/api/") and path not in OPEN_PATHS:
            if not auth.valid(request.cookies.get(COOKIE)):
                return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    def _set_cookie(resp: Response, request: Request):
        resp.set_cookie(COOKIE, auth.issue(), max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")

    @app.get("/auth/desktop")
    def desktop_login(request: Request, key: str = ""):
        if not auth.desktop_key or not hmac.compare_digest(key, auth.desktop_key):
            raise HTTPException(403)
        resp = RedirectResponse("/", status_code=303)
        _set_cookie(resp, request)
        return resp

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/session")
    def session(request: Request):
        return {"authenticated": auth.valid(request.cookies.get(COOKIE)),
                "password_required": bool(auth.password), "mode": runtime.mode()}

    @app.post("/api/login")
    async def login(request: Request, body: dict = Body(...)):
        if not auth.password:
            raise HTTPException(400, "Este servidor no usa contraseña.")
        await asyncio.sleep(0.4)  # blunt brute force
        if not hmac.compare_digest(str(body.get("password", "")).encode(), auth.password.encode()):
            return JSONResponse({"error": "Contraseña incorrecta."}, status_code=401)
        resp = JSONResponse({"ok": True})
        _set_cookie(resp, request)
        return resp

    @app.post("/api/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ── State & events ────────────────────────────────────────────────────

    @app.get("/api/state")
    def state():
        return core.state()

    @app.patch("/api/settings")
    def settings(patch: dict = Body(...)):
        return core.update_settings(patch)

    @app.get("/api/events")
    async def events(request: Request):
        q = core.bus.subscribe()

        async def stream():
            try:
                yield "retry: 2000\n\n"
                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {data}\n\n"
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": ping\n\n"
            finally:
                core.bus.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── Downloads ─────────────────────────────────────────────────────────

    @app.post("/api/downloads")
    def add_downloads(body: Text):
        return core.add_downloads(body.text)

    @app.post("/api/downloads/{job_id}/cancel")
    def cancel(job_id: int):
        core.downloads.cancel(job_id)
        return {"ok": True}

    @app.post("/api/downloads/{job_id}/retry")
    def retry(job_id: int):
        core.downloads.retry(job_id)
        return {"ok": True}

    @app.post("/api/downloads/cancel-all")
    def cancel_all():
        core.downloads.cancel_all()
        return {"ok": True}

    @app.post("/api/downloads/clear")
    def clear():
        core.downloads.clear_finished()
        return {"ok": True}

    @app.get("/api/history")
    def history():
        return core.history()

    @app.get("/api/search")
    def search(q: str = ""):
        return core.search(q)

    @app.get("/api/update")
    def update_status():
        return core.updates.status()

    @app.post("/api/update/check")
    def update_check():
        return core.updates.check()

    @app.post("/api/update/download")
    def update_download():
        return core.updates.start_download()

    @app.post("/api/update/skip")
    def update_skip():
        return core.updates.skip()

    @app.post("/api/preview")
    def preview(body: Text):
        return core.preview(body.text)

    @app.get("/api/preview/{name}")
    def preview_audio(name: str, t: float = 0):
        try:
            chunks = core.previews.stream(Path(name).stem, max(t, 0))
        except KeyError:
            raise HTTPException(404)
        return StreamingResponse(chunks, media_type="audio/mpeg",
                                 headers={"Cache-Control": "no-store"})

    # ── Subscriptions ─────────────────────────────────────────────────────

    @app.get("/api/subscriptions")
    def subs():
        return core.subscriptions.list()

    @app.post("/api/subscriptions")
    def sub_add(body: SubBody):
        return core.subscriptions.add(body.url, body.interval_hours)

    @app.patch("/api/subscriptions/{sub_id}")
    def sub_update(sub_id: str, patch: dict = Body(...)):
        return core.subscriptions.update(sub_id, patch)

    @app.delete("/api/subscriptions/{sub_id}")
    def sub_delete(sub_id: str):
        core.subscriptions.remove(sub_id)
        return {"ok": True}

    @app.post("/api/subscriptions/{sub_id}/check")
    def sub_check(sub_id: str):
        core.subscriptions.check(sub_id)
        return {"ok": True}

    # ── SoundCloud ────────────────────────────────────────────────────────

    @app.post("/api/soundcloud/token")
    def sc_token(body: dict = Body(...)):
        return core.soundcloud_set_token(str(body.get("token", "")))

    @app.delete("/api/soundcloud/token")
    def sc_logout():
        return core.soundcloud_logout()

    # ── Files ─────────────────────────────────────────────────────────────

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...)):
        return core.save_upload(file.filename, file.file)

    @app.get("/api/library")
    def library():
        return core.library_list()

    @app.delete("/api/library")
    def library_delete(path: str):
        core.delete_file(path)
        return {"ok": True}

    @app.get("/api/stream")
    def stream_file(path: str):
        return FileResponse(core.check_path(path))

    @app.get("/api/playable")
    def playable(path: str):
        return {"url": core.playable_url(core.check_path(path))}

    @app.get("/api/files/download")
    def download_file(path: str):
        p = core.check_path(path)
        if not p.is_file():
            raise HTTPException(404)
        return FileResponse(p, filename=p.name)

    @app.get("/api/cover")
    def cover(path: str):
        img = core.library.cover(core.check_path(path))
        if not img:
            return Response(status_code=204)
        return FileResponse(img, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/audio/{name}")
    def audio(name: str):
        f = core.cached_audio(Path(name).stem)
        if not f or not f.exists():
            raise HTTPException(404)
        return FileResponse(f, media_type="audio/wav")

    # ── Analysis & conversion ─────────────────────────────────────────────

    @app.post("/api/analyze")
    def analyze(body: PathBody):
        return core.analyze(body.path)

    @app.post("/api/null-test")
    def null_test(body: Pair):
        return core.null_test(body.a, body.b)

    @app.post("/api/convert")
    def convert(body: ConvertBody):
        return core.convert(body.files, body.format, body.out_dir, body.normalize_lufs)

    @app.post("/api/ytdlp/update")
    def ytdlp_update():
        return core.update_ytdlp()

    # ── UI ────────────────────────────────────────────────────────────────

    @app.get("/")
    def index():
        return FileResponse(UI_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=UI_DIR), name="ui")
    return app
