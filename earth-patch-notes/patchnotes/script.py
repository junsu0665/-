"""Claude로 '지구 패치노트' 대본을 만든다."""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
from pydantic import BaseModel

from .config import Settings


class Scene(BaseModel):
    narration: str
    """한국어 내레이션 1~2문장 (읽었을 때 4~9초)."""
    image_prompt: str
    """영어. 이 장면의 첫 프레임(세로 9:16) 묘사."""
    motion_prompt: str
    """영어. 첫 프레임에서 시작해 5~10초 동안 일어나는 움직임과 카메라 워크."""


class VideoScript(BaseModel):
    topic: str
    patch_title: str
    """패치 한 줄 요약. 예: '중력 10,000배 상향'"""
    patch_lines: list[str]
    """패치노트 항목 2~4개. 예: '[물리] 중력 가속도 9.8 → 98,000 m/s²'"""
    intro_narration: str
    scenes: list[Scene]
    outro_narration: str
    youtube_title: str
    youtube_description: str
    tags: list[str]


class TopicIdea(BaseModel):
    topic: str


SYSTEM_PROMPT = """\
너는 과학 유튜브 쇼츠 채널 '지구 패치노트'의 작가다.
컨셉: 지구가 게임이고, 개발자가 물리 법칙을 패치한다. 매 영상은
"지구 패치노트 1.0.x — <변경 사항>" 으로 시작해서, 그 변경이 실제 과학적으로
어떤 일을 일으키는지 시간 순서대로(0.001초 뒤 → 1초 뒤 → 1분 뒤 → 1년 뒤 …) 보여준다.

대본 규칙
- 전체 길이 45~58초짜리 세로 쇼츠. 장면(scenes)은 5~7개.
- intro_narration: "지구 패치노트 <버전>. <변경 사항>." 형태로 짧고 강하게. (예: "지구 패치노트 1.0.1. 중력이 만 배가 되었습니다.")
- 각 scene.narration 은 한국어 구어체 1~2문장, 소리 내 읽었을 때 4~9초. 숫자는 읽기 쉽게 한글로 풀어 써라 (예: "만 배", "초속 십일 킬로미터").
- 과학적으로 정확해야 한다. 물리량·수치는 실제 계산에 근거하고, 전제(무엇이 바뀌고 무엇이 그대로인지)를 일관되게 유지해라. 확실하지 않은 건 "~할 수도 있습니다"처럼 표현.
- 게임 패치노트 말투의 유머를 섞어라 (버그, 너프, 버프, 핫픽스, 롤백 등). 마지막 outro_narration 은 댓글을 유도하는 한 문장 (예: "롤백해야 할까요? 댓글로 투표해주세요.").
- patch_lines: 게임 패치노트처럼 짧은 항목 2~4개. 예: "[물리] 중력 가속도 9.8 → 98,000 m/s²", "[알려진 문제] 모든 생명체가 납작해짐".

영상 프롬프트 규칙 (Higgsfield 영상 생성용, 반드시 영어)
- image_prompt: 세로(9:16) 구도의 사실적·시네마틱한 한 장면. 조명, 렌즈, 분위기까지 구체적으로. 장면마다 스타일이 이어지도록 "cinematic, photorealistic, dramatic lighting, 35mm" 같은 공통 스타일을 유지.
- motion_prompt: 그 이미지에서 시작해 5~10초 동안 벌어지는 움직임과 카메라 워크 (예: "slow push-in as buildings collapse downward, dust billows").
- 화면 안에 글자·자막·로고를 넣지 마라 (자막은 후반 작업에서 넣는다).
- 실존 인물, 유혈·신체 훼손 묘사는 금지. 재난은 건물·지형·대기·바다·우주 스케일로 표현해라.

유튜브 메타데이터
- youtube_title: 100자 이내, 호기심을 끄는 제목 + " #shorts". 예: "지구 패치노트 1.0.1: 중력 10,000배 😱 #shorts"
- youtube_description: 3~6줄. 영상 요약, 핵심 과학 개념 설명 한두 줄, 해시태그 3~5개. 마지막 줄에 "※ 이 영상의 장면은 AI로 생성되었습니다."
- tags: 8~15개 (한국어 위주, 영어 몇 개).
"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _parse(settings: Settings, output_format, user_prompt: str, effort: str):
    response = _client().beta.messages.parse(
        model=settings.claude_model,
        max_tokens=16000,
        # 안전 분류기가 요청을 거절하면 서버에서 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=output_format,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude가 요청을 거절했습니다: {response.stop_details}")
    if response.parsed_output is None:
        raise RuntimeError(f"대본 JSON을 해석하지 못했습니다 (stop_reason={response.stop_reason})")
    return response.parsed_output


def generate_script(settings: Settings, topic: str, version: str) -> VideoScript:
    prompt = (
        f"패치 버전: {version}\n"
        f"변경 사항(주제): {topic}\n\n"
        "위 주제로 '지구 패치노트' 쇼츠 대본을 작성해줘."
    )
    script = _parse(settings, VideoScript, prompt, effort="high")
    script.topic = topic
    return script


def generate_topic(settings: Settings, used_topics: list[str]) -> str:
    used = "\n".join(f"- {t}" for t in used_topics[-80:]) or "(없음)"
    prompt = (
        "'지구 패치노트' 다음 영상 주제를 하나 제안해줘. 물리 상수·천체·화학·생물 규칙 중 하나를 "
        "극단적으로 바꾸는 '패치' 형태의 한 문장이어야 한다 (예: '중력이 10,000배가 되었습니다').\n"
        "과학적으로 흥미로운 연쇄 반응이 생기는 주제를 골라라.\n\n"
        f"이미 사용한 주제 (겹치지 말 것):\n{used}"
    )
    return _parse(settings, TopicIdea, prompt, effort="low").topic.strip()


def save_script(script: VideoScript, path: Path) -> None:
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")


def load_script(path: Path) -> VideoScript:
    return VideoScript.model_validate(json.loads(path.read_text(encoding="utf-8")))
