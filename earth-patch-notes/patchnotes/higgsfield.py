"""Higgsfield API로 장면별 영상 클립을 생성·다운로드한다.

API 흐름 (https://docs.higgsfield.ai):
  POST {base}/{model_path}              → {request_id, status_url, ...}
  GET  {base}/requests/{id}/status      → {status: queued|in_progress|completed|failed|nsfw|canceled,
                                           images:[{url}], video:{url}}

요청 ID는 작업 폴더의 hf_requests.json 에 저장된다. 중간에 끊겨도 다시 실행하면
새로 과금되는 요청을 보내지 않고 기존 요청의 결과를 이어서 받아온다.
"""

from __future__ import annotations

import json
import random
import subprocess
import threading
import time
from pathlib import Path

import requests

from .config import Settings
from .script import Scene
from .utils import ffmpeg_exe, log

TERMINAL_FAIL = {"failed", "nsfw", "canceled", "cancelled"}


class HiggsfieldError(RuntimeError):
    pass


class HiggsfieldClient:
    def __init__(self, settings: Settings):
        if not (settings.hf_key and settings.hf_secret):
            raise HiggsfieldError(
                "Higgsfield 인증 정보가 없습니다. .env 에 HF_API_KEY / HF_API_SECRET 을 설정하세요."
            )
        self.base = settings.hf_api_base.rstrip("/")
        self.timeout_sec = settings.hf_timeout_sec
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Key {settings.hf_key}:{settings.hf_secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def submit(self, model_path: str, payload: dict) -> str:
        url = f"{self.base}/{model_path.strip('/')}"
        # 서버가 명시적으로 429/5xx를 돌려준 경우만 재시도한다.
        # 연결 끊김 같은 애매한 실패는 중복 과금 위험이 있어 재시도하지 않는다.
        for attempt in range(5):
            resp = self.session.post(url, json=payload, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = min(60, 2 ** (attempt + 1)) + random.random()
                log(f"  Higgsfield {resp.status_code}, {wait:.0f}초 후 재시도")
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                raise HiggsfieldError(f"POST {model_path} 실패 ({resp.status_code}): {resp.text[:500]}")
            return resp.json()["request_id"]
        raise HiggsfieldError(f"POST {model_path}: 재시도 한도 초과")

    def wait(self, request_id: str) -> dict:
        url = f"{self.base}/requests/{request_id}/status"
        deadline = time.monotonic() + self.timeout_sec
        delay = 3.0
        while time.monotonic() < deadline:
            try:
                resp = self.session.get(url, timeout=30)
            except requests.RequestException as exc:
                log(f"  상태 조회 오류 ({exc}), 재시도")
                resp = None
            if resp is not None and resp.status_code < 500 and resp.status_code != 429:
                if resp.status_code >= 400:
                    raise HiggsfieldError(f"상태 조회 실패 ({resp.status_code}): {resp.text[:500]}")
                data = resp.json()
                status = str(data.get("status", "")).lower()
                if status == "completed":
                    return data
                if status in TERMINAL_FAIL:
                    raise HiggsfieldError(f"요청 {request_id} 실패: status={status} error={data.get('error')}")
            time.sleep(delay + random.random())
            delay = min(delay * 1.5, 20.0)
        raise HiggsfieldError(f"요청 {request_id} 시간 초과 ({self.timeout_sec}초)")

    def download(self, url: str, dest: Path) -> Path:
        tmp = dest.with_suffix(dest.suffix + ".part")
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
        tmp.replace(dest)
        return dest


class _RequestLedger:
    """장면별 요청 ID를 파일에 기록 (이어받기용)."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key: str) -> str | None:
        with self.lock:
            return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        with self.lock:
            self.data[key] = value
            self.path.write_text(json.dumps(self.data, indent=2))

    def drop(self, key: str) -> None:
        with self.lock:
            self.data.pop(key, None)
            self.path.write_text(json.dumps(self.data, indent=2))


def pick_duration(allowed: list[int], needed_sec: float) -> int:
    for d in allowed:
        if d >= needed_sec:
            return d
    return allowed[-1]


class HiggsfieldGenerator:
    def __init__(self, settings: Settings, workdir: Path):
        self.s = settings
        self.client = HiggsfieldClient(settings)
        self.ledger = _RequestLedger(workdir / "hf_requests.json")

    def _run(self, key: str, model_path: str, payload: dict) -> dict:
        request_id = self.ledger.get(key)
        if request_id:
            log(f"  [{key}] 기존 요청 이어받기 {request_id}")
        else:
            request_id = self.client.submit(model_path, payload)
            self.ledger.set(key, request_id)
            log(f"  [{key}] 요청 제출 {request_id}")
        try:
            return self.client.wait(request_id)
        except HiggsfieldError:
            # 실패한 요청은 기록에서 지워 다음 실행 때 새로 요청하게 한다.
            self.ledger.drop(key)
            raise

    def still_image(self, idx: int, scene: Scene, dest: Path) -> Path:
        """장면의 첫 프레임(9:16) 이미지. 인트로 배경·썸네일에도 쓴다."""
        if dest.exists():
            return dest
        result = self._run(
            f"scene{idx}.image",
            self.s.hf_image_model,
            {"prompt": scene.image_prompt, "aspect_ratio": "9:16", "resolution": "2K", "num_images": 1},
        )
        return self.client.download(result["images"][0]["url"], dest)

    def scene_clip(self, idx: int, scene: Scene, needed_sec: float, workdir: Path) -> Path:
        dest = workdir / f"scene{idx}.mp4"
        if dest.exists():
            return dest
        duration = pick_duration(self.s.hf_video_durations, needed_sec)
        if self.s.hf_mode == "text-to-video":
            payload = {"prompt": f"{scene.image_prompt}. {scene.motion_prompt}", "duration": duration}
            result = self._run(f"scene{idx}.video", self.s.hf_t2v_model, payload)
        else:
            image = self.still_image(idx, scene, workdir / f"scene{idx}.jpg")
            image_url = self._image_url(idx, image)
            payload = {"prompt": scene.motion_prompt, "image_url": image_url, "duration": duration}
            result = self._run(f"scene{idx}.video", self.s.hf_video_model, payload)
        return self.client.download(result["video"]["url"], dest)

    def _image_url(self, idx: int, image: Path) -> str:
        # Soul 결과 URL은 최소 7일 유지되므로 그대로 재사용한다.
        request_id = self.ledger.get(f"scene{idx}.image")
        if request_id:
            return self.client.wait(request_id)["images"][0]["url"]
        raise HiggsfieldError(f"scene{idx} 이미지 URL을 찾을 수 없습니다 ({image})")


class PlaceholderGenerator:
    """API 비용 없이 파이프라인을 시험하기 위한 가짜 클립 생성기 (--placeholder)."""

    PALETTE = ["0x1d3557", "0x6a040f", "0x283618", "0x3c096c", "0x7f5539", "0x023e8a", "0x9d0208"]

    def __init__(self, settings: Settings, workdir: Path):
        self.s = settings

    def still_image(self, idx: int, scene: Scene, dest: Path) -> Path:
        if not dest.exists():
            color = self.PALETTE[idx % len(self.PALETTE)]
            subprocess.run(
                [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                 "-i", f"gradients=s=1080x1920:c0={color}:c1=black:x0=0:y0=0:x1=1080:y1=1920",
                 "-frames:v", "1", str(dest)],
                check=True,
            )
        return dest

    def scene_clip(self, idx: int, scene: Scene, needed_sec: float, workdir: Path) -> Path:
        dest = workdir / f"scene{idx}.mp4"
        if dest.exists():
            return dest
        duration = pick_duration(self.s.hf_video_durations, needed_sec)
        color = self.PALETTE[idx % len(self.PALETTE)]
        subprocess.run(
            [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"gradients=s=720x1280:c0={color}:c1=black:speed=0.02:d={duration}",
             "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)],
            check=True,
        )
        return dest


def make_generator(settings: Settings, workdir: Path, placeholder: bool):
    return PlaceholderGenerator(settings, workdir) if placeholder else HiggsfieldGenerator(settings, workdir)
