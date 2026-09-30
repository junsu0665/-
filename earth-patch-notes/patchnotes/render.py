"""자막·패치노트 카드를 그리고 ffmpeg로 세로 쇼츠(1080x1920)를 합성한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import Settings
from .utils import find_font, media_duration, run_ffmpeg

ACCENT = (0, 229, 255)      # 시안 (게임 UI 느낌)
WARN = (255, 196, 0)        # 앰버
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TAIL_PAD = 0.3              # 장면 끝 여유(초)


@dataclass
class Segment:
    visual: Path            # 영상(mp4) 또는 정지 이미지
    audio: Path
    narration: str
    is_image: bool = False
    card: Path | None = None  # 인트로 패치노트 카드


# ── 글자 그리기 ─────────────────────────────────────────────

def _font(settings: Settings, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(find_font(settings.font_path), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        # 공백 없이 너무 긴 줄은 글자 단위로 자른다
        while draw.textlength(line, font=font) > max_width and len(line) > 1:
            cut = len(line)
            while cut > 1 and draw.textlength(line[:cut], font=font) > max_width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
        lines.append(line)
    return lines


def split_captions(text: str, max_chars: int = 16) -> list[str]:
    """내레이션을 화면에 한 번에 보여줄 자막 조각으로 나눈다."""
    chunks: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        chunk = ""
        for word in sentence.split():
            if chunk and len(chunk) + 1 + len(word) > max_chars:
                chunks.append(chunk)
                chunk = word
            else:
                chunk = f"{chunk} {word}".strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [text]


def render_caption(settings: Settings, text: str, dest: Path) -> Path:
    W, H = settings.width, settings.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(settings, 84)
    lines = _wrap(draw, text.rstrip("."), font, 900)[:3]
    line_h = 104
    y = 1240 - (len(lines) * line_h) // 2   # 쇼츠 하단 UI를 피한 위치
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, font=font, fill=WHITE, stroke_width=9, stroke_fill=BLACK)
        y += line_h
    img.save(dest)
    return dest


def render_badge(settings: Settings, version: str, dest: Path) -> Path:
    W, H = settings.width, settings.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(settings, 44)
    label = f"EARTH PATCH v{version}"
    tw = draw.textlength(label, font=font)
    x0, y0 = (W - tw) / 2 - 34, 170
    draw.rounded_rectangle((x0, y0, x0 + tw + 68, y0 + 78), radius=18, fill=(10, 14, 22, 200),
                           outline=ACCENT + (255,), width=3)
    draw.text((x0 + 34, y0 + 14), label, font=font, fill=ACCENT)
    img.save(dest)
    return dest


def render_intro_card(settings: Settings, version: str, title: str, lines: list[str],
                      dest: Path) -> Path:
    """게임 패치노트 스타일 카드 (투명 배경)."""
    W, H = settings.width, settings.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    px0, px1 = 70, W - 70
    inner = px1 - px0 - 100

    f_small = _font(settings, 40)
    f_head = _font(settings, 76)
    f_ver = _font(settings, 150)
    f_title = _font(settings, 84)
    f_line = _font(settings, 46)

    title_lines = _wrap(draw, title, f_title, inner)
    body = [(ln, j == 0) for item in lines for j, ln in enumerate(_wrap(draw, item, f_line, inner - 36))]
    panel_h = 90 + 60 + 90 + 170 + 50 + len(title_lines) * 100 + 40 + len(body) * 64 + 90
    py0 = max(260, (H - panel_h) // 2 - 80)
    py1 = py0 + panel_h

    draw.rounded_rectangle((px0, py0, px1, py1), radius=28, fill=(8, 12, 20, 225),
                           outline=ACCENT + (255,), width=5)
    draw.rectangle((px0 + 5, py0 + 5, px1 - 5, py0 + 16), fill=ACCENT + (255,))

    x, y = px0 + 50, py0 + 70
    draw.text((x, y), "SYSTEM UPDATE · PLANET EARTH", font=f_small, fill=(150, 170, 190))
    y += 60
    draw.text((x, y), "PATCH NOTES", font=f_head, fill=WHITE)
    y += 90
    draw.text((x, y), f"v{version}", font=f_ver, fill=ACCENT)
    y += 170
    draw.line((x, y, px1 - 50, y), fill=(60, 80, 100), width=3)
    y += 40
    for ln in title_lines:
        draw.text((x, y), ln, font=f_title, fill=WARN)
        y += 100
    y += 30
    for ln, first in body:
        if first:  # 글꼴에 따라 '•' 글리프가 없어서 도형으로 그린다
            draw.rectangle((x, y + 24, x + 14, y + 38), fill=ACCENT + (255,))
        draw.text((x + 36, y), ln, font=f_line, fill=(220, 230, 240))
        y += 64
    img.save(dest)
    return dest


def dim_background(src: Path, dest: Path, settings: Settings) -> Path:
    W, H = settings.width, settings.height
    img = Image.open(src).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(6))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    img.save(dest, quality=92)
    return dest


def extract_first_frame(video: Path, dest: Path) -> Path:
    run_ffmpeg(["-i", str(video), "-frames:v", "1", "-q:v", "2", str(dest)])
    return dest


# ── ffmpeg 합성 ────────────────────────────────────────────

def render_segment(settings: Settings, seg: Segment, badge: Path, workdir: Path, name: str) -> Path:
    W, H, fps = settings.width, settings.height, settings.fps
    audio_dur = media_duration(seg.audio)
    dur = audio_dur + TAIL_PAD
    out = workdir / f"{name}.mp4"

    inputs: list[str] = []
    if seg.is_image:
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(seg.visual)]
    else:
        inputs += ["-i", str(seg.visual)]
    inputs += ["-i", str(seg.audio)]
    inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(badge)]

    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}"
    if seg.is_image:
        frames = int(dur * fps) + 1
        base = (f"[0:v]scale={W * 2}:{H * 2},zoompan=z='min(zoom+0.0007,1.12)':d={frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},setsar=1")
    else:
        # 생성된 클립이 내레이션보다 짧으면 최대 1.3배까지 느리게 재생하고, 남으면 마지막 프레임으로 채운다
        stretch = min(max(dur / media_duration(seg.visual), 1.0), 1.3)
        base = f"[0:v]setpts={stretch:.4f}*PTS,{fit},tpad=stop_mode=clone:stop_duration={dur:.3f}"
    filters = [f"{base},trim=duration={dur:.3f},setpts=PTS-STARTPTS[v0]"]
    last = "v0"
    idx = 3

    if seg.card is not None:
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(seg.card)]
        filters.append(f"[{idx}:v]format=rgba,fade=in:st=0.15:d=0.45:alpha=1[card]")
        filters.append(f"[{last}][card]overlay=0:0[v{idx}]")
        last = f"v{idx}"
        idx += 1
    else:
        filters.append(f"[{last}][2:v]overlay=0:0[vb]")
        last = "vb"
        # 자막: 글자 수 비율로 시간 배분
        chunks = split_captions(seg.narration)
        total_chars = sum(len(c) for c in chunks)
        t = 0.0
        for i, chunk in enumerate(chunks):
            span = audio_dur * len(chunk) / total_chars
            start, end = t, (dur if i == len(chunks) - 1 else t + span)
            png = render_caption(settings, chunk, workdir / f"{name}_cap{i}.png")
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(png)]
            filters.append(f"[{last}][{idx}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[v{idx}]")
            last = f"v{idx}"
            idx += 1
            t += span

    filters.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur:.3f}[a]")
    run_ffmpeg([
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{last}]", "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ])
    return out


def concat_segments(settings: Settings, segments: list[Path], dest: Path) -> Path:
    inputs: list[str] = []
    for seg in segments:
        inputs += ["-i", str(seg)]
    n = len(segments)
    total = sum(media_duration(s) for s in segments)
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    filters = [f"{streams}concat=n={n}:v=1:a=1[v][voice]"]

    if settings.bgm_path.exists():
        inputs += ["-stream_loop", "-1", "-i", str(settings.bgm_path)]
        filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,"
                       f"volume={settings.bgm_volume},atrim=0:{total:.3f}[bgm]")
        filters.append("[voice][bgm]amix=inputs=2:duration=first:normalize=0[mix]")
        audio = "mix"
    else:
        audio = "voice"
    filters.append(f"[{audio}]afade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6[aout]")

    run_ffmpeg([
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(dest),
    ])
    return dest
