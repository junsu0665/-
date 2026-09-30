# 🌍 지구 패치노트 — 과학 쇼츠 자동 제작·업로드

> **지구 패치노트 1.0.1 — 중력이 10,000배가 되었습니다.**
> 0.01초 뒤, 0.1초 뒤, 몇 분 뒤… 실제 물리로 계산한 결과를 AI 영상으로 보여주는 유튜브 쇼츠를
> 명령어 한 줄로 만들고 업로드합니다.

```
topics.txt ─▶ Claude (대본·과학 검증·영상 프롬프트·제목/설명/태그)
                 │
                 ├─▶ edge-tts (한국어 내레이션)
                 └─▶ Higgsfield (장면별 Soul 9:16 이미지 → Kling 영상, 병렬 생성)
                          │
                          ▼
             ffmpeg 합성 (패치노트 인트로 카드 + 버전 배지 + 자막 + BGM)
                          │
                          ▼
                 YouTube 업로드 (AI 생성 콘텐츠 표시, 기본 비공개)
```

결과물: 1080×1920 세로 쇼츠, 약 45~60초, `output/v1.0.1/final.mp4`

---

## 1. 설치

```bash
cd earth-patch-notes
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # 그리고 .env 에 키 입력
```

ffmpeg는 `imageio-ffmpeg` 가 자동으로 받아오므로 따로 설치하지 않아도 됩니다.
한글 자막 글꼴(Black Han Sans)도 첫 실행 때 자동으로 받습니다. 다른 글꼴을 쓰려면 `.env` 의 `FONT_PATH` 를 지정하세요.

## 2. 필요한 키

| 무엇 | 어디서 | `.env` |
|---|---|---|
| Claude API 키 (대본) | https://console.anthropic.com | `ANTHROPIC_API_KEY` |
| Higgsfield API 키 (영상) | https://cloud.higgsfield.ai → API Keys | `HF_API_KEY`, `HF_API_SECRET` |
| YouTube 업로드 권한 | 아래 3번 참고 | `client_secret.json` 파일 |

## 3. YouTube 연결 (최초 1회)

