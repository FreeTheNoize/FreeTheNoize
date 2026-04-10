import tkinter as tk
from tkinter import ttk, filedialog
from ..styles import BG, FG, FG2, BTN_BG, BTN_HOV, ENTRY, make_button, sep
from ..converter import FORMATS


# ── Format ────────────────────────────────────────────────────────────────────

def create_format_tab(nb, state):
    f = ttk.Frame(nb, padding=(14, 10))
    f.columnconfigure(0, weight=1)
    f.columnconfigure(1, weight=1)
    f.columnconfigure(2, weight=1)

    ttk.Label(f, text="AUDIO FORMAT", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

    state["fmt"] = tk.StringVar(value="default")
    options = [
        ("default",       "Original  (m4a / opus)"),
        ("onlymp3",       "MP3"),
        ("wav",           "WAV  —  lossless for DAWs"),
        ("flac",          "FLAC  (if source is lossless)"),
        ("alac",          "ALAC  —  Apple Lossless"),
        ("opus",          "Prefer Opus"),
        ("no_original",   "No original  →  mp3 / m4a / opus"),
        ("only_original", "Originals only  (WAV, FLAC, AIFF…)"),
    ]
    for i, (val, label) in enumerate(options):
        ttk.Radiobutton(f, text=label,
                        variable=state["fmt"], value=val).grid(
            row=1 + i // 3, column=i % 3, sticky="w", padx=(0, 16), pady=2)

    mp3_frame = ttk.Frame(f)
    mp3_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
    ttk.Label(mp3_frame, text="MP3 bitrate:", foreground=FG2).pack(side="left", padx=(0, 8))
    state["mp3_quality"] = tk.StringVar(value="0")
    for val, label in [
        ("0",    "VBR max"),
        ("320K", "320 kbps"),
        ("256K", "256 kbps"),
        ("192K", "192 kbps"),
        ("128K", "128 kbps"),
    ]:
        ttk.Radiobutton(mp3_frame, text=label,
                        variable=state["mp3_quality"], value=val).pack(side="left", padx=(0, 10))

    def _on_fmt_change(*_):
        if state["fmt"].get() == "onlymp3":
            mp3_frame.grid()
        else:
            mp3_frame.grid_remove()

    state["fmt"].trace_add("write", _on_fmt_change)
    mp3_frame.grid_remove()

    sep(f, row=5, cols=3)
    ttk.Label(f, text="ARTWORK", font=("Helvetica", 8),
              foreground=FG2).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))

    state["original_art"]    = tk.BooleanVar()
    state["embed_thumbnail"] = tk.BooleanVar(value=True)
    state["write_thumbnail"] = tk.BooleanVar()

    ttk.Checkbutton(f,
        text="Embed cover art into file  (recommended — visible in DAWs and players)",
        variable=state["embed_thumbnail"]).grid(row=7, column=0, columnspan=3, sticky="w", pady=1)
    ttk.Checkbutton(f,
        text="Save cover as a separate PNG file  (useful for sample folders)",
        variable=state["write_thumbnail"]).grid(row=8, column=0, columnspan=3, sticky="w", pady=1)
    ttk.Checkbutton(f,
        text="Original SoundCloud artwork resolution  (no crop to 500×500)",
        variable=state["original_art"]).grid(row=9, column=0, columnspan=3, sticky="w", pady=1)

    return f


# ── Metadata ──────────────────────────────────────────────────────────────────

