import sys
import tkinter as tk
from tkinter import ttk

# ── Color palette ─────────────────────────────────────────────────────────────
BG      = "#0e0e0e"
BG2     = "#171717"
PANEL   = "#1f1f1f"
BORDER  = "#2d2d2d"
FG      = "#f0f0f0"
FG2     = "#7a7a7a"
BTN_BG  = "#282828"
BTN_HOV = "#3a3a3a"
ENTRY   = "#161616"
SEL     = "#363636"

# Scale factor for HiDPI screens (Windows / macOS / Linux)
_SCALE = 1.0
if sys.platform == "win32":
    try:
        import ctypes
        _SCALE = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
    except Exception:
        pass
_SCALE = max(1.0, _SCALE)


def _font(size: int, weight: str = "normal") -> tuple:
    return ("Helvetica", max(8, round(size * _SCALE)), weight)


def configure_styles(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".",
        background=BG, foreground=FG,
        fieldbackground=ENTRY,
        troughcolor=BORDER, bordercolor=BORDER,
        darkcolor=BG2, lightcolor=PANEL,
        selectbackground=SEL, selectforeground=FG,
        font=_font(9),
    )
    s.configure("TFrame",  background=BG)
    s.configure("TLabel",  background=BG, foreground=FG2, font=_font(9))
    s.configure("TEntry",  fieldbackground=ENTRY, foreground=FG,
                insertcolor=FG, borderwidth=1, relief="flat")
    s.configure("TCheckbutton", background=BG, foreground=FG, font=_font(9))
    s.map("TCheckbutton",
          background=[("active", BG)], foreground=[("active", FG)],
          indicatorcolor=[("selected", FG2), ("!selected", BORDER)])
    s.configure("TRadiobutton", background=BG, foreground=FG, font=_font(9))
    s.map("TRadiobutton",
          background=[("active", BG)], foreground=[("active", FG)],
          indicatorcolor=[("selected", FG2), ("!selected", BORDER)])
    s.configure("TSeparator", background=BORDER)
    s.configure("TNotebook",
        background=BG2, borderwidth=0, tabmargins=[0, 2, 0, 0])
    s.configure("TNotebook.Tab",
        background=BTN_BG, foreground=FG2,
        padding=[12, 5], borderwidth=0, focuscolor=BG,
        font=_font(9))
    s.map("TNotebook.Tab",
          background=[("selected", PANEL), ("active", BTN_HOV)],
          foreground=[("selected", FG),    ("active", FG)])
    s.configure("TScrollbar",
        background=BTN_BG, troughcolor=BG2,
        borderwidth=0, arrowsize=12)
    s.configure("TLabelframe",
        background=BG, foreground=FG2,
        bordercolor=BORDER, relief="flat")
    s.configure("TLabelframe.Label",
        background=BG, foreground=FG2, font=_font(8))


def make_button(parent, text, cmd, large=False):
    return tk.Button(
        parent, text=text, command=cmd,
        bg=BTN_BG, fg=FG,
        activebackground=BTN_HOV, activeforeground=FG,
        relief="flat",
        font=_font(10 if large else 9, "bold" if large else "normal"),
        padx=18 if large else 10,
        pady=7  if large else 4,
        cursor="hand2",
        bd=0,
    )


def sep(parent, row, cols=2, pady=6):
    ttk.Separator(parent, orient="horizontal").grid(
        row=row, column=0, columnspan=cols,
        sticky="ew", pady=pady)
