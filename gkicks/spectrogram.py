"""Spectrogram analysis and display — matplotlib embedded in Tk.

Performance:
  • ffmpeg decodes directly to a float32 pipe — no temp file I/O
  • Audio resampled to 22 kHz by ffmpeg, halving STFT work vs 44.1 kHz
  • scipy.fft workers=-1 → all logical CPU cores used for FFT
  • Display pre-rendered as a log-frequency image in the worker thread
  • Main thread only calls ax.imshow() + canvas.draw() — fast texture upload
"""
import subprocess
import threading
from pathlib import Path

import numpy as np

from .downloader import FFMPEG_EXE, build_env


_TARGET_SR     = 22050   # Hz — enough for full 0–11 kHz display range
_DISPLAY_TBINS = 2048    # max time columns in rendered image
_DISPLAY_FBINS = 512     # log-spaced frequency rows in rendered image
_F_MIN_HZ      = 20.0    # lowest frequency shown
_MAX_SECS      = 600     # truncate audio at 10 min (prevents OOM)


# ── Audio reading ──────────────────────────────────────────────────────────────

def _ffmpeg_pipe(path: str) -> tuple:
    """Decode any audio format to float32 mono at _TARGET_SR via pipe.
    No temp files — data streams directly into memory.
    """
    cmd = [
        FFMPEG_EXE, "-v", "quiet",
        "-i", path,
        "-ar", str(_TARGET_SR), "-ac", "1",
        "-f", "f32le", "pipe:1",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=build_env(),
    )
    raw = proc.stdout.read()
    proc.wait()
    if proc.returncode != 0 and len(raw) == 0:
        raise RuntimeError(f"ffmpeg decode failed (exit {proc.returncode})")
    return np.frombuffer(raw, dtype=np.float32).copy(), _TARGET_SR


def read_audio(path: str) -> tuple:
    """Return (float32 mono samples, sample_rate).
    Fast path: soundfile for WAV/FLAC with integer decimation.
    All other formats go through the ffmpeg pipe.
    """
    try:
        import soundfile as sf
        ext = Path(path).suffix.lower()
        if ext in {".wav", ".flac", ".ogg", ".aiff", ".aif", ".caf"}:
            data, sr = sf.read(path, always_2d=True)
            samples = data.mean(axis=1).astype(np.float32)
            # Fast integer decimation (no filter — adequate for display)
            if sr > _TARGET_SR and sr % _TARGET_SR == 0:
                step = sr // _TARGET_SR
                return samples[::step], _TARGET_SR
            return samples, sr
    except Exception:
        pass

    if not FFMPEG_EXE:
        raise RuntimeError(
            "Cannot read audio: soundfile failed and ffmpeg was not found."
        )
    return _ffmpeg_pipe(path)


# ── STFT ───────────────────────────────────────────────────────────────────────

def compute_spectrogram(samples: np.ndarray, sr: int) -> tuple:
    """STFT using all CPU cores.  Returns (freqs, times, Sxx_dB, duration_s)."""
    from scipy.signal import spectrogram as _spectrogram
    from scipy.fft import set_workers

    n = min(len(samples), int(_MAX_SECS * sr))
    samples  = samples[:n]
    duration = n / sr

    nperseg  = min(len(samples), 2048)
    noverlap = nperseg * 3 // 4

    with set_workers(-1):           # use every logical CPU core
        freqs, times, Sxx = _spectrogram(
            samples, fs=sr,
            nperseg=nperseg, noverlap=noverlap,
            window="hann", scaling="density",
        )

    Sxx_dB = 10.0 * np.log10(np.maximum(Sxx, 1e-12))
    return freqs, times, Sxx_dB, duration


# ── Display preparation ────────────────────────────────────────────────────────

