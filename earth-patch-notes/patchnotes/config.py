"""환경변수(.env) 기반 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def _hf_credentials() -> tuple[str, str]:
    key, secret = _env("HF_API_KEY"), _env("HF_API_SECRET")
    if not (key and secret) and ":" in _env("HF_KEY"):
        key, secret = _env("HF_KEY").split(":", 1)
    return key, secret


@dataclass
class Settings:
    root: Path = ROOT
    output_dir: Path = field(default_factory=lambda: Path(_env("OUTPUT_DIR", str(ROOT / "output"))))
    state_file: Path = field(default_factory=lambda: Path(_env("STATE_FILE", str(ROOT / "state" / "history.json"))))
    topics_file: Path = field(default_factory=lambda: Path(_env("TOPICS_FILE", str(ROOT / "topics.txt"))))
    channel_name: str = field(default_factory=lambda: _env("CHANNEL_NAME", "지구 패치노트"))

    # Claude
    claude_model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-opus-5-5"))

    # Higgsfield
    hf_api_base: str = field(default_factory=lambda: _env("HF_API_BASE", "https://api.higgsfield.ai"))
    hf_key: str = field(default_factory=lambda: _hf_credentials()[0])
    hf_secret: str = field(default_factory=lambda: _hf_credentials()[1])
    hf_mode: str = field(default_factory=lambda: _env("HF_MODE", "image-to-video"))
    hf_image_model: str = field(default_factory=lambda: _env("HF_IMAGE_MODEL", "higgsfield-ai/soul/standard"))
    hf_video_model: str = field(
        default_factory=lambda: _env("HF_VIDEO_MODEL", "kling-video/v2.5-turbo/pro/image-to-video")
    )
    hf_t2v_model: str = field(
        default_factory=lambda: _env("HF_T2V_MODEL", "kling-video/v2.5-turbo/pro/text-to-video")
    )
    hf_video_durations: list[int] = field(
        default_factory=lambda: sorted(int(x) for x in _env("HF_VIDEO_DURATIONS", "5,10").split(","))
    )
    hf_timeout_sec: int = field(default_factory=lambda: int(_env("HF_TIMEOUT_SEC", "1800")))

    # TTS
    tts_voice: str = field(default_factory=lambda: _env("TTS_VOICE", "ko-KR-InJoonNeural"))
    tts_rate: str = field(default_factory=lambda: _env("TTS_RATE", "+12%"))

    # Render
    width: int = 1080
    height: int = 1920
    fps: int = 30
    font_path: str = field(default_factory=lambda: _env("FONT_PATH"))
    bgm_path: Path = field(default_factory=lambda: Path(_env("BGM_PATH", str(ROOT / "assets" / "bgm.mp3"))))
    bgm_volume: float = field(default_factory=lambda: float(_env("BGM_VOLUME", "0.12")))

    # YouTube
    yt_client_secrets: Path = field(
        default_factory=lambda: Path(_env("YT_CLIENT_SECRETS", str(ROOT / "client_secret.json")))
    )
    yt_token_file: Path = field(
        default_factory=lambda: Path(_env("YT_TOKEN_FILE", str(ROOT / "youtube_token.json")))
    )
    yt_privacy: str = field(default_factory=lambda: _env("YT_PRIVACY", "private"))
    yt_category_id: str = field(default_factory=lambda: _env("YT_CATEGORY_ID", "28"))  # 과학기술
