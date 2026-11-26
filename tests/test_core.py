import shutil
import subprocess

import numpy as np
import pytest

from freethenoize.audio import compare, loudness, spectrum, tagging
from freethenoize.plugins.downloads import naming
from freethenoize.plugins.downloads.service import describe_quality

FFMPEG = shutil.which("ffmpeg")


@pytest.mark.parametrize("raw, clean", [
    ("Track Name [FREE DL]", "Track Name"),
    ("Track Name (Out Now!)", "Track Name"),
    ("Artist - Track | FREE DOWNLOAD", "Artist - Track"),
    ("Premiere: nothing to strip", "Premiere: nothing to strip"),
    ("Song (Original Mix) *Free Download*", "Song (Original Mix)"),
])
def test_clean_title(raw, clean):
    assert naming.clean_title(raw) == clean


def test_split_artist_title():
    assert naming.split_artist_title("DJ X - Tune", "uploader") == ("DJ X", "Tune")
    assert naming.split_artist_title("Just a tune", "uploader") == ("uploader", "Just a tune")


def test_render_template_is_safe():
    assert naming.render_template("{artist} - {title}", {"artist": "A/B", "title": 'x:"y"'}) == "A_B - x__y_"
    # Unknown fields or attribute access fall back to the default template.
    assert naming.render_template("{title.__class__}", {"artist": "A", "title": "T"}) == "A - T"
    assert naming.render_template("{index} - {title}", {"title": "T"}) == "T"
    assert naming.safe_filename("con") == "_con"


def test_describe_quality():
    assert describe_quality({"format_id": "download", "ext": "wav"})["lossless"] is True
    assert describe_quality({"format_id": "hls_aac_256k", "acodec": "mp4a.40.2", "abr": 256,
                             "format_note": "Premium"})["tier"] == "premium"
    assert describe_quality({"format_id": "http_mp3_0_0", "acodec": "mp3", "abr": 128})["label"] == "MP3 128k"
    assert describe_quality({"format_id": "hls_mp3_preview", "acodec": "mp3", "abr": 128})["preview"]


def test_loudness_reference_sine():
    # BS.1770: a 997 Hz sine at -20 dBFS peak in both channels reads ≈ -20 LUFS.
    sr = 48_000
    t = np.arange(sr * 10) / sr
    x = (10 ** (-20 / 20) * np.sin(2 * np.pi * 997 * t)).astype(np.float32)
    m = loudness.measure(np.stack([x, x], axis=1), sr)
    assert m["integrated_lufs"] == pytest.approx(-20.0, abs=0.2)
    assert m["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.1)


def test_cutoff_detects_lowpass():
    sr = 44_100
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(sr * 20).astype(np.float32) * 0.1
    from scipy import signal
    sos = signal.butter(16, 16_000, fs=sr, output="sos")
    lowpassed = signal.sosfilt(sos, noise).astype(np.float32)
    full = spectrum.detect_cutoff(noise, sr, lossless_container=True)
    cut = spectrum.detect_cutoff(lowpassed, sr, lossless_container=True)
    assert not full["sharp"] and full["level"] == "good"
    assert cut["sharp"] and 16_000 < cut["cutoff_hz"] < 18_500 and cut["level"] == "bad"


def test_null_test_aligns_and_matches_gain():
    sr = 44_100
    rng = np.random.default_rng(1)
    a = rng.standard_normal((sr * 5, 2)).astype(np.float32) * 0.1
    lag = 441  # 10 ms
    b = np.vstack([np.zeros((lag, 2), np.float32), a * 0.5])
    r = compare.null_test(a, b, sr)
    assert r["offset_ms"] == pytest.approx(-10.0, abs=0.05)
    assert r["gain_db"] == pytest.approx(6.02, abs=0.05)
    assert r["null_depth_db"] < -90


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("ext", ["mp3", "wav", "aiff", "flac", "m4a", "opus"])
def test_tag_roundtrip(tmp_path, ext):
    path = tmp_path / f"t.{ext}"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(path)], check=True)
    cover = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    meta = {"title": "Título", "artist": "Artista", "album": "Álbum", "date": "2024-05-01", "comment": "c"}
    assert tagging.write_tags(path, meta, cover)
    got, got_cover = tagging.read_tags(path)
    assert got["title"] == "Título" and got["artist"] == "Artista" and got["album"] == "Álbum"
    assert got_cover == cover


def _clicks(bpm: float, seconds: int = 30, sr: int = 44_100) -> np.ndarray:
    t = np.arange(sr * seconds) / sr
    x = np.zeros_like(t)
    n = int(0.08 * sr)
    for b in np.arange(0, seconds, 60 / bpm):
        i = int(b * sr)
        x[i:i + n] += np.sin(2 * np.pi * 60 * t[:n])[: len(x[i:i + n])] * np.exp(-t[:n] * 40)[: len(x[i:i + n])]
    return x.astype(np.float32)


