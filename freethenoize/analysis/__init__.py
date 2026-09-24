"""High-level analysis entry points used by the UI bridge."""
from pathlib import Path

import numpy as np

from . import compare, decode, loudness, spectrum

ANALYSIS_RATE_CAP = 96_000


def _rate(info: dict) -> int:
    return min(info.get("sample_rate") or 44_100, ANALYSIS_RATE_CAP)


def analyze(path: str | Path) -> dict:
    info = decode.probe(path)
    sr = _rate(info)
    stereo = decode.decode(path, sr, channels=2)
    mono = stereo.mean(axis=1)
    return {
        "info": info,
        "analysed_seconds": round(len(mono) / sr, 1),
        "truncated": (info.get("duration") or 0) > decode.MAX_SECONDS,
        "loudness": loudness.measure(stereo, sr),
        "cutoff": spectrum.detect_cutoff(mono, sr, info["lossless_container"]),
        "spectrogram": spectrum.spectrogram(mono, sr),
    }


def null_test(path_a: str | Path, path_b: str | Path) -> tuple[dict, np.ndarray, int]:
    """Returns (report, diff signal, sample rate)."""
    info_a, info_b = decode.probe(path_a), decode.probe(path_b)
    sr = max(_rate(info_a), _rate(info_b))
    a = decode.decode(path_a, sr, channels=2)
    b = decode.decode(path_b, sr, channels=2)
    report = compare.null_test(a, b, sr)
    diff = report.pop("diff")
    report["spectrogram"] = spectrum.spectrogram(diff.mean(axis=1), sr)
    return report, diff, sr
