import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def make_kernel(tmp_path, monkeypatch, mode="server", plugin_ids=None, settings=None):
    """A fresh kernel with its own data and music folders."""
    music, data = tmp_path / "music", tmp_path / "data"
    music.mkdir(exist_ok=True)
    monkeypatch.setenv("FTN_DATA_DIR", str(data))
    monkeypatch.setenv("FTN_MUSIC_DIR", str(music))
    from freethenoize import runtime

    runtime.set_mode(mode)
    import freethenoize.paths as paths

    importlib.reload(paths)  # it reads the environment at import time
    if settings:
        import json

        paths.SETTINGS_FILE.write_text(json.dumps(settings), encoding="utf-8")
    from freethenoize.kernel import Kernel

    return Kernel(plugin_ids), music


@pytest.fixture()
def kernel_factory(tmp_path, monkeypatch):
    from freethenoize import runtime

    yield lambda **kw: make_kernel(tmp_path, monkeypatch, **kw)
    runtime.set_mode("desktop")


@pytest.fixture()
def client(kernel_factory):
    """HTTP client against a server-mode app with password "secret"."""
    from fastapi.testclient import TestClient

    from freethenoize.web import Auth, create_app

    kernel, music = kernel_factory()
    c = TestClient(create_app(kernel, Auth(password="secret", desktop=False)))
    c.music = music
    c.kernel = kernel
    return c


def login(c):
    assert c.post("/api/login", json={"password": "secret"}).status_code == 200
