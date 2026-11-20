"""Tempo (BPM) and key estimation, with Camelot notation for DJs.

Plain numpy/scipy, no ML: good on electronic music with a steady beat and a
clear tonal centre; treat it as a hint on anything else.
"""
import numpy as np
from scipy import ndimage, signal

RATE = 22_050
HOP = 256  # ≈ 86 frames/s
BPM_MIN, BPM_MAX = 70.0, 180.0

# Spelling as DJ software shows it.
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]

# Krumhansl–Kessler key profiles.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Camelot wheel: pitch class → number. B = major, A = minor.
_CAMELOT_MAJOR = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
_CAMELOT_MINOR = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}


def _excerpt(mono: np.ndarray, sr: int, seconds: float = 120) -> np.ndarray:
    """Resample to RATE and keep the middle of the track (skip intro/outro)."""
    if sr != RATE:
        g = np.gcd(int(sr), RATE)
        mono = signal.resample_poly(mono, RATE // g, int(sr) // g)
    n = int(seconds * RATE)
    if len(mono) > n:
        start = (len(mono) - n) // 2
        mono = mono[start:start + n]
    return mono.astype(np.float32)


def _stft_mag(x: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    win = np.hanning(n_fft).astype(np.float32)
    return np.abs(np.fft.rfft(frames * win, axis=1))  # (time, bins)


def estimate_bpm(x: np.ndarray) -> dict:
    """x: mono at RATE."""
    mag = _stft_mag(x, 1024, HOP)
    # Onset strength: half-wave rectified flux of log-compressed magnitude.
    logm = np.log1p(100 * mag)
    flux = np.maximum(np.diff(logm, axis=0), 0).sum(axis=1)
    # No transients at all (drones, test tones): no tempo to find.
    if len(flux) < 4 * 86 or flux.mean() < 0.02 * logm.sum(axis=1).mean():
        return {"bpm": None, "confidence": 0.0}
    flux -= ndimage.uniform_filter1d(flux, 43)  # remove slow trend
    flux = np.maximum(flux, 0)
    flux /= flux.std() + 1e-9

    fps = RATE / HOP
    ac = signal.correlate(flux, flux, mode="full", method="fft")[len(flux) - 1:]
    ac /= ac[0] + 1e-9
    lag_min, lag_max = int(fps * 60 / BPM_MAX), int(fps * 60 / BPM_MIN) + 1
    lags = np.arange(lag_min, min(lag_max, len(ac) - 1))
    if not len(lags):
        return {"bpm": None, "confidence": 0.0}
    # Reward lags whose double also correlates (beat vs. half-beat ambiguity),
    # and gently prefer the usual dance range.
    score = ac[lags] + 0.5 * ac[np.minimum(lags * 2, len(ac) - 1)]
    bpms = 60 * fps / lags
    score *= np.exp(-0.5 * (np.log2(bpms / 125) / 0.9) ** 2)
    i = int(np.argmax(score))
    # Refine on a fine grid: the comb of beat multiples (up to 16 beats) pins
    # the period far below one frame of resolution.
    coarse = 60 * fps / lags[i]
    grid = np.arange(coarse - 2, coarse + 2, 0.02)
    ks = np.arange(1, 17)
    pos = (60 * fps / grid)[:, None] * ks[None, :]
    valid = pos < len(ac) - 1
    comb = np.where(valid, np.interp(np.minimum(pos, len(ac) - 1), np.arange(len(ac)), ac), 0).sum(axis=1)
    bpm = float(grid[int(np.argmax(comb))])
    # Confidence: how strongly the onset curve repeats at the beat period,
    # relative to its typical self-similarity. Steady tones and noise ≈ 0.
    beat_ac = float(np.interp(60 * fps / bpm, np.arange(len(ac)), ac))
    conf = float(np.clip((beat_ac - np.median(ac[lags])) / 0.3, 0, 1))
    if conf < 0.15:
        return {"bpm": None, "confidence": round(conf, 2)}
    # Snap to integers when close: most produced music sits on whole BPMs.
    if abs(bpm - round(bpm)) < 0.3:
        bpm = float(round(bpm))
    return {"bpm": round(float(bpm), 1), "confidence": round(conf, 2)}


def chroma(x: np.ndarray) -> np.ndarray:
    n_fft = 8192
    mag = _stft_mag(x, n_fft, 2048)
    freqs = np.fft.rfftfreq(n_fft, 1 / RATE)
    sel = (freqs >= 55) & (freqs <= 2000)
    pc = ((np.round(12 * np.log2(freqs[sel] / 440.0)) + 9) % 12).astype(int)
    # Per-frame chroma, normalised, then averaged: loud passages do not
    # dominate, and the 1/f weighting tames upper harmonics (which otherwise
    # push the estimate towards the dominant).
    m = mag[:, sel] / freqs[sel]
    frames = np.zeros((len(m), 12))
    for k in range(12):
        frames[:, k] = m[:, pc == k].sum(axis=1)
    frames /= frames.max(axis=1, keepdims=True) + 1e-9
    out = frames.mean(axis=0)
    return out / (out.max() + 1e-9)


def estimate_key(x: np.ndarray) -> dict:
    c = chroma(x)
    if not c.any():
        return {"key": None, "camelot": None, "confidence": 0.0}
    scores = []
    for tonic in range(12):
        for mode, prof in (("major", _MAJOR), ("minor", _MINOR)):
            scores.append((np.corrcoef(c, np.roll(prof, tonic))[0, 1], tonic, mode))
    scores.sort(reverse=True)
    best, tonic, mode = scores[0]
    minor = mode == "minor"
    note = (MINOR_NAMES if minor else MAJOR_NAMES)[tonic]
    name = note + ("m" if minor else "")
    camelot = f"{_CAMELOT_MINOR[tonic]}A" if minor else f"{_CAMELOT_MAJOR[tonic]}B"
    return {
        "key": name,
        "key_long": f"{note} {'menor' if minor else 'mayor'}",
        "camelot": camelot,
        "confidence": round(float(best - scores[1][0]), 3),
    }


def analyze(mono: np.ndarray, sr: int) -> dict:
    x = _excerpt(mono, sr)
    tempo = estimate_bpm(x)
    key = estimate_key(x)
    return {
        "bpm": tempo["bpm"],
        "bpm_confidence": tempo["confidence"],
        "key": key["key"],
        "key_long": key.get("key_long"),
        "camelot": key["camelot"],
        "key_confidence": key["confidence"],
    }
