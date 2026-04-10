import sys
import os
import atexit
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

import pygame
from PIL import Image, ImageTk

from ..paths import ICON_PATH, FAVICON_PATH, DEFAULT_OUTPUT
from ..config import load_config, save_config
from ..music import start_music
from ..downloader import SCDL_EXE, FFMPEG_EXE, FFMPEG_ERR
from ..styles import BG, BG2, FG, FG2, BTN_BG, BTN_HOV, configure_styles, make_button
from .tabs import create_format_tab, create_metadata_tab, create_filters_tab, create_advanced_tab, create_converter_tab

# ── DPI Awareness (Windows) ───────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🏴‍☠️GKICKS SoundCloud Downloader🏴‍☠️")
        self.configure(bg=BG)
        self.resizable(False, False)
        configure_styles(self)

        self.state = {}
        self._proc: subprocess.Popen | None = None
        cfg = load_config()
        self._muted = bool(cfg.get("muted", False))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        atexit.register(self._kill_proc)
        self._set_icon()
        self._build_header()
        self._build_main()
        self._build_tabs()
        self._build_log()

        self._restore_state(cfg)
        self._center()

        from pathlib import Path
        self._log(f"scdl: {SCDL_EXE}")
        if FFMPEG_EXE:
            self._log(f"ffmpeg: {Path(FFMPEG_EXE).name}")
        else:
            self._log(f"Advertència: ffmpeg no detectat — la conversió d'àudio pot fallar."
                      f"{f' ({FFMPEG_ERR})' if FFMPEG_ERR else ''}")

        start_music()
        self.after(200, self._apply_initial_mute)

    # ── Icona ──────────────────────────────────────────────────────────────────

    def _set_icon(self):
        # iconphoto amb PNG (funciona a totes les plataformes sense conflictes)
        # L'icona del taskbar/explorer ve de l'exe embedded (icon= al spec)
        if ICON_PATH.exists():
            try:
                img = Image.open(ICON_PATH).resize((128, 128), Image.LANCZOS)
                self._icon_photo = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._icon_photo)
            except Exception:
                pass
        # .ico per Windows title bar (opcional, si funciona)
        if FAVICON_PATH.exists():
            try:
                self.iconbitmap(str(FAVICON_PATH))
            except Exception:
                pass

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Capçalera + botó Mute ──────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG2)
        hdr.pack(fill="x")

        if ICON_PATH.exists():
            img = Image.open(ICON_PATH)
            img.thumbnail((300, 120), Image.LANCZOS)
            self._logo = ImageTk.PhotoImage(img)
            tk.Label(hdr, image=self._logo, bg=BG2).pack(pady=(14, 6))
        else:
            tk.Label(hdr, text="GKICKS", font=("Helvetica", 26, "bold"),
                     fg=FG, bg=BG2).pack(pady=(12, 4))

        tk.Label(hdr, text="CODED BY @quim_d",
                 font=("Helvetica", 10), fg=FG2, bg=BG2).pack(pady=(0, 4))

        self._mute_btn = tk.Button(
            hdr,
            text="🔇" if self._muted else "🔊",
            command=self._toggle_mute,
            bg=BTN_BG, fg=FG,
            activebackground=BTN_HOV, activeforeground=FG,
            relief="flat",
            font=("Courier", 9, "bold"),
            padx=10, pady=4,
            cursor="hand2",
            bd=0,
        )
        self._mute_btn.pack(pady=(0, 8))

    def _apply_initial_mute(self):
        try:
            if self._muted:
                pygame.mixer.music.set_volume(0.0)
        except Exception:
            pass

    def _toggle_mute(self):
        self._muted = not self._muted
        try:
            pygame.mixer.music.set_volume(0.0 if self._muted else 1.0)
            self._mute_btn.configure(text="🔇" if self._muted else "🔊")
        except Exception:
            pass
        cfg = load_config()
        cfg["muted"] = self._muted
        save_config(cfg)

    # ── Interfície principal ───────────────────────────────────────────────────

    def _build_main(self):
        m = ttk.Frame(self, padding=(16, 12))
        m.pack(fill="x")
        m.columnconfigure(1, weight=1)

        ttk.Label(m, text="URL").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.state["url"] = tk.StringVar()
        ttk.Entry(m, textvariable=self.state["url"]).grid(
            row=0, column=1, sticky="ew", ipady=5)
        make_button(m, "Enganxar", self._paste).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(m, text="Destí").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.state["dest"] = tk.StringVar(value=DEFAULT_OUTPUT)
        ttk.Entry(m, textvariable=self.state["dest"]).grid(
            row=1, column=1, sticky="ew", ipady=5, pady=(8, 0))
        make_button(m, "Triar…", self._browse).grid(row=1, column=2, padx=(6, 0), pady=(8, 0))

        ttk.Label(m, text="Tipus").grid(row=2, column=0, sticky="nw", padx=(0, 10), pady=(10, 0))
        tipus = ttk.Frame(m)
        tipus.grid(row=2, column=1, columnspan=2, sticky="w", pady=(10, 0))
        self.state["dl_type"] = tk.StringVar(value="link")
        for val, label in [
            ("link",      "Enllaç (pista/llista)"),
            ("all",       "Tot + Reposts"),
            ("tracks",    "Pujades"),
            ("favorites", "Likes"),
            ("comments",  "Comentats"),
            ("playlists", "Llistes"),
            ("reposts",   "Reposts"),
        ]:
            ttk.Radiobutton(tipus, text=label,
                            variable=self.state["dl_type"], value=val).pack(
                side="left", padx=(0, 10))

        self.dl_btn = make_button(m, "   Descarregar   ", self._start_download, large=True)
        self.dl_btn.grid(row=3, column=0, columnspan=3, pady=(14, 0))

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="x", padx=16, pady=(10, 0))
        nb.add(create_format_tab(nb,    self.state),                          text="  Format  ")
        nb.add(create_metadata_tab(nb,  self.state),                          text="  Metadades  ")
        nb.add(create_filters_tab(nb,   self.state),                          text="  Filtres  ")
        nb.add(create_advanced_tab(nb,  self.state),                          text="  Avançat  ")
        nb.add(create_converter_tab(nb, self.state, self._start_conversion, self._start_embed_art),  text="  Convertidor  ")

    def _build_log(self):
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self.log_widget = scrolledtext.ScrolledText(
            log_frame,
            height=6,
            bg="#080808",
            fg="#c8c8c8",
            font=("Courier", 9),
            relief="flat",
            state="disabled",
            wrap="word",
            insertbackground=FG,
        )
        self.log_widget.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status_var,
                 bg=BG2, fg=FG2, font=("Helvetica", 9),
                 anchor="w", padx=12).pack(fill="x", pady=(4, 0))

        tk.Label(
            self,
            text="Si no et funciona te jodes a mi em va   - Quim",
            bg=BG, fg="#3a3a3a",
            font=("Courier", 8, "italic"),
            anchor="center",
        ).pack(fill="x", pady=(2, 6))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _paste(self):
        try:
            self.state["url"].set(self.clipboard_get())
        except tk.TclError:
            pass

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.state["dest"].get())
        if d:
            self.state["dest"].set(d)

    def _log(self, text):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    # ── Construcció de la comanda ──────────────────────────────────────────────

    def _build_cmd(self):
        s = self.state
        url  = s["url"].get().strip()
        dest = s["dest"].get().strip()
        cmd  = SCDL_EXE + ["--path", dest]

        t = s["dl_type"].get()
        if   t == "link":      cmd += ["-l", url]
        elif t == "all":       cmd += ["-l", url, "-a"]
        elif t == "tracks":    cmd += ["-l", url, "-t"]
        elif t == "favorites": cmd += ["-l", url, "-f"]
        elif t == "comments":  cmd += ["-l", url, "-C"]
        elif t == "playlists": cmd += ["-l", url, "-p"]
        elif t == "reposts":   cmd += ["-l", url, "-r"]

        fmt   = s["fmt"].get()
        # shlex.split (usat per scdl internament) tracta backslashes com a escape
        # i trenca paths amb espais → forward slashes + cometes dobles al voltant
        _ffmpeg = FFMPEG_EXE.replace("\\", "/") if FFMPEG_EXE else None
        ytdlp = ["--ffmpeg-location", f'"{_ffmpeg}"'] if _ffmpeg else []

        if fmt == "onlymp3":
            cmd.append("--onlymp3")
            q = s["mp3_quality"].get()
            if q != "0":
                ytdlp += ["--audio-quality", q]
        elif fmt == "flac":          cmd.append("--flac")
        elif fmt == "opus":          cmd.append("--opus")
        elif fmt == "no_original":   cmd.append("--no-original")
        elif fmt == "only_original": cmd.append("--only-original")
        elif fmt == "wav":
            ytdlp += ["-x", "--audio-format", "wav", "--audio-quality", "0"]
        elif fmt == "alac":
            ytdlp += ["-x", "--audio-format", "alac"]

        if s["original_art"].get():    cmd.append("--original-art")
        if s["embed_thumbnail"].get(): ytdlp.append("--embed-thumbnail")
        if s["write_thumbnail"].get(): ytdlp += ["--write-thumbnail",
                                                  "--convert-thumbnails", "png"]
        if s["embed_metadata"].get():  ytdlp.append("--embed-metadata")
        if s["extract_artist"].get():  cmd.append("--extract-artist")
        if s["original_meta"].get():   cmd.append("--original-metadata")
        if s["original_name"].get():   cmd.append("--original-name")
        if s["force_meta"].get():      cmd.append("--force-metadata")
        if s["no_album_tag"].get():    cmd.append("--no-album-tag")
        if s["add_description"].get(): cmd.append("--add-description")
        if s["addtofile"].get():       cmd.append("--addtofile")
        if s["addtimestamp"].get():    cmd.append("--addtimestamp")
        if s["name_fmt"].get():        cmd += ["--name-format",          s["name_fmt"].get()]
        if s["pl_name_fmt"].get():     cmd += ["--playlist-name-format", s["pl_name_fmt"].get()]
        if s["min_size"].get():        cmd += ["--min-size", s["min_size"].get()]
        if s["max_size"].get():        cmd += ["--max-size", s["max_size"].get()]
        if s["offset"].get():          cmd += ["-o",         s["offset"].get()]
        if s["continue_dl"].get():     cmd.append("-c")
        if s["overwrite"].get():       cmd.append("--overwrite")
        if s["no_playlist"].get():     cmd.append("--no-playlist")
        if s["no_pl_folder"].get():    cmd.append("--no-playlist-folder")
        if s["strict_playlist"].get(): cmd.append("--strict-playlist")
        if s["dl_archive"].get():      cmd += ["--download-archive", s["dl_archive"].get()]
        if s["sync_file"].get():       cmd += ["--sync",             s["sync_file"].get()]
        if s["client_id"].get():       cmd += ["--client-id",  s["client_id"].get()]
        if s["auth_token"].get():      cmd += ["--auth-token", s["auth_token"].get()]
        if s["ytdlp_args"].get():      ytdlp.append(s["ytdlp_args"].get().strip())
        if ytdlp:                      cmd += ["--yt-dlp-args", " ".join(ytdlp)]
        if s["log_debug"].get():       cmd.append("--debug")
        elif s["log_error"].get():     cmd.append("--error")
        if s["hidewarnings"].get():    cmd.append("--hidewarnings")
        if s["hide_progress"].get():   cmd.append("--hide-progress")

        return cmd, url, dest

    # ── Descàrrega ────────────────────────────────────────────────────────────

    def _start_download(self):
        if not self.state["url"].get().strip():
            self.status_var.set("Introdueix una URL primer.")
            return
        if not self.state["dest"].get().strip():
            self.status_var.set("Tria una carpeta de destí.")
            return

        self.dl_btn.configure(state="disabled", text="   Descarregant…   ")
        self.status_var.set("Descarregant…")

        cmd, _, _ = self._build_cmd()
        self.after(0, self._log, "$ " + " ".join(cmd) + "\n")

        from ..downloader import run_download
        run_download(
            cmd,
            on_line=lambda line: self.after(0, self._log, line),
            on_done=lambda msg: self.after(0, self._finish, msg),
            on_proc=lambda p: setattr(self, "_proc", p),
        )

    def _finish(self, msg):
        self._log(f"\n{msg}")
        self.status_var.set(msg)
        self.dl_btn.configure(state="normal", text="   Descarregar   ")

    # ── Convertidor ───────────────────────────────────────────────────────────

    def _start_conversion(self, files: list):
        if not files:
            self.status_var.set("Afegeix almenys un fitxer.")
            return

        s = self.state
        out_dir = None if s["conv_same_dir"].get() else (s["conv_out_dir"].get().strip() or None)
        fmt     = s["conv_fmt"].get()
        quality = s["conv_mp3_quality"].get()

        btn = s.get("_conv_btn")
        if btn:
            btn.configure(state="disabled", text="   Convertint…   ")
        self.status_var.set("Convertint…")
        self._log(f"\nConvertint {len(files)} fitxer(s) → {fmt.upper()}")

        from ..converter import run_conversion
        run_conversion(
            files, out_dir, fmt, quality,
            on_line=lambda line: self.after(0, self._log, line),
            on_done=lambda msg: self.after(0, self._finish_conversion, msg),
        )

    def _finish_conversion(self, msg):
        self._log(f"\n{msg}")
        self.status_var.set(msg)
        btn = self.state.get("_conv_btn")
        if btn:
            btn.configure(state="normal", text="   Convertir   ")

    # ── Incrustar portada ─────────────────────────────────────────────────────

    def _start_embed_art(self, files: list, image_path: str | None):
        if not files:
            self.status_var.set("Afegeix almenys un fitxer.")
            return

        btn = self.state.get("_embed_btn")
        if btn:
            btn.configure(state="disabled", text="   Incrustant…   ")
        self.status_var.set("Incrustant portada…")
        self._log(f"\nIncrustant portada a {len(files)} fitxer(s)")

        from ..converter import embed_cover_art
        embed_cover_art(
            files,
            image_path or None,
            on_line=lambda line: self.after(0, self._log, line),
            on_done=lambda msg: self.after(0, self._finish_embed_art, msg),
        )

    def _finish_embed_art(self, msg):
        self._log(f"\n{msg}")
        self.status_var.set(msg)
        btn = self.state.get("_embed_btn")
        if btn:
            btn.configure(state="normal", text="   Incrustar portada   ")

    # ── Matar procés ──────────────────────────────────────────────────────────

    def _kill_proc(self):
        proc = self._proc
        if proc is None:
            return
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._proc = None

    # ── Persistir estat UI ────────────────────────────────────────────────────

    def _save_state(self):
        cfg = load_config()
        cfg["estat"] = {k: v.get() for k, v in self.state.items()
                        if hasattr(v, "get")}
        save_config(cfg)

    def _restore_state(self, cfg: dict):
        for key, value in cfg.get("estat", {}).items():
            var = self.state.get(key)
            if var is None:
                continue
            try:
                var.set(bool(value) if isinstance(var, tk.BooleanVar) else value)
            except Exception:
                pass

    def _on_close(self):
        self._save_state()
        self._kill_proc()
        self.destroy()
