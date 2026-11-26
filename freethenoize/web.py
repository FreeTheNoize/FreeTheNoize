"""HTTP API + the UI, for the desktop window and for browsers alike.

The kernel's routes live here; each plugin's router is mounted at
/api/<plugin> behind the same auth, CSRF check and error handling, and its
ui/ folder is served at /plugins/<plugin>/.

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
from html import escape
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, paths, plugins, runtime
from .kernel import Kernel
from .plugin import LibraryPath

log = logging.getLogger("freethenoize")

COOKIE = "ftn_session"
SESSION_TTL = 30 * 24 * 3600
OPEN_PATHS = {"/api/health", "/api/session", "/api/login", "/auth/desktop"}
# First path segment under /api/ that belongs to the kernel; no plugin may use one.
KERNEL_PREFIXES = {"health", "session", "login", "logout", "state", "settings", "events", "upload",
                   "stream", "playable", "files", "audio", "soundcloud", "update", "ytdlp"}


class Auth:
    def __init__(self, password: str | None, desktop: bool):
        self.password = password or None
        self.desktop = desktop
        self.desktop_key = secrets.token_urlsafe(24) if desktop else None
        self.secret = self._secret()

    @staticmethod
    def _secret() -> bytes:
        try:
            data = paths.SECRET_FILE.read_bytes()
            if len(data) >= 32:
                return data
        except OSError:
            pass
        data = secrets.token_bytes(32)
        paths.SECRET_FILE.write_bytes(data)
        try:
            os.chmod(paths.SECRET_FILE, 0o600)
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


def create_app(kernel: Kernel, auth: Auth) -> FastAPI:
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

    @app.exception_handler(RequestValidationError)
    async def bad_request(_req, exc: RequestValidationError):
        first = (exc.errors() or [{}])[0]
        where = ".".join(str(x) for x in first.get("loc", ())[1:])
        msg = str(first.get("msg", "Petición no válida.")).removeprefix("Value error, ")
        return JSONResponse({"error": f"{where}: {msg}" if where else msg}, status_code=400)

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

    # ── State, settings & events ──────────────────────────────────────────

    @app.get("/api/state")
    def state():
        return kernel.state()

    @app.patch("/api/settings")
    def settings(patch: dict = Body(...)):
        return kernel.update_settings(patch)

    @app.get("/api/events")
    async def events(request: Request):
        q = kernel.bus.subscribe()

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
                kernel.bus.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── Files & audio (shared by every plugin) ────────────────────────────

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...)):
        return kernel.save_upload(file.filename, file.file)

    @app.get("/api/stream")
    def stream_file(path: LibraryPath):
        return FileResponse(path)

    @app.get("/api/playable")
    def playable(path: LibraryPath):
        return {"url": kernel.playable_url(path)}

    @app.get("/api/files/download")
    def download_file(path: LibraryPath):
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, filename=path.name)

    @app.get("/api/audio/{name}")
    def audio(name: str):
        f = kernel.cached_audio(Path(name).stem)
        if not f or not f.exists():
            raise HTTPException(404)
        return FileResponse(f, media_type="audio/wav")

    # ── SoundCloud session ────────────────────────────────────────────────

    @app.post("/api/soundcloud/token")
    def sc_token(body: dict = Body(...)):
        return kernel.soundcloud_set_token(str(body.get("token", "")))

    @app.delete("/api/soundcloud/token")
    def sc_logout():
        return kernel.soundcloud_logout()

    # ── Updates ───────────────────────────────────────────────────────────

    @app.get("/api/update")
    def update_status():
        return kernel.updates.status()

    @app.post("/api/update/check")
    def update_check():
        return kernel.updates.check()

    @app.post("/api/update/download")
    def update_download():
        return kernel.updates.start_download()

    @app.post("/api/update/skip")
    def update_skip():
        return kernel.updates.skip()

    @app.post("/api/ytdlp/update")
    def ytdlp_update():
        return kernel.update_ytdlp()

    # ── Plugins ───────────────────────────────────────────────────────────

    ui_tags = []
    for lp in kernel.active():
        p = lp.plugin
        if p.id in KERNEL_PREFIXES:
            raise ValueError(f"plugin id {p.id!r} clashes with a kernel route")
        if p.api:
            app.include_router(p.api(lp.service, lp.ctx), prefix=f"/api/{p.id}")
        ui_dir = plugins.folder(p.id) / "ui"
        if ui_dir.is_dir():
            app.mount(f"/plugins/{p.id}", StaticFiles(directory=ui_dir), name=f"plugin-{p.id}")
            v = escape(f"{__version__}-{p.version}")
            if (ui_dir / f"{p.id}.css").is_file():
                ui_tags.append(f'<link rel="stylesheet" href="/plugins/{p.id}/{p.id}.css?v={v}">')
            if (ui_dir / f"{p.id}.js").is_file():
                ui_tags.append(f'<script src="/plugins/{p.id}/{p.id}.js?v={v}"></script>')

    # ── UI ────────────────────────────────────────────────────────────────

    page = (paths.UI_DIR / "index.html").read_text(encoding="utf-8")
    page = page.replace("<!-- plugins -->", "\n".join(ui_tags)).replace("{{version}}", escape(__version__))

    @app.get("/")
    def index():
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=paths.UI_DIR), name="ui")
    return app
