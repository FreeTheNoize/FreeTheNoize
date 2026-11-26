"""Check that the code follows the FreeTheNoize framework (ARCHITECTURE.md).

    python tools/check_architecture.py            # the whole repo
    python tools/check_architecture.py FILE…      # only these files
    python tools/check_architecture.py --hook     # Claude Code hook: file from stdin JSON

Prints `file:line: rule → what to do (ARCHITECTURE.md#anchor)` and exits 1 if
anything breaks the rules (2 in --hook mode, so the agent sees it). No
dependencies: AST for Python, regular expressions for the plugins' JS.

A line that has a good reason to break a rule says so, on that line or the
one above:   # ftn-arch: allow <rule> — why
"""
from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "freethenoize"
DOC = "ARCHITECTURE.md"

RULES = {
    "plugin-imports-plugin": (
        "un complemento importa otro",
        "ponlo en requires=(…) y usa ctx.require('<id>'); en la página, FTN.provide/FTN.use",
        "un-complemento-no-importa-otro"),
    "kernel-names-plugin": (
        "el kernel nombra o importa un complemento",
        "el kernel no conoce complementos: mueve esto al complemento o expón algo genérico en Ctx",
        "el-kernel-no-conoce-los-complementos"),
    "event-prefix": (
        "evento con prefijo puesto a mano",
        "ctx.emit('evento') ya añade '<id>.'; para escuchar otro complemento usa ctx.on('<otro>.evento')",
        "eventos-y-ajustes-con-tu-prefijo"),
    "settings-namespace": (
        "ajuste de otro espacio de nombres",
        "ctx.settings solo ve los tuyos y sin prefijo: ctx.settings['clave']",
        "eventos-y-ajustes-con-tu-prefijo"),
    "plugin-files": (
        "fichero fuera de las carpetas del complemento",
        "usa ctx.data_dir, ctx.cache_dir o ctx.data_file(); la música, con ctx.music_dir()",
        "tus-ficheros-en-tu-carpeta"),
    "library-path": (
        "ruta de archivo sin LibraryPath",
        "declárala como LibraryPath (from ...plugin import LibraryPath) para que llegue validada",
        "rutas-de-archivo-con-librarypath"),
    "ui-fetch": (
        "fetch() directo",
        "usa FTN.GET/POST/PATCH/DEL (o FTN.getBytes para binarios): sesión, errores y login ya resueltos",
        "http-y-dom-por-ftn"),
    "ui-global-dom": (
        "búsqueda en todo el documento",
        "usa FTN.$(selector, el) con el elemento de tu vista (init(el))",
        "http-y-dom-por-ftn"),
    "ui-html-data": (
        "HTML construido con datos",
        "innerHTML solo con plantillas fijas; lo que lleve datos, con FTN.h() (escapa el texto)",
        "nada-de-html-con-datos"),
    "ui-external-code": (
        "código cargado de fuera",
        "nada de CDN ni URLs externas: copia lo que necesites al repo o usa FTN",
        "sin-scripts-externos"),
    "ui-view-id": (
        "id de vista repetido o de otro",
        "cada vista tiene un id único; no uses el id de otro complemento ni 'settings'",
        "vistas-con-id-propio"),
}

PATH_NAME = re.compile(r"(^|_)(path|paths|file|files|dir|folder|dest|src)$")
ALLOW = re.compile(r"ftn-arch:\s*allow\s+([\w-]+)")
RESERVED_VIEWS = {"settings"}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str

    def __str__(self) -> str:
        what, fix, anchor = RULES[self.rule]
        return f"{self.path}:{self.line}: {what} [{self.rule}] → {fix} ({DOC}#{anchor})"


def plugin_ids(root: Path = ROOT) -> set[str]:
    base = root / PKG / "plugins"
    return {d.name for d in base.iterdir() if (d / "__init__.py").is_file()} if base.is_dir() else set()


def _where(rel: str) -> tuple[str, str | None]:
    """('plugin', id) | ('kernel', None) | ('other', None) for a repo-relative path."""
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[0] == PKG and parts[1] == "plugins":
        return "plugin", parts[2] if len(parts) > 3 else None
    if len(parts) >= 2 and parts[0] == PKG:
        return "kernel", None
    return "other", None


def _allowed(lines: list[str], line: int, rule: str) -> bool:
    for n in (line, line - 1):
        if 1 <= n <= len(lines):
            m = ALLOW.search(lines[n - 1])
            if m and m.group(1) == rule:
                return True
    return False


# ── Python ────────────────────────────────────────────────────────────────────