1. [Google Cloud Console](https://console.cloud.google.com) 에서 프로젝트 생성
2. **API 및 서비스 → 라이브러리** 에서 **YouTube Data API v3** 사용 설정
3. **OAuth 동의 화면** 설정 → 테스트 사용자에 본인 계정 추가
   (계속 자동으로 돌릴 거면 **"프로덕션으로 게시"** 해야 토큰이 7일 만에 만료되지 않습니다)
4. **사용자 인증 정보 → OAuth 클라이언트 ID → 데스크톱 앱** 생성 → JSON 다운로드 → `client_secret.json` 으로 저장
5. 로그인:
   ```bash
   python -m patchnotes auth
   ```
   브라우저에서 채널 계정으로 로그인하면 `youtube_token.json` 이 생깁니다.

> ⚠️ Google 감사(audit)를 받지 않은 API 프로젝트로 올린 영상은 **비공개로 잠깁니다.**
> 공개 업로드까지 자동화하려면 [YouTube API 감사 신청](https://support.google.com/youtube/contact/yt_api_form)이 필요합니다.
> 그 전까지는 비공개로 올라간 영상을 YouTube Studio에서 확인하고 직접 공개로 바꾸면 됩니다.

## 4. 사용법

```bash
# ① 돈 안 드는 시험: 예제 대본 + 가짜 클립으로 전체 흐름 확인 (업로드 안 함)
python -m patchnotes run --script examples/gravity-10000x.json --placeholder

# ② 대본만 뽑아보기 (Claude만 사용)
python -m patchnotes script --topic "중력이 10,000배가 되었습니다"

# ③ 진짜로 만들기 (업로드는 아직 안 함)
python -m patchnotes run --topic "중력이 10,000배가 되었습니다" --no-upload

# ④ 만들어 둔 영상 업로드
python -m patchnotes upload output/v1.0.1 --privacy private

# ⑤ 한 번에: topics.txt 다음 주제로 제작 + 업로드
python -m patchnotes run

# 예약 공개
python -m patchnotes run --publish-at 2026-10-01T18:00:00+09:00
```

- **버전 번호**는 자동으로 올라갑니다 (1.0.1 → 1.0.2 → …). 이력은 `state/history.json`.
- **주제**는 `topics.txt` 에서 위부터 하나씩 씁니다. 다 쓰면 Claude가 겹치지 않는 새 주제를 만듭니다.
- **중간에 끊겨도** 다시 `run` 하면 이어서 합니다. Higgsfield 요청 ID를 `output/vX/hf_requests.json` 에
  저장해 두기 때문에 같은 장면을 두 번 결제하지 않습니다.
- `assets/bgm.mp3` 를 넣어두면 배경음악으로 깔립니다 (음량은 `BGM_VOLUME`).
  저작권 문제 없는 음원(YouTube 오디오 라이브러리 등)을 쓰세요.

## 5. 매일 자동 업로드 (GitHub Actions)

`.github/workflows/earth-patch-notes.yml` 이 들어 있습니다.

1. 저장소 **Settings → Secrets and variables → Actions → Secrets** 에 추가
   - `ANTHROPIC_API_KEY`, `HF_API_KEY`, `HF_API_SECRET`
   - `YT_TOKEN_JSON` — 로컬에서 `auth` 로 만든 `youtube_token.json` 파일 내용 전체
2. **Variables** 에 `PATCHNOTES_AUTO` = `true` → 매일 18:07(KST)에 1편 제작·업로드
   (`YT_PRIVACY` 변수로 공개 설정 변경 가능, 기본 `private`)
3. **Actions 탭 → 지구 패치노트 자동 업로드 → Run workflow** 로 주제를 지정해 수동 실행도 됩니다.

완성된 mp4는 실행 결과의 Artifacts에서 7일간 받을 수 있고, 버전 이력은 자동으로 커밋됩니다.

로컬 PC에서 돌리고 싶다면 cron(맥/리눅스) 이나 작업 스케줄러(윈도우)에
`cd /경로/earth-patch-notes && .venv/bin/python -m patchnotes run` 을 등록하면 됩니다.

## 6. 설정 바꾸기 (`.env`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HF_MODE` | `image-to-video` | `text-to-video` 로 바꾸면 이미지 단계 없이 바로 영상 생성 (가로 영상은 가운데를 잘라 세로로) |
| `HF_IMAGE_MODEL` | `higgsfield-ai/soul/standard` | 첫 프레임 이미지 모델 |
| `HF_VIDEO_MODEL` | `kling-video/v2.5-turbo/pro/image-to-video` | 예: `kling-video/v2.5-turbo/standard/image-to-video` (더 저렴), `minimax/hailuo-2.3/standard/image-to-video` |
| `HF_VIDEO_DURATIONS` | `5,10` | 모델이 허용하는 클립 길이. Hailuo 는 `6,10` |
| `TTS_VOICE` | `ko-KR-InJoonNeural` | 여성 음성: `ko-KR-SunHiNeural` |
| `TTS_RATE` | `+12%` | 말하기 속도 |
| `CLAUDE_MODEL` | `claude-opus-5-5` | 대본 작성 모델 |
| `YT_PRIVACY` | `private` | `unlisted` / `public` |

대본 스타일(말투, 길이, 과학 검증 규칙, 영상 프롬프트 규칙)은 `patchnotes/script.py` 의 `SYSTEM_PROMPT` 에서 고치면 됩니다.

## 7. 비용·주의사항

- **Higgsfield**: 영상 1편 = 장면 6개 × (이미지 1장 + 영상 클립 1개). 내레이션이 5초를 넘는 장면은 10초 클립으로
  요청하므로 크레딧이 더 듭니다. 장면을 짧게 쓰거나 `standard` 모델을 쓰면 절약됩니다. 요금은 Higgsfield 콘솔에서 확인하세요.
- **Claude**: 1편당 요청 1~2번.
- **edge-tts**: 무료이지만 Microsoft의 비공식 엔드포인트라 막힐 수 있습니다. 필요하면 `patchnotes/tts.py` 만 다른 TTS로 바꾸면 됩니다.
- **YouTube 정책**: 업로드 시 "변경되었거나 합성된 콘텐츠"(`containsSyntheticMedia`)로 자동 표시합니다.
  AI 대량 생산 채널은 수익화 심사에서 '재사용/반복 콘텐츠'로 걸릴 수 있으니, 처음 몇 편은 비공개로 올려서
  대본의 과학적 정확성과 영상 품질을 직접 확인하는 걸 추천합니다.

## 구조

```
earth-patch-notes/
├── patchnotes/
│   ├── __main__.py    # CLI (run / script / auth / upload)
│   ├── pipeline.py    # 전체 흐름, 버전·이력 관리
│   ├── script.py      # Claude 대본 생성 (구조화 출력)
│   ├── higgsfield.py  # Higgsfield API (제출→폴링→다운로드, 이어받기)
│   ├── tts.py         # 한국어 내레이션
│   ├── render.py      # 인트로 카드·자막·배지 + ffmpeg 합성
│   ├── youtube.py     # YouTube 업로드
│   └── config.py      # .env 설정
├── examples/gravity-10000x.json   # 예제 대본 (중력 10,000배)
├── topics.txt         # 주제 목록
└── state/history.json # 버전·업로드 이력
```
