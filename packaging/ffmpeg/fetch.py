"""Download the pinned audio-only ffmpeg for this platform and check its hash.

    python packaging/ffmpeg/fetch.py <dest-dir>     → prints the path

Exit 3 (and prints why) when assets.txt pins no build for this platform yet:
callers then fall back to another ffmpeg (imageio-ffmpeg, apt).
Standard library only: runs in CI and inside the Docker build.
"""
import hashlib
import os
import platform
import stat
import sys
import urllib.request
from pathlib import Path

REPO = "FreeTheNoize/FreeTheNoize"
HERE = Path(__file__).resolve().parent


def asset_name() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "darwin":
        return f"ffmpeg-macos-{arch}"
    if sys.platform == "win32":
        return "ffmpeg-windows-x86_64.exe"
    return f"ffmpeg-linux-{arch}"


def pinned() -> tuple[str | None, dict[str, str]]:
    tag, sums = None, {}
    for line in (HERE / "assets.txt").read_text().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "tag":
            tag = parts[1]
        elif len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return tag, sums


def main(dest: str) -> int:
    name = asset_name()
    tag, sums = pinned()
    if not tag or name not in sums:
        print(f"no pinned {name} in packaging/ffmpeg/assets.txt", file=sys.stderr)
        return 3
    url = os.environ.get("FTN_FFMPEG_BASE_URL", f"https://github.com/{REPO}/releases/download/{tag}") + f"/{name}"
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sums[name]:
        print(f"{name}: sha256 {digest} does not match assets.txt", file=sys.stderr)
        return 1
    out = Path(dest) / ("ffmpeg.exe" if name.endswith(".exe") else "ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
