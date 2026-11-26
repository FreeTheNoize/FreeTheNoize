"""tools/check_architecture.py catches what breaks the framework, and only that."""
import json
import subprocess
import sys

import pytest

from conftest import ROOT, load_tool

arch = load_tool("check_architecture")
IDS = {"downloads", "library", "convert"}
VIEWS = {"library": [("freethenoize/plugins/library/ui/library.js", 1)]}


def rules(rel, text):
    return [v.rule for v in arch.check_source(rel, text, ids=IDS, views=VIEWS)]


PLUGIN = "freethenoize/plugins/convert/service.py"
API = "freethenoize/plugins/convert/api.py"
JS = "freethenoize/plugins/convert/ui/convert.js"


@pytest.mark.parametrize("rel, code, rule", [
    # Python: plugins
    (PLUGIN, "from ..downloads.service import DownloadManager", "plugin-imports-plugin"),
    (PLUGIN, "import freethenoize.plugins.library", "plugin-imports-plugin"),
    (PLUGIN, "self.ctx.emit('convert.progress', {})", "event-prefix"),
    (PLUGIN, "emit('downloads.job', {})", "event-prefix"),
    (PLUGIN, "x = self.ctx.settings['downloads.concurrency']", "settings-namespace"),
    (PLUGIN, "x = settings.get('downloads.concurrency')", "settings-namespace"),
    (PLUGIN, "from ... import paths", "plugin-files"),
    (PLUGIN, "f = paths.DATA_DIR / 'x.json'", "plugin-files"),
    (PLUGIN, "f = Path.home() / '.ftn'", "plugin-files"),
    (PLUGIN, "open('/tmp/x.json', 'w')", "plugin-files"),
    (PLUGIN, "p = Path('~/Music/out.wav')", "plugin-files"),
    (API, "class Body(BaseModel):\n    path: str", "library-path"),
    (API, "class Body(BaseModel):\n    files: list[str]", "library-path"),
    (API, "@r.get('/cover')\ndef cover(path: str):\n    pass", "library-path"),
    (API, "@r.post('')\ndef go(out_dir: Path | None = None):\n    pass", "library-path"),
    # Python: kernel
    ("freethenoize/kernel.py", "from .plugins.downloads import service", "kernel-names-plugin"),
    ("freethenoize/web.py", "svc = kernel.service('library')", "kernel-names-plugin"),
    ("freethenoize/web.py", "if kind == 'downloads.job': pass", "kernel-names-plugin"),
    # JS
    (JS, "const r = await fetch('/api/convert');", "ui-fetch"),
    (JS, "document.getElementById('x').hidden = true;", "ui-global-dom"),
    (JS, "document.querySelector('#x');", "ui-global-dom"),
    (JS, "el.innerHTML = `<b>${name}</b>`;", "ui-html-data"),
    (JS, "el.innerHTML += `<li>\n  ${item.title}\n</li>`;", "ui-html-data"),
    (JS, "el.insertAdjacentHTML('beforeend', `<i>${t}</i>`);", "ui-html-data"),
    (JS, "const s = '<script src=\"https://cdn.example/x.js\"></script>';", "ui-external-code"),
    (JS, "import { x } from 'https://esm.sh/lit';", "ui-external-code"),
    (JS, "const m = await import('//cdn.example/m.js');", "ui-external-code"),
    (JS, "FTN.registerView({ id: 'library', title: 'x' });", "ui-view-id"),
    (JS, "FTN.registerView({ id: 'settings', title: 'x' });", "ui-view-id"),
    (JS, "FTN.registerView({ id: 'downloads', title: 'x' });", "ui-view-id"),
])
def test_catches(rel, code, rule):
    assert rule in rules(rel, code)


@pytest.mark.parametrize("rel, code", [
    (PLUGIN, "from ...plugin import Plugin\nfrom ...audio import tagging\nfrom .api import routes"),
    (PLUGIN, "self.ctx.emit('progress', {})\nself.ctx.on('downloads.job', fn)"),
    (PLUGIN, "x = self.settings['concurrency']\nf = self.ctx.data_file('h.json')\nopen(f, 'a')"),
    (API, "class Body(BaseModel):\n    path: LibraryPath\n    out_dir: LibraryPath | None = None\n    name: str"),
    (API, "@r.get('/cover')\ndef cover(path: LibraryPath):\n    pass"),
    ("freethenoize/plugins/__init__.py", "BUILTIN = ('downloads', 'library')"),
    ("freethenoize/kernel.py", "kind = 'settings'\nfrom . import plugins"),
    ("freethenoize/app.py", "# ftn-arch: allow kernel-names-plugin — the get command\nkernel.service('downloads')"),
    (JS, "const r = await FTN.GET('/api/convert');\nconst b = await FTN.getBytes(url);"),
    (JS, "el.innerHTML = `<div class=\"x\"><b>fijo</b></div>`;\n$('#x', el).append(h('b', {}, name));"),
    (JS, "// fetch( in a comment\n/* document.querySelector('#a') */"),
    (JS, "const link = 'https://soundcloud.com/' + user;"),
    (JS, "FTN.registerView({ id: 'convert', title: 'x' });"),
])
def test_allows(rel, code):
    assert rules(rel, code) == []


def test_output_says_where_and_what_to_do():
    v = arch.check_source(JS, "x;\nfetch('/a');", ids=IDS, views=VIEWS)[0]
    text = str(v)
    assert text.startswith(f"{JS}:2: ") and "FTN.GET" in text and "ARCHITECTURE.md#" in text


def test_every_rule_points_to_a_section_of_the_doc():
    doc = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    anchors = {"-".join(line.lstrip("#").strip().lower().split()) for line in doc.splitlines() if line.startswith("#")}
    for rule, (_, _, anchor) in arch.RULES.items():
        assert anchor in anchors, f"{rule}: ARCHITECTURE.md has no heading for #{anchor}"


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "check_architecture.py"), *args],
                          input=stdin, capture_output=True, text=True, cwd=ROOT)


def test_cli_on_the_repo_is_clean():
    r = run()
    assert r.returncode == 0, r.stdout


def test_cli_fails_on_a_bad_file(tmp_path, monkeypatch):
    bad = ROOT / "freethenoize" / "plugins" / "convert" / "_arch_bad_test.py"
    bad.write_text("from ..downloads import service\n", encoding="utf-8")
    try:
        r = run(str(bad))
        assert r.returncode == 1 and "plugin-imports-plugin" in r.stdout
        hook = run("--hook", stdin=json.dumps({"tool_input": {"file_path": str(bad)}}))
        assert hook.returncode == 2 and "plugin-imports-plugin" in hook.stderr
    finally:
        bad.unlink()


def test_hook_ignores_files_outside_and_bad_input(tmp_path):
    outside = tmp_path / "x.py"
    outside.write_text("from freethenoize.plugins.downloads import service\n")
    assert run("--hook", stdin=json.dumps({"tool_input": {"file_path": str(outside)}})).returncode == 0
    assert run("--hook", stdin="not json").returncode == 0
