"""Plugins that ship with FreeTheNoize, in the order the page shows them.

This list is the only place that names plugins. Add yours here (see
CONTRIBUTING.md › Crear un complemento, or run `python tools/new_plugin.py <id>`).
"""
import importlib
import sys
from pathlib import Path

from ..plugin import Plugin

BUILTIN = (
    "downloads",
    "preview",
    "search",
    "subscriptions",
    "library",
    "analysis",
    "convert",
)


def load(plugin_id: str) -> Plugin:
    module = importlib.import_module(f"{__name__}.{plugin_id}")
    plugin = getattr(module, "PLUGIN", None)
    if not isinstance(plugin, Plugin):
        raise TypeError(f"freethenoize.plugins.{plugin_id} does not define PLUGIN = Plugin(...)")
    if plugin.id != plugin_id:
        raise ValueError(f"freethenoize.plugins.{plugin_id}: PLUGIN.id is {plugin.id!r}")
    return plugin


def folder(plugin_id: str) -> Path:
    """The plugin's package folder (its ui/ lives here)."""
    return Path(sys.modules[f"{__name__}.{plugin_id}"].__file__).parent