def create_metadata_tab(nb, state):
    f = ttk.Frame(nb, padding=(14, 10))
    f.columnconfigure(0, weight=1)

    ttk.Label(f, text="TAGS", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

    bool_opts = [
        ("embed_metadata",  "Embed full metadata  (title, artist, date, BPM, genre…)"),
        ("extract_artist",  "Extract artist from track title  (instead of SC username)"),
        ("original_meta",   "Do not modify original file metadata"),
        ("original_name",   "Do not modify original filename"),
        ("force_meta",      "Force metadata write even if file already exists"),
        ("no_album_tag",    "Skip album tag  (avoids shared covers in some players)"),
        ("add_description", "Save track description to a separate .txt file"),
        ("addtofile",       "Append artist to filename if missing"),
        ("addtimestamp",    "Append upload timestamp to filename"),
    ]
    for i, (key, label) in enumerate(bool_opts):
        state[key] = tk.BooleanVar()
        ttk.Checkbutton(f, text=label, variable=state[key]).grid(
            row=1 + i, column=0, sticky="w", pady=1)

    sep(f, row=1 + len(bool_opts), pady=8)
    base = 2 + len(bool_opts)

    ttk.Label(f, text="NAME FORMAT  (variables: %title%, %artist%, %year%, %playlist%…)",
              font=("Helvetica", 8), foreground=FG2).grid(
        row=base, column=0, sticky="w", pady=(0, 2))
    state["name_fmt"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["name_fmt"]).grid(
        row=base + 1, column=0, sticky="ew", ipady=4, pady=(0, 8))

    ttk.Label(f, text="PLAYLIST NAME FORMAT",
              font=("Helvetica", 8), foreground=FG2).grid(
        row=base + 2, column=0, sticky="w", pady=(0, 2))
    state["pl_name_fmt"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["pl_name_fmt"]).grid(
        row=base + 3, column=0, sticky="ew", ipady=4)

    return f


# ── Filters ───────────────────────────────────────────────────────────────────

def create_filters_tab(nb, state):
    f = ttk.Frame(nb, padding=(14, 10))
    f.columnconfigure(1, weight=1)
    f.columnconfigure(3, weight=1)

    ttk.Label(f, text="SIZE & OFFSET", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))

    ttk.Label(f, text="Min size  (e.g. 1m, 500k)").grid(
        row=1, column=0, sticky="w", padx=(0, 8))
    state["min_size"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["min_size"], width=10).grid(
        row=1, column=1, sticky="w", ipady=3)

    ttk.Label(f, text="Max size").grid(
        row=1, column=2, sticky="w", padx=(16, 8))
    state["max_size"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["max_size"], width=10).grid(
        row=1, column=3, sticky="w", ipady=3)

    ttk.Label(f, text="Start from track #").grid(
        row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
    state["offset"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["offset"], width=6).grid(
        row=2, column=1, sticky="w", ipady=3, pady=(6, 0))

    sep(f, row=3, cols=4)

    ttk.Label(f, text="BEHAVIOR", font=("Helvetica", 8),
              foreground=FG2).grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 4))

    bool_opts = [
        ("continue_dl",     "Skip file if it already exists  (no re-download)"),
        ("overwrite",       "Overwrite existing files"),
        ("no_playlist",     "Ignore playlists when downloading a profile"),
        ("no_pl_folder",    "No subfolder for playlist  (all files in root)"),
        ("strict_playlist", "Abort entire playlist if one track fails"),
    ]
    for i, (key, label) in enumerate(bool_opts):
        state[key] = tk.BooleanVar()
        ttk.Checkbutton(f, text=label, variable=state[key]).grid(
            row=5 + i, column=0, columnspan=4, sticky="w", pady=1)

    sep(f, row=5 + len(bool_opts), cols=4)
    base = 6 + len(bool_opts)

    ttk.Label(f, text="DOWNLOAD ARCHIVE  (--download-archive)",
              font=("Helvetica", 8), foreground=FG2).grid(
        row=base, column=0, columnspan=4, sticky="w", pady=(0, 2))

    archive_row = ttk.Frame(f)
    archive_row.grid(row=base + 1, column=0, columnspan=4, sticky="ew", pady=(0, 8))
    archive_row.columnconfigure(0, weight=1)
    state["dl_archive"] = tk.StringVar()
    ttk.Entry(archive_row, textvariable=state["dl_archive"]).grid(
        row=0, column=0, sticky="ew", ipady=3)
    make_button(archive_row, "…", lambda: _pick_file(state["dl_archive"])).grid(
        row=0, column=1, padx=(4, 0))

    ttk.Label(f, text="SYNC FILE  (--sync)",
              font=("Helvetica", 8), foreground=FG2).grid(
        row=base + 2, column=0, columnspan=4, sticky="w", pady=(0, 2))

    sync_row = ttk.Frame(f)
    sync_row.grid(row=base + 3, column=0, columnspan=4, sticky="ew")
    sync_row.columnconfigure(0, weight=1)
    state["sync_file"] = tk.StringVar()
    ttk.Entry(sync_row, textvariable=state["sync_file"]).grid(
        row=0, column=0, sticky="ew", ipady=3)
    make_button(sync_row, "…", lambda: _pick_file(state["sync_file"])).grid(
        row=0, column=1, padx=(4, 0))

    f.columnconfigure(0, weight=1)
    return f


