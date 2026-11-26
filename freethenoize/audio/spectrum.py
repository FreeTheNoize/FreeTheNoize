"""Spectrogram images and lossy-cutoff detection."""
import base64

import numpy as np

from . import dsp

DB_FLOOR = -120.0
F_MIN = 20.0


def spectrogram(mono: np.ndarray, sr: int, width: int = 1600, height: int = 480) -> dict:
    """Two uint8 images (log and linear frequency), row 0 = lowest frequency.

    Values map 0..255 → DB_FLOOR..0 dB relative to the loudest bin; the UI
    applies the colormap and contrast so those can change without recomputing.
    """
    n_fft = 4096 if sr <= 50_000 else 8192
    if len(mono) < n_fft:
        mono = np.pad(mono, (0, n_fft - len(mono)))
    hop = max(n_fft // 4, (len(mono) - n_fft) // width + 1)
    frames = np.lib.stride_tricks.sliding_window_view(mono, n_fft)[::hop]
    window = dsp.hann(n_fft).astype(np.float32)
    mag = np.abs(np.fft.rfft(frames * window, axis=1)).T  # (bins, time)
    db = 20 * np.log10(mag + 1e-12)
    db -= db.max()
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)

    def to_rows(edges: np.ndarray) -> np.ndarray:
        # Max of the linear bins inside each display row; nearest bin when a
        # row is narrower than one bin (low end of the log scale).
        lo = np.searchsorted(freqs, edges[:-1])
        hi = np.maximum(np.searchsorted(freqs, edges[1:]), lo + 1)
        lo = np.minimum(lo, len(freqs) - 1)
        rows = np.empty((len(lo), db.shape[1]), dtype=np.float32)
        for i, (a, b) in enumerate(zip(lo, hi)):
            rows[i] = db[a:b].max(axis=0)
        return rows

    nyquist = sr / 2
    log_edges = np.geomspace(F_MIN, nyquist, height + 1)
    lin_edges = np.linspace(0, nyquist, height + 1)

    def encode(rows: np.ndarray) -> str:
        q = np.clip((rows - DB_FLOOR) / -DB_FLOOR * 255, 0, 255).astype(np.uint8)
        return base64.b64encode(q.tobytes()).decode("ascii")

    return {
        "width": int(db.shape[1]),
        "height": height,
        "log": encode(to_rows(log_edges)),
        "linear": encode(to_rows(lin_edges)),
        "duration": len(mono) / sr,
        "f_min": F_MIN,
        "f_max": nyquist,
        "db_floor": DB_FLOOR,
    }


def average_spectrum(mono: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    freqs, psd = dsp.welch_spectrum(mono, sr, nperseg=8192)
    return freqs, 10 * np.log10(psd + 1e-20)


# Where lossy encoders put their low-pass, roughly. Heuristic, not proof.
_CUTOFF_HINTS = [
    (11_500, "≈ 64 kbps o menos"),
    (15_500, "≈ 96–112 kbps"),
    (17_300, "≈ 128 kbps (MP3 128 / AAC 96)"),
    (18_900, "≈ 160–192 kbps"),
    (19_800, "≈ 192–256 kbps (p. ej. AAC 256 de Go+)"),
]


def detect_cutoff(mono: np.ndarray, sr: int, lossless_container: bool) -> dict:
    freqs, db = average_spectrum(mono, sr)
    smooth = dsp.moving_average(db, 9, mode="nearest")
    band = (freqs >= 1000) & (freqs <= 8000)
    reference = float(np.median(smooth[band]))
    threshold = reference - 50

    above = np.nonzero(smooth > threshold)[0]
    cutoff = float(freqs[above[-1]]) if len(above) else 0.0
    nyquist = sr / 2

    # A lossy low-pass is a cliff; a natural roll-off is a slope.
    def mean_db(lo, hi):
        sel = (freqs >= lo) & (freqs <= hi)
        return float(smooth[sel].mean()) if sel.any() else float("nan")

    drop = mean_db(cutoff - 600, cutoff - 100) - mean_db(cutoff + 150, cutoff + 900)
    sharp = cutoff < nyquist - 1000 and drop > 25

    hint = None
    if sharp:
        hint = next((text for limit, text in _CUTOFF_HINTS if cutoff < limit), None)

    if hint and lossless_container:
        verdict, level = "Probable falso lossless: el archivo es sin pérdida pero el audio viene de una fuente con pérdida", "bad"
    elif hint:
        verdict, level = "Corte típico de codificación con pérdida", "warn"
    elif sharp:
        verdict, level = "Corte alto; compatible con 320 kbps o con un master filtrado", "ok"
    else:
        verdict, level = "Espectro completo; sin indicios de codificación con pérdida", "good"

    step = max(1, len(freqs) // 1024)
    return {
        "cutoff_hz": round(cutoff),
        "sharp": bool(sharp),
        "drop_db": None if np.isnan(drop) else round(drop, 1),
        "estimate": hint,
        "verdict": verdict,
        "level": level,
        "curve": {
            "freqs": freqs[::step].round(1).tolist(),
            "db": (smooth[::step] - smooth.max()).round(1).tolist(),
        },
    }
