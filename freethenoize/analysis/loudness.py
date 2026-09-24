"""ITU-R BS.1770-4 loudness, EBU R128 loudness range, true peak."""
import numpy as np
from scipy import signal


def _biquad_shelf(sr: int, gain_db: float, q: float, fc: float):
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * q)
    cos = np.cos(w0)
    b = [a * ((a + 1) + (a - 1) * cos + 2 * np.sqrt(a) * alpha),
         -2 * a * ((a - 1) + (a + 1) * cos),
         a * ((a + 1) + (a - 1) * cos - 2 * np.sqrt(a) * alpha)]
    den = [(a + 1) - (a - 1) * cos + 2 * np.sqrt(a) * alpha,
           2 * ((a - 1) - (a + 1) * cos),
           (a + 1) - (a - 1) * cos - 2 * np.sqrt(a) * alpha]
    return np.array(b) / den[0], np.array(den) / den[0]


def _biquad_highpass(sr: int, q: float, fc: float):
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * q)
    cos = np.cos(w0)
    b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2]
    den = [1 + alpha, -2 * cos, 1 - alpha]
    return np.array(b) / den[0], np.array(den) / den[0]


def k_weight(x: np.ndarray, sr: int) -> np.ndarray:
    b1, a1 = _biquad_shelf(sr, 4.0, 1 / np.sqrt(2), 1500.0)
    b2, a2 = _biquad_highpass(sr, 0.5, 38.0)
    return signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)


def _block_loudness(weighted: np.ndarray, sr: int, block_s: float, hop_s: float) -> np.ndarray:
    block, hop = int(block_s * sr), int(hop_s * sr)
    if len(weighted) < block:
        return np.array([])
    power = np.cumsum(np.vstack([np.zeros((1, weighted.shape[1])), weighted ** 2]), axis=0)
    starts = np.arange(0, len(weighted) - block + 1, hop)
    ms = (power[starts + block] - power[starts]) / block  # mean square per channel
    return -0.691 + 10 * np.log10(ms.sum(axis=1) + 1e-20)


def measure(x: np.ndarray, sr: int) -> dict:
    """x: float32 (frames, channels)."""
    w = k_weight(x.astype(np.float64), sr)

    blocks = _block_loudness(w, sr, 0.4, 0.1)
    integrated = None
    if len(blocks):
        gated = blocks[blocks > -70]
        if len(gated):
            rel = 10 * np.log10(np.mean(10 ** (gated / 10))) - 10
            gated = gated[gated > rel]
            integrated = float(10 * np.log10(np.mean(10 ** (gated / 10))))

    short = _block_loudness(w, sr, 3.0, 1.0)
    lra = None
    if len(short):
        s = short[short > -70]
        if len(s):
            rel = 10 * np.log10(np.mean(10 ** (s / 10))) - 20
            s = s[s > rel]
            if len(s) > 1:
                lra = float(np.percentile(s, 95) - np.percentile(s, 10))

    sample_peak = float(np.abs(x).max()) if len(x) else 0.0
    oversampled = signal.resample_poly(x, 4, 1, axis=0) if sr < 176_400 else x
    true_peak = float(np.abs(oversampled).max()) if len(x) else 0.0

    def db(v):
        return None if v <= 0 else round(20 * np.log10(v), 2)

    return {
        "integrated_lufs": None if integrated is None else round(integrated, 1),
        "lra": None if lra is None else round(lra, 1),
        "sample_peak_db": db(sample_peak),
        "true_peak_dbtp": db(true_peak),
        "plr": None if integrated is None or true_peak <= 0
        else round(20 * np.log10(true_peak) - integrated, 1),
    }