def _pick_file(var):
    p = filedialog.askopenfilename()
    if p:
        var.set(p)


# ── Advanced ──────────────────────────────────────────────────────────────────

def create_advanced_tab(nb, state):
    f = ttk.Frame(nb, padding=(14, 10))
    f.columnconfigure(1, weight=1)

    ttk.Label(f, text="AUTHENTICATION  (SoundCloud)", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

    state["client_id"]  = tk.StringVar()
    state["auth_token"] = tk.StringVar()
    for i, (label, key) in enumerate([("Client ID", "client_id"), ("Auth Token", "auth_token")]):
        ttk.Label(f, text=label).grid(row=1 + i, column=0, sticky="w", padx=(0, 10), pady=2)
        ttk.Entry(f, textvariable=state[key], show="•").grid(
            row=1 + i, column=1, sticky="ew", ipady=4, pady=2)

    sep(f, row=3, cols=2)

    ttk.Label(f, text="YT-DLP", font=("Helvetica", 8),
              foreground=FG2).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
    ttk.Label(f, text="Extra yt-dlp arguments").grid(
        row=5, column=0, sticky="w", padx=(0, 10))
    state["ytdlp_args"] = tk.StringVar()
    ttk.Entry(f, textvariable=state["ytdlp_args"]).grid(
        row=5, column=1, sticky="ew", ipady=4)

    sep(f, row=6, cols=2)

    ttk.Label(f, text="LOGGING", font=("Helvetica", 8),
              foreground=FG2).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 4))

    bool_opts = [
        ("log_debug",     "Debug  (very verbose log)"),
        ("log_error",     "Errors only"),
        ("hidewarnings",  "Hide warnings"),
        ("hide_progress", "Hide progress bar"),
    ]
    for i, (key, label) in enumerate(bool_opts):
        state[key] = tk.BooleanVar()
        ttk.Checkbutton(f, text=label, variable=state[key]).grid(
            row=8 + i, column=0, columnspan=2, sticky="w", pady=1)

    return f


# ── Converter ─────────────────────────────────────────────────────────────────

