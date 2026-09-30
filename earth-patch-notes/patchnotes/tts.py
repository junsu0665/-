"""edge-tts(무료 Microsoft 음성)로 한국어 내레이션을 만든다."""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from .config import Settings
from .utils import log, media_duration, run_ffmpeg


async def _save(text: str, dest: Path, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(str(dest))


def synthesize(settings: Settings, text: str, dest: Path, allow_silent_fallback: bool = False) -> float:
    """text 를 음성 파일로 저장하고 길이(초)를 돌려준다."""
    if not dest.exists():
        try:
            asyncio.run(_save(text, dest, settings.tts_voice, settings.tts_rate))
        except Exception as exc:
            dest.unlink(missing_ok=True)
            if not allow_silent_fallback:
                raise
            # 테스트용: 음성 서버에 못 붙으면 글자 수로 길이를 추정한 무음으로 대체
            seconds = max(2.0, len(text) * 0.1)
            log(f"  TTS 실패({type(exc).__name__}) → {seconds:.1f}초 무음으로 대체")
            run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(dest)])
    return media_duration(dest)
