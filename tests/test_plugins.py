"""The plugin contract: every plugin loads alone, can be switched off, stays
inside its own routes, events, settings and files, and never imports another
plugin. These tests guard the architecture (see ARCHITECTURE.md)."""
import ast
import json
from pathlib import Path

import pytest
from conftest import login

from freethenoize import plugins
from freethenoize.plugin import Plugin

PKG = Path(__file__).parents[1] / "freethenoize"


def _imports(path: Path) -> list[str]:
    """Absolute dotted names imported by a module (relative ones resolved)."""
    parts = path.relative_to(PKG.parent).with_suffix("").parts
    package = ".".join(parts[:-1])  # a module's package; for __init__.py, the package itself
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                parts = parts[: len(parts) - node.level + 1]
                base = ".".join(parts + ([base] if base else []))
            out.append(base)
            out += [f"{base}.{a.name}" for a in node.names]
    return out


def test_every_builtin_plugin_is_active(kernel_factory):
    kernel, _ = kernel_factory()
    assert [lp.id for lp in kernel.active()] == list(plugins.BUILTIN)
    for pid in plugins.BUILTIN:
        p = plugins.load(pid)
        assert isinstance(p, Plugin) and p.title and p.description


def test_kernel_never_imports_a_plugin():
    for path in PKG.rglob("*.py"):
        if "plugins" in path.relative_to(PKG).parts:
            continue
        for name in _imports(path):
            assert not name.startswith("freethenoize.plugins."), f"{path.name} imports {name}"


@pytest.mark.parametrize("pid", plugins.BUILTIN)
def test_plugins_do_not_import_each_other(pid):
    for path in (PKG / "plugins" / pid).rglob("*.py"):
        for name in _imports(path):
            if name.startswith("freethenoize.plugins."):
                other = name.split(".")[2]
                assert other == pid, f"{path.relative_to(PKG)} imports plugin {other}; use requires + ctx.require()"


@pytest.mark.parametrize("pid", plugins.BUILTIN)
def test_each_plugin_can_be_switched_off(kernel_factory, pid):
    from fastapi.testclient import TestClient

    from freethenoize.web import Auth, create_app

    kernel, _ = kernel_factory(settings={"disabled_plugins": [pid]})
    assert kernel.plugins[pid].status == "disabled"
    dependents = {p for p in plugins.BUILTIN if pid in plugins.load(p).requires}
    for other in set(plugins.BUILTIN) - {pid}:
        expected = "unavailable" if other in dependents else "active"
        assert kernel.plugins[other].status == expected, other
    c = TestClient(create_app(kernel, Auth(password="secret", desktop=False)))
    login(c)
    state = c.get("/api/state").json()
    assert pid not in state["plugins"]
    assert f"/plugins/{pid}/" not in c.get("/").text
    assert c.get(f"/plugins/{pid}/{pid}.js").status_code == 404


def test_plugin_routes_and_ui_are_namespaced(client):
    login(client)
    page = client.get("/").text
    for lp in client.kernel.active():
        ui = PKG / "plugins" / lp.id / "ui"
        if (ui / f"{lp.id}.js").exists():
            assert f'src="/plugins/{lp.id}/{lp.id}.js' in page
            assert client.get(f"/plugins/{lp.id}/{lp.id}.js").status_code == 200
    from freethenoize.web import KERNEL_PREFIXES

    for route in client.app.router.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/"):
            first = path.split("/")[2]
            assert first in KERNEL_PREFIXES or first in plugins.BUILTIN, path


def test_views_have_unique_ids():
    import re

    seen = {}
    for js in (PKG / "plugins").glob("*/ui/*.js"):
        for vid in re.findall(r"registerView\(\{\s*id: '([\w-]+)'", js.read_text(encoding="utf-8")):
            assert vid not in seen, f"view {vid} in {js} and {seen[vid]}"
            seen[vid] = js


def test_ctx_prefixes_events_and_scopes_settings(kernel_factory):
    kernel, _ = kernel_factory()
    got = []
    kernel.bus.listen(lambda k, p: got.append(k))
    ctx = kernel.plugins["convert"].ctx
    ctx.emit("progress", {"x": 1})
    assert got == ["convert.progress"]
    dl = kernel.plugins["downloads"].ctx
    assert dl.settings["concurrency"] == kernel.settings["downloads.concurrency"] == 3
    dl.settings.update({"concurrency": 99})
    assert kernel.settings["downloads.concurrency"] == 8  # limits
    with pytest.raises(RuntimeError):
        ctx.require("downloads")  # not in convert's requires
    assert kernel.plugins["subscriptions"].ctx.require("downloads") is kernel.service("downloads")


def test_settings_from_3x_are_kept(kernel_factory):
    old = {"download_dir": "/x", "concurrency": 5, "colormap": "magma", "check_updates": False,
           "filename_template": "{title}"}
    kernel, _ = kernel_factory(mode="desktop", settings=old)
    s = kernel.settings
    assert s["downloads.concurrency"] == 5
    assert s["downloads.filename_template"] == "{title}"
    assert s["analysis.colormap"] == "magma"
    assert s["check_updates"] is False and s["download_dir"] == "/x"


def test_switched_off_plugin_keeps_its_settings(kernel_factory, tmp_path):
    kernel, _ = kernel_factory(mode="desktop", settings={"disabled_plugins": ["analysis"], "analysis.colormap": "gris"})
    kernel.update_settings({"check_updates": False})
    from freethenoize import paths

    saved = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert saved["analysis.colormap"] == "gris"


def test_legacy_data_files_move_to_the_plugin_folder(kernel_factory, tmp_path):
    data = tmp_path / "data" / "data"
    data.mkdir(parents=True)
    (data / "archive.txt").write_text("soundcloud 1\n", encoding="utf-8")
    (data / "subscriptions.json").write_text("[]", encoding="utf-8")
    kernel, _ = kernel_factory()
    assert "soundcloud 1" in kernel.service("downloads").archive
    assert (data / "downloads" / "archive.txt").exists() and not (data / "archive.txt").exists()
    assert (data / "subscriptions" / "subscriptions.json").exists()


def test_a_broken_plugin_does_not_break_the_app(kernel_factory):
    kernel, _ = kernel_factory(plugin_ids=["convert", "does_not_exist"])
    assert kernel.plugins["convert"].status == "active"
    assert kernel.plugins["does_not_exist"].status == "unavailable"
    assert any(p["id"] == "does_not_exist" for p in kernel.state()["plugin_list"])


def test_plugin_definition_is_validated():
    with pytest.raises(ValueError):
        Plugin(id="Bad-Id", title="x")
    with pytest.raises(ValueError):
        Plugin(id="ok", title="x", limits={"missing": (0, 1)})
    with pytest.raises(ValueError):
        Plugin(id="ok", title="x", modes=frozenset({"mobile"}))