def create_converter_tab(nb, state, on_convert, on_embed_art):
    f = ttk.Frame(nb, padding=(14, 10))
    f.columnconfigure(0, weight=1)

    # ── Input files ───────────────────────────────────────────────────────────
    ttk.Label(f, text="INPUT FILES", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, sticky="w", pady=(0, 4))

    files_frame = ttk.Frame(f)
    files_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
    files_frame.columnconfigure(0, weight=1)

    lb = tk.Listbox(
        files_frame,
        height=5, bg=ENTRY, fg=FG, selectbackground=BTN_HOV,
        selectforeground=FG, relief="flat", font=("Courier", 8),
        activestyle="none", bd=0,
    )
    lb.grid(row=0, column=0, sticky="ew")

    btn_col = ttk.Frame(files_frame)
    btn_col.grid(row=0, column=1, sticky="n", padx=(6, 0))

    _files: list[str] = []

    def _add_files():
        paths = filedialog.askopenfilenames(title="Select files")
        for p in paths:
            if p not in _files:
                _files.append(p)
                lb.insert("end", p)

    def _remove_sel():
        for i in reversed(lb.curselection()):
            lb.delete(i)
            _files.pop(i)

    def _clear():
        lb.delete(0, "end")
        _files.clear()

    make_button(btn_col, "Add…",   _add_files).pack(fill="x", pady=(0, 4))
    make_button(btn_col, "Remove", _remove_sel).pack(fill="x", pady=(0, 4))
    make_button(btn_col, "Clear",  _clear).pack(fill="x")

    sep(f, row=2, cols=1)

    # ── Output folder ─────────────────────────────────────────────────────────
    ttk.Label(f, text="OUTPUT FOLDER", font=("Helvetica", 8),
              foreground=FG2).grid(row=3, column=0, sticky="w", pady=(0, 4))

    out_row = ttk.Frame(f)
    out_row.grid(row=4, column=0, sticky="ew", pady=(0, 2))
    out_row.columnconfigure(0, weight=1)

    state["conv_out_dir"] = tk.StringVar()
    out_entry = ttk.Entry(out_row, textvariable=state["conv_out_dir"])
    out_entry.grid(row=0, column=0, sticky="ew", ipady=4)

    def _browse_out():
        d = filedialog.askdirectory()
        if d:
            state["conv_out_dir"].set(d)
            state["conv_same_dir"].set(False)

    make_button(out_row, "Browse…", _browse_out).grid(row=0, column=1, padx=(6, 0))

    state["conv_same_dir"] = tk.BooleanVar(value=True)

    def _toggle_same(*_):
        out_entry.configure(state="disabled" if state["conv_same_dir"].get() else "normal")

    state["conv_same_dir"].trace_add("write", _toggle_same)
    ttk.Checkbutton(f, text="Same folder as input",
                    variable=state["conv_same_dir"]).grid(
        row=5, column=0, sticky="w", pady=(2, 0))
    _toggle_same()

    sep(f, row=6, cols=1)

    # ── Output format ─────────────────────────────────────────────────────────
    ttk.Label(f, text="OUTPUT FORMAT", font=("Helvetica", 8),
              foreground=FG2).grid(row=7, column=0, sticky="w", pady=(0, 6))

    fmt_frame = ttk.Frame(f)
    fmt_frame.grid(row=8, column=0, sticky="w")
    state["conv_fmt"] = tk.StringVar(value="mp3")
    for val, label in FORMATS:
        ttk.Radiobutton(fmt_frame, text=label,
                        variable=state["conv_fmt"], value=val).pack(
            side="left", padx=(0, 12))

    mp3_q_frame = ttk.Frame(f)
    mp3_q_frame.grid(row=9, column=0, sticky="w", pady=(6, 0))
    ttk.Label(mp3_q_frame, text="MP3 quality:", foreground=FG2).pack(side="left", padx=(0, 8))
    state["conv_mp3_quality"] = tk.StringVar(value="0")
    for val, label in [
        ("0",    "VBR max"),
        ("320k", "320 kbps"),
        ("256k", "256 kbps"),
        ("192k", "192 kbps"),
        ("128k", "128 kbps"),
    ]:
        ttk.Radiobutton(mp3_q_frame, text=label,
                        variable=state["conv_mp3_quality"], value=val).pack(
            side="left", padx=(0, 8))

    def _on_fmt(*_):
        if state["conv_fmt"].get() == "mp3":
            mp3_q_frame.grid()
        else:
            mp3_q_frame.grid_remove()

    state["conv_fmt"].trace_add("write", _on_fmt)

    sep(f, row=10, cols=1)

    conv_btn = make_button(f, "   Convert   ", lambda: on_convert(_files), large=True)
    conv_btn.grid(row=11, column=0, pady=(4, 0))
    state["_conv_btn"] = conv_btn

    # ── Embed cover art ───────────────────────────────────────────────────────
    sep(f, row=12, cols=1)

    ttk.Label(f, text="EMBED COVER ART  (WAV · MP3 · FLAC · M4A)",
              font=("Helvetica", 8), foreground=FG2).grid(
        row=13, column=0, sticky="w", pady=(0, 4))

    ttk.Label(
        f,
        text="Embeds artwork directly into the audio file — compatible with Traktor, Rekordbox, VirtualDJ",
        foreground=FG2, font=("Helvetica", 8),
    ).grid(row=14, column=0, sticky="w", pady=(0, 6))

    state["art_mode"] = tk.StringVar(value="auto")
    art_radio_frame = ttk.Frame(f)
    art_radio_frame.grid(row=15, column=0, sticky="w", pady=(0, 4))
    ttk.Radiobutton(art_radio_frame,
                    text="Auto-detect image  (looks for .jpg/.png with same filename)",
                    variable=state["art_mode"], value="auto").pack(anchor="w")
    ttk.Radiobutton(art_radio_frame,
                    text="Select image manually  (one image for all files)",
                    variable=state["art_mode"], value="manual").pack(anchor="w")

    img_row = ttk.Frame(f)
    img_row.grid(row=16, column=0, sticky="ew", pady=(0, 4))
    img_row.columnconfigure(0, weight=1)
    state["art_image"] = tk.StringVar()
    ttk.Entry(img_row, textvariable=state["art_image"]).grid(
        row=0, column=0, sticky="ew", ipady=4)

    def _browse_img():
        p = filedialog.askopenfilename(
            title="Select cover image",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.webp"),
                ("All files", "*.*"),
            ],
        )
        if p:
            state["art_image"].set(p)

    make_button(img_row, "Browse…", _browse_img).grid(row=0, column=1, padx=(6, 0))

    def _toggle_img(*_):
        if state["art_mode"].get() == "manual":
            img_row.grid()
        else:
            img_row.grid_remove()

    state["art_mode"].trace_add("write", _toggle_img)
    _toggle_img()

    def _do_embed():
        img = state["art_image"].get().strip() if state["art_mode"].get() == "manual" else None
        on_embed_art(_files, img)

    embed_btn = make_button(f, "   Embed Cover Art   ", _do_embed, large=True)
    embed_btn.grid(row=17, column=0, pady=(4, 0))
    state["_embed_btn"] = embed_btn

    return f


