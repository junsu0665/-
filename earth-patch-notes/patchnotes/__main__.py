"""사용법: python -m patchnotes <명령> [옵션]

  run      주제 선택 → 대본 → 음성 → Higgsfield 영상 → 합성 → YouTube 업로드
  script   대본만 만들어서 보기 (영상 생성 X, 비용 거의 없음)
  auth     YouTube 로그인 (최초 1회)
  upload   이미 만든 영상 폴더를 업로드
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="patchnotes", description="지구 패치노트 쇼츠 자동 제작")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="영상 1편 제작 + 업로드")
    p_run.add_argument("--topic", help='예: "중력이 10,000배가 되었습니다" (없으면 topics.txt 다음 주제)')
    p_run.add_argument("--version", help="패치 버전 (없으면 자동 증가, 1.0.1부터)")
    p_run.add_argument("--script", type=Path, help="Claude 대신 이 대본 JSON 사용")
    p_run.add_argument("--no-upload", action="store_true", help="영상만 만들고 업로드하지 않음")
    p_run.add_argument("--placeholder", action="store_true",
                       help="Higgsfield 대신 가짜 클립으로 시험 (비용 0, 업로드 안 함)")
    p_run.add_argument("--privacy", choices=["private", "unlisted", "public"])
    p_run.add_argument("--publish-at", help="예약 공개 시각 (ISO 8601, 예: 2026-10-01T18:00:00+09:00)")

    p_script = sub.add_parser("script", help="대본만 생성")
    p_script.add_argument("--topic", required=True)
    p_script.add_argument("--version", default="1.0.1")
    p_script.add_argument("--out", type=Path)

    p_auth = sub.add_parser("auth", help="YouTube OAuth 로그인")
    p_auth.add_argument("--headless", action="store_true", help="브라우저 자동 열기 안 함")

    p_up = sub.add_parser("upload", help="만들어 둔 영상 업로드")
    p_up.add_argument("workdir", type=Path, help="예: output/v1.0.1")
    p_up.add_argument("--privacy", choices=["private", "unlisted", "public"])
    p_up.add_argument("--publish-at")

    args = parser.parse_args(argv)
    settings = Settings()

    if args.cmd == "run":
        from .pipeline import run

        record = run(settings, topic=args.topic, version=args.version, script_path=args.script,
                     upload=not args.no_upload, placeholder=args.placeholder,
                     privacy=args.privacy, publish_at=args.publish_at)
        print(record)
    elif args.cmd == "script":
        from .script import generate_script, save_script

        script = generate_script(settings, args.topic, args.version)
        print(script.model_dump_json(indent=2))
        if args.out:
            save_script(script, args.out)
    elif args.cmd == "auth":
        from .youtube import authorize

        authorize(settings, headless=args.headless)
    elif args.cmd == "upload":
        from .pipeline import upload_existing

        upload_existing(settings, args.workdir, args.privacy, args.publish_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
