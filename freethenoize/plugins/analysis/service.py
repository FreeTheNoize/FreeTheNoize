from pathlib import Path

from ... import audio


class Analysis:
    def __init__(self, ctx):
        self.ctx = ctx

    def analyze(self, path: Path) -> dict:
        result = audio.analyze(path)
        result["audio_url"] = self.ctx.playable_url(path)
        return result

    def null_test(self, a: Path, b: Path) -> dict:
        report, diff, sr = audio.null_test(a, b)
        report["audio_url"] = self.ctx.samples_url(diff, sr)
        return report
