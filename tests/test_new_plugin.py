"""tools/new_plugin.py creates a plugin that loads, serves its API and UI, and
follows the same rules as the built-in ones."""
import re
import sys

from fastapi.testclient import TestClient

from conftest import ROOT, load_tool, login
from freethenoize import plugins
from freethenoize.web import Auth, create_app

new_plugin = load_tool("new_plugin")
check_architecture = load_tool("check_architecture")


def test_scaffold_registers_in_builtin(tmp_path):
    registry = tmp_path / "__init__.py"
    registry.write_text((ROOT / "freethenoize" / "plugins" / "__init__.py").read_text())
    new_plugin.create("demo_tool", "Demo", plugins_dir=tmp_path)
    builtin = re.findall(r'"(\w+)",', re.search(r"BUILTIN = \((.*?)\n\)", registry.read_text(), re.S).group(1))
    assert builtin == [*plugins.BUILTIN, "demo_tool"]
    new_plugin.add_to_builtin(registry, "demo_tool")  # idempotent
    assert registry.read_text().count('"demo_tool"') == 1


def test_scaffolded_plugin_works(tmp_path, kernel_factory, monkeypatch):
    pkg = tmp_path / "pkg"
    new_plugin.create("demo_tool", "Demo", plugins_dir=pkg, register=False)
    monkeypatch.setattr(plugins, "__path__", [*plugins.__path__, str(pkg)])
    monkeypatch.delitem(sys.modules, "freethenoize.plugins.demo_tool", raising=False)

    kernel, _ = kernel_factory(plugin_ids=["demo_tool"])
    assert kernel.plugins["demo_tool"].status == "active", kernel.plugins["demo_tool"].reason
    c = TestClient(create_app(kernel, Auth(password="secret", desktop=False)))
    login(c)
    assert c.post("/api/demo_tool/hello", json={"name": "Ana"}).json() == {"message": "hola, Ana"}
    assert c.get("/api/state").json()["plugins"]["demo_tool"] == {"count": 1}
    assert c.get("/api/state").json()["settings"]["demo_tool.greeting"] == "hola"
    assert c.get("/plugins/demo_tool/demo_tool.js").status_code == 200
    assert "/plugins/demo_tool/demo_tool.js" in c.get("/").text

    # The generated code passes the architecture check, like the built-ins.
    for f in [*(pkg / "demo_tool").glob("*.py"), *(pkg / "demo_tool").glob("ui/*.js")]:
        rel = "freethenoize/plugins/demo_tool/" + f.relative_to(pkg / "demo_tool").as_posix()
        assert check_architecture.check_source(rel, f.read_text()) == [], rel
