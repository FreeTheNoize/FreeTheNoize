"""Null test: align two versions, match gain, subtract, measure what is left."""
import numpy as np

from . import dsp

ALIGN_SECONDS = 30
MAX_LAG_SECONDS = 10


def find_offset(a: np.ndarray, b: np.ndarray, sr: int) -> int:
    """Samples to delay b by so it lines up with a (negative = advance)."""
    seg = int(ALIGN_SECONDS * sr)
    start = min(len(a), len(b)) // 4 if min(len(a), len(b)) > 2 * seg else 0
    x = a[start:start + seg]
    y = b[start:start + seg]
    lags, corr = dsp.xcorr(x, y)
    limit = int(MAX_LAG_SECONDS * sr)
    sel = np.abs(lags) <= limit
    return int(lags[sel][np.argmax(np.abs(corr[sel]))])


def null_test(a: np.ndarray, b: np.ndarray, sr: int) -> dict:
    """a, b: float32 (frames, channels) at the same sample rate."""
    lag = find_offset(a.mean(axis=1), b.mean(axis=1), sr)
    if lag > 0:
        b = np.vstack([np.zeros((lag, b.shape[1]), b.dtype), b])
    elif lag < 0:
        b = b[-lag:]
    n = min(len(a), len(b))
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)

    # Least-squares gain; also reveals a polarity flip (negative gain).
    gain = float(np.sum(a * b) / max(np.sum(b * b), 1e-20))
    diff = a - gain * b

    energy_a = float(np.mean(a ** 2))
    energy_d = float(np.mean(diff ** 2))
    depth = 10 * np.log10(max(energy_d, 1e-20) / max(energy_a, 1e-20))
    correlation = float(np.corrcoef(a.mean(axis=1), b.mean(axis=1))[0, 1]) if n > 1 else 0.0

    # Typical depths on real music: lossless vs MP3 320 ≈ -35…-45 dB,
    # vs MP3 128 ≈ -18…-28 dB; unrelated masters rarely get below -12 dB.
    if depth < -90:
        verdict, level = "Idénticos (bit a bit o prácticamente)", "good"
    elif depth < -32:
        verdict, level = "Mismo master; solo difieren en una codificación de alta calidad", "good"
    elif depth < -14:
        verdict, level = "Mismo master con pérdidas audibles (codificación agresiva) o retoques leves", "warn"
    else:
        verdict, level = "Versiones distintas (otro master, edit o mezcla)", "bad"

    return {
        "offset_ms": round(lag / sr * 1000, 2),
        "gain_db": round(20 * np.log10(abs(gain)), 2) if gain else None,
        "inverted": gain < 0,
        "null_depth_db": round(depth, 1),
        "correlation": round(correlation, 4),
        "verdict": verdict,
        "level": level,
        "diff": diff.astype(np.float32),
    }
