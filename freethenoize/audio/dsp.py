"""The few signal-processing helpers the analysis needs, in plain numpy.

scipy did this before and was ~30 MB of the desktop app for seven functions.
Each helper matches the scipy call it replaces (see tests/test_dsp.py).
"""
from functools import lru_cache

import numpy as np

_BLOCK = 1 << 18  # samples per FFT block when filtering long signals


def _fft_size(n: int) -> int:
    return 1 << max(0, int(n - 1).bit_length())


def hann(n: int) -> np.ndarray:
    """Periodic Hann window, as scipy.signal.get_window("hann", n)."""
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def xcorr(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Full cross-correlation of 1-D x and y via FFT.

    Returns (lags, corr) like scipy.signal.correlation_lags / correlate(mode="full").
    """
    n = len(x) + len(y) - 1
    size = _fft_size(n)
    c = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(y, size)), size)
    corr = np.concatenate([c[size - (len(y) - 1):], c[:len(x)]]) if len(y) > 1 else c[:len(x)]
    return np.arange(-(len(y) - 1), len(x)), corr


def autocorr(x: np.ndarray) -> np.ndarray:
    """Non-negative lags of the autocorrelation (lag 0 first)."""
    size = _fft_size(2 * len(x) - 1)
    f = np.fft.rfft(x, size)
    return np.fft.irfft(f * np.conj(f), size)[:len(x)]


def moving_average(x: np.ndarray, size: int, mode: str = "reflect") -> np.ndarray:
    """scipy.ndimage.uniform_filter1d for 1-D x. mode: "reflect" or "nearest"."""
    left = size // 2
    right = size - 1 - left
    pad = np.pad(np.asarray(x, dtype=np.float64), (left, right),
                 mode="symmetric" if mode == "reflect" else "edge")
    c = np.concatenate([[0.0], np.cumsum(pad)])
    return (c[size:] - c[:-size]) / size


def welch_spectrum(x: np.ndarray, sr: int, nperseg: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """scipy.signal.welch(x, sr, nperseg=nperseg, scaling="spectrum"):
    Hann window, 50 % overlap, mean removed per segment, one-sided."""
    x = np.asarray(x, dtype=np.float64)
    nperseg = min(nperseg, len(x))
    step = nperseg - nperseg // 2
    win = hann(nperseg)
    count = (len(x) - nperseg) // step + 1
    acc = np.zeros(nperseg // 2 + 1)
    frames = np.lib.stride_tricks.sliding_window_view(x, nperseg)[::step][:count]
    for i in range(0, count, 512):  # bounded memory on long tracks
        seg = frames[i:i + 512]
        seg = (seg - seg.mean(axis=1, keepdims=True)) * win
        acc += (np.abs(np.fft.rfft(seg, axis=1)) ** 2).sum(axis=0)
    psd = acc / count / win.sum() ** 2
    psd[1:-1 if nperseg % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(nperseg, 1 / sr), psd


def fir_filter(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Causal FIR filter along axis 0 (overlap-add FFT): y[n] = sum h[k] x[n-k]."""
    x = np.asarray(x, dtype=np.float64)
    squeeze = x.ndim == 1
    if squeeze:
        x = x[:, None]
    m = len(h)
    size = _fft_size(_BLOCK + m - 1)
    hf = np.fft.rfft(h, size)[:, None]
    y = np.zeros((len(x) + m - 1, x.shape[1]))
    for start in range(0, len(x), _BLOCK):
        block = x[start:start + _BLOCK]
        seg = np.fft.irfft(np.fft.rfft(block, size, axis=0) * hf, size, axis=0)
        end = min(start + len(block) + m - 1, len(y))
        y[start:end] += seg[:end - start]
    y = y[:len(x)]
    return y[:, 0] if squeeze else y


def biquad_response(sections: list[tuple[np.ndarray, np.ndarray]], n: int) -> np.ndarray:
    """First n samples of the impulse response of cascaded biquads (b, a with a[0] == 1).

    Filtering with this (fir_filter) equals scipy.signal.lfilter as long as n
    covers the decay; plain Python, so keep n small and cache the result.
    """
    h = np.zeros(n)
    h[0] = 1.0
    for b, a in sections:
        out = np.zeros(n)
        x1 = x2 = y1 = y2 = 0.0
        for i, x0 in enumerate(h.tolist()):
            y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
            out[i] = y0
            x2, x1, y2, y1 = x1, x0, y1, y0
        h = out
    return h


@lru_cache(maxsize=8)
def _interp_filter(up: int) -> np.ndarray:
    # scipy.signal.resample_poly's default: Kaiser (beta 5) low-pass at 1/up,
    # 10 zero crossings each side, gain = up.
    half = 10 * up
    n = np.arange(2 * half + 1) - half
    h = np.sinc(n / up) / up * np.kaiser(2 * half + 1, 5.0)
    return h / h.sum() * up


def upsample(x: np.ndarray, up: int) -> np.ndarray:
    """Band-limited interpolation by an integer factor along axis 0 (for true peak)."""
    x = np.asarray(x, dtype=np.float64)
    squeeze = x.ndim == 1
    if squeeze:
        x = x[:, None]
    h = _interp_filter(up)
    out = np.empty((len(x) * up, x.shape[1]))
    delay = (len(h) - 1) // 2
    for phase in range(up):
        # Output sample k*up + phase takes taps h[phase + j*up] (polyphase).
        taps = h[(phase + delay) % up::up]
        first = (phase + delay) // up
        for ch in range(x.shape[1]):
            full = np.convolve(x[:, ch], taps)
            out[phase::up, ch] = full[first:first + len(x)]
    return out[:, 0] if squeeze else out
