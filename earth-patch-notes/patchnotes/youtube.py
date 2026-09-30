"""YouTube Data API v3 업로드."""

from __future__ import annotations

import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import Settings
from .script import VideoScript
from .utils import log

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def authorize(settings: Settings, headless: bool = False) -> Credentials:
    """최초 1회 브라우저로 로그인해서 토큰을 저장한다."""
    if not settings.yt_client_secrets.exists():
        raise FileNotFoundError(
            f"{settings.yt_client_secrets} 가 없습니다. Google Cloud Console에서 "
            "'데스크톱 앱' OAuth 클라이언트를 만들고 JSON을 이 경로에 저장하세요."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.yt_client_secrets), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=not headless)
    settings.yt_token_file.write_text(creds.to_json())
    log(f"YouTube 토큰 저장: {settings.yt_token_file}")
    return creds


def _credentials(settings: Settings) -> Credentials:
    if not settings.yt_token_file.exists():
        raise FileNotFoundError(
            f"{settings.yt_token_file} 가 없습니다. 먼저 `python -m patchnotes auth` 를 실행하세요."
        )
    creds = Credentials.from_authorized_user_file(str(settings.yt_token_file), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        settings.yt_token_file.write_text(creds.to_json())
    return creds


def upload(settings: Settings, video: Path, script: VideoScript, privacy: str | None = None,
           publish_at: str | None = None) -> str:
    youtube = build("youtube", "v3", credentials=_credentials(settings), cache_discovery=False)
    privacy = privacy or settings.yt_privacy
    status = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
        # AI로 만든 사실적인 장면이므로 '변경/합성 콘텐츠'로 표시 (YouTube 정책)
        "containsSyntheticMedia": True,
    }
    if publish_at:
        status["publishAt"] = publish_at  # 예: 2026-10-01T09:00:00+09:00
    body = {
        "snippet": {
            "title": script.youtube_title[:100],
            "description": script.youtube_description[:5000],
            "tags": script.tags[:30],
            "categoryId": settings.yt_category_id,
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": status,
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retries = 0
    while response is None:
        try:
            progress, response = request.next_chunk()
            if progress:
                log(f"  업로드 {int(progress.progress() * 100)}%")
        except HttpError as exc:
            if exc.resp.status not in (500, 502, 503, 504) or retries >= 5:
                raise
            retries += 1
            time.sleep(2 ** retries)
    video_id = response["id"]
    log(f"업로드 완료: https://youtube.com/shorts/{video_id} ({status['privacyStatus']})")
    return video_id