def prepare_display(freqs: np.ndarray, times: np.ndarray,
                    Sxx_dB: np.ndarray) -> dict:
    """Downsample to display resolution on a log-frequency grid.

    Does all heavy numpy work in the worker thread so the main thread only
    has to call ax.imshow() with the resulting float32 array.

    Returns a dict consumed by _draw().
    """
    mask  = freqs >= _F_MIN_HZ
    f_src = freqs[mask]
    S     = Sxx_dB[mask, :]

    if len(f_src) < 2:
        raise ValueError("Not enough frequency bins above 20 Hz.")

    # Log-spaced target frequency grid
    f_log_hz = np.logspace(
        np.log10(f_src[0]),
        np.log10(f_src[-1]),
        _DISPLAY_FBINS,
    )

    # Nearest-neighbour mapping to log grid (fast; good enough for display)
    idx   = np.searchsorted(f_src, f_log_hz).clip(0, len(f_src) - 1)
    S_log = S[idx, :]                        # (_DISPLAY_FBINS, n_times)

    # Decimate time axis
    n_t = S_log.shape[1]
    if n_t > _DISPLAY_TBINS:
        t_idx  = np.round(np.linspace(0, n_t - 1, _DISPLAY_TBINS)).astype(int)
        S_log  = S_log[:, t_idx]
        t_plot = times[t_idx]
    else:
        t_plot = times

    vmin = float(np.percentile(S_log, 5))
    vmax = float(np.percentile(S_log, 99.5))

    return {
        "S":     S_log.astype(np.float32),
        "t_min": float(t_plot[0]),
        "t_max": float(t_plot[-1]),
        "f_min": float(f_log_hz[0]),    # Hz
        "f_max": float(f_log_hz[-1]),   # Hz
        "vmin":  vmin,
        "vmax":  vmax,
    }


# ── Tkinter widget ─────────────────────────────────────────────────────────────

