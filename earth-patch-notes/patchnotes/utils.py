from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
FONT_CACHE = ROOT / "assets" / "fonts"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf"
SYSTEM_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/NanumGothicBold.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode})")


def media_duration(path: Path) -> float:
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        raise RuntimeError(f"길이를 읽을 수 없습니다: {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


@lru_cache(maxsize=1)
def find_font(configured: str = "") -> str:
    """한글 굵은 글꼴 경로. FONT_PATH → assets/fonts → 다운로드 → 시스템 글꼴 순."""
    if configured and Path(configured).exists():
        return configured
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    local = sorted(p for p in FONT_CACHE.iterdir() if p.suffix.lower() in {".ttf", ".otf", ".ttc"})
    if local:
        return str(local[0])
    dest = FONT_CACHE / "BlackHanSans-Regular.ttf"
    try:
        urllib.request.urlretrieve(FONT_URL, dest)
        return str(dest)
    except Exception:
        dest.unlink(missing_ok=True)
    for path in SYSTEM_FONTS:
        if Path(path).exists():
            return path
    raise RuntimeError("한글 글꼴을 찾지 못했습니다. .env 의 FONT_PATH 에 .ttf 경로를 지정하세요.")
