"""주제 선택 → 대본 → 음성 → Higgsfield 영상 → 합성 → 업로드 전체 흐름."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import render, script as script_mod, tts
from .config import Settings
from .higgsfield import make_generator
from .script import VideoScript
from .utils import log, media_duration


# ── 상태(버전·이력) ────────────────────────────────────────

def load_state(settings: Settings) -> dict:
    if settings.state_file.exists():
        return json.loads(settings.state_file.read_text(encoding="utf-8"))
    return {"videos": [], "pending": None}


def save_state(settings: Settings, state: dict) -> None:
    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    settings.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def next_version(state: dict) -> str:
    versions = [v["version"] for v in state["videos"]]
    if not versions:
        return "1.0.1"
    major, minor, patch = max(tuple(map(int, v.split("."))) for v in versions)
    return f"{major}.{minor}.{patch + 1}"


def next_topic(settings: Settings, state: dict) -> str:
    used = {v["topic"] for v in state["videos"]}
    if settings.topics_file.exists():
        for line in settings.topics_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line not in used:
                return line
    log("topics.txt 의 주제를 다 썼습니다 → Claude가 새 주제를 만듭니다")
    return script_mod.generate_topic(settings, [v["topic"] for v in state["videos"]])


# ── 제작 ──────────────────────────────────────────────────

def produce(settings: Settings, workdir: Path, script: VideoScript, version: str,
            placeholder: bool = False) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    final = workdir / "final.mp4"

    # 1) 내레이션 (마지막 장면에 outro 를 붙인다)
    log("음성 생성")
    texts = [script.intro_narration] + [s.narration for s in script.scenes]
    texts[-1] = f"{texts[-1]} {script.outro_narration}".strip()
    audio = [workdir / f"voice{i}.mp3" for i in range(len(texts))]
    durations = [tts.synthesize(settings, t, a, allow_silent_fallback=placeholder) for t, a in zip(texts, audio)]
    log("  길이: " + ", ".join(f"{d:.1f}s" for d in durations))

    # 2) Higgsfield 영상 (장면별 병렬)
    log("영상 생성 (Higgsfield)" if not placeholder else "영상 생성 (placeholder)")
    gen = make_generator(settings, workdir, placeholder)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(gen.scene_clip, i, scene, durations[i + 1] + render.TAIL_PAD, workdir)
            for i, scene in enumerate(script.scenes)
        ]
        clips = [f.result() for f in futures]

    # 3) 인트로 배경: 첫 장면 이미지 (없으면 첫 클립의 첫 프레임)
    first_still = workdir / "scene0.jpg"
    if not first_still.exists():
        render.extract_first_frame(clips[0], first_still)
    intro_bg = render.dim_background(first_still, workdir / "intro_bg.jpg", settings)
    card = render.render_intro_card(settings, version, script.patch_title, script.patch_lines,
                                    workdir / "intro_card.png")
    badge = render.render_badge(settings, version, workdir / "badge.png")

    # 4) 합성
    log("합성")
    segments = [render.Segment(intro_bg, audio[0], texts[0], is_image=True, card=card)]
    segments += [render.Segment(clip, audio[i + 1], texts[i + 1]) for i, clip in enumerate(clips)]
    parts = [render.render_segment(settings, seg, badge, workdir, f"part{i}") for i, seg in enumerate(segments)]
    render.concat_segments(settings, parts, final)
    log(f"완성: {final} ({media_duration(final):.1f}초)")
    return final


def run(settings: Settings, topic: str | None = None, version: str | None = None,
        script_path: Path | None = None, upload: bool = True, placeholder: bool = False,
        privacy: str | None = None, publish_at: str | None = None) -> dict:
    state = load_state(settings)
    pending = state.get("pending")

    if pending and not (topic or version or script_path or placeholder):
        log(f"중단된 작업 이어서: v{pending['version']} {pending['topic']}")
        version, topic = pending["version"], pending["topic"]
    else:
        version = version or next_version(state)
        topic = topic or (None if script_path else next_topic(settings, state))

    # placeholder 시험 결과는 따로 두고 이력(state)도 건드리지 않는다
    workdir = settings.output_dir / ("_placeholder" if placeholder else "") / f"v{version}"
    workdir.mkdir(parents=True, exist_ok=True)
    script_file = workdir / "script.json"

    if script_path:
        script = script_mod.load_script(script_path)
        topic = topic or script.topic
        script_mod.save_script(script, script_file)
    elif script_file.exists():
        script = script_mod.load_script(script_file)
    else:
        log(f"대본 작성 (Claude): v{version} — {topic}")
        script = script_mod.generate_script(settings, topic, version)
        script_mod.save_script(script, script_file)
    log(f"제목: {script.youtube_title}")

    if not placeholder:
        state["pending"] = {"version": version, "topic": topic, "dir": str(workdir)}
        save_state(settings, state)

    final = produce(settings, workdir, script, version, placeholder=placeholder)

    record = {
        "version": version,
        "topic": topic,
        "title": script.youtube_title,
        "file": str(final),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "youtube_id": None,
    }
    if upload and not placeholder:
        from . import youtube

        record["youtube_id"] = youtube.upload(settings, final, script, privacy, publish_at)
    elif upload:
        log("placeholder 모드라서 업로드는 건너뜁니다")

    if not placeholder:
        state["videos"].append(record)
        state["pending"] = None
        save_state(settings, state)
    return record


def upload_existing(settings: Settings, workdir: Path, privacy: str | None = None,
                    publish_at: str | None = None) -> str:
    """이미 만든 영상(output/vX.Y.Z)을 나중에 업로드."""
    from . import youtube

    script = script_mod.load_script(workdir / "script.json")
    video_id = youtube.upload(settings, workdir / "final.mp4", script, privacy, publish_at)
    state = load_state(settings)
    for rec in state["videos"]:
        if Path(rec["file"]).resolve() == (workdir / "final.mp4").resolve():
            rec["youtube_id"] = video_id
    save_state(settings, state)
    return video_id
