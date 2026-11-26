"""The numpy DSP helpers against the scipy calls they replace (scipy is not a
dependency; these tests run only where it happens to be installed)."""
import numpy as np
import pytest

from freethenoize.audio import dsp, loudness

signal = pytest.importorskip("scipy.signal")
ndimage = pytest.importorskip("scipy.ndimage")

rng = np.random.default_rng(0)
X = rng.standard_normal(50_001)
Y = rng.standard_normal(30_000)


def test_xcorr_and_autocorr():
    lags, corr = dsp.xcorr(X, Y)
    assert (lags == signal.correlation_lags(len(X), len(Y), mode="full")).all()
    assert np.allclose(corr, signal.correlate(X, Y, mode="full", method="fft"), atol=1e-9)
    ref = signal.correlate(X, X, mode="full", method="fft")[len(X) - 1:]
    assert np.allclose(dsp.autocorr(X), ref, atol=1e-8)


@pytest.mark.parametrize("size", [9, 43, 86])
@pytest.mark.parametrize("mode", ["reflect", "nearest"])
def test_moving_average(size, mode):
    assert np.allclose(dsp.moving_average(X[:5000], size, mode), ndimage.uniform_filter1d(X[:5000], size, mode=mode))


@pytest.mark.parametrize("n", [5000, 8192, 50_001])
def test_welch(n):
    f, p = signal.welch(X[:n], 44_100, nperseg=min(8192, n), scaling="spectrum")
    f2, p2 = dsp.welch_spectrum(X[:n], 44_100)
    assert (f == f2).all() and np.allclose(p, p2, rtol=1e-9)


def test_hann_and_upsample():
    assert np.allclose(dsp.hann(4096), signal.get_window("hann", 4096))
    st = rng.standard_normal((44_100, 2))
    assert np.allclose(dsp.upsample(st, 4), signal.resample_poly(st, 4, 1, axis=0), atol=1e-12)


@pytest.mark.parametrize("sr", [44_100, 48_000, 96_000])
def test_k_weighting(sr):
    st = rng.standard_normal((sr * 2, 2))
    b1, a1 = loudness._biquad_shelf(sr, 4.0, 1 / np.sqrt(2), 1500.0)
    b2, a2 = loudness._biquad_highpass(sr, 0.5, 38.0)
    ref = signal.lfilter(b2, a2, signal.lfilter(b1, a1, st, axis=0), axis=0)
    assert np.allclose(loudness.k_weight(st, sr), ref, atol=1e-10)