def create_spectrogram_tab(parent, state: dict):
    """Build and return the spectrogram tab frame."""
    import tkinter as tk
    from tkinter import ttk, filedialog

    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    from .styles import BG, FG, FG2, make_button

    f = ttk.Frame(parent, padding=(14, 10))
    f.columnconfigure(0, weight=1)
    f.rowconfigure(3, weight=1)

    # ── Header ────────────────────────────────────────────────────────────────
    ttk.Label(f, text="SPECTROGRAM VIEWER", font=("Helvetica", 8),
              foreground=FG2).grid(row=0, column=0, sticky="w", pady=(0, 6))

    # ── File selector row ─────────────────────────────────────────────────────
    sel_row = ttk.Frame(f)
    sel_row.grid(row=1, column=0, sticky="ew", pady=(0, 4))
    sel_row.columnconfigure(0, weight=1)

    file_var = tk.StringVar()
    ttk.Entry(sel_row, textvariable=file_var).grid(
        row=0, column=0, sticky="ew", ipady=4)

    def _browse():
        p = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files",
                 "*.wav *.flac *.mp3 *.m4a *.aac *.ogg *.opus *.aiff *.aif"),
                ("All files", "*.*"),
            ],
        )
        if p:
            file_var.set(p)
            _load()

    _browse_btn  = make_button(sel_row, "Browse…", _browse)
    _browse_btn.grid(row=0, column=1, padx=(6, 0))

    _analyze_btn = make_button(sel_row, "Analyze", lambda: _load())
    _analyze_btn.grid(row=0, column=2, padx=(4, 0))

    # ── Status row (label + progress bar) ─────────────────────────────────────
    status_row = ttk.Frame(f)
    status_row.grid(row=2, column=0, sticky="ew", pady=(0, 4))
    status_row.columnconfigure(0, weight=1)

    status_var = tk.StringVar(value="Select an audio file and click Analyze.")
    ttk.Label(status_row, textvariable=status_var,
              foreground=FG2, font=("Helvetica", 8)).grid(
        row=0, column=0, sticky="w")

    progress = ttk.Progressbar(status_row, mode="indeterminate", length=160)
    # hidden until analysis starts

    # ── Matplotlib figure ─────────────────────────────────────────────────────
    fig = Figure(figsize=(9, 3.8), facecolor=BG, tight_layout=True)
    ax  = fig.add_subplot(111)
    ax.set_facecolor("#080808")
    ax.set_xlabel("Time (s)",        color=FG2, fontsize=8)
    ax.set_ylabel("Frequency",       color=FG2, fontsize=8)
    ax.tick_params(colors=FG2, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2d2d2d")

    canvas        = FigureCanvasTkAgg(fig, master=f)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.configure(bg=BG)
    canvas_widget.grid(row=3, column=0, sticky="nsew")

    # ── Colormap selector ─────────────────────────────────────────────────────
    cmap_row = ttk.Frame(f)
    cmap_row.grid(row=4, column=0, sticky="w", pady=(6, 0))
    ttk.Label(cmap_row, text="Color scheme:", foreground=FG2,
              font=("Helvetica", 8)).pack(side="left", padx=(0, 8))
    if "spec_cmap" not in state:
        state["spec_cmap"] = tk.StringVar(value="inferno")
    for val, lbl in [
        ("inferno", "Inferno"), ("magma",   "Magma"),
        ("plasma",  "Plasma"),  ("turbo",   "Turbo"),
        ("viridis", "Viridis"),
    ]:
        ttk.Radiobutton(cmap_row, text=lbl,
                        variable=state["spec_cmap"], value=val).pack(
            side="left", padx=(0, 10))

    # ── Shared mutable state ──────────────────────────────────────────────────
    _cache   = {}         # last 'display' dict for cmap re-render
    _running = [False]    # guard against double-click

    # ── Render ────────────────────────────────────────────────────────────────
    def _draw(disp: dict, cmap: str):
        """Render pre-computed display dict.  Fast: one texture upload."""
        ax.clear()
        ax.set_facecolor("#080808")

        ax.imshow(
            disp["S"],
            aspect="auto",
            origin="lower",
            extent=[disp["t_min"], disp["t_max"], 0, _DISPLAY_FBINS],
            cmap=cmap,
            vmin=disp["vmin"],
            vmax=disp["vmax"],
            interpolation="bilinear",
        )

        # Y-axis tick labels mapped from log-frequency pixel positions
        f_min_hz = disp["f_min"]
        f_max_hz = disp["f_max"]
        log_min  = np.log10(f_min_hz)
        log_max  = np.log10(f_max_hz)

        tick_pos, tick_lbl = [], []
        for fhz in [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]:
            if f_min_hz <= fhz <= f_max_hz:
                pos = ((np.log10(fhz) - log_min)
                       / (log_max - log_min) * _DISPLAY_FBINS)
                lbl = f"{fhz // 1000}k" if fhz >= 1000 else str(fhz)
                tick_pos.append(pos)
                tick_lbl.append(lbl)

        ax.set_yticks(tick_pos, tick_lbl)
        ax.set_xlabel("Time (s)",    color=FG2, fontsize=8)
        ax.set_ylabel("Frequency",   color=FG2, fontsize=8)
        ax.tick_params(colors=FG2, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2d2d2d")
        canvas.draw()

    # ── Worker ────────────────────────────────────────────────────────────────
    def _load():
        path = file_var.get().strip()
        if not path or not Path(path).exists():
            status_var.set("File not found.")
            return
        if _running[0]:
            return

        _running[0] = True
        _analyze_btn.configure(state="disabled")
        _browse_btn.configure(state="disabled")
        progress.grid(row=0, column=1, padx=(12, 0))
        progress.start(12)

        def _worker():
            try:
                parent.after(0, lambda: status_var.set("Decoding audio…"))
                samples, sr = read_audio(path)

                dur_s = len(samples) / sr
                parent.after(0, lambda: status_var.set(
                    f"Computing spectrogram  "
                    f"({sr / 1000:.1f} kHz · {dur_s:.0f} s) …"
                ))
                freqs, times, Sxx_dB, duration = compute_spectrogram(samples, sr)

                parent.after(0, lambda: status_var.set("Preparing display…"))
                disp = prepare_display(freqs, times, Sxx_dB)
                _cache["display"] = disp

                info = (
                    f"{Path(path).name}  |  "
                    f"{sr / 1000:.1f} kHz  |  "
                    f"{duration:.1f} s"
                )
                cmap = state["spec_cmap"].get()

                def _finish():
                    _draw(disp, cmap)
                    status_var.set(info)
                    progress.stop()
                    progress.grid_remove()
                    _analyze_btn.configure(state="normal")
                    _browse_btn.configure(state="normal")
                    _running[0] = False

                parent.after(0, _finish)

            except Exception as e:
                def _err():
                    status_var.set(f"Error: {e}")
                    progress.stop()
                    progress.grid_remove()
                    _analyze_btn.configure(state="normal")
                    _browse_btn.configure(state="normal")
                    _running[0] = False
                parent.after(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Cmap change ───────────────────────────────────────────────────────────
    def _on_cmap_change(*_):
        if "display" in _cache:
            _draw(_cache["display"], state["spec_cmap"].get())

    state["spec_cmap"].trace_add("write", _on_cmap_change)

    return f
