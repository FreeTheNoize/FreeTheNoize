"""Spectrogram analysis and display — matplotlib embedded in Tk, similar to Spek.

Audio reading strategy:
  1. soundfile  → handles WAV, FLAC, OGG, AIFF, etc.
  2. ffmpeg     → converts any supported format to a temp WAV, then re-read.
  3. stdlib wave → last-resort wav reader (no extra deps needed).
"""
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from .downloader import FFMPEG_EXE, build_env


# ── Audio reading ──────────────────────────────────────────────────────────────

def _read_with_soundfile(path: str):
    import soundfile as sf
    data, sr = sf.read(path, always_2d=True)
    return data.mean(axis=1).astype(np.float32), sr


def _read_with_wave(path: str):
    with wave.open(path, "rb") as wf:
        sr        = wf.getframerate()
        n_frames  = wf.getnframes()
        n_ch      = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        raw       = wf.readframes(n_frames)
    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise RuntimeError(f"Unsupported sample width: {sampwidth}")
    if n_ch > 1:
        samples = samples.reshape(-1, n_ch).mean(axis=1)
    return samples, sr


def _ffmpeg_to_wav(path: str) -> str:
    """Convert *path* to a temp WAV (44100 Hz, mono). Returns temp file path."""
    tmp = tempfile.mktemp(suffix=".wav")
    cmd = [
        FFMPEG_EXE, "-y", "-v", "quiet",
        "-i", path,
        "-ar", "44100", "-ac", "1",
        "-f", "wav", tmp,
    ]
    result = subprocess.run(cmd, env=build_env(), capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return tmp


def read_audio(path: str):
    """Return (samples: float32 ndarray, sample_rate: int).
    Tries soundfile → ffmpeg+soundfile → ffmpeg+wave stdlib.
    """
    # 1 — soundfile direct
    try:
        return _read_with_soundfile(path)
    except ImportError:
        pass
    except Exception:
        pass

    # 2 & 3 — ffmpeg conversion
    if not FFMPEG_EXE:
        raise RuntimeError(
            "Cannot read audio: soundfile is unavailable and ffmpeg was not found."
        )
    tmp = None
    try:
        tmp = _ffmpeg_to_wav(path)
        try:
            return _read_with_soundfile(tmp)
        except ImportError:
            return _read_with_wave(tmp)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


# ── Spectrogram computation ────────────────────────────────────────────────────

def compute_spectrogram(samples: np.ndarray, sr: int):
    """Return (freqs, times, Sxx_dB) using scipy.signal.spectrogram."""
    from scipy.signal import spectrogram

    nperseg  = min(len(samples), 4096)
    noverlap = nperseg * 3 // 4

    freqs, times, Sxx = spectrogram(
        samples, fs=sr,
        nperseg=nperseg, noverlap=noverlap,
        window="hann", scaling="density",
    )
    Sxx_dB = 10.0 * np.log10(np.maximum(Sxx, 1e-12))
    return freqs, times, Sxx_dB


# ── Tkinter widget ─────────────────────────────────────────────────────────────

def create_spectrogram_tab(parent, state: dict):
    """Build and return the spectrogram tab frame, embedded matplotlib figure."""
    import tkinter as tk
    from tkinter import ttk, filedialog

    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    from .styles import BG, FG, FG2, ENTRY, BTN_BG, BTN_HOV, make_button

    f = ttk.Frame(parent, padding=(14, 10))
    f.columnconfigure(0, weight=1)
    f.rowconfigure(3, weight=1)

    # ── Section header ────────────────────────────────────────────────────────
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
                ("Audio files", "*.wav *.flac *.mp3 *.m4a *.aac *.ogg *.opus *.aiff *.aif"),
                ("All files", "*.*"),
            ],
        )
        if p:
            file_var.set(p)

    make_button(sel_row, "Browse…", _browse).grid(row=0, column=1, padx=(6, 0))
    make_button(sel_row, "Analyze", lambda: _load(_file_var=file_var.get())).grid(
        row=0, column=2, padx=(4, 0))

    # ── Status label ──────────────────────────────────────────────────────────
    status_var = tk.StringVar(value="Select an audio file and click Analyze.")
    ttk.Label(f, textvariable=status_var, foreground=FG2,
              font=("Helvetica", 8)).grid(row=2, column=0, sticky="w", pady=(0, 4))

    # ── Matplotlib figure ─────────────────────────────────────────────────────
    fig = Figure(figsize=(9, 3.8), facecolor=BG, tight_layout=True)
    ax  = fig.add_subplot(111)
    ax.set_facecolor("#080808")
    ax.set_xlabel("Time (s)", color=FG2, fontsize=8)
    ax.set_ylabel("Frequency (kHz)", color=FG2, fontsize=8)
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
    state["spec_cmap"] = tk.StringVar(value="inferno")
    for cmap_val, cmap_lbl in [
        ("inferno", "Inferno"),
        ("magma",   "Magma"),
        ("plasma",  "Plasma"),
        ("turbo",   "Turbo"),
        ("viridis", "Viridis"),
    ]:
        ttk.Radiobutton(cmap_row, text=cmap_lbl,
                        variable=state["spec_cmap"], value=cmap_val).pack(
            side="left", padx=(0, 10))

    _cache = {}   # holds last computed (freqs, times, Sxx_dB) to allow cmap re-render

    def _draw(freqs, times, Sxx_dB, cmap="inferno"):
        ax.clear()
        ax.set_facecolor("#080808")

        # Use frequencies above 20 Hz for a cleaner log-scale view
        mask   = freqs >= 20
        f_plot = freqs[mask] / 1000.0   # → kHz
        S_plot = Sxx_dB[mask, :]

        vmin = float(np.percentile(S_plot, 5))
        vmax = float(np.percentile(S_plot, 99.5))

        ax.pcolormesh(times, f_plot, S_plot,
                      shading="gouraud", cmap=cmap,
                      vmin=vmin, vmax=vmax)
        ax.set_yscale("log")
        ax.set_ylim(20 / 1000, f_plot[-1])
        ax.set_ylabel("Frequency (kHz)", color=FG2, fontsize=8)
        ax.set_xlabel("Time (s)",        color=FG2, fontsize=8)
        ax.tick_params(colors=FG2, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2d2d2d")
        canvas.draw()

    def _load(_file_var=None):
        path = _file_var or file_var.get().strip()
        if not path or not Path(path).exists():
            status_var.set("File not found.")
            return
        status_var.set(f"Loading {Path(path).name} …")

        def _worker():
            try:
                samples, sr = read_audio(path)
                freqs, times, Sxx_dB = compute_spectrogram(samples, sr)
                _cache["data"] = (freqs, times, Sxx_dB)
                info = (f"{Path(path).name}  |  "
                        f"{sr / 1000:.1f} kHz  |  "
                        f"{times[-1]:.1f} s  |  "
                        f"{len(samples) / sr:.1f} s duration")
                parent.after(0, lambda: [
                    status_var.set(info),
                    _draw(freqs, times, Sxx_dB, state["spec_cmap"].get()),
                ])
            except Exception as e:
                parent.after(0, lambda: status_var.set(f"Error: {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_cmap_change(*_):
        if "data" in _cache:
            freqs, times, Sxx_dB = _cache["data"]
            _draw(freqs, times, Sxx_dB, state["spec_cmap"].get())

    state["spec_cmap"].trace_add("write", _on_cmap_change)

    return f