@pytest.mark.parametrize("bpm", [90, 122.5, 128, 140, 174])
def test_bpm(bpm):
    from freethenoize.audio import musical
    assert musical.analyze(_clicks(bpm), 44_100)["bpm"] == pytest.approx(bpm, abs=0.3)


@pytest.mark.parametrize("hz", [40, 55, 110, 440])
def test_no_bpm_for_steady_tone(hz):
    from freethenoize.audio import musical
    t = np.arange(44_100 * 20) / 44_100
    assert musical.analyze(np.sin(2 * np.pi * hz * t).astype(np.float32), 44_100)["bpm"] is None


@pytest.mark.parametrize("name, camelot, chords", [
    ("C", "8B", [(0, 4, 7), (5, 9, 12), (7, 11, 14), (0, 4, 7)]),
    ("Am", "8A", [(9, 12, 16), (2, 5, 9), (4, 8, 11), (9, 12, 16)]),
    ("F#m", "11A", [(6, 9, 13), (11, 14, 18), (1, 5, 8), (6, 9, 13)]),
])
def test_key(name, camelot, chords):
    from freethenoize.audio import musical
    sr = 44_100
    tt = np.arange(sr * 2) / sr
    tone = lambda f: sum(np.sin(2 * np.pi * f * h * tt) / h for h in (1, 2, 3, 4))
    x = np.concatenate([sum(tone(220 * 2 ** ((n - 9) / 12)) for n in c) for c in chords * 6])
    r = musical.analyze(x.astype(np.float32), sr)
    assert (r["key"], r["camelot"]) == (name, camelot)


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("ext", ["mp3", "flac", "m4a", "aiff"])
def test_bpm_key_tags_roundtrip(tmp_path, ext):
    path = tmp_path / f"t.{ext}"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(path)], check=True)
    assert tagging.write_tags(path, {"title": "x", "bpm": 127.6, "key": "F#m"})
    got, _ = tagging.read_tags(path)
    assert got["bpm"] == "128" and got["key"] == "F#m"


def test_archive_key():
    from freethenoize.plugins.downloads.resolve import archive_key
    assert archive_key("Soundcloud", "123") == "soundcloud 123"
    assert archive_key(None, "123") is None


def test_update_version_compare_and_asset():
    from freethenoize import updates

    assert updates.version_tuple("v3.1.0") > updates.version_tuple("3.0.12") > updates.version_tuple("3.0.4")
    assert updates.version_tuple("3.0") == (3, 0, 0)
    assert updates.asset_name() is None or updates.asset_name().startswith("FreeTheNoize-")


def test_windowed_build_without_std_streams_starts(monkeypatch, tmp_path):
    """Double-click on Windows: no stdout/stderr. uvicorn must still configure logging."""
    import platformdirs
    import sys

    import uvicorn

    from freethenoize import runtime

    monkeypatch.setattr(platformdirs, "user_log_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(runtime, "_redirected", False)  # restored after the test
    runtime.ensure_std_streams()
    try:
        uvicorn.Config(lambda *a: None, log_level="warning", lifespan="off")
        print("hola")
    finally:
        sys.stdout.close()
    assert (tmp_path / "output.log").read_text(encoding="utf-8") == "hola\n"
    assert runtime.streams_redirected()


def test_single_desktop_instance(monkeypatch, tmp_path):
    """A second launch finds the first one and asks it to show its window."""
    import threading

    from freethenoize import instance

    monkeypatch.setattr(instance, "INFO_FILE", tmp_path / "instance.json")
    monkeypatch.setattr(instance, "_LOCK_FILE", tmp_path / "desktop.lock")
    monkeypatch.setattr(instance, "DATA_DIR", tmp_path)
    monkeypatch.setattr(instance, "_held", None)
    shown = threading.Event()

    assert instance.acquire()
    instance.serve(shown.set)
    held = instance._held
    try:
        # Same process: a new lock attempt sees the one already held.
        monkeypatch.setattr(instance, "_held", None)
        assert not instance.acquire()
        assert instance.show_running()
        assert shown.wait(2)
    finally:
        instance._held = held


def test_source_of_checks_the_real_hostname():
    from freethenoize.ytdlp import source_of

    assert source_of("https://soundcloud.com/a/b") == "soundcloud"
    assert source_of("https://m.soundcloud.com/a/b") == "soundcloud"
    assert source_of("https://on.soundcloud.com/x") == "soundcloud"
    assert source_of("https://snd.sc/x") == "soundcloud"
    assert source_of("https://www.youtube.com/watch?v=1") == "youtube"
    assert source_of("https://youtu.be/1") == "youtube"
    for trap in ("https://evil.com/?soundcloud.com", "https://soundcloud.com.evil.com/a",
                 "https://evilsoundcloud.com/a", "https://evil.com/soundcloud.com/a",
                 "https://notyoutube.com/watch", "https://youtube.com.evil.com/x",
                 "https://user@evil.com/soundcloud.com", "http://[::1/x", ""):
        assert source_of(trap) == "other", trap