# ── Spectrogram ───────────────────────────────────────────────────────────────

def create_spectrogram_tab(nb, state):
    """Create the spectrogram tab. Imports matplotlib lazily to avoid slowing startup."""
    import tkinter as tk
    from tkinter import ttk

    placeholder = ttk.Frame(nb, padding=(14, 10))
    placeholder.columnconfigure(0, weight=1)
    placeholder.rowconfigure(1, weight=1)

    status_var = tk.StringVar(value="Loading spectrogram viewer…")
    ttk.Label(placeholder, textvariable=status_var,
              foreground=FG2, font=("Helvetica", 9)).grid(
        row=0, column=0, sticky="w")

    _built = [False]

    def _build():
        if _built[0]:
            return
        _built[0] = True
        try:
            from ..spectrogram import create_spectrogram_tab as _create
            # Replace placeholder contents with the real widget
            for w in placeholder.winfo_children():
                w.destroy()
            inner = _create(placeholder, state)
            inner.pack(fill="both", expand=True)
        except ImportError as e:
            status_var.set(
                f"Missing dependency: {e}\n"
                "Install with: pip install numpy scipy matplotlib soundfile"
            )
        except Exception as e:
            status_var.set(f"Error loading spectrogram: {e}")

    # Build lazily when the tab is first shown
    placeholder.bind("<Visibility>", lambda _: _build())
    # Also trigger after a short delay as fallback (some platforms skip Visibility)
    placeholder.after(300, _build)

    return placeholder
