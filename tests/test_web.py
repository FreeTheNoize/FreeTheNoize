"""HTTP API in server mode: auth, path sandbox, uploads, library, analysis."""
import shutil
import subprocess

import pytest

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    music, data = tmp_path / "music", tmp_path / "data"
    music.mkdir()
    monkeypatch.setenv("FTN_DATA_DIR", str(data))
    monkeypatch.setenv("FTN_MUSIC_DIR", str(music))
    # paths.py and friends read the environment at import time.
    import importlib

    from freethenoize import runtime
    runtime.set_mode("server")
    import freethenoize.paths as paths
    importlib.reload(paths)
    import freethenoize.settings as settings
    importlib.reload(settings)
    import freethenoize.library as library
    importlib.reload(library)
    import freethenoize.subscriptions as subscriptions
    importlib.reload(subscriptions)
    import freethenoize.downloads.manager as manager
    importlib.reload(manager)
    import freethenoize.core as core
    importlib.reload(core)
    import freethenoize.web as web
    importlib.reload(web)
    from fastapi.testclient import TestClient

    c = TestClient(web.create_app(core.Core(), web.Auth(password="secret", desktop=False)))
    c.music = music
    yield c
    runtime.set_mode("desktop")


def login(c):
    assert c.post("/api/login", json={"password": "secret"}).status_code == 200


def test_auth_required(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    login(client)
    state = client.get("/api/state").json()
    assert state["mode"] == "server"
    assert "download_dir" in state["locked_settings"]


def test_cross_origin_writes_blocked(client):
    login(client)
    r = client.patch("/api/settings", json={"concurrency": 2}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_download_dir_locked_on_server(client):
    login(client)
    before = client.get("/api/state").json()["settings"]["download_dir"]
    after = client.patch("/api/settings", json={"download_dir": "/etc", "concurrency": 5}).json()
    assert after["download_dir"] == before
    assert after["concurrency"] == 5


def test_paths_outside_library_rejected(client):
    login(client)
    assert client.post("/api/analyze", json={"path": "/etc/hosts"}).status_code == 403
    assert client.get("/api/stream", params={"path": "/etc/hosts"}).status_code == 403
    assert client.get("/api/files/download", params={"path": str(client.music / ".." / "x")}).status_code in (403, 404)


def test_upload_rejects_non_audio(client):
    login(client)
    r = client.post("/api/upload", files={"file": ("evil.sh", b"#!/bin/sh")})
    assert r.status_code == 400


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_library_stream_analyze(client):
    login(client)
    f = client.music / "Artist - Tune.flac"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-ac", "2", str(f)], check=True)
    items = client.get("/api/library").json()["items"]
    assert [i["rel"] for i in items] == ["Artist - Tune.flac"]
    assert client.get("/api/stream", params={"path": str(f)}, headers={"Range": "bytes=0-9"}).status_code == 206
    r = client.post("/api/analyze", json={"path": str(f)}).json()
    assert r["cutoff"]["level"] == "good" and "musical" in r
    assert client.get(r["audio_url"]).status_code == 200
    up = client.post("/api/upload", files={"file": ("copy.flac", f.read_bytes())}).json()
    assert client.post("/api/analyze", json={"path": up["path"]}).status_code == 200
    assert client.delete("/api/library", params={"path": str(f)}).status_code == 200
    assert not f.exists()


def test_preview_validation(client):
    assert client.post("/api/preview", json={"text": "https://x"}).status_code == 401
    login(client)
    assert client.post("/api/preview", json={"text": "not a url"}).status_code == 400
    assert client.get("/api/preview/nope.mp3").status_code == 404