def imports(tree: ast.AST, rel: str) -> list[tuple[str, int]]:
    """(absolute dotted name, line) for every import, relative ones resolved."""
    parts = Path(rel).with_suffix("").parts
    package = ".".join(parts[:-1])  # a module's package; for __init__.py, the package itself
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = package.split(".")
                up = up[: len(up) - node.level + 1]
                base = ".".join(up + ([base] if base else []))
            out.append((base, node.lineno))
            out += [(f"{base}.{a.name}", node.lineno) for a in node.names]
    return out


def _callee(node: ast.Call) -> str:
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _is_settings(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "settings") or \
           (isinstance(node, ast.Attribute) and node.attr == "settings")


def _str(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _annotation_ok(ann: ast.AST | None) -> bool:
    return ann is None or "LibraryPath" in ast.unparse(ann)


def check_python(rel: str, text: str, ids: set[str]) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    kind, pid = _where(rel)
    found: list[tuple[int, str]] = []

    for name, line in imports(tree, rel):
        if name.startswith(f"{PKG}.plugins."):
            other = name.split(".")[2]
            if kind == "plugin" and other != pid and other in ids:
                found.append((line, "plugin-imports-plugin"))
            elif kind == "kernel" and other in ids:
                found.append((line, "kernel-names-plugin"))
        if kind == "plugin" and name in (f"{PKG}.paths", f"{PKG}.paths.DATA_DIR", f"{PKG}.paths.CACHE_DIR",
                                         f"{PKG}.paths.CONFIG_DIR"):
            found.append((line, "plugin-files"))

    is_registry = rel == f"{PKG}/plugins/__init__.py"
    for node in ast.walk(tree):
        # The kernel never says a plugin's name ("downloads", "downloads.job").
        if kind == "kernel" and not is_registry and (s := _str(node)) is not None:
            if s in ids or (s.split(".")[0] in ids and re.fullmatch(r"[a-z_]+\.[\w.]+", s)):
                found.append((node.lineno, "kernel-names-plugin"))
        if kind != "plugin":
            continue
        if isinstance(node, ast.Call):
            name = _callee(node)
            first = _str(node.args[0]) if node.args else None
            if name == "emit" and first and "." in first:
                found.append((node.lineno, "event-prefix"))
            if name == "get" and isinstance(node.func, ast.Attribute) and _is_settings(node.func.value) \
                    and first and "." in first:
                found.append((node.lineno, "settings-namespace"))
            # Hard-coded places on disk: Path.home(), "~/…" or "/abs/…".
            if name == "home" and isinstance(node.func, ast.Attribute) and ast.unparse(node.func.value) == "Path":
                found.append((node.lineno, "plugin-files"))
            if name in ("Path", "open") and first and (first.startswith(("~", "/")) or re.match(r"[A-Za-z]:\\", first)):
                found.append((node.lineno, "plugin-files"))
        elif isinstance(node, ast.Subscript) and _is_settings(node.value):
            key = _str(node.slice)
            if key and "." in key:
                found.append((node.lineno, "settings-namespace"))
        elif isinstance(node, ast.Attribute) and node.attr in ("DATA_DIR", "CACHE_DIR", "CONFIG_DIR") \
                and ast.unparse(node.value) == "paths":
            found.append((node.lineno, "plugin-files"))

    if kind == "plugin" and Path(rel).name == "api.py":
        found += _check_api(tree)
    return found


def _check_api(tree: ast.AST) -> list[tuple[int, str]]:
    """File paths that reach a route must be LibraryPath (body models and parameters)."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(ast.unparse(b).endswith("BaseModel") for b in node.bases):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) \
                        and PATH_NAME.search(item.target.id) and not _annotation_ok(item.annotation):
                    found.append((item.lineno, "library-path"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr in ("get", "post", "put", "patch", "delete") for d in node.decorator_list):
            for arg in node.args.args + node.args.kwonlyargs:
                if PATH_NAME.search(arg.arg) and not _annotation_ok(arg.annotation):
                    found.append((arg.lineno, "library-path"))
    return found


# ── JavaScript (plugin UIs) ──────────────────────────────────────────────────

JS_RULES = [
    (re.compile(r"(?<![\w.$])fetch\s*\("), "ui-fetch"),
    (re.compile(r"\bdocument\s*\.\s*(getElementById|getElementsBy\w+|querySelector(All)?)\s*\("), "ui-global-dom"),
    (re.compile(r"<script[^>]*\bsrc\s*=\s*['\"]?(https?:)?//", re.I), "ui-external-code"),
    (re.compile(r"\bimport\s*(\(\s*|[^;'\"]*\bfrom\s*)['\"`](https?:)?//"), "ui-external-code"),
    (re.compile(r"<link[^>]*\bhref\s*=\s*['\"]?(https?:)?//", re.I), "ui-external-code"),
]
HTML_SINK = re.compile(r"(\.(innerHTML|outerHTML)\s*\+?=\s*|\.insertAdjacentHTML\s*\([^,]*,\s*)`")
VIEW_ID = re.compile(r"registerView\s*\(\s*\{\s*id\s*:\s*['\"]([\w-]+)['\"]")


def _blank_comments(text: str) -> str:
    """Comments → spaces (keeps offsets and line numbers). Good enough for our JS:
    `//` inside strings or URLs is left alone when preceded by ':' or a quote."""
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)
    return re.sub(r"(?<![:'\"\\])//[^\n]*", lambda m: " " * len(m.group()), text)


def _template_end(text: str, start: int) -> int:
    """Index of the backtick closing the template literal opened at text[start-1]."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "`" and depth == 0:
            return i
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if c == "}" and depth:
            depth -= 1
        i += 1
    return len(text)


def check_js(rel: str, text: str, views: dict[str, list[tuple[str, int]]], ids: set[str]) -> list[tuple[int, str]]:
    kind, pid = _where(rel)
    if kind != "plugin":
        return []
    code = _blank_comments(text)
    line_of = lambda pos: code.count("\n", 0, pos) + 1  # noqa: E731
    found = []
    for rx, rule in JS_RULES:
        found += [(line_of(m.start()), rule) for m in rx.finditer(code)]
    for m in HTML_SINK.finditer(code):
        body = code[m.end(): _template_end(code, m.end())]
        if "${" in body:
            found.append((line_of(m.start()), "ui-html-data"))
    for m in VIEW_ID.finditer(code):
        vid = m.group(1)
        clash = (vid in RESERVED_VIEWS or (vid in ids and vid != pid)
                 or any(other != rel for other, _ in views.get(vid, [])))
        if clash:
            found.append((line_of(m.start()), "ui-view-id"))
    return found


def view_ids(root: Path) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    for js in sorted((root / PKG / "plugins").glob("*/ui/*.js")):
        code = _blank_comments(js.read_text(encoding="utf-8"))
        rel = js.relative_to(root).as_posix()
        for m in VIEW_ID.finditer(code):
            out.setdefault(m.group(1), []).append((rel, code.count("\n", 0, m.start()) + 1))
    return out


# ── Driver ────────────────────────────────────────────────────────────────────

def check_source(rel: str, text: str, root: Path = ROOT, ids: set[str] | None = None,
                 views: dict | None = None) -> list[Violation]:
    """Check one file's text as if it lived at `rel` (repo-relative, '/' separators)."""
    ids = plugin_ids(root) if ids is None else ids
    if rel.endswith(".py"):
        found = check_python(rel, text, ids)
    elif rel.endswith(".js"):
        found = check_js(rel, text, view_ids(root) if views is None else views, ids)
    else:
        return []
    lines = text.splitlines()
    return sorted({Violation(rel, n, r) for n, r in found if not _allowed(lines, n, r)},
                  key=lambda v: (v.path, v.line, v.rule))


def targets(root: Path = ROOT) -> list[Path]:
    pkg = root / PKG
    return sorted([*pkg.rglob("*.py"), *pkg.glob("plugins/*/ui/*.js")])


def check(files: list[Path] | None = None, root: Path = ROOT) -> list[Violation]:
    ids, views = plugin_ids(root), view_ids(root)
    out = []
    for f in files if files is not None else targets(root):
        f = Path(f).resolve()
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            continue  # not in this repo
        if f.is_file():
            out += check_source(rel, f.read_text(encoding="utf-8"), root, ids, views)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    hook = "--hook" in argv
    if hook:
        try:
            data = json.load(sys.stdin)
            files = [Path(data["tool_input"]["file_path"])]
        except (ValueError, KeyError, TypeError):
            return 0
    else:
        files = [Path(a) for a in argv] or None
    problems = check(files)
    for p in problems:
        print(p, file=sys.stderr if hook else sys.stdout)
    if problems:
        if hook:
            print(f"Arréglalo para respetar el framework (ver {DOC}).", file=sys.stderr)
            return 2
        print(f"\n{len(problems)} problema(s) de arquitectura. Detalles en {DOC}.")
        return 1
    if not hook:
        print("Arquitectura OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
