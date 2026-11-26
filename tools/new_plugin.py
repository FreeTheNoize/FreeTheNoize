"""Create a new FreeTheNoize plugin with everything wired up.

    python tools/new_plugin.py <id> [--title "Título"]

Writes freethenoize/plugins/<id>/ (PLUGIN, service, API and a view) and adds
<id> to plugins.BUILTIN. Run the app and the new view is already in the menu;
`pytest tests/test_plugins.py` checks it follows the contract.
See ARCHITECTURE.md and CONTRIBUTING.md › Crear un complemento.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def files(pid: str, title: str) -> dict[str, str]:
    cls = "".join(part.capitalize() for part in pid.split("_")) + "Service"
    return {
        "__init__.py": f'''"""{title}: describe here in one line what this plugin does."""
from ...plugin import Plugin
from .api import routes
from .service import {cls}

PLUGIN = Plugin(
    id="{pid}",
    title="{title}",
    description="Qué hace, en una frase (se ve en Ajustes › complementos).",
    service={cls},
    api=routes,
    settings={{"greeting": "hola"}},   # ctx.settings["greeting"]; "{pid}.greeting" for the page
)
''',
        "service.py": f'''class {cls}:
    """The plugin's logic. It only talks to the kernel through `ctx`."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.count = 0

    def state(self) -> dict:
        """Goes to /api/state as plugins.{pid} (FTN.state.plugins.{pid} in the page)."""
        return {{"count": self.count}}

    def hello(self, name: str) -> dict:
        self.count += 1
        self.ctx.emit("greeted", {{"count": self.count}})   # the page hears "{pid}.greeted"
        return {{"message": f"{{self.ctx.settings['greeting']}}, {{name or 'mundo'}}"}}
''',
        "api.py": f'''from fastapi import APIRouter
from pydantic import BaseModel


class Hello(BaseModel):
    name: str = ""


def routes(svc, ctx) -> APIRouter:
    """Mounted at /api/{pid}. Paths from the page: use LibraryPath (freethenoize.plugin)."""
    r = APIRouter()

    @r.post("/hello")
    def hello(body: Hello):
        return svc.hello(body.name)

    return r
''',
        f"ui/{pid}.js": f'''/* Plugin {pid}: {title}. Plain JS, no build step: everything comes from window.FTN. */
(function () {{
  const {{ $, h, POST, toast }} = FTN;

  FTN.registerView({{
    id: '{pid}',
    group: 'laboratorio',          // fuente | archivo | laboratorio
    order: 90,
    title: '{title}',
    heading: '{title}',
    intro: 'Qué puede hacer aquí la gente, en una frase.',
    // Static template only: anything with user or server data goes through h().
    html: `
      <form class="drop" id="{pid}-form">
        <input id="{pid}-name" placeholder="tu nombre" autocomplete="off">
        <button class="btn primary" type="submit">Saludar</button>
      </form>
      <div class="list" id="{pid}-out"></div>`,
    init(el) {{
      $('#{pid}-form', el).addEventListener('submit', async (e) => {{
        e.preventDefault();
        const r = await POST('/api/{pid}/hello', {{ name: $('#{pid}-name', el).value }});
        $('#{pid}-out', el).prepend(h('div', {{ class: 'row-item' }}, r.message));
      }});
      FTN.on('{pid}.greeted', (d) => toast(`Saludos: ${{d.count}}`));
    }},
  }});
}})();
''',
    }


def add_to_builtin(registry: Path, pid: str) -> None:
    text = registry.read_text(encoding="utf-8")
    match = re.search(r"BUILTIN = \((.*?)\n\)", text, re.S)
    if not match:
        raise SystemExit(f"No encuentro BUILTIN en {registry}")
    if f'"{pid}"' in match.group(1):
        return
    text = text[:match.end(1)] + f'\n    "{pid}",' + text[match.end(1):]
    registry.write_text(text, encoding="utf-8")


def create(pid: str, title: str, plugins_dir: Path = ROOT / "freethenoize" / "plugins",
           register: bool = True) -> Path:
    if not PLUGIN_ID.match(pid):
        raise SystemExit("El id va en minúsculas, cifras y _, empieza por letra (2-31 caracteres).")
    target = plugins_dir / pid
    if target.exists():
        raise SystemExit(f"Ya existe {target}")
    for rel, content in files(pid, title).items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if register:
        add_to_builtin(plugins_dir / "__init__.py", pid)
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Crea un complemento nuevo de FreeTheNoize.")
    ap.add_argument("id", help="identificador: minúsculas, cifras y _ (p. ej. waveform)")
    ap.add_argument("--title", help="nombre que se ve en el menú (por defecto, el id)")
    args = ap.parse_args(argv)
    target = create(args.id, args.title or args.id.replace("_", " ").capitalize())
    print(f"Creado {target.relative_to(ROOT)} y añadido a plugins.BUILTIN.\n"
          f"Arranca la app (freethenoize serve) y verás la vista nueva; luego pytest tests/test_plugins.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
